"""DART 사업보고서 "III. 생산 및 설비" 섹션 → PG + Neo4j 적재.

본 loader 는 6 한국 자동차 OEM 의 DART 사업보고서 zip 을 walk 하면서
``dart_production_parser.parse_business_report()`` 를 호출, 결과 PlantRow 를
다음 세 곳에 적재한다:

- ``anxg_auto.plant_capacity``   (생산능력)
- ``anxg_auto.plant_production`` (생산실적)
- (선택) Neo4j ``(:Anxg_Manufacturer)-[:MANUFACTURED_AT {capa, actual, util}]->(:Anxg_Plant)``

선행 조건:
    1. ``make migrate-auto-production`` — 15_autograph_production.sql 적용.
    2. (Neo4j sync 활성 시) ``make load-auto-seed-standards-plants``,
       ``make load-auto-neo4j`` — :Manufacturer / :Plant 노드 존재.

원본 zip:
    data/raw/dart_bulk/corp/<corp_code>/documents/<rcept_no>.zip

UPSERT 키: ``(corp_code, plant_code, snapshot_year)``.
재실행 안전 — 같은 키 충돌 시 capacity/actual 값 갱신 + ``updated_at = now()``.

PRD §3.5: DART 공식 공시 = B 등급 → confidence 0.80, validated_status='validated'.

CLI:
    python -m autograph.loaders.load_dart_production
    python -m autograph.loaders.load_dart_production --corp-code 00164742 --dry-run
    python -m autograph.loaders.load_dart_production --no-neo4j
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path

from autonexusgraph.config import get_settings

from ..extractors.dart_production_parser import (
    PlantRow,
    parse_business_report,
)
from ._neo4j_helpers import default_schema_version as _default_schema_version
from ._neo4j_helpers import edge_meta_cypher, run_batched

log = logging.getLogger(__name__)


# ── 6 OEM 화이트리스트 — Phase A 확정 범위 ───────────────────────
# corp_code 출처: data/raw/ingest_targets.jsonl 의 KRX 매핑.
# alias_for_mfr 은 anxg_auto.master_manufacturers.name 의 영문 정규형 (NHTSA vPIC).
OEM_CORP_CODES: dict[str, dict] = {
    "00164742": {"name": "현대자동차",   "alias_for_mfr": "HYUNDAI"},
    "00106641": {"name": "기아",         "alias_for_mfr": "KIA"},
    "00164788": {"name": "현대모비스",   "alias_for_mfr": None},   # supplier
    "00161125": {"name": "한온시스템",   "alias_for_mfr": None},
    "01042775": {"name": "HL만도",       "alias_for_mfr": None},
    "00106623": {"name": "현대위아",     "alias_for_mfr": None},
}


# ── DART 법인명(약어) → plants.yaml :Plant.code 매핑 ─────────────
# plants.yaml 에 등록된 18 plant 중 DART 사업보고서 표 와 1:1 대응되는 것만 등록.
# 미등록 plant (HMI 인도 첸나이, HMMR 러시아, HTMV 베트남 등) 는 미매핑 — PG 에는
# 행이 저장되지만 Neo4j 엣지는 생성되지 않고 log.warning. 후속 PR 로 plants.yaml
# 을 확장하면 본 dict 만 갱신.
_DART_PLANT_CODE_MAP: dict[tuple[str, str], str] = {
    # 현대자동차 (00164742) — 2026-06-01 plants.yaml 확장 완료
    ("00164742", "HMC"):          "HYU_ULSAN",        # 한국 — 본사 (울산 mass)
    ("00164742", "HMMA"):         "HYU_MONTGOMERY",   # 미국 앨라배마
    ("00164742", "HMI"):          "HYU_CHENNAI",      # 인도 첸나이
    ("00164742", "HAOS"):         "HYU_IZMIT",        # 튀르키예 이즈미트
    ("00164742", "HMMC"):         "HYU_NOSOVICE",     # 체코 노쇼비체
    ("00164742", "HMMR"):         "HYU_PETERSBURG",   # 러시아 상트페테르부르크 (운영중단)
    ("00164742", "HMB"):          "HYU_PIRACICABA",   # 브라질 피라시카바
    ("00164742", "HTMV"):         "HYU_NINH_BINH",    # 베트남 닌빈
    ("00164742", "HMMI"):         "HYU_BEKASI",       # 인도네시아 브카시
    ("00164742", "HMGMA"):        "HYU_METAPLANT",    # 미국 조지아 (EV 전용, 2024 가동)
    # DART XML 의 "HMMA / HMGMA" / "HMMA/ HMGMA" 등 공백 변형 — 정규화 후 단일 키.
    ("00164742", "HMMA/HMGMA"):   "HYU_METAPLANT",    # 통합 칸 → 신규 metaplant 우선
    ("00164742", "HMTR"):         "HYU_IZMIR",        # 튀르키예 이즈미르 (HAOS 별표기)
    # 기아 (00106641) — DART 사업보고서 capa 표 추출 실패 (B4 후속).
    # 본 매핑은 향후 Kia 파서 확장 시 유효.
    ("00106641", "기아"):          "KIA_HWASEONG",     # 한국 (대표) — 화성/광주 통합
    ("00106641", "KMA"):          "KIA_WEST_POINT",   # 미국 조지아 (Kia Motors America)
    ("00106641", "KMMG"):         "KIA_WEST_POINT",   # 미국 조지아 (Kia Motors Manufacturing Georgia)
    ("00106641", "KMS"):          "KIA_ZILINA",       # 슬로바키아 질리나
    ("00106641", "KMX"):          "KIA_MONTERREY",    # 멕시코 페스케리아
    # Kia 사업보고서 (한국어 plant 명) — 사업보고서가 영문 약어 아닌 한국어 사용
    ("00106641", "국내공장"):       "KIA_HWASEONG",     # 광명+화성+광주+서산 통합 (대표)
    ("00106641", "미국공장"):       "KIA_WEST_POINT",   # KMA/KMMG 통합
    ("00106641", "슬로박공장"):      "KIA_ZILINA",
    ("00106641", "멕시코공장"):      "KIA_MONTERREY",
    ("00106641", "인도공장"):       "KIA_ANANTAPUR",    # 2026-06-01 plants.yaml 추가
    # 모비스/한온/만도/위아 의 사내 법인명은 사업보고서 별 다양 — B4 후속에서 1:1 매핑 추가.
}


# 메타 (PRD §3.5 B 등급).
_SOURCE_TYPE = "dart_business_report"
_CONFIDENCE_SCORE = 0.80
_VALIDATED_STATUS = "validated"
_EXTRACTION_METHOD = "dart_xml_table_parser"


# ── zip iterator ─────────────────────────────────────────────────
def _iter_corp_zips(corp_code: str) -> Iterator[tuple[str, Path]]:
    """``(rcept_no, zip_path)`` 페어 — 한 corp_code 의 모든 사업보고서 zip."""
    bulk_root = get_settings().ingest_raw_dir / "dart_bulk" / "corp"
    docs = bulk_root / corp_code / "documents"
    if not docs.exists():
        return
    for z in sorted(docs.glob("*.zip")):
        yield z.stem, z


def _read_main_xml(zip_path: Path) -> str | None:
    """zip 안에서 사업보고서 메인 XML 텍스트 추출.

    DART 사업보고서 zip 의 첫 번째 비-언더스코어 XML 이 본문 (`{rcept_no}.xml`).
    이 패턴은 ``autonexusgraph/extraction/dart_parser.py::parse_dart_zip`` 와 동일.
    """
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            xml_name = f"{zip_path.stem}.xml"
            if xml_name not in names:
                # underscore 안 들어간 첫 XML
                for nm in names:
                    if nm.endswith(".xml") and "_" not in Path(nm).stem:
                        xml_name = nm
                        break
                else:
                    log.warning("[dart_prod] %s: 본문 XML 없음", zip_path.name)
                    return None
            with zf.open(xml_name) as f:
                raw = f.read()
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("euc-kr", errors="replace")
    except (zipfile.BadZipFile, OSError) as exc:
        log.warning("[dart_prod] %s 손상: %s", zip_path.name, exc)
        return None


def _is_vehicle_division(div: str | None) -> bool:
    """차량/자동차 사업부문 여부 — 금융/위탁/상용/레일솔루션 제외.

    DART 표의 사업부문 cell 변형:
        Hyundai: '차량부문' / '차량부문(대수)' / '기타부문(억원)' / '레일솔루션부문'
        Kia:     '자동차제조업' (대표) / '기타' 등
    '차량' 또는 '자동차' substring 매칭으로 양쪽 인식. None 은 ROWSPAN 상속 →
    상위 그룹이 차량/자동차일 때만 그 행에 도달하므로 True.
    """
    if not div:
        return True   # 상속 행
    return ("차량" in div) or ("자동차" in div)


# ── UPSERT 함수 ──────────────────────────────────────────────────
def _upsert_capacity(cur, *, corp_code: str, rcept_no: str,
                     row: PlantRow) -> bool:
    """1 행 UPSERT. RETURN is_new (True=insert, False=update)."""
    cur.execute("""
        INSERT INTO anxg_auto.plant_capacity
          (corp_code, business_division, plant_code, plant_region,
           snapshot_year, capacity_units, source_rcept_no, raw)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (corp_code, plant_code, snapshot_year) DO UPDATE SET
          business_division = EXCLUDED.business_division,
          plant_region      = EXCLUDED.plant_region,
          capacity_units    = EXCLUDED.capacity_units,
          source_rcept_no   = EXCLUDED.source_rcept_no,
          raw               = EXCLUDED.raw,
          updated_at        = now()
        RETURNING (xmax = 0) AS is_new
    """, (corp_code, row.business_division, row.plant_code,
          row.plant_region, row.year,
          int(row.value) if row.value is not None else None,
          rcept_no,
          json.dumps({"plant_code": row.plant_code,
                       "region": row.plant_region,
                       "value": row.value}, ensure_ascii=False)))
    return bool(cur.fetchone()[0])


def _upsert_utilization(cur, *, corp_code: str, rcept_no: str,
                        row: PlantRow) -> bool:
    """Hyundai 가동률 표 — value=utilization_pct, extra 에 capa/actual."""
    extra = row.extra or {}
    cur.execute("""
        INSERT INTO anxg_auto.plant_utilization
          (corp_code, business_division, plant_code, snapshot_year,
           utilization_pct, actual_hours, available_hours,
           source_rcept_no, raw)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (corp_code, plant_code, snapshot_year) DO UPDATE SET
          business_division = EXCLUDED.business_division,
          utilization_pct   = EXCLUDED.utilization_pct,
          actual_hours      = EXCLUDED.actual_hours,
          available_hours   = EXCLUDED.available_hours,
          source_rcept_no   = EXCLUDED.source_rcept_no,
          raw               = EXCLUDED.raw,
          updated_at        = now()
        RETURNING (xmax = 0) AS is_new
    """, (corp_code, row.business_division, row.plant_code,
          row.year,
          row.value,   # utilization_pct
          extra.get("actual_units"),       # Hyundai 표 는 "시간" 단위 아닌 "대수"
          extra.get("capacity_units"),     # — 같은 컬럼 재활용 (NUMERIC 호환)
          rcept_no,
          json.dumps({"util_pct": row.value, **extra}, ensure_ascii=False)))
    return bool(cur.fetchone()[0])


def _upsert_production(cur, *, corp_code: str, rcept_no: str,
                       row: PlantRow) -> bool:
    cur.execute("""
        INSERT INTO anxg_auto.plant_production
          (corp_code, business_division, plant_code, plant_region,
           snapshot_year, actual_units, source_rcept_no, raw)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (corp_code, plant_code, snapshot_year) DO UPDATE SET
          business_division = EXCLUDED.business_division,
          plant_region      = EXCLUDED.plant_region,
          actual_units      = EXCLUDED.actual_units,
          source_rcept_no   = EXCLUDED.source_rcept_no,
          raw               = EXCLUDED.raw,
          updated_at        = now()
        RETURNING (xmax = 0) AS is_new
    """, (corp_code, row.business_division, row.plant_code,
          row.plant_region, row.year,
          int(row.value) if row.value is not None else None,
          rcept_no,
          json.dumps({"plant_code": row.plant_code,
                       "region": row.plant_region,
                       "value": row.value}, ensure_ascii=False)))
    return bool(cur.fetchone()[0])


# ── Neo4j 동기화 (A4) ───────────────────────────────────────────
def _resolve_manufacturer_id(corp_code: str) -> int | None:
    """corp_code → manufacturer_id.

    우선순위:
      1. anxg_bridge.corp_entity 의 (corp_code, entity_type='manufacturer') 매칭
      2. OEM_CORP_CODES[cc]['alias_for_mfr'] 로 anxg_auto.master_manufacturers.name exact
      3. 모두 실패 → None (Neo4j 엣지 skip + log)
    """
    from autonexusgraph.db.postgres import get_connection
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT entity_id::int FROM anxg_bridge.corp_entity
                 WHERE corp_code = %s
                   AND entity_type = 'manufacturer'
                   AND reviewed_status <> 'rejected'
                 ORDER BY confidence_score DESC LIMIT 1
            """, (corp_code,))
            r = cur.fetchone()
            if r and r[0] is not None:
                return int(r[0])

            alias = OEM_CORP_CODES.get(corp_code, {}).get("alias_for_mfr")
            if alias:
                cur.execute("""
                    SELECT manufacturer_id FROM anxg_auto.master_manufacturers
                     WHERE name = %s
                     ORDER BY manufacturer_id LIMIT 1
                """, (alias,))
                r = cur.fetchone()
                if r:
                    return int(r[0])
    finally:
        conn.commit()
    return None


