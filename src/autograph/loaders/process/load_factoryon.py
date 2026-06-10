"""팩토리온 (data.go.kr 15087611) raw json → anxg_auto.factoryon_registry PG 적재.

PRD v2.2 §2.3 — 공정·라인·설비 부분 진입 (LLM 0%).
factoryon_registry.py 가 raw 저장만 — 본 loader 가 PG 정규화 적재.

CLI:
    python -m autograph.loaders.process.load_factoryon
    python -m autograph.loaders.process.load_factoryon --dry-run
    python -m autograph.loaders.process.load_factoryon --raw-dir data/raw/auto/factoryon
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
RAW_DIR = ROOT / "data" / "raw" / "auto" / "factoryon"

log = logging.getLogger(__name__)


def _iter_raw_files(raw_dir: Path) -> Iterator[tuple[Path, str]]:
    """raw_dir 의 모든 *.json 파일 + 엔드포인트 라벨."""
    if not raw_dir.exists():
        return
    for endpoint in ("by_company", "by_factory_no", "by_industrial_complex"):
        sub = raw_dir / endpoint
        if not sub.exists():
            continue
        for fp in sorted(sub.glob("*.json")):
            yield fp, endpoint


def _extract_items(payload: Any) -> list[dict]:
    """factoryon API 응답 — 키 패턴 다양 → flatten."""
    if not isinstance(payload, dict):
        return []
    return (
        payload.get("data")
        or payload.get("items")
        or payload.get("response", {}).get("body", {}).get("items")
        or []
    )


def _normalize_row(item: dict, endpoint: str, *,
                    snapshot_year: int,
                    schema_version: str = "v2.2") -> dict[str, Any]:
    """raw item → anxg_auto.factoryon_registry row."""
    def _i(*keys) -> Any:
        for k in keys:
            v = item.get(k)
            if v not in (None, ""):
                return v
        return None
    def _int(*keys) -> int | None:
        v = _i(*keys)
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None
    def _num(*keys) -> float | None:
        v = _i(*keys)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def _date(*keys) -> str | None:
        v = _i(*keys)
        if not v:
            return None
        d = str(v).strip()
        if len(d) == 8 and d.isdigit():        # YYYYMMDD → ISO YYYY-MM-DD
            return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
        return d

    # 키 우선순위: 실제 API 필드(2026-06 실측, getFctry*Service_v2) 를 1순위로,
    # 과거 추정 키는 호환용 fallback. 실측 필드는 docs/data_lineage.md 팩토리온 절 참조.
    return {
        "factory_no":         _i("fctryManageNo", "factoryNo", "fctry_no"),
        "company_name":       _i("cmpnyNm", "companyName", "cmpny_nm") or "",
        "business_no":        _i("brno", "bsnsno", "businessNo"),
        "representative":     _i("rprsntvNm", "ceoNm"),
        "address":            _i("rnAdres", "adres", "rdnmadr", "lnmAdres"),
        "industrial_complex": _i("irsttNm", "complexNm"),
        "industry_code":      _i("rprsntvIndutyCode", "indstyClCd", "ksicCd"),
        "industry_codes":     _i("indutyCodes"),
        "industry_name":      _i("indutyNm", "indstyClNm", "ksicNm"),
        "products":           _i("mainProductCn", "prdctnPdct", "prdctnPrdct"),
        "capacity":           _i("prdctnCpct", "capacity"),
        "employees":          _int("allEmplyCo", "emplyCnt", "emplyeeCnt"),
        "land_area_m2":       _num("site_area", "lndAr"),
        "building_area_m2":   _num("bldng_area", "bldngAr"),
        "registered_at":      _date("frstFctryRegistDe", "rgstdt", "registDate"),
        "charge_org":         _i("cvplChrgOrgnztNm"),
        "tel":                _i("cmpnyTelno"),
        "fax":                _i("cmpnyFxnum"),
        "homepage":           _i("hmpadr"),
        "source_endpoint":    endpoint,
        "snapshot_year":      snapshot_year,
        "schema_version":     schema_version,
        "raw_payload":        json.dumps(item, ensure_ascii=False),
    }


def collect_rows(raw_dir: Path | None = None) -> list[dict]:
    """raw json → 정규화 row list (PG INSERT 호환)."""
    raw_dir = raw_dir or RAW_DIR
    snapshot_year = datetime.now(timezone.utc).year
    rows: list[dict] = []
    seen: set[str] = set()
    for fp, endpoint in _iter_raw_files(raw_dir):
        try:
            payload = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:   # noqa: BLE001 — file 읽기/JSON 파싱 실패 흡수 → continue (다음 raw 파일)
            log.warning("[factoryon.load] %s 파싱 실패: %s", fp, e)
            continue
        for item in _extract_items(payload):
            row = _normalize_row(item, endpoint, snapshot_year=snapshot_year)
            fno = row.get("factory_no")
            if not fno or fno in seen:
                continue
            seen.add(fno)
            rows.append(row)
    return rows


def upsert_pg(rows: list[dict]) -> int:
    """anxg_auto.factoryon_registry UPSERT. DB 미가용 시 0 + warning."""
    if not rows:
        return 0
    try:
        from autonexusgraph.db.postgres import get_pool
    except Exception as e:   # noqa: BLE001 — postgres 모듈 미가용 (db 미설치) 흡수 → 적재 skip
        log.warning("[factoryon.load_pg] postgres 모듈 미가용: %s", e)
        return 0
    sql = """
    INSERT INTO anxg_auto.factoryon_registry (
        factory_no, company_name, business_no, representative, address,
        industrial_complex, industry_code, industry_codes, industry_name, products, capacity,
        employees, land_area_m2, building_area_m2, registered_at,
        charge_org, tel, fax, homepage,
        source_endpoint, snapshot_year, schema_version, raw_payload
    ) VALUES (
        %(factory_no)s, %(company_name)s, %(business_no)s, %(representative)s, %(address)s,
        %(industrial_complex)s, %(industry_code)s, %(industry_codes)s, %(industry_name)s, %(products)s, %(capacity)s,
        %(employees)s, %(land_area_m2)s, %(building_area_m2)s, %(registered_at)s,
        %(charge_org)s, %(tel)s, %(fax)s, %(homepage)s,
        %(source_endpoint)s, %(snapshot_year)s, %(schema_version)s, %(raw_payload)s::jsonb
    )
    ON CONFLICT (factory_no) DO UPDATE SET
        company_name       = EXCLUDED.company_name,
        business_no        = COALESCE(EXCLUDED.business_no, anxg_auto.factoryon_registry.business_no),
        representative     = COALESCE(EXCLUDED.representative, anxg_auto.factoryon_registry.representative),
        address            = COALESCE(EXCLUDED.address, anxg_auto.factoryon_registry.address),
        industrial_complex = COALESCE(EXCLUDED.industrial_complex, anxg_auto.factoryon_registry.industrial_complex),
        industry_code      = COALESCE(EXCLUDED.industry_code, anxg_auto.factoryon_registry.industry_code),
        industry_codes     = COALESCE(EXCLUDED.industry_codes, anxg_auto.factoryon_registry.industry_codes),
        industry_name      = COALESCE(EXCLUDED.industry_name, anxg_auto.factoryon_registry.industry_name),
        products           = COALESCE(EXCLUDED.products, anxg_auto.factoryon_registry.products),
        capacity           = COALESCE(EXCLUDED.capacity, anxg_auto.factoryon_registry.capacity),
        employees          = COALESCE(EXCLUDED.employees, anxg_auto.factoryon_registry.employees),
        land_area_m2       = COALESCE(EXCLUDED.land_area_m2, anxg_auto.factoryon_registry.land_area_m2),
        building_area_m2   = COALESCE(EXCLUDED.building_area_m2, anxg_auto.factoryon_registry.building_area_m2),
        registered_at      = COALESCE(EXCLUDED.registered_at, anxg_auto.factoryon_registry.registered_at),
        charge_org         = COALESCE(EXCLUDED.charge_org, anxg_auto.factoryon_registry.charge_org),
        tel                = COALESCE(EXCLUDED.tel, anxg_auto.factoryon_registry.tel),
        fax                = COALESCE(EXCLUDED.fax, anxg_auto.factoryon_registry.fax),
        homepage           = COALESCE(EXCLUDED.homepage, anxg_auto.factoryon_registry.homepage),
        snapshot_year      = EXCLUDED.snapshot_year,
        schema_version     = EXCLUDED.schema_version,
        raw_payload        = EXCLUDED.raw_payload,
        updated_at         = now()
    """
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            n = 0
            for r in rows:
                # PG date 호환 변환 — 빈/잘못된 값은 None.
                if r.get("registered_at") and not isinstance(r["registered_at"], (str,)):
                    r["registered_at"] = None
                cur.execute(sql, r)
                n += cur.rowcount or 0
            return n
    except Exception as e:   # noqa: BLE001 — PG 적재 실패 흡수 → 0 반환 (fail-soft, 다음 호출 시 재시도)
        log.warning("[factoryon.load_pg] PG 적재 실패 (fail-soft): %s", e)
        return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="autograph.loaders.process.load_factoryon",
                                 description=__doc__.split("\n")[0])
    p.add_argument("--raw-dir", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(message)s")

    rows = collect_rows(args.raw_dir)
    log.info("[factoryon] %d rows collected from raw json", len(rows))
    if args.dry_run:
        for r in rows[:5]:
            print(f"  {r['factory_no']:14s} {r['company_name'][:30]:30s} "
                  f"{r.get('industrial_complex', '')!s:25s}")
        return 0
    n = upsert_pg(rows)
    print(f"[factoryon.load] upserted {n} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
