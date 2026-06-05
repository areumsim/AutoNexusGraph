"""데이터 freshness 모니터링 (Q-5) — source별 마지막 적재/콘텐츠 시각 + stale 판정.

배경 (BACKLOG Q-5 / README §12.4): "NHTSA recalls 마지막 호출 / DART 마지막 filing"
처럼 소스별로 (1) 우리가 마지막으로 적재한 시각(ingest), (2) 최신 콘텐츠 일자
(content) 를 측정해 오래 갱신 안 된 소스를 stale 로 표시.

사전 정의 소스 allowlist(`FRESHNESS_SOURCES`) 만 조회 — 자유 SQL 금지. 각 소스는
graceful: 테이블/컬럼 부재·빈 테이블이면 crash 없이 status 로 표기.

CLI:
    python -m autonexusgraph.freshness                 # 표
    python -m autonexusgraph.freshness --json
    python -m autonexusgraph.freshness --stale-days 30
Makefile: ``make freshness``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any

DEFAULT_STALE_DAYS = 90

# (label, schema.table, ingest 타임스탬프 컬럼, content 일자 컬럼)
FRESHNESS_SOURCES: list[dict[str, str]] = [
    {"label": "DART filings",      "table": "anxg_fin.filings",            "ingest": "ingested_at", "content": "rcept_dt"},
    {"label": "anxg_vec.chunks",        "table": "anxg_vec.chunks",             "ingest": "created_at",  "content": "created_at"},
    {"label": "NHTSA recalls",     "table": "anxg_auto.events_recalls",    "ingest": "ingested_at", "content": "report_date"},
    {"label": "NHTSA complaints",  "table": "anxg_auto.events_complaints", "ingest": "ingested_at", "content": "filed_date"},
    {"label": "OEM SEC financials","table": "anxg_auto.oem_financials_sec","ingest": "ingested_at", "content": "filed_at"},
    {"label": "IP patents",        "table": "anxg_ip.patents",             "ingest": "ingested_at", "content": "filing_date"},
    {"label": "anxg_bridge.corp_entity","table": "anxg_bridge.corp_entity",     "ingest": "created_at",  "content": "updated_at"},
    {"label": "anxg_master.persons",    "table": "anxg_master.persons",         "ingest": "updated_at",  "content": "updated_at"},
]


def _run(sql: str, params: Sequence | None = None) -> list[dict]:
    from autonexusgraph.db.postgres import get_connection

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params or ()))
        cols = [d.name for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.commit()
    return rows


def _age_days(ts: Any, now: datetime) -> int | None:
    """timestamp/date → now 와의 일수 차. None/파싱불가 → None."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        t = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        return (now - t).days
    if isinstance(ts, date):
        return (now.date() - ts).days
    return None


def _classify(n: int, age_days: int | None, stale_days: int) -> str:
    if n == 0:
        return "empty"
    if age_days is None:
        return "unknown"
    return "stale" if age_days > stale_days else "ok"


def check_freshness(*, stale_days: int = DEFAULT_STALE_DAYS,
                    now: datetime | None = None,
                    sources: list[dict] | None = None) -> dict[str, Any]:
    """소스별 freshness 측정. 각 소스 graceful (오류 → status='error')."""
    now = now or datetime.now(timezone.utc)
    srcs = sources if sources is not None else FRESHNESS_SOURCES
    out: list[dict] = []
    for s in srcs:
        rec: dict[str, Any] = {"label": s["label"], "table": s["table"]}
        try:
            sql = (f"SELECT count(*) AS n, max({s['ingest']}) AS last_ingested, "
                   f"max({s['content']}) AS last_content FROM {s['table']}")
            row = _run(sql)[0]
            n = int(row["n"])
            age = _age_days(row["last_ingested"], now)
            rec.update({
                "n": n,
                "last_ingested": row["last_ingested"],
                "last_content": row["last_content"],
                "ingest_age_days": age,
                "status": _classify(n, age, stale_days),
            })
        except Exception as e:   # noqa: BLE001 — 테이블/컬럼 부재 graceful
            rec.update({"n": None, "status": "error", "error": str(e).splitlines()[0][:120]})
        out.append(rec)
    n_stale = sum(1 for r in out if r["status"] == "stale")
    return {"stale_days": stale_days, "n_sources": len(out),
            "n_stale": n_stale, "sources": out}


def _format_table(rep: dict[str, Any]) -> str:
    icon = {"ok": "✅", "stale": "⚠️ STALE", "empty": "·empty", "unknown": "?", "error": "❌err"}
    lines = [f"데이터 freshness — stale 임계 {rep['stale_days']}일 · stale {rep['n_stale']}/{rep['n_sources']}", ""]
    for s in rep["sources"]:
        st = icon.get(s["status"], s["status"])
        if s["status"] == "error":
            lines.append(f"  {s['label']:<20} {st}  {s.get('error','')}")
        else:
            age = s.get("ingest_age_days")
            lines.append(f"  {s['label']:<20} {st:<9} n={s.get('n')}  "
                         f"ingest {age if age is not None else '?'}일전  content={s.get('last_content')}")
    return "\n".join(lines)


def _main(argv: Sequence[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="autonexusgraph.freshness",
                                description="데이터 freshness 모니터링 (Q-5)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    args = p.parse_args(argv)
    rep = check_freshness(stale_days=args.stale_days)
    print(json.dumps(rep, ensure_ascii=False, indent=2, default=str) if args.json
          else _format_table(rep))
    # stale/error 있으면 비0 exit (cron 알람용)
    return 1 if (rep["n_stale"] or any(s["status"] == "error" for s in rep["sources"])) else 0


__all__ = ["check_freshness", "_age_days", "_classify", "FRESHNESS_SOURCES", "DEFAULT_STALE_DAYS"]


if __name__ == "__main__":
    raise SystemExit(_main())