_PLANT_LABEL_WS_RE = re.compile(r"\s+")


def _normalize_dart_plant_label(label: str) -> str:
    """DART raw plant 표기 정규화 — 공백 압축 + 대문자 일관.

    예: 'HMMA/ HMGMA' → 'HMMA/HMGMA' (DART XML 의 공백 노이즈 제거)
        '  HMC  '   → 'HMC'
    한글 표기 (예: '기아') 는 strip + 동일.
    """
    if not label:
        return ""
    # 공백 모두 압축 (탭/줄바꿈 포함)
    return _PLANT_LABEL_WS_RE.sub("", label.strip())


def _resolve_plant_node_code(corp_code: str, raw_plant_label: str
                             ) -> str | None:
    """DART raw 법인명 → plants.yaml :Plant.code. 미매핑이면 None.

    1차: raw label 그대로 (strip) 매칭.
    2차: 공백 압축 정규화 매칭 ('HMMA/ HMGMA' → 'HMMA/HMGMA' 등).
    """
    raw = (raw_plant_label or "").strip()
    direct = _DART_PLANT_CODE_MAP.get((corp_code, raw))
    if direct is not None:
        return direct
    # 공백 노이즈 제거 후 재시도
    norm = _normalize_dart_plant_label(raw_plant_label)
    if norm != raw:
        return _DART_PLANT_CODE_MAP.get((corp_code, norm))
    return None


