#!/usr/bin/env python3
"""PRD §10 DoD #17 (a) — MCP 래퍼 wire-up audit.

검증 흐름:
  1. ``mcp`` SDK 미설치 시 SKIPPED + exit 0 (fail-soft).
  2. ``build_tool_manifest('all')`` → tool 수 / 도메인 분포 확인.
  3. SDK 설치 시 ``build_mcp_server('all')`` boot + tool list 검증.
  4. JSON 리포트 ``data/reports/audit_mcp_<ISO>.json``.

종료 코드:
    0: PASS 또는 SKIPPED
    1: FAIL (tool discovery 0 건 / server boot 실패)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from autonexusgraph.mcp import build_tool_manifest   # noqa: E402

log = logging.getLogger(__name__)


def _check_mcp_sdk() -> bool:
    try:
        import mcp   # noqa: F401
        return True
    except ImportError:
        return False


def _check_server_boot() -> dict:
    """SDK 설치 환경 — build_mcp_server 호출 실측."""
    try:
        from autonexusgraph.mcp.server import build_mcp_server
    except ImportError as e:
        return {"passed": False, "reason": f"server import 실패: {e}"}
    try:
        server, specs = build_mcp_server("all")
    except Exception as e:   # noqa: BLE001
        return {"passed": False, "reason": f"build_mcp_server 실패: {e}"}
    return {"passed": True, "n_tools": len(specs),
            "server_name": getattr(server, "name", "?")}


def main() -> int:
    p = argparse.ArgumentParser(prog="audit-mcp", description=__doc__.split("\n")[0])
    p.add_argument("--out-dir", type=Path,
                   default=ROOT / "data" / "reports",
                   help="JSON 리포트 저장 디렉토리")
    p.add_argument("--log-level", default="WARNING")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out_dir / f"audit_mcp_{ts}.json"

    sdk_ok = _check_mcp_sdk()
    # discovery 는 SDK 무관 — 항상 검증.
    try:
        specs = build_tool_manifest("all")
    except Exception as e:   # noqa: BLE001
        payload = {"passed": False, "reason": f"tool discovery 실패: {e}"}
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        print(f"[audit-mcp] FAIL — {payload['reason']}  ({out_path})")
        return 1

    by_domain: dict[str, int] = {}
    for s in specs:
        by_domain[s.domain] = by_domain.get(s.domain, 0) + 1

    if not specs:
        payload = {"passed": False, "reason": "tool discovery 0 건"}
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        print(f"[audit-mcp] FAIL — tool 0 건  ({out_path})")
        return 1

    if not sdk_ok:
        payload = {
            "skipped":   True,
            "reason":    "mcp SDK 미설치 — pip install mcp 후 재시도",
            "n_tools":   len(specs),
            "by_domain": by_domain,
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        print(f"[audit-mcp] SKIPPED — mcp SDK 미설치. tool discovery {len(specs)} 건 OK  ({out_path})")
        return 0

    # SDK 설치 — server boot 검증.
    boot = _check_server_boot()
    overall = boot.get("passed", False)
    payload = {
        "passed":    overall,
        "n_tools":   len(specs),
        "by_domain": by_domain,
        "server":    boot,
        "sample":    [{"name": s.name, "domain": s.domain} for s in specs[:10]],
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    if overall:
        print(f"[audit-mcp] PASS — {len(specs)} tools ({by_domain})  ({out_path})")
        return 0
    print(f"[audit-mcp] FAIL — {boot.get('reason', '?')}  ({out_path})")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
