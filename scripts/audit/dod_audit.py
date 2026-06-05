#!/usr/bin/env python3
"""PRD §10 DoD 14 항목 트래픽라이트 — SSOT thin wrapper.

본 스크립트는 과거에 자체 측정 로직을 들고 있었으나 ``eval/metrics/prd_dashboard.py``
가 더 정확한 메트릭(PG/Neo4j 직접 조회) 을 보유함이 확인되어 thin wrapper 로
재작성됨 (PRD §10 SSOT). 기존 CLI flag (--out / --stdout / --strict) 는 보존.

CLI:
    python scripts/audit/dod_audit.py            # 기본 경로에 md 저장
    python scripts/audit/dod_audit.py --stdout   # 화면 출력
    python scripts/audit/dod_audit.py --strict   # ❌ 1건 이상이면 exit 1

종료 코드:
    0: 항상 (또는 --strict 면서 ❌ 0건)
    1: --strict 면서 1 개 이상 ❌
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# repo 루트 (eval/) 와 src/ (autonexusgraph/) 모두 path 에 — 메트릭 모듈이 양쪽 import.
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

# SSOT — eval.metrics.prd_dashboard.collect_dashboard() 가 14항 측정.
from eval.metrics.prd_dashboard import collect_dashboard, format_summary_md  # noqa: E402

log = logging.getLogger(__name__)


def main() -> int:
    p = argparse.ArgumentParser(prog="dod_audit", description=__doc__.split("\n")[0])
    p.add_argument("--out", type=Path, default=None,
                   help="md 저장 경로 (생략 시 data/reports/dod_audit_YYYYMMDD.md)")
    p.add_argument("--stdout", action="store_true",
                   help="파일 저장 대신 stdout 으로 출력")
    p.add_argument("--strict", action="store_true",
                   help="❌ 1건 이상이면 exit 1")
    p.add_argument("--log-level", default="WARNING")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level)

    dash = collect_dashboard()
    md = format_summary_md(dash)

    if args.stdout:
        print(md)
    else:
        out = args.out or (ROOT / "data" / "reports"
                           / f"dod_audit_{date.today().strftime('%Y%m%d')}.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md + "\n", encoding="utf-8")
        print(f"[dod_audit] wrote {out}")

    # dashboard 의 item 중 'fail' 상태가 1건 이상이면 strict 실패.
    # prd_dashboard 의 status enum: pass | fail | blocked | n/a
    failed = sum(1 for item in dash.get("items", [])
                 if item.get("status") == "fail")
    if args.strict and failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