def _merge_capa_and_actual(capacity_rows: list[PlantRow],
                           production_rows: list[PlantRow],
                           utilization_rows: list[PlantRow] | None = None,
                           ) -> dict[tuple[str, int], dict]:
    """(plant_code, year) 키로 capacity + production + utilization 합치기.

    같은 plant·year 에 capa/actual/util — Neo4j 엣지 한 줄로 표현.
    utilization_rows 가 있으면 그 값을 우선 사용 (실측 가동률).
    """
    out: dict[tuple[str, int], dict] = {}

    def _entry(key, plant_code, region, year):
        return out.setdefault(key, {
            "plant_code": plant_code,
            "plant_region": region,
            "snapshot_year": year,
            "capa_units": None,
            "actual_units": None,
            "utilization_pct_explicit": None,   # 가동률 표 출처
        })

    for r in capacity_rows:
        if r.year <= 0 or not r.plant_code:
            continue
        key = (r.plant_code, r.year)
        _entry(key, r.plant_code, r.plant_region, r.year)
        out[key]["capa_units"] = int(r.value) if r.value is not None else None
    for r in production_rows:
        if r.year <= 0 or not r.plant_code:
            continue
        key = (r.plant_code, r.year)
        _entry(key, r.plant_code, r.plant_region, r.year)
        out[key]["actual_units"] = int(r.value) if r.value is not None else None
    for r in (utilization_rows or []):
        if r.year <= 0 or not r.plant_code:
            continue
        key = (r.plant_code, r.year)
        _entry(key, r.plant_code, r.plant_region, r.year)
        out[key]["utilization_pct_explicit"] = r.value
        # 가동률 표가 capa/actual 도 같이 노출 — 미설정 시 보강
        if out[key]["capa_units"] is None and r.extra:
            cu = r.extra.get("capacity_units")
            if cu is not None:
                out[key]["capa_units"] = int(cu)
        if out[key]["actual_units"] is None and r.extra:
            au = r.extra.get("actual_units")
            if au is not None:
                out[key]["actual_units"] = int(au)
    return out


