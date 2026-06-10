"""KAMP 제조AI 데이터셋 카탈로그(data.go.kr 15089213) → anxg_auto.kamp_catalog UPSERT.

Layer A — 카탈로그(인덱스). 50종 데이터셋의 메타·링크만 적재.
실제 공정 센서 통계는 별도 ``load_kamp_process_metrics`` (Layer B, anxg_auto.process_metrics).

원본 CSV 인코딩은 EUC-KR/CP949 — 자동 감지 후 UTF-8 처리.

raw 파일 위치:
    data/raw/kamp/catalog/_catalog_15089213.csv        # 원본 EUC-KR
    data/raw/kamp/catalog/_catalog_15089213.utf8.csv   # UTF-8 변환본 (있으면 우선)

CLI:
    python -m autograph.loaders.process.load_kamp_catalog
    python -m autograph.loaders.process.load_kamp_catalog --dry-run
    python -m autograph.loaders.process.load_kamp_catalog --csv <path>
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from autonexusgraph.db.postgres import get_connection

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CATALOG_DIR = ROOT / "data" / "raw" / "kamp" / "catalog"

_SOURCE = "datagokr_kamp_15089213"
_SOURCE_TYPE = "kamp_manufacturing"
_CONFIDENCE = 0.800   # B 등급 (익명)
_SCHEMA_VERSION = "kamp_catalog_v1"

# 산단공 :Process 사전 정규화 매핑. KAMP 37 unique "적용공정" → (norm, category).
# category 는 anxg_auto.process_metrics.process_category 와 동일 분류 체계 사용:
#   casting | forging | stamping | welding | coating | machining | assembly | inspection
#   + 확장: melting | injection_molding | heat_treatment | plating | logistics | mixing | safety
#
# 매핑 미정 항목은 (None, None) — DB 적재 시 NULL, 후속 수동 보강.
_PROCESS_NORM: dict[str, tuple[str | None, str | None]] = {
    # 주조
    "다이캐스팅 공정":                      ("die_casting",       "casting"),
    "용해공정":                             ("melting",           "melting"),
    # 소성가공 (프레스/단조)
    "프레스공정":                           ("press",             "stamping"),
    "프레스 공정":                          ("press",             "stamping"),
    "파인블랭킹 프레스 공정":               ("fine_blanking",     "stamping"),
    "소성가공 공정":                        ("plastic_forming",   "stamping"),
    "냉간단조 공정":                        ("cold_forging",      "forging"),
    # 용접
    "용접공정":                             ("welding",           "welding"),
    "용접 공정":                            ("welding",           "welding"),
    "배터리 용접 공정":                     ("battery_welding",   "welding"),
    # 열처리
    "열처리 공정":                          ("heat_treatment",    "heat_treatment"),
    # 표면처리
    "도금 공정":                            ("plating",           "plating"),
    "전해탈지 공정":                        ("electro_cleaning",  "plating"),
    "산제 전처리 공정":                     ("acid_pretreatment", "plating"),
    "크로메이트 공정":                      ("chromate",          "plating"),
    "열풍건조 공정":                        ("hot_air_drying",    "plating"),
    # 정밀가공
    "CNC 가공공정":                         ("cnc_machining",     "machining"),
    "CNC 정밀가공 공정":                    ("cnc_machining",     "machining"),
    "레이저 가공 공정":                     ("laser_machining",   "machining"),
    "NC 공정":                              ("nc_machining",      "machining"),
    "제관공정":                             ("can_making",        "machining"),
    "제관 Count-Weight의 충진공정":         ("can_filling",       "machining"),
    # 사출성형
    "사출공정":                             ("injection_molding", "injection_molding"),
    "사출성형 공정":                        ("injection_molding", "injection_molding"),
    # 검사
    "검사공정":                             ("inspection",        "inspection"),
    "품질외관검사공정":                     ("visual_inspection", "inspection"),
    "출하검사 공정":                        ("outgoing_inspection","inspection"),
    "배터리 충방전 시험 공정":              ("battery_test",      "inspection"),
    # 기타 / 보조
    "회전기계":                             ("rotating_machinery","assembly"),
    "살균공정":                             ("sterilization",     None),
    "건조공정":                             ("drying",            None),
    "포장공정":                             ("packaging",         None),
    "염색공정":                             ("dyeing",            None),
    "혼합 공정":                            ("mixing",            "mixing"),
    "VMI 발주":                             ("vmi_order",         "logistics"),
    "생산 계획 수립":                       ("production_plan",   "logistics"),
    "자재 입고에서 제품 출하까지의 전 제조공정": ("full_supply_chain", "logistics"),
}


# ──────────────────────────────────────────────────────────────────────
# CSV 읽기 (EUC-KR/UTF-8 자동 처리)
# ──────────────────────────────────────────────────────────────────────

def _find_csv(csv_arg: str | None) -> Path | None:
    """UTF-8 변환본 우선 → 원본 EUC-KR fallback."""
    if csv_arg:
        p = Path(csv_arg)
        return p if p.is_file() else None
    for name in ("_catalog_15089213.utf8.csv", "_catalog_15089213.csv"):
        p = DEFAULT_CATALOG_DIR / name
        if p.is_file():
            return p
    return None


def _read_text(path: Path) -> str:
    """UTF-8 시도 → 실패 시 CP949."""
    raw = path.read_bytes()
    for enc in ("utf-8", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _iter_rows(path: Path) -> Iterator[dict[str, str]]:
    text = _read_text(path)
    reader = csv.DictReader(text.splitlines())
    for row in reader:
        # 키 정규화 (혹시 BOM/공백 섞이면)
        yield {(k or "").strip(): (v or "").strip() for k, v in row.items()}


# ──────────────────────────────────────────────────────────────────────
# 정규화
# ──────────────────────────────────────────────────────────────────────

# CSV 헤더(EUC-KR 원문)
_H = {
    "seq":      "연번",
    "year":     "기준년도",
    "industry": "업종",
    "purpose":  "목적",
    "process":  "적용공정",
    "name":     "제공 제조AI데이터셋 명",
    "desc":     "제조AI데이터셋 내용",
    "type":     "유형",
    "terms":    "사용조건",
    "link":     "데이터셋 다운 링크",
}


def _normalize(row: dict[str, str]) -> dict[str, Any] | None:
    try:
        seq = int(row[_H["seq"]])
        base_year = int(row[_H["year"]])
    except (KeyError, ValueError):
        log.warning("[kamp.catalog] seq/year 파싱 실패 — skip: %r", row)
        return None

    process_raw = row.get(_H["process"], "") or None
    norm, category = _PROCESS_NORM.get(process_raw or "", (None, None))

    return {
        "seq":               seq,
        "base_year":         base_year,
        "industry":          row.get(_H["industry"]) or None,
        "purpose":           row.get(_H["purpose"]) or None,
        "process_name_raw":  process_raw or "",
        "process_name_norm": norm,
        "process_category":  category,
        "dataset_name":      row.get(_H["name"]) or "",
        "dataset_desc":      row.get(_H["desc"]) or None,
        "data_type":         row.get(_H["type"]) or None,
        "usage_terms":       row.get(_H["terms"]) or None,
        "download_url":      row.get(_H["link"]) or None,
        # 7키 (테이블 DEFAULT 와 일치하지만 명시 — 갱신 시 누락 방지)
        "source":            _SOURCE,
        "source_type":       _SOURCE_TYPE,
        "source_id":         f"kamp:15089213/{seq}",
        "confidence_score":  _CONFIDENCE,
        "validated_status":  "candidate",
        "snapshot_year":     base_year,
        "extraction_method": "deterministic",
        "schema_version":    _SCHEMA_VERSION,
        "raw":               json.dumps(row, ensure_ascii=False),
    }


def collect_rows(csv_path: Path | None = None) -> list[dict[str, Any]]:
    src = csv_path if csv_path else _find_csv(None)
    if src is None:
        log.warning("[kamp.catalog] CSV 없음 (%s) — graceful skip",
                    DEFAULT_CATALOG_DIR)
        return []
    rows: list[dict[str, Any]] = []
    for raw in _iter_rows(src):
        norm = _normalize(raw)
        if norm is not None:
            rows.append(norm)
    log.info("[kamp.catalog] %d rows from %s", len(rows), src)
    return rows


# ──────────────────────────────────────────────────────────────────────
# PG UPSERT
# ──────────────────────────────────────────────────────────────────────

_UPSERT_SQL = """
INSERT INTO anxg_auto.kamp_catalog (
    seq, base_year, industry, purpose,
    process_name_raw, process_name_norm, process_category,
    dataset_name, dataset_desc, data_type, usage_terms, download_url,
    source, source_type, source_id, confidence_score, validated_status,
    snapshot_year, extraction_method, schema_version, raw
) VALUES (
    %(seq)s, %(base_year)s, %(industry)s, %(purpose)s,
    %(process_name_raw)s, %(process_name_norm)s, %(process_category)s,
    %(dataset_name)s, %(dataset_desc)s, %(data_type)s, %(usage_terms)s, %(download_url)s,
    %(source)s, %(source_type)s, %(source_id)s, %(confidence_score)s, %(validated_status)s,
    %(snapshot_year)s, %(extraction_method)s, %(schema_version)s, %(raw)s::jsonb
)
ON CONFLICT (source, seq, base_year) DO UPDATE SET
    industry          = EXCLUDED.industry,
    purpose           = EXCLUDED.purpose,
    process_name_raw  = EXCLUDED.process_name_raw,
    process_name_norm = EXCLUDED.process_name_norm,
    process_category  = EXCLUDED.process_category,
    dataset_name      = EXCLUDED.dataset_name,
    dataset_desc      = EXCLUDED.dataset_desc,
    data_type         = EXCLUDED.data_type,
    usage_terms       = EXCLUDED.usage_terms,
    download_url      = EXCLUDED.download_url,
    source_type       = EXCLUDED.source_type,
    source_id         = EXCLUDED.source_id,
    confidence_score  = EXCLUDED.confidence_score,
    validated_status  = EXCLUDED.validated_status,
    extraction_method = EXCLUDED.extraction_method,
    schema_version    = EXCLUDED.schema_version,
    raw               = EXCLUDED.raw,
    updated_at        = now()
