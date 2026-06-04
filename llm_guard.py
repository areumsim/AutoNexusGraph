#!/usr/bin/env python3
"""LLM 비용 가드 운영 CLI — kill-switch 토글 + 사용량/한도 점검.

순수 Python (Windows/Unix 공통). 전체 정책: COST_GUARD.md

사용:
    python llm_guard.py status     # llm_enabled + window 누적/한도/오늘/이번달
    python llm_guard.py on          # LLM 호출 허용  (.env LLM_ENABLED=true)
    python llm_guard.py off         # LLM 호출 차단  (.env LLM_ENABLED=false)
    python llm_guard.py reset       # cost_log.jsonl 아카이브 → 누적 window 리셋

Makefile: make llm-status / llm-on / llm-off / llm-reset

주의: on/off 는 .env 를 갱신한다. 이미 실행 중인 프로세스(서버 등)는 설정 캐시
(get_settings lru_cache) 때문에 재시작해야 반영된다. 배치/CLI 는 새 프로세스라 즉시 반영.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"


# ── .env LLM_ENABLED 토글 ──────────────────────────────────────────────
def _set_env_flag(value: bool) -> str:
    """.env 의 LLM_ENABLED 라인을 value 로 갱신(없으면 추가). 반환: 적용 문자열."""
    flag = "true" if value else "false"
    line = f"LLM_ENABLED={flag}"
    if not ENV_PATH.exists():
        ENV_PATH.write_text(line + "\n", encoding="utf-8")
        return flag
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    out, found = [], False
    for ln in lines:
        stripped = ln.lstrip()
        if stripped.startswith("LLM_ENABLED=") or stripped.startswith("#LLM_ENABLED="):
            out.append(line)
            found = True
        else:
            out.append(ln)
    if not found:
        out.append(line)
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    return flag


# ── status ─────────────────────────────────────────────────────────────
def _fmt(v: float) -> str:
    return f"${v:.2f}" if v >= 1 else f"${v:.4f}"


def cmd_status() -> int:
    # 설정/누적은 패키지 헬퍼 재사용 (cost_log + cost 한도 resolver).
    from autonexusgraph.config import get_settings
    from autonexusgraph.llm.cost import get_session_limit_usd, get_cost_window_hours
    from autonexusgraph.llm.cost_log import total_cost

    s = get_settings()
    enabled = getattr(s, "llm_enabled", True)
    limit = get_session_limit_usd()
    hrs = get_cost_window_hours()

    now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=hrs)) if hrs and hrs > 0 else None
    window_total = total_cost(since=since)
    today_total = total_cost(since=now.replace(hour=0, minute=0, second=0, microsecond=0))
    month_total = total_cost(since=now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))

    win_label = f"최근 {hrs:g}h" if (hrs and hrs > 0) else "전체기간"
    frac = (window_total / limit * 100) if limit > 0 else 0.0

    print("═" * 52)
    print(" LLM 가드 상태")
    print("═" * 52)
    print(f" LLM 호출   : {'✅ ENABLED' if enabled else '⛔ DISABLED (off)'}")
    print(f" 누적({win_label}) : {_fmt(window_total)} / 한도 {_fmt(limit)}  ({frac:.0f}%)")
    print(f" 오늘       : {_fmt(today_total)}")
    print(f" 이번 달    : {_fmt(month_total)}")
    print(f" 로그       : {s.llm_cost_log_path}")
    print("─" * 52)
    print(" 토글: make llm-on / llm-off   ·   리셋: make llm-reset")
    print(" 상세: python -m autonexusgraph.llm.cost_history")
    if frac >= 100:
        print(" ⚠ 누적이 한도 초과 — 후속 호출은 BudgetExceeded 로 차단됩니다.")
    return 0


def cmd_on() -> int:
    _set_env_flag(True)
    print("✅ LLM_ENABLED=true (.env). LLM 호출 허용.")
    print("   (실행 중 서버는 재시작해야 반영)")
    return 0


def cmd_off() -> int:
    _set_env_flag(False)
    print("⛔ LLM_ENABLED=false (.env). 이후 get_llm_client() 는 LLMError 로 차단.")
    print("   (실행 중 서버는 재시작해야 반영)")
    return 0


def cmd_reset(yes: bool) -> int:
    from autonexusgraph.config import get_settings
    path = Path(get_settings().llm_cost_log_path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        print(f"리셋할 로그 없음: {path}")
        return 0
    if not yes:
        ans = input(f"{path} 를 아카이브하고 누적을 리셋합니다. 진행? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("취소.")
            return 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = path.with_name(path.name + f".bak.{stamp}")
    path.rename(bak)
    print(f"✅ 누적 리셋 — 아카이브: {bak.name}")
    print("   (새 호출부터 새 cost_log.jsonl 에 기록)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="llm_guard.py",
        description="LLM 비용 가드 운영 — kill-switch 토글 + 사용량/한도 점검 (COST_GUARD.md)",
    )
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("status", help="상태/누적/한도")
    sub.add_parser("on", help="LLM 호출 허용")
    sub.add_parser("off", help="LLM 호출 차단(kill-switch)")
    r = sub.add_parser("reset", help="cost_log.jsonl 아카이브 → 누적 리셋")
    r.add_argument("-y", "--yes", action="store_true", help="확인 prompt 생략")
    args = ap.parse_args(argv)

    if args.cmd == "on":
        return cmd_on()
    if args.cmd == "off":
        return cmd_off()
    if args.cmd == "reset":
        return cmd_reset(args.yes)
    # 기본 = status
    return cmd_status()


if __name__ == "__main__":
    raise SystemExit(main())