_MANUFACTURED_AT_CYPHER = f"""
UNWIND $rows AS r
MATCH (mm:Anxg_Manufacturer {{id: r.manufacturer_id}})
MATCH (p:Anxg_Plant {{code: r.plant_code}})
MERGE (mm)-[edge:MANUFACTURED_AT {{snapshot_year: r.snapshot_year}}]->(p)
SET {edge_meta_cypher('edge')},
    edge.capa_units      = r.capa_units,
    edge.actual_units    = r.actual_units,
    edge.utilization_pct = r.utilization_pct
WITH edge
RETURN count(edge) AS n
"""


def _sync_manufactured_at_to_neo4j(*, capacity_rows: list[PlantRow],
                                    production_rows: list[PlantRow],
                                    utilization_rows: list[PlantRow] | None = None,
                                    corp_code: str,
                                    rcept_no: str) -> dict:
    """PG 적재된 capacity + production (+ utilization) → MANUFACTURED_AT 엣지.

    Returns ``{"edges_created":int, "plants_skipped":int}``.
    """
    mfr_id = _resolve_manufacturer_id(corp_code)
    if mfr_id is None:
        log.warning("[dart_prod:neo4j] corp_code=%s 의 manufacturer_id 미해결 — "
                    "MANUFACTURED_AT skip", corp_code)
        return {"edges_created": 0, "plants_skipped": 0}

    merged = _merge_capa_and_actual(capacity_rows, production_rows,
                                      utilization_rows=utilization_rows)
    rows: list[dict] = []
    plants_skipped = 0
    for (raw_label, year), val in merged.items():
        plant_code = _resolve_plant_node_code(corp_code, raw_label)
        if plant_code is None:
            log.warning("[dart_prod:neo4j] (%s, %s) plants.yaml 미등록 — "
                        "edge skip", corp_code, raw_label)
            plants_skipped += 1
            continue
        capa = val["capa_units"]
        actual = val["actual_units"]
        # 가동률 우선순위: explicit (DART 가동률 표) > 계산값.
        utilization = val.get("utilization_pct_explicit")
        if utilization is None and capa and actual and capa > 0:
            utilization = round(actual / capa * 100, 2)
        rows.append({
            "manufacturer_id":  mfr_id,
            "plant_code":       plant_code,
            "snapshot_year":    year,
            "capa_units":       capa,
            "actual_units":     actual,
            "utilization_pct":  utilization,
            "source_type":      _SOURCE_TYPE,
            "source_id":        rcept_no,
            "confidence_score": _CONFIDENCE_SCORE,
            "validated_status": _VALIDATED_STATUS,
            "extraction_method": _EXTRACTION_METHOD,
            "schema_version":   _default_schema_version(),
        })

    if not rows:
        return {"edges_created": 0, "plants_skipped": plants_skipped}

    from autonexusgraph.db.neo4j import get_session

    with get_session() as session:
        run_batched(session, _MANUFACTURED_AT_CYPHER, rows)
    return {"edges_created": len(rows), "plants_skipped": plants_skipped}