"""


def upsert_pg(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    try:
        conn = get_connection()
    except Exception as e:   # noqa: BLE001 — PG 연결 실패 흡수 → graceful skip (db 미가동 환경)
        log.warning("[kamp.catalog] PG 미가용 — graceful skip: %s", e)
        return 0
    # NOTE: get_connection() 은 @lru_cache(maxsize=1) 싱글톤 — close() 호출 금지.
    # 닫으면 다음 호출자(다른 loader 포함)가 closed conn 을 받아 깨진다. 정리는
    # db.postgres.close() 가 cache_clear 와 함께 일괄 처리.
    n = 0
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('anxg_auto.kamp_catalog')")
            if cur.fetchone()[0] is None:
                log.error("[kamp.catalog] anxg_auto.kamp_catalog 미생성 — "
                          "make migrate-schema-pg MIGRATE_FILE=27_auto_kamp_catalog.sql 먼저")
                return 0
            for r in rows:
                cur.execute(_UPSERT_SQL, r)
                n += cur.rowcount or 0
        conn.commit()
    except Exception as e:   # noqa: BLE001 — PG 적재 실패 흡수 → rollback 후 log (다음 호출 시 재시도)
        log.warning("[kamp.catalog] PG 적재 실패 (fail-soft): %s", e)
        try:
            conn.rollback()
        except Exception:   # noqa: BLE001 — rollback 자체 실패 silent (이미 연결 손상 가능성)
            pass
    return n


def run(*, csv_path: str | Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    src = Path(csv_path) if csv_path else None
    rows = collect_rows(src)
    stats = {
        "source_csv":  str(src) if src else None,
        "rows_total":  len(rows),
        "rows_with_norm": sum(1 for r in rows if r["process_name_norm"]),
        "industries":  sorted({r["industry"] for r in rows if r["industry"]}),
        "upserted":    0,
    }
    if dry_run:
        return stats
    stats["upserted"] = upsert_pg(rows)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(prog="autograph.loaders.process.load_kamp_catalog",
                                  description=__doc__.split("\n")[0])
    ap.add_argument("--csv", default=None, help="CSV 경로 (지정 안 하면 기본 위치)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stats = run(csv_path=args.csv, dry_run=args.dry_run)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
