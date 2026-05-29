"""LLM 비용 누계 CLI — cost_log.jsonl 을 기간/caller/모델/provider 별 집계.

사용:
    python -m autonexusgraph.llm.cost_history                       # 전체 누계
    python -m autonexusgraph.llm.cost_history --from 2026-05-01     # 기간 필터
    python -m autonexusgraph.llm.cost_history --from 2026-05-01 --to 2026-05-31
    python -m autonexusgraph.llm.cost_history --json                # 기계 파싱용

본 도구는 DB 없이 동작 — 로컬 ``data/cost_log.jsonl`` 만 읽음. 따라서
프로세스 재시작 / DB 다운 / 다른 환경에서도 누계 추적 가능.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _parse_ts(ts_str: str) -> datetime | None:
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def summarize(
    entries,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[str, Any]:
    """entries → 집계 dict (총합 + by_day/caller/model/provider 4개 축)."""
    total_cost = 0.0
    total_calls = 0
    total_in = 0
    total_out = 0

    by_day: dict[str, dict[str, float]] = defaultdict(
        lambda: {"cost": 0.0, "calls": 0, "in": 0, "out": 0},
    )
    by_caller: dict[str, dict[str, float]] = defaultdict(
        lambda: {"cost": 0.0, "calls": 0},
    )
    by_model: dict[str, dict[str, float]] = defaultdict(
        lambda: {"cost": 0.0, "calls": 0, "in": 0, "out": 0},
    )
    by_provider: dict[str, dict[str, float]] = defaultdict(
        lambda: {"cost": 0.0, "calls": 0},
    )

    first_ts: datetime | None = None
    last_ts: datetime | None = None

    for e in entries:
        ts = _parse_ts(str(e.get("ts", "")))
        if ts is None:
            continue
        d = ts.date()
        if from_date and d < from_date:
            continue
        if to_date and d > to_date:
            continue

        cost = float(e.get("cost_usd", 0.0) or 0.0)
        n_in = int(e.get("input_tokens", 0) or 0)
        n_out = int(e.get("output_tokens", 0) or 0)
        caller = str(e.get("caller", "?") or "?")
        model = str(e.get("model", "?") or "?")
        provider = str(e.get("provider", "?") or "?")

        total_cost += cost
        total_calls += 1
        total_in += n_in
        total_out += n_out

        day_key = d.isoformat()
        by_day[day_key]["cost"] += cost
        by_day[day_key]["calls"] += 1
        by_day[day_key]["in"] += n_in
        by_day[day_key]["out"] += n_out

        by_caller[caller]["cost"] += cost
        by_caller[caller]["calls"] += 1

        by_model[model]["cost"] += cost
        by_model[model]["calls"] += 1
        by_model[model]["in"] += n_in
        by_model[model]["out"] += n_out

        by_provider[provider]["cost"] += cost
        by_provider[provider]["calls"] += 1

        if first_ts is None or ts < first_ts:
            first_ts = ts
        if last_ts is None or ts > last_ts:
            last_ts = ts

    return {
        "total_cost":   total_cost,
        "total_calls":  total_calls,
        "total_in":     total_in,
        "total_out":    total_out,
        "first_ts":     first_ts.isoformat() if first_ts else None,
        "last_ts":      last_ts.isoformat() if last_ts else None,
        "by_day":       dict(by_day),
        "by_caller":    dict(by_caller),
        "by_model":     dict(by_model),
        "by_provider":  dict(by_provider),
    }


def format_report(s: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("LLM 비용 누계 요약")
    lines.append("=" * 60)
    if s["first_ts"]:
        # 기간 표시 — 날짜 부분만.
        first_d = s["first_ts"][:10]
        last_d = s["last_ts"][:10]
        if first_d == last_d:
            lines.append(f"기간     : {first_d} (단일일)")
        else:
            lines.append(f"기간     : {first_d} ~ {last_d}")
    lines.append(f"총 호출  : {s['total_calls']:,}")
    lines.append(f"총 토큰  : in={s['total_in']:,}  out={s['total_out']:,}  "
                 f"합={s['total_in']+s['total_out']:,}")
    lines.append(f"총 비용  : ${s['total_cost']:.6f}")
    lines.append("")

    lines.append("── 일별 ──")
    for day, v in sorted(s["by_day"].items()):
        lines.append(
            f"  {day}  ${v['cost']:.6f}  "
            f"calls={int(v['calls']):,}  tokens={int(v['in']+v['out']):,}"
        )
    if not s["by_day"]:
        lines.append("  (no entries)")
    lines.append("")

    lines.append("── Provider 별 ──")
    for p, v in sorted(s["by_provider"].items(), key=lambda x: -x[1]["cost"]):
        share = (v["cost"] / s["total_cost"] * 100) if s["total_cost"] else 0.0
        lines.append(
            f"  {p:12s}  ${v['cost']:.6f}  ({share:5.1f}%)  "
            f"calls={int(v['calls']):,}"
        )
    lines.append("")

    lines.append("── 모델 별 ──")
    for m, v in sorted(s["by_model"].items(), key=lambda x: -x[1]["cost"]):
        lines.append(
            f"  {m:30s}  ${v['cost']:.6f}  "
            f"calls={int(v['calls']):,}  "
            f"in={int(v['in']):,}  out={int(v['out']):,}"
        )
    lines.append("")

    lines.append("── Caller 별 (top 10) ──")
    for caller, v in sorted(
        s["by_caller"].items(), key=lambda x: -x[1]["cost"],
    )[:10]:
        lines.append(
            f"  {caller:25s}  ${v['cost']:.6f}  calls={int(v['calls']):,}"
        )

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(prog="autonexusgraph.llm.cost_history")
    ap.add_argument("--from", dest="from_date",
                    help="시작일 (YYYY-MM-DD, 포함)")
    ap.add_argument("--to", dest="to_date",
                    help="종료일 (YYYY-MM-DD, 포함)")
    ap.add_argument("--path", type=Path, default=None,
                    help="cost_log.jsonl 경로 override (기본: settings.llm_cost_log_path)")
    ap.add_argument("--json", action="store_true",
                    help="JSON 출력 (기계 파싱용)")
    args = ap.parse_args()

    try:
        from_d = date.fromisoformat(args.from_date) if args.from_date else None
        to_d = date.fromisoformat(args.to_date) if args.to_date else None
    except ValueError as e:
        print(f"날짜 형식 오류: {e}")
        return 2

    from .cost_log import iter_entries
    s = summarize(
        iter_entries(args.path), from_date=from_d, to_date=to_d,
    )

    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_report(s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
