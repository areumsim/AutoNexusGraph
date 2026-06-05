"""KOSIS 산업 통계 raw → anxg_macro.kosis_series PG 적재.

PRD §10 — 자동차 산업 거시 통계 (광업제조업 동향조사 등) 시계열 통합.
scripts/ingest/download_kosis.py 가 raw json 만 저장 — 본 loader 가 PG 정규화.

사용:
    python -m autograph.loaders.load_kosis_industry
    python -m autograph.loaders.load_kosis_industry --dry-run
    python -m autograph.loaders.load_kosis_industry --raw-dir data/raw/kosis
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "raw" / "kosis"

log = logging.getLogger(__name__)


def _iter_raw_files(raw_dir: Path) -> Iterator[tuple[Path, str]]:
    """raw_dir/<stat_code>/<period>.json 트리 순회."""
    if not raw_dir.exists():
        return
    for stat_dir in sorted(raw_dir.iterdir()):
        if not stat_dir.is_dir():
            continue
        for fp in sorted(stat_dir.glob("*.json")):
            yield fp, stat_dir.name


def _coerce_rows(payload, stat_code_hint: str) -> list[dict]:
    """KOSIS raw payload → KosisRow dict list."""
    try:
        from autonexusgraph.ingestion.kosis_client import KosisClient
    except Exception:   # noqa: BLE001 — [load_kosis_industry] fail-soft 흡수 → [] 반환
        return []
    # payload 가 list (raw rows) 또는 dict (wrap) 양쪽 지원.
    raw_rows = payload if isinstance(payload, list) else payload.get("data") or payload.get("items") or []
    if not raw_rows:
        return []
    # KosisClient 인스턴스 만들지 않고 static normalize 만 호출 — api_key 없어도 OK.
    cli = KosisClient.__new__(KosisClient)
    cli.api_key = "_normalize_only_"
    normalized = cli.normalize(raw_rows, stat_code_hint=stat_code_hint)
    out: list[dict] = []
    for r in normalized:
        # anxg_macro.kosis_series PK = (stat_code, item_code, time). cycle = period_type.
        # time 의 길이로 cycle 추론: 4→A, 6→M, 5(YYYY+Q)→Q.
        cycle = "A"
        if len(r.time) == 6:
            cycle = "M"
        elif len(r.time) == 5 and "Q" in r.time:
            cycle = "Q"
        out.append({
            "stat_code":  r.stat_code,
            "item_code":  r.item_code,
            "time":       r.time,
            "cycle":      cycle,
            "value":      r.value,
            "unit":       r.unit,
            "stat_name":  r.stat_name,
            "item_name":  r.item_name,
            "raw":        json.dumps({"src_row": True}, ensure_ascii=False),
        })
    return out


def collect_rows(raw_dir: Path | None = None) -> list[dict]:
    raw_dir = raw_dir or RAW_DIR
    rows: list[dict] = []
    for fp, stat_code in _iter_raw_files(raw_dir):
        try:
            payload = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:   # noqa: BLE001 — [load_kosis_industry] 1 unit 실패 흡수 → log + continue (부분 성공 보존)
            log.warning("[kosis.load] %s 파싱 실패: %s", fp, e)
            continue
        rows.extend(_coerce_rows(payload, stat_code_hint=stat_code))
    return rows


def upsert_pg(rows: list[dict]) -> int:
    if not rows:
        return 0
    try:
        from autonexusgraph.db.postgres import get_pool
    except Exception as e:   # noqa: BLE001 — [load_kosis_industry] fail-soft 흡수 → 0 반환 (log 동반)
        log.warning("[kosis.load_pg] postgres 모듈 미가용: %s", e)
        return 0
    sql = """
    INSERT INTO anxg_macro.kosis_series (
        stat_code, item_code, time, cycle, value,
        unit, stat_name, item_name, raw
    ) VALUES (
        %(stat_code)s, %(item_code)s, %(time)s, %(cycle)s, %(value)s,
        %(unit)s, %(stat_name)s, %(item_name)s, %(raw)s::jsonb
    )
    ON CONFLICT (stat_code, item_code, time) DO UPDATE SET
        value      = EXCLUDED.value,
        unit       = COALESCE(EXCLUDED.unit, anxg_macro.kosis_series.unit),
        stat_name  = COALESCE(EXCLUDED.stat_name, anxg_macro.kosis_series.stat_name),
        item_name  = COALESCE(EXCLUDED.item_name, anxg_macro.kosis_series.item_name),
        raw        = EXCLUDED.raw
    """
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            n = 0
            for r in rows:
                cur.execute(sql, r)
                n += cur.rowcount or 0
            return n
    except Exception as e:   # noqa: BLE001 — [load_kosis_industry] fail-soft 흡수 → 0 반환 (log 동반)
        log.warning("[kosis.load_pg] PG 적재 실패 (fail-soft): %s", e)
        return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="autograph.loaders.load_kosis_industry",
                                 description=__doc__.split("\n")[0])
    p.add_argument("--raw-dir", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(message)s")

    rows = collect_rows(args.raw_dir)
    log.info("[kosis] %d rows collected from raw json", len(rows))
    if args.dry_run:
        # 상위 5 row 출력.
        for r in rows[:5]:
            print(f"  {r['stat_code']:14s} {r['item_code']:12s} "
                  f"{r['time']:8s} {r['cycle']:1s} {r['value']!s:12s} {r['unit']!s}")
        return 0
    n = upsert_pg(rows)
    print(f"[kosis.load] upserted {n} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
