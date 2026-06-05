"""anxg_vec.chunks 임베딩 backfill 진행률 (Q-4) — read-only 가시화.

배경: `anxg_vec.chunks.embedding` (BGE-M3 1024d) 은 `embed_chunks.py` 로 backfill 된다.
finance 청크는 대량(~748K) 이라 부분 적재, auto 청크(~16K)는 100%. 어디까지
채워졌는지 한눈에 보기 위한 진행률 도구 (BACKLOG Q-4 / README §12.4).

`source` 컬럼으로 도메인 구분 (finance: dart/wikipedia/fss_press · auto:
nhtsa_recall/nhtsa_complaint/wikipedia_auto). `embedding IS NULL` = pending.

CLI:
    python -m autonexusgraph.embed_status          # 표 형식
    python -m autonexusgraph.embed_status --json    # JSON

Makefile: ``make embed-status``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any


# ── DB 실행기 (테스트 monkeypatch 지점) ──────────────────────────────
def _run(sql: str, params: Sequence | None = None, *, fetch: str = "rows") -> Any:
    from autonexusgraph.db.postgres import get_connection

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params or ()))
        if fetch == "rows":
            cols = [d.name for d in cur.description]
            out: Any = [dict(zip(cols, r)) for r in cur.fetchall()]
        else:  # scalar
            row = cur.fetchone()
            out = row[0] if row else None
    conn.commit()
    return out


def _pct(embedded: int, total: int) -> float:
    return round(100.0 * embedded / total, 1) if total else 0.0


def _summarize(overall: dict, by_source: list[dict]) -> dict[str, Any]:
    """순수 집계 (DB 없이 테스트 가능). count → pct + per-source pct."""
    total = int(overall.get("total", 0))
    embedded = int(overall.get("embedded", 0))
    pending = total - embedded
    sources = [
        {
            "source": (r.get("source") or "(null)"),
            "total": int(r["total"]),
            "embedded": int(r["embedded"]),
            "pending": int(r["total"]) - int(r["embedded"]),
            "pct": _pct(int(r["embedded"]), int(r["total"])),
        }
        for r in by_source
    ]
    return {
        "total": total,
        "embedded": embedded,
        "pending": pending,
        "pct": _pct(embedded, total),
        "by_source": sources,
    }


def embed_status() -> dict[str, Any]:
    """anxg_vec.chunks 임베딩 backfill 진행률 — 전체 + source 별."""
    overall = _run(
        "SELECT count(*) AS total, count(embedding) AS embedded FROM anxg_vec.chunks",
        fetch="rows",
    )[0]
    by_source = _run(
        """
        SELECT source, count(*) AS total, count(embedding) AS embedded
          FROM anxg_vec.chunks
         GROUP BY source
         ORDER BY (count(*) - count(embedding)) DESC, count(*) DESC
        """,
        fetch="rows",
    )
    return _summarize(overall, by_source)


def _format_table(st: dict[str, Any]) -> str:
    lines = [
        f"anxg_vec.chunks 임베딩 backfill — {st['embedded']:,}/{st['total']:,} "
        f"({st['pct']}%) · pending {st['pending']:,}",
        "",
        f"  {'source':<18} {'embedded':>12} {'total':>12} {'pct':>7}  pending",
        f"  {'-'*18} {'-'*12} {'-'*12} {'-'*7}  {'-'*9}",
    ]
    for s in st["by_source"]:
        lines.append(
            f"  {s['source']:<18} {s['embedded']:>12,} {s['total']:>12,} "
            f"{s['pct']:>6}% {s['pending']:>9,}"
        )
    return "\n".join(lines)


def _main(argv: Sequence[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="autonexusgraph.embed_status",
                                description="anxg_vec.chunks 임베딩 backfill 진행률 (Q-4)")
    p.add_argument("--json", action="store_true", help="JSON 출력 (기본은 표)")
    args = p.parse_args(argv)
    st = embed_status()
    if args.json:
        print(json.dumps(st, ensure_ascii=False, indent=2))
    else:
        print(_format_table(st))
    return 0


__all__ = ["embed_status", "_summarize"]


if __name__ == "__main__":
    raise SystemExit(_main())