# ── 핵심 실행 함수 ──────────────────────────────────────────────
def _process_one_zip(cur, *, corp_code: str, rcept_no: str, zip_path: Path,
                     sync_neo4j: bool) -> dict:
    """단일 zip → parse + UPSERT + (옵션) Neo4j sync. 통계 dict 반환."""
    stats = {
        "capacity_inserted": 0, "capacity_updated": 0, "capacity_skipped": 0,
        "production_inserted": 0, "production_updated": 0, "production_skipped": 0,
        "utilization_inserted": 0, "utilization_updated": 0, "utilization_skipped": 0,
        "neo4j_edges": 0, "neo4j_plants_skipped": 0,
    }

    xml_text = _read_main_xml(zip_path)
    if not xml_text:
        return stats

    extract = parse_business_report(xml_text, rcept_no=rcept_no)

    # ── capacity UPSERT (차량부문만) ──
    capacity_rows = [r for r in extract.capacity
                     if _is_vehicle_division(r.business_division) and r.plant_code]
    for row in capacity_rows:
        cur.execute("SAVEPOINT sp_dart_cap")
        try:
            if _upsert_capacity(cur, corp_code=corp_code,
                                 rcept_no=rcept_no, row=row):
                stats["capacity_inserted"] += 1
            else:
                stats["capacity_updated"] += 1
            cur.execute("RELEASE SAVEPOINT sp_dart_cap")
        except Exception as exc:   # noqa: BLE001 — [dart_prod] capacity UPSERT 실패 흡수 → SAVEPOINT rollback + skip 카운트 + 다음 row
            cur.execute("ROLLBACK TO SAVEPOINT sp_dart_cap")
            log.warning("[dart_prod] capacity %s/%s/%s 실패: %s",
                        corp_code, row.plant_code, row.year, exc)
            stats["capacity_skipped"] += 1

    # ── production UPSERT (차량부문만) ──
    production_rows = [r for r in extract.production
                       if _is_vehicle_division(r.business_division) and r.plant_code]
    for row in production_rows:
        cur.execute("SAVEPOINT sp_dart_prod")
        try:
            if _upsert_production(cur, corp_code=corp_code,
                                   rcept_no=rcept_no, row=row):
                stats["production_inserted"] += 1
            else:
                stats["production_updated"] += 1
            cur.execute("RELEASE SAVEPOINT sp_dart_prod")
        except Exception as exc:   # noqa: BLE001 — [dart_prod] production UPSERT 실패 흡수 → SAVEPOINT rollback + skip 카운트 + 다음 row
            cur.execute("ROLLBACK TO SAVEPOINT sp_dart_prod")
            log.warning("[dart_prod] production %s/%s/%s 실패: %s",
                        corp_code, row.plant_code, row.year, exc)
            stats["production_skipped"] += 1

    # ── utilization UPSERT (차량부문만, 2026-06-01 신규) ──
    utilization_rows = [r for r in extract.utilization
                         if _is_vehicle_division(r.business_division) and r.plant_code]
    for row in utilization_rows:
        cur.execute("SAVEPOINT sp_dart_util")
        try:
            if _upsert_utilization(cur, corp_code=corp_code,
                                    rcept_no=rcept_no, row=row):
                stats["utilization_inserted"] += 1
            else:
                stats["utilization_updated"] += 1
            cur.execute("RELEASE SAVEPOINT sp_dart_util")
        except Exception as exc:   # noqa: BLE001 — [dart_prod] utilization UPSERT 실패 흡수 → SAVEPOINT rollback + skip 카운트 + 다음 row
            cur.execute("ROLLBACK TO SAVEPOINT sp_dart_util")
            log.warning("[dart_prod] utilization %s/%s/%s 실패: %s",
                        corp_code, row.plant_code, row.year, exc)
            stats["utilization_skipped"] += 1

    # ── Neo4j sync (utilization 포함) ──
    if sync_neo4j:
        try:
            sync = _sync_manufactured_at_to_neo4j(
                capacity_rows=capacity_rows,
                production_rows=production_rows,
                utilization_rows=utilization_rows,
                corp_code=corp_code,
                rcept_no=rcept_no,
            )
            stats["neo4j_edges"] = sync["edges_created"]
            stats["neo4j_plants_skipped"] = sync["plants_skipped"]
        except Exception as exc:   # noqa: BLE001 — [dart_prod:neo4j] %s/%s sync 실패 흡수 → stats 반환
            log.warning("[dart_prod:neo4j] %s/%s sync 실패: %s",
                        corp_code, rcept_no, exc)

    return stats


