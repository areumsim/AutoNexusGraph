"""anxg_chat.feedback 분석 (E-4) — read-only 분포·트렌드·부정 message 모니터링.

배경: `anxg_chat.feedback` 스키마는 이미 적재 가능 상태 (`01_schema.sql:132-140`).
UI 의 `record_feedback` (`ui/storage.py:177`) 이 +1/-1/0 (comment-only) UPSERT.
본 모듈은 그 누적을 운영자가 보는 분석 계층 — retraining loop 가 등장하기 전의
이른 단계 신호 (어떤 message 에 -1 모이나, 최근 7일 사용자 만족 추세).

`embed_status.py` / `freshness.py` 와 같은 read-only 가시화 패턴.

CLI:
    python -m autonexusgraph.feedback_stats             # 표 형식
    python -m autonexusgraph.feedback_stats --json       # JSON
    python -m autonexusgraph.feedback_stats --days 30    # 최근 30일

Makefile: ``make feedback-stats``.

지표:
- overall: total / up(+1) / down(-1) / comment(0) / up_rate(%)
- recent_n_days: 최근 N일 (created_at 기준) up_rate, 트렌드 비교
- top_negative_messages: -1 누적 상위 N message (메시지 내용 truncate)
"""

from __future__ import annotations

import json
from typing import Any, Sequence


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


# ── 순수 집계 (DB 없이 테스트 가능) ───────────────────────────────────
def _up_rate(up: int, down: int) -> float:
    """+1 / (-1 + +1) 비율 — comment-only(0) 는 제외 (사용자 의견 무방향).

    분모 0 → 0.0 (집계 불가 / 의견 없음).
    """
    rated = up + down
    return round(100.0 * up / rated, 1) if rated else 0.0


def _summarize(overall: dict, recent: dict, top_negative: list[dict],
                *, days: int = 7) -> dict[str, Any]:
    """DB 결과 → 표시·JSON 공용 dict.

    overall: {total, up, down, comment} (전 기간)
    recent:  {total, up, down, comment} (최근 days)
    top_negative: [{message_id, content_preview, n_down}, ...]
    """
    total = int(overall.get("total", 0))
    up = int(overall.get("up", 0))
    down = int(overall.get("down", 0))
    comment = int(overall.get("comment", 0))

    r_total = int(recent.get("total", 0))
    r_up = int(recent.get("up", 0))
    r_down = int(recent.get("down", 0))
    r_comment = int(recent.get("comment", 0))

    return {
        "overall": {
            "total":   total,
            "up":      up,
            "down":    down,
            "comment": comment,
            "up_rate": _up_rate(up, down),
        },
        "recent": {
            "days":    days,
            "total":   r_total,
            "up":      r_up,
            "down":    r_down,
            "comment": r_comment,
            "up_rate": _up_rate(r_up, r_down),
        },
        "top_negative": [
            {
                "message_id":      int(r["message_id"]),
                "content_preview": (r.get("content_preview") or "")[:160],
                "n_down":          int(r.get("n_down", 1)),
                "last_at":         r.get("last_at"),
            }
            for r in top_negative
        ],
    }


# ── 실데이터 진입점 ──────────────────────────────────────────────────
_SQL_OVERALL = """
SELECT
  count(*) AS total,
  count(*) FILTER (WHERE rating = 1)  AS up,
  count(*) FILTER (WHERE rating = -1) AS down,
  count(*) FILTER (WHERE rating = 0)  AS comment
FROM anxg_chat.feedback
"""

_SQL_RECENT = """
SELECT
  count(*) AS total,
  count(*) FILTER (WHERE rating = 1)  AS up,
  count(*) FILTER (WHERE rating = -1) AS down,
  count(*) FILTER (WHERE rating = 0)  AS comment
FROM anxg_chat.feedback
 WHERE created_at >= now() - (%s::int * interval '1 day')
"""

_SQL_TOP_NEGATIVE = """
SELECT
  f.message_id,
  substr(m.content, 1, 160) AS content_preview,
  count(*) AS n_down,
  max(f.created_at) AS last_at
FROM anxg_chat.feedback f
JOIN anxg_chat.messages m ON m.id = f.message_id
WHERE f.rating = -1
GROUP BY f.message_id, m.content
ORDER BY count(*) DESC, max(f.created_at) DESC
LIMIT %s
"""


def feedback_stats(*, days: int = 7, top_n: int = 10) -> dict[str, Any]:
    overall = _run(_SQL_OVERALL, fetch="rows")[0]
    recent = _run(_SQL_RECENT, (days,), fetch="rows")[0]
    top_negative = _run(_SQL_TOP_NEGATIVE, (top_n,), fetch="rows")
    return _summarize(overall, recent, top_negative, days=days)


# ── 표 출력 ──────────────────────────────────────────────────────────
def _format_table(st: dict[str, Any]) -> str:
    o = st["overall"]
    r = st["recent"]
    lines = [
        f"anxg_chat.feedback — total {o['total']:,} "
        f"(👍 {o['up']:,} / 👎 {o['down']:,} / 📝 {o['comment']:,}) · "
        f"up_rate {o['up_rate']}%",
        f"  최근 {r['days']}일: total {r['total']:,} "
        f"(👍 {r['up']:,} / 👎 {r['down']:,} / 📝 {r['comment']:,}) · "
        f"up_rate {r['up_rate']}%",
    ]
    if st["top_negative"]:
        lines.append("")
        lines.append(f"  부정(-1) 누적 상위 (message_id · n_down · preview)")
        lines.append(f"  {'-'*72}")
        for tn in st["top_negative"]:
            preview = (tn["content_preview"] or "").replace("\n", " ")[:50]
            lines.append(
                f"  {tn['message_id']:>10} {tn['n_down']:>3}x  {preview}…"
            )
    else:
        lines.append("")
        lines.append("  부정(-1) 누적 0건 — feedback 부족 또는 모두 긍정.")
    return "\n".join(lines)


def _main(argv: Sequence[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="autonexusgraph.feedback_stats",
        description="anxg_chat.feedback 분포·트렌드·부정 message 모니터링 (E-4)",
    )
    p.add_argument("--days", type=int, default=7,
                   help="최근 N일 트렌드 (기본 7)")
    p.add_argument("--top-n", type=int, default=10,
                   help="부정 message 상위 N (기본 10)")
    p.add_argument("--json", action="store_true",
                   help="JSON 출력 (기본은 표)")
    args = p.parse_args(argv)
    st = feedback_stats(days=args.days, top_n=args.top_n)
    if args.json:
        print(json.dumps(st, ensure_ascii=False, indent=2, default=str))
    else:
        print(_format_table(st))
    return 0


__all__ = ["feedback_stats", "_summarize", "_up_rate"]


if __name__ == "__main__":
    raise SystemExit(_main())
