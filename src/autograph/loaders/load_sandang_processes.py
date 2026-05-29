"""data.go.kr 15151075 — 한국산업단지공단 자동차 부품 제조업 공정 합성데이터.

CSV → ``auto.processes`` UPSERT. 550 row 자동차 부품 제조 공정 (전처리/도장/조립/
검사 등) 의 정규화된 taxonomy 사전. **합성 데이터 (PRD §3.5 C 등급)** — 단독
근거 금지, 공정명 정규형 사전으로만 사용.

CSV 스키마 (8 컬럼):
    공장관리번호, 업종차수, 업종코드, 공정도명, 공정도설명, 공정순서, 공정명, 공정설명

원본 위치 (사용자 수동 다운로드):
    data/raw/datagokr/한국산업단지공단_자동차 부품 제조업 공정 합성데이터_*.csv

CSV 없으면 graceful skip — exit 0.

CLI:
    python -m autograph.loaders.load_sandang_processes
    python -m autograph.loaders.load_sandang_processes --csv path/to/file.csv
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


_SOURCE = "datagokr_15151075"
_CSV_GLOB = "한국산업단지공단_자동차*공정*.csv"


_WS_RE = re.compile(r"\s+")


def _normalize_process_name(name: str) -> str:
    """공정명 정규형 — lowercase + 공백 정리."""
    if not name:
        return ""
    return _WS_RE.sub(" ", name.strip()).lower()


def _find_csv(csv_arg: str | None) -> Path | None:
    """명시 경로 우선, 없으면 ``data/raw/datagokr/`` 에서 glob."""
    if csv_arg:
        p = Path(csv_arg)
        return p if p.exists() else None
    root = get_settings().ingest_raw_dir / "datagokr"
    if not root.exists():
        return None
    matches = sorted(root.glob(_CSV_GLOB))
    return matches[-1] if matches else None   # 가장 최근 (정렬 시 _YYYYMMDD 가 뒤로)


def _open_csv(path: Path):
    """euc-kr 또는 utf-8 자동 감지하여 row dict iterate."""
    # data.go.kr 파일은 종종 EUC-KR 또는 CP949. utf-8 시도 후 fallback.
    for enc in ("utf-8-sig", "utf-8", "euc-kr", "cp949"):
        try:
            with path.open("r", encoding=enc, newline="") as f:
                head = f.read(2048)
                f.seek(0)
                if "공정명" in head:
                    log.info("[load:sandang] encoding=%s", enc)
                    return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    log.warning("[load:sandang] encoding 자동 감지 실패")
    return []


def _coerce_int(s: str | None) -> int | None:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def run(*, csv_path: str | None = None, dry_run: bool = False) -> dict:
    """CSV → auto.processes UPSERT (또는 dry_run 통계만)."""
    src = _find_csv(csv_path)
    if src is None:
        log.warning("[load:sandang] CSV 없음 (찾는 위치: data/raw/datagokr/%s) — "
                    "graceful skip", _CSV_GLOB)
        return {"inserted": 0, "updated": 0, "skipped": 0, "csv": None}

    rows = _open_csv(src)
    log.info("[load:sandang] %s — %d rows", src.name, len(rows))

    if dry_run:
        # 검사 — 공정명 distinct, 업종코드 distinct.
        names = {r.get("공정명") for r in rows if r.get("공정명")}
        industries = {r.get("업종코드") for r in rows if r.get("업종코드")}
        log.info("[load:sandang:dry_run] distinct process_names=%d industries=%d",
                 len(names), len(industries))
        return {
            "inserted": 0, "updated": 0, "skipped": 0,
            "csv": str(src),
            "n_rows": len(rows),
            "distinct_process_names": len(names),
            "distinct_industries": len(industries),
        }

    # 실제 적재 — PG 연결.
    from autonexusgraph.db.postgres import get_connection

    conn = get_connection()
    inserted = updated = skipped = 0
    with conn.cursor() as cur:
        for r in rows:
            factory_no = (r.get("공장관리번호") or "").strip()
            process_name = (r.get("공정명") or "").strip()
            process_order = _coerce_int(r.get("공정순서"))
            if not factory_no or not process_name:
                skipped += 1
                continue

            cur.execute("SAVEPOINT sp_sandang")
            try:
                cur.execute("""
                    INSERT INTO auto.processes
                      (factory_manage_no, industry_code, industry_level,
                       process_map_name, process_map_desc,
                       process_order, process_name, process_name_norm,
                       process_desc, raw, snapshot_year)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (factory_manage_no, process_order, process_name)
                    DO UPDATE SET
                      industry_code     = EXCLUDED.industry_code,
                      industry_level    = EXCLUDED.industry_level,
                      process_map_name  = EXCLUDED.process_map_name,
                      process_map_desc  = EXCLUDED.process_map_desc,
                      process_desc      = EXCLUDED.process_desc,
                      process_name_norm = EXCLUDED.process_name_norm,
                      raw               = EXCLUDED.raw,
                      updated_at        = now()
                    RETURNING (xmax = 0) AS is_new
                """, (
                    factory_no,
                    (r.get("업종코드") or "").strip() or None,
                    _coerce_int(r.get("업종차수")),
                    (r.get("공정도명") or "").strip() or None,
                    (r.get("공정도설명") or "").strip() or None,
                    process_order or 0,
                    process_name,
                    _normalize_process_name(process_name),
                    (r.get("공정설명") or "").strip() or None,
                    json.dumps(r, ensure_ascii=False),
                    2025,
                ))
                is_new = cur.fetchone()[0]
                cur.execute("RELEASE SAVEPOINT sp_sandang")
                if is_new:
                    inserted += 1
                else:
                    updated += 1
            except Exception as exc:   # noqa: BLE001
                cur.execute("ROLLBACK TO SAVEPOINT sp_sandang")
                log.warning("[load:sandang] %s/%s/%s 실패: %s",
                            factory_no, process_order, process_name, exc)
                skipped += 1

    conn.commit()
    log.info("[load:sandang] inserted=%d updated=%d skipped=%d",
             inserted, updated, skipped)
    return {"inserted": inserted, "updated": updated, "skipped": skipped,
            "csv": str(src)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None,
                    help="CSV 경로 (생략 시 data/raw/datagokr/ glob)")
    ap.add_argument("--dry-run", action="store_true",
                    help="PG 호출 없이 통계만 출력")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    out = run(csv_path=args.csv, dry_run=args.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["run", "_find_csv", "_open_csv", "_normalize_process_name"]