def run(*, corp_codes: list[str] | None = None,
        sync_neo4j: bool = True,
        dry_run: bool = False) -> dict:
    """전체 실행. corp_codes 미지정 시 ``OEM_CORP_CODES`` 전체."""
    targets = corp_codes or list(OEM_CORP_CODES.keys())
    total = {
        "corp_codes_seen": 0, "zips_seen": 0, "zips_parsed": 0,
        "capacity_inserted": 0, "capacity_updated": 0, "capacity_skipped": 0,
        "production_inserted": 0, "production_updated": 0, "production_skipped": 0,
        "utilization_inserted": 0, "utilization_updated": 0, "utilization_skipped": 0,
        "neo4j_edges": 0, "neo4j_plants_skipped": 0,
    }

    if dry_run:
        for cc in targets:
            zips = list(_iter_corp_zips(cc))
            log.info("[dart_prod:dry_run] %s — %d zips", cc, len(zips))
            total["corp_codes_seen"] += 1
            total["zips_seen"] += len(zips)
            for rcept_no, zp in zips[:2]:   # dry_run 시 sample 2 개만 파싱
                xml = _read_main_xml(zp)
                if xml is None:
                    continue
                ext = parse_business_report(xml, rcept_no=rcept_no)
                cap = [r for r in ext.capacity
                       if _is_vehicle_division(r.business_division)]
                prd = [r for r in ext.production
                       if _is_vehicle_division(r.business_division)]
                log.info("  %s: capa=%d prod=%d (dry_run sample)",
                         rcept_no, len(cap), len(prd))
                total["zips_parsed"] += 1
                total["capacity_inserted"] += len(cap)
                total["production_inserted"] += len(prd)
        return total

    from autonexusgraph.db.postgres import get_connection
    conn = get_connection()
    with conn.cursor() as cur:
        for cc in targets:
            zips = list(_iter_corp_zips(cc))
            total["corp_codes_seen"] += 1
            total["zips_seen"] += len(zips)
            log.info("[dart_prod] %s (%s) — %d zips",
                     cc, OEM_CORP_CODES.get(cc, {}).get("name", "?"), len(zips))
            for rcept_no, zp in zips:
                stats = _process_one_zip(cur, corp_code=cc, rcept_no=rcept_no,
                                          zip_path=zp, sync_neo4j=sync_neo4j)
                total["zips_parsed"] += 1
                for k in ("capacity_inserted", "capacity_updated",
                           "capacity_skipped", "production_inserted",
                           "production_updated", "production_skipped",
                           "utilization_inserted", "utilization_updated",
                           "utilization_skipped",
                           "neo4j_edges", "neo4j_plants_skipped"):
                    total[k] += stats[k]
                # 중간 commit — 각 zip 마다 1 트랜잭션 (롤백 영향 최소화)
                conn.commit()

    log.info("[dart_prod] 완료: %s", json.dumps(total, ensure_ascii=False))
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corp-code", action="append", default=None,
                    help="대상 corp_code (반복). 미지정 시 6 OEM 전체.")
    ap.add_argument("--no-neo4j", action="store_true",
                    help="Neo4j sync skip")
    ap.add_argument("--dry-run", action="store_true",
                    help="PG/Neo4j 호출 없이 zip 통계 + 첫 zip 파싱 sample")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    out = run(corp_codes=args.corp_code,
              sync_neo4j=not args.no_neo4j,
              dry_run=args.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "OEM_CORP_CODES",
    "_DART_PLANT_CODE_MAP",
    "run",
    "_iter_corp_zips",
    "_read_main_xml",
    "_is_vehicle_division",
    "_resolve_plant_node_code",
    "_merge_capa_and_actual",
]
