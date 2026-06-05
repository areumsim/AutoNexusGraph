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
    by_month: dict[str, dict[str, float]] = defaultdict(
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

        month_key = day_key[:7]   # YYYY-MM
        by_month[month_key]["cost"] += cost
        by_month[month_key]["calls"] += 1
        by_month[month_key]["in"] += n_in
        by_month[month_key]["out"] += n_out

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
        "by_month":     dict(by_month),
        "by_caller":    dict(by_caller),
        "by_model":     dict(by_model),
        "by_provider":  dict(by_provider),
    }


def _bar(frac: float, width: int = 18) -> str:
    """0~1 비율 → 막대 문자열 (보기 쉽게 시각화)."""
    frac = 0.0 if frac < 0 else (1.0 if frac > 1 else frac)
    filled = int(round(frac * width))
    return "█" * filled + "·" * (width - filled)


def _fmt_usd(v: float) -> str:
    """비용 표기 — 작은 값도 0 으로 뭉개지지 않게 4자리, 큰 값은 2자리."""
    return f"${v:>8.2f}" if v >= 1 else f"${v:>8.4f}"


def _month_projection(by_month: dict[str, Any]) -> str | None:
    """이번 달(UTC) run-rate 예상 비용 — 비용까지 계산해서 보여주기."""
    from calendar import monthrange
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    mkey = now.strftime("%Y-%m")
    cur = by_month.get(mkey)
    if not cur or now.day < 1:
        return None
    days_in_month = monthrange(now.year, now.month)[1]
    spent = float(cur["cost"])
    projected = spent / now.day * days_in_month
    return (f"  이번 달 {mkey}: 현재 {_fmt_usd(spent).strip()} "
            f"(경과 {now.day}/{days_in_month}일) → 예상 월비용 ~{_fmt_usd(projected).strip()}")


def format_report(s: dict[str, Any], *, daily_limit: int | None = 31,
                  monthly_only: bool = False) -> str:
    lines: list[str] = []
    lines.append("═" * 64)
    lines.append(" LLM 사용량 · 비용 요약")
    lines.append("═" * 64)
    if s["first_ts"]:
        first_d, last_d = s["first_ts"][:10], s["last_ts"][:10]
        period = first_d if first_d == last_d else f"{first_d} ~ {last_d}"
        lines.append(f" 기간   : {period}")
    tok = s["total_in"] + s["total_out"]
    lines.append(f" 총비용 : {_fmt_usd(s['total_cost']).strip()}   "
                 f"(호출 {s['total_calls']:,} · 토큰 {tok:,})")

    # 한도 대비 (현 window 누적) — 비용 가드와 연결해서 보기 쉽게
    try:
        from .cost import get_session_limit_usd
        limit = get_session_limit_usd()
        if limit > 0:
            frac = s["total_cost"] / limit
            lines.append(f" 한도   : {_fmt_usd(s['total_cost']).strip()} / "
                         f"${limit:.2f}  {_bar(frac)} {frac*100:4.0f}%")
    except Exception:   # noqa: BLE001 — 예외 silent (best-effort, 메인 흐름 보존)
        pass
    proj = _month_projection(s.get("by_month", {}))
    if proj:
        lines.append(proj)
    lines.append("")

    # ── 월별 ──
    months = sorted(s.get("by_month", {}).items())
    mmax = max((v["cost"] for _, v in months), default=0.0) or 1.0
    lines.append("── 월별 ──────────────────────────────────────────────")
    for mk, v in months:
        lines.append(f"  {mk}  {_fmt_usd(v['cost'])}  {_bar(v['cost']/mmax)}  "
                     f"calls {int(v['calls']):,}")
    if not months:
        lines.append("  (기록 없음)")
    lines.append("")

    # ── 일별 ── (기본 최근 N일만 — 너무 길어지지 않게)
    if not monthly_only:
        days = sorted(s["by_day"].items())
        hidden = 0
        if daily_limit is not None and len(days) > daily_limit:
            hidden = len(days) - daily_limit
            days = days[-daily_limit:]
        dmax = max((v["cost"] for _, v in days), default=0.0) or 1.0
        title = "── 일별 ──" if not hidden else f"── 일별 (최근 {len(days)}일) ──"
        lines.append(title + "─" * max(0, 54 - len(title)))
        if hidden:
            lines.append(f"  (앞 {hidden}일 생략 — 전체는 --days 0 또는 --from 지정)")
        for dk, v in days:
            lines.append(f"  {dk}  {_fmt_usd(v['cost'])}  {_bar(v['cost']/dmax)}  "
                         f"calls {int(v['calls']):,}")
        if not days:
            lines.append("  (기록 없음)")
        lines.append("")

    lines.append("── Provider 별 ──")
    for p, v in sorted(s["by_provider"].items(), key=lambda x: -x[1]["cost"]):
        share = (v["cost"] / s["total_cost"] * 100) if s["total_cost"] else 0.0
        lines.append(f"  {p:10s}  {_fmt_usd(v['cost'])}  ({share:5.1f}%)  "
                     f"calls {int(v['calls']):,}")
    lines.append("")

    lines.append("── 모델 별 ──")
    for m, v in sorted(s["by_model"].items(), key=lambda x: -x[1]["cost"]):
        lines.append(f"  {m:28s}  {_fmt_usd(v['cost'])}  calls {int(v['calls']):,}  "
                     f"in {int(v['in']):,} / out {int(v['out']):,}")
    lines.append("")

    lines.append("── Caller 별 (top 10) ──")
    for caller, v in sorted(
        s["by_caller"].items(), key=lambda x: -x[1]["cost"],
    )[:10]:
        lines.append(f"  {caller:24s}  {_fmt_usd(v['cost'])}  calls {int(v['calls']):,}")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="autonexusgraph.llm.cost_history",
        description="LLM 일별·월별 사용량/비용 — cost_log.jsonl 집계 (DB 불필요)",
    )
    ap.add_argument("--from", dest="from_date", help="시작일 (YYYY-MM-DD, 포함)")
    ap.add_argument("--to", dest="to_date", help="종료일 (YYYY-MM-DD, 포함)")
    ap.add_argument("--today", action="store_true", help="오늘(UTC)만")
    ap.add_argument("--this-month", action="store_true", help="이번 달(UTC)만")
    ap.add_argument("--days", type=int, default=31,
                    help="일별 표시 일수 (기본 31, 0 = 전체)")
    ap.add_argument("--month", action="store_true",
                    help="월별 요약만 (일별 생략)")
    ap.add_argument("--path", type=Path, default=None,
                    help="cost_log.jsonl 경로 override (기본: settings.llm_cost_log_path)")
    ap.add_argument("--json", action="store_true", help="JSON 출력 (기계 파싱용)")
    args = ap.parse_args()

    try:
        from_d = date.fromisoformat(args.from_date) if args.from_date else None
        to_d = date.fromisoformat(args.to_date) if args.to_date else None
    except ValueError as e:
        print(f"날짜 형식 오류: {e}")
        return 2

    # 편의 플래그 — 오늘/이번 달 (현재 날짜 기준)
    if args.today or args.this_month:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).date()
        if args.today:
            from_d = to_d = today
        else:
            from_d = today.replace(day=1)
            to_d = today

    from .cost_log import iter_entries
    s = summarize(iter_entries(args.path), from_date=from_d, to_date=to_d)

    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=2, default=str))
    else:
        daily_limit = None if args.days == 0 else args.days
        print(format_report(s, daily_limit=daily_limit, monthly_only=args.month))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
