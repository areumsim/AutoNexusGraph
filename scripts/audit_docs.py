#!/usr/bin/env python3
"""문서·코드 정합성 자동 감사 — drift 회귀 가드.

측정 대상:
- AgentState 필드 카운트 (`src/autonexusgraph/agents/state.py`)
- 도메인별 .py 카운트 (autonexusgraph / autograph / ipgraph / common)
- gold QA row 카운트 (auto / cross / ip / v0)
- `PRD §X.Y` 잔재 카운트 (src/, docs/ 별도 — F-7 점진 정책 모니터링)
- MCP tool 등록 카운트 (간접 — server.py 의 ToolSpec list 길이)

베이스라인 비교 (`docs/audit_baseline.json` — 있을 때만):
  - 값 일치 → ✅ OK
  - drift 발견 → ⚠️ 경고 + exit 1
  - baseline 파일 없으면 측정만 출력 (informational mode)

사용:
    python3 scripts/audit_docs.py            # 측정 + 표 출력
    python3 scripts/audit_docs.py --strict   # baseline 미일치 시 exit 1
    python3 scripts/audit_docs.py --update-baseline  # 현재 측정값으로 baseline 갱신

전체 점검 (Makefile):
    make audit-docs
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def count_agent_state_fields() -> int:
    """src/autonexusgraph/agents/state.py 의 class AgentState 필드 카운트."""
    path = ROOT / "src/autonexusgraph/agents/state.py"
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_class = False
    count = 0
    field_re = re.compile(r"^[ \t]+[a-z_][a-z_0-9]*[ \t]*:[ \t]")
    for line in lines:
        if line.startswith("class AgentState"):
            in_class = True
            continue
        if in_class and re.match(r"^class [A-Z]", line):
            break
        if in_class and field_re.match(line):
            count += 1
    return count


def count_py_per_domain() -> OrderedDict[str, int]:
    """도메인별 .py 카운트."""
    out: OrderedDict[str, int] = OrderedDict()
    for d in ["autonexusgraph", "autograph", "ipgraph", "common"]:
        base = ROOT / "src" / d
        if not base.exists():
            out[d] = 0
            continue
        out[d] = sum(1 for _ in base.rglob("*.py"))
    return out


def count_gold_rows() -> OrderedDict[str, int]:
    """gold QA row 카운트 (example 제외)."""
    out: OrderedDict[str, int] = OrderedDict()
    gold_dir = ROOT / "eval" / "qa_gold"
    for name in ["gold_qa_auto_v0", "gold_qa_cross_v0", "gold_qa_ip_v0", "gold_qa_v0"]:
        p = gold_dir / f"{name}.jsonl"
        if not p.exists():
            out[name] = -1
            continue
        out[name] = sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())
    return out


def count_prd_refs() -> OrderedDict[str, int]:
    """`PRD §X.Y` 잔재 카운트 (src/ / docs/ 별도)."""
    out: OrderedDict[str, int] = OrderedDict()
    pat = re.compile(r"PRD §")
    for label, glob_root, glob_pat in [
        ("src", ROOT / "src", "**/*.py"),
        ("docs", ROOT / "docs", "**/*.md"),
    ]:
        n = 0
        for f in glob_root.glob(glob_pat):
            if "_legacy" in f.parts or "egg-info" in str(f):
                continue
            try:
                txt = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            n += len(pat.findall(txt))
        out[label] = n
    return out


def count_mcp_tools() -> int:
    """MCP tool 등록 카운트 — server.py 의 ToolSpec list 길이 간접 측정.

    server.build_mcp_server(domain='all') 호출 시 반환되는 tools 리스트.
    """
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from autonexusgraph.mcp.server import build_mcp_server
        _, tools = build_mcp_server(domain="all")
        return len(tools)
    except Exception as exc:   # noqa: BLE001 — audit 보조 측정 — 실패 시 -1
        print(f"  [WARN] MCP tool 카운트 측정 실패: {exc}", file=sys.stderr)
        return -1


def gather_measurements() -> dict:
    return {
        "agent_state_fields": count_agent_state_fields(),
        "py_per_domain": count_py_per_domain(),
        "gold_rows": count_gold_rows(),
        "prd_refs": count_prd_refs(),
        "mcp_tools": count_mcp_tools(),
    }


def fmt_diff(measured: int, expected: int) -> str:
    if measured == expected:
        return "✅"
    delta = measured - expected
    sign = "+" if delta > 0 else ""
    return f"⚠️ {sign}{delta}"


def render_table(measured: dict, baseline: dict | None) -> str:
    lines = ["# audit-docs — 문서·코드 정합성 측정", ""]

    def section(title: str, items: list[tuple[str, int, int | None]]) -> None:
        lines.append(f"## {title}")
        lines.append("")
        if baseline is not None:
            lines.append("| 항목 | 측정 | baseline | drift |")
            lines.append("|---|---:|---:|:---:|")
            for k, v, exp in items:
                exp_str = "—" if exp is None else str(exp)
                diff = "—" if exp is None else fmt_diff(v, exp)
                lines.append(f"| `{k}` | {v} | {exp_str} | {diff} |")
        else:
            lines.append("| 항목 | 측정 |")
            lines.append("|---|---:|")
            for k, v, _ in items:
                lines.append(f"| `{k}` | {v} |")
        lines.append("")

    # AgentState
    bl_state = (baseline or {}).get("agent_state_fields")
    section("AgentState 필드 카운트", [
        ("agent_state_fields", measured["agent_state_fields"], bl_state),
    ])

    # py per domain
    bl_py = (baseline or {}).get("py_per_domain", {})
    section(".py per domain", [
        (k, v, bl_py.get(k)) for k, v in measured["py_per_domain"].items()
    ])

    # gold rows
    bl_gold = (baseline or {}).get("gold_rows", {})
    items = [(k, v, bl_gold.get(k)) for k, v in measured["gold_rows"].items()]
    items.append(("total", sum(measured["gold_rows"].values()),
                  bl_gold.get("total")))
    section("gold QA row 카운트", items)

    # PRD refs
    bl_prd = (baseline or {}).get("prd_refs", {})
    section("PRD § 잔재 카운트 (F-7 점진 모니터링)", [
        (k, v, bl_prd.get(k)) for k, v in measured["prd_refs"].items()
    ])

    # MCP tools
    bl_mcp = (baseline or {}).get("mcp_tools")
    section("MCP tool 등록", [
        ("mcp_tools", measured["mcp_tools"], bl_mcp),
    ])

    return "\n".join(lines)


def has_drift(measured: dict, baseline: dict) -> bool:
    """baseline 과 1 항목이라도 다르면 True. (raw 값 비교 — total 미포함)"""
    if measured["agent_state_fields"] != baseline.get("agent_state_fields"):
        return True
    if measured["py_per_domain"] != baseline.get("py_per_domain", {}):
        return True
    if measured["gold_rows"] != baseline.get("gold_rows", {}):
        return True
    if measured["prd_refs"] != baseline.get("prd_refs", {}):
        return True
    if measured["mcp_tools"] != baseline.get("mcp_tools"):
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="문서·코드 정합성 감사")
    ap.add_argument("--baseline", type=Path,
                    default=ROOT / "docs" / "audit_baseline.json",
                    help="baseline JSON (기본: docs/audit_baseline.json)")
    ap.add_argument("--strict", action="store_true",
                    help="baseline 미일치 시 exit 1")
    ap.add_argument("--update-baseline", action="store_true",
                    help="현재 측정값으로 baseline 갱신")
    args = ap.parse_args()

    measured = gather_measurements()
    # baseline 은 raw row 만 저장 (total 미포함 — has_drift 가 계산)
    measured_for_baseline = {
        "agent_state_fields": measured["agent_state_fields"],
        "py_per_domain": dict(measured["py_per_domain"]),
        "gold_rows": dict(measured["gold_rows"]),
        "prd_refs": dict(measured["prd_refs"]),
        "mcp_tools": measured["mcp_tools"],
    }

    if args.update_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(
            json.dumps(measured_for_baseline, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"baseline 갱신: {args.baseline}")
        return 0

    baseline: dict | None = None
    if args.baseline.exists():
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))

    report = render_table(measured, baseline)
    print(report)

    if baseline is None:
        print("\n_baseline 파일 없음 — informational mode. `--update-baseline` 으로 생성 가능._")
        return 0

    if has_drift(measured_for_baseline, baseline):
        print("\n**⚠️ drift 발견** — 의도된 변경이면 `--update-baseline` 으로 갱신.")
        if args.strict:
            return 1
        return 0

    print("\n**✅ 모든 항목 baseline 일치**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
