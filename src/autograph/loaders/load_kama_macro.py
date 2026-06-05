"""KAMA (한국자동차산업협회) 매크로 통계 — data.go.kr 15051116 / 15051118 CSV 적재.

산단공/DART per-OEM 적재와는 별개의 **매크로 시계열** — 한국 자동차 산업 보건의
연/월 단위 컨텍스트. DART 분기 매출 / ECOS 환율 / KOSIS 산업통계와 join 가능.

원천 (사용자 직접 다운, 키 불필요):
    data/raw/datagokr/산업통상부_국내 및 세계 자동차 생산량(한국자동차산업협회)_*.csv
        → anxg_auto.macro_production_yearly (snapshot_year PK)
    data/raw/datagokr/산업통상부_전체 자동차 산업 현황_*.csv
        → anxg_auto.macro_industry_monthly  (snapshot_year, snapshot_month PK)

PRD §3.5: KAMA / 산업통상자원부 공식 = A 등급, confidence 0.950.

CSV 없으면 graceful skip — exit 0.

CLI:
    python -m autograph.loaders.load_kama_macro
    python -m autograph.loaders.load_kama_macro --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
from pathlib import Path

from autonexusgraph.config import get_settings


log = logging.getLogger(__name__)


_YEARLY_GLOB  = "산업통상부_국내 및 세계 자동차 생산량*.csv"
_MONTHLY_GLOB = "산업통상부_전체 자동차 산업 현황*.csv"

_MONTH_RE = re.compile(r"^(\d{4})-(\d{1,2})$")


def _coerce_int(s: str | None) -> int | None:
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if not s or s in ("-", "—", "–"):
        return None
    try:
        return int(s)
    except (TypeError, ValueError):
        try:
            return int(float(s))
        except (TypeError, ValueError):
            return None


def _open_csv(path: Path, *, expected_header_token: str) -> list[dict]:
    """utf-8 / cp949 자동 감지하여 row dict 반환.

    DataReader header 가 ``expected_header_token`` 을 포함하는 인코딩만 채택.
    (data.go.kr CSV 는 cp949 가 많음. utf-8 디코드 자체는 통과해도 mojibake.)
    """
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            with path.open("r", encoding=enc, newline="") as f:
                head = f.read(2048)
                f.seek(0)
                if expected_header_token in head:
                    log.info("[load:kama_macro] %s encoding=%s", path.name, enc)
                    return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    log.warning("[load:kama_macro] %s encoding 자동 감지 실패", path.name)
    return []


def _find_csvs(*, root: Path | None = None
               ) -> tuple[Path | None, Path | None]:
    """(yearly_csv, monthly_csv) — 못 찾으면 None."""
    if root is None:
        root = get_settings().ingest_raw_dir / "datagokr"
    if not root.exists():
        return None, None
    yearly  = sorted(root.glob(_YEARLY_GLOB))
    monthly = sorted(root.glob(_MONTHLY_GLOB))
    return (yearly[-1] if yearly else None,
            monthly[-1] if monthly else None)


def _parse_yearly_row(row: dict) -> tuple[int, int | None, int | None] | None:
    """15051116 row → (year, domestic_units_k, global_units_k). 무효면 None."""
    year_s = (row.get("연도") or row.get("year") or "").strip()
    if not year_s.isdigit():
        return None
    year = int(year_s)
    domestic = _coerce_int(row.get("국내생산(1000대)") or row.get("국내생산"))
    glob = _coerce_int(row.get("세계생산(1000대)") or row.get("세계생산"))
    return year, domestic, glob


def _parse_monthly_row(row: dict
                       ) -> tuple[int, int, int | None, int | None, int | None] | None:
    """15051118 row → (year, month, domestic_sales, export_units, export_value_k).

    '기간' 컬럼 형식: 'YYYY-MM'.
    """
    period = (row.get("기간") or row.get("period") or "").strip()
    m = _MONTH_RE.match(period)
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if not (1 <= month <= 12):
        return None
    domestic = _coerce_int(row.get("내수판매(국산차)") or row.get("내수판매"))
    export_u = _coerce_int(row.get("수출량") or row.get("export_units"))
    export_v = _coerce_int(row.get("수출금액(천달러)") or row.get("수출금액"))
    return year, month, domestic, export_u, export_v


def _upsert_yearly(cur, *, year: int, domestic_k: int | None,
                   global_k: int | None, raw_row: dict) -> bool:
    cur.execute("""
        INSERT INTO anxg_auto.macro_production_yearly
          (snapshot_year, domestic_units_k, global_units_k, raw)
        VALUES (%s, %s, %s, %s::jsonb)
        ON CONFLICT (snapshot_year) DO UPDATE SET
          domestic_units_k = EXCLUDED.domestic_units_k,
          global_units_k   = EXCLUDED.global_units_k,
          raw              = EXCLUDED.raw,
          updated_at       = now()
        RETURNING (xmax = 0) AS is_new
    """, (year, domestic_k, global_k,
          json.dumps(raw_row, ensure_ascii=False)))
    return bool(cur.fetchone()[0])


def _upsert_monthly(cur, *, year: int, month: int,
                    domestic: int | None, export_u: int | None,
                    export_v: int | None, raw_row: dict) -> bool:
    cur.execute("""
        INSERT INTO anxg_auto.macro_industry_monthly
          (snapshot_year, snapshot_month,
           domestic_sales, export_units, export_value_usd_k, raw)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (snapshot_year, snapshot_month) DO UPDATE SET
          domestic_sales     = EXCLUDED.domestic_sales,
          export_units       = EXCLUDED.export_units,
          export_value_usd_k = EXCLUDED.export_value_usd_k,
          raw                = EXCLUDED.raw,
          updated_at         = now()
        RETURNING (xmax = 0) AS is_new
    """, (year, month, domestic, export_u, export_v,
          json.dumps(raw_row, ensure_ascii=False)))
    return bool(cur.fetchone()[0])


def run(*, root: Path | None = None,
        dry_run: bool = False) -> dict:
    """두 CSV → PG UPSERT (또는 dry_run 통계).

    Returns:
        ``{"yearly": {"inserted":..,"updated":..,"skipped":..,"csv":...},
           "monthly": {...}}``
    """
    yearly_csv, monthly_csv = _find_csvs(root=root)

    if yearly_csv is None and monthly_csv is None:
        log.warning("[load:kama_macro] KAMA CSV 없음 (찾는 위치: data/raw/datagokr/) — "
                    "graceful skip")
        return {
            "yearly":  {"inserted": 0, "updated": 0, "skipped": 0, "csv": None},
            "monthly": {"inserted": 0, "updated": 0, "skipped": 0, "csv": None},
        }

    yearly_rows = (_open_csv(yearly_csv, expected_header_token="연도")
                   if yearly_csv else [])
    monthly_rows = (_open_csv(monthly_csv, expected_header_token="기간")
                    if monthly_csv else [])

    log.info("[load:kama_macro] yearly=%d monthly=%d", len(yearly_rows),
             len(monthly_rows))

    if dry_run:
        return {
            "yearly": {
                "n_rows": len(yearly_rows),
                "valid_rows": sum(1 for r in yearly_rows
                                  if _parse_yearly_row(r)),
                "csv": str(yearly_csv) if yearly_csv else None,
                "inserted": 0, "updated": 0, "skipped": 0,
            },
            "monthly": {
                "n_rows": len(monthly_rows),
                "valid_rows": sum(1 for r in monthly_rows
                                  if _parse_monthly_row(r)),
                "csv": str(monthly_csv) if monthly_csv else None,
                "inserted": 0, "updated": 0, "skipped": 0,
            },
        }

    from autonexusgraph.db.postgres import get_connection
    conn = get_connection()
    y_ins = y_upd = y_skip = 0
    m_ins = m_upd = m_skip = 0

    with conn.cursor() as cur:
        for r in yearly_rows:
            parsed = _parse_yearly_row(r)
            if parsed is None:
                y_skip += 1
                continue
            year, dom, glob = parsed
            cur.execute("SAVEPOINT sp_kama_y")
            try:
                if _upsert_yearly(cur, year=year, domestic_k=dom,
                                  global_k=glob, raw_row=r):
                    y_ins += 1
                else:
                    y_upd += 1
                cur.execute("RELEASE SAVEPOINT sp_kama_y")
            except Exception as exc:   # noqa: BLE001 — [load:kama_macro:yearly] 연간 row UPSERT 실패 흡수 → SAVEPOINT rollback + skip + 다음 year
                cur.execute("ROLLBACK TO SAVEPOINT sp_kama_y")
                log.warning("[load:kama_macro:yearly] %s 실패: %s", year, exc)
                y_skip += 1

        for r in monthly_rows:
            parsed = _parse_monthly_row(r)
            if parsed is None:
                m_skip += 1
                continue
            year, month, dom, eu, ev = parsed
            cur.execute("SAVEPOINT sp_kama_m")
            try:
                if _upsert_monthly(cur, year=year, month=month,
                                   domestic=dom, export_u=eu, export_v=ev,
                                   raw_row=r):
                    m_ins += 1
                else:
                    m_upd += 1
                cur.execute("RELEASE SAVEPOINT sp_kama_m")
            except Exception as exc:   # noqa: BLE001 — [load:kama_macro:monthly] 월별 row UPSERT 실패 흡수 → SAVEPOINT rollback + skip + 다음 month
                cur.execute("ROLLBACK TO SAVEPOINT sp_kama_m")
                log.warning("[load:kama_macro:monthly] %d-%02d 실패: %s",
                            year, month, exc)
                m_skip += 1

    conn.commit()
    log.info("[load:kama_macro] yearly ins=%d upd=%d skip=%d / "
             "monthly ins=%d upd=%d skip=%d",
             y_ins, y_upd, y_skip, m_ins, m_upd, m_skip)
    return {
        "yearly":  {"inserted": y_ins, "updated": y_upd, "skipped": y_skip,
                    "csv": str(yearly_csv) if yearly_csv else None},
        "monthly": {"inserted": m_ins, "updated": m_upd, "skipped": m_skip,
                    "csv": str(monthly_csv) if monthly_csv else None},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="PG 호출 없이 row 통계만 출력")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    out = run(dry_run=args.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "run",
    "_find_csvs",
    "_open_csv",
    "_parse_yearly_row",
    "_parse_monthly_row",
]
