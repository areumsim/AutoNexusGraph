"""Per-turn trace 홉 메트릭 (E-3 / DoD §10.13) — tool_results 에서 파생.

배경: 기존 trace 는 latency·cost 만 기록하고 **cypher hop 수·tool 호출 sequence**
는 미기록 (BACKLOG E-3). main_hop_efficiency 는 evidence-count 프록시만 썼다.

본 모듈은 **state["tool_results"] 만으로 파생** — worker/state 변경 없음 (자유 SQL
금지·core 최소 변경 원칙). graph tool 의 hop 깊이는 결정적으로 도출:
- ``find_paths(max_hops=N)``  → N (clamp 1~5, 템플릿 ``find_paths_{N}hops``)
- ``get_subgraph(depth=N)``   → N (clamp 1~3, 템플릿 ``get_subgraph_d{N}``)
- 그 외 graph 호출            → intent 명의 ``_Nhops`` / ``_dN`` 파싱, 없으면 1
- 비-graph tool (sql/research/calculator) → 0 hop

tracing.py(Langfuse) + api/main.py(PG chat.messages.agent_trace) 가 turn END 에
``hop_count`` + ``tool_sequence`` 로 기록한다.
"""

from __future__ import annotations

import re
from typing import Any

_HOPS_RE = re.compile(r"_(\d+)hops?\b")
_DEPTH_RE = re.compile(r"_d(\d+)\b")
# graph tool 식별 — agent 가 'graph' 아닌 경우의 백업 휴리스틱.
_GRAPH_HINT_RE = re.compile(r"(hop|subgraph|path|chain|graph|neighbor|traverse)", re.I)
_MAX_TOOL_SEQ = 50          # metadata 비대화 방지 캡


def _clamp(v: Any, lo: int, hi: int) -> int:
    try:
        return max(lo, min(int(v), hi))
    except (TypeError, ValueError):
        return lo


def _is_graph(entry: dict) -> bool:
    if entry.get("agent") == "graph":
        return True
    return bool(_GRAPH_HINT_RE.search(str(entry.get("tool") or "")))


def _hops_for(entry: dict) -> int:
    """단일 tool_result 의 cypher hop 깊이. 비-graph 는 0."""
    if not _is_graph(entry):
        return 0
    args = entry.get("args")
    if isinstance(args, dict):
        if args.get("max_hops") is not None:
            return _clamp(args["max_hops"], 1, 5)
        if args.get("depth") is not None:
            return _clamp(args["depth"], 1, 3)
        if args.get("radius") is not None:
            return _clamp(args["radius"], 1, 5)
    tool = str(entry.get("tool") or "")
    m = _HOPS_RE.search(tool) or _DEPTH_RE.search(tool)
    if m:
        return int(m.group(1))
    return 1   # 단일 graph traversal 기본 1 hop


def _tool_results(src: Any) -> list[dict]:
    """state dict 또는 tool_results list 어느 쪽이든 받아 list[dict] 반환."""
    if isinstance(src, dict):
        tr = src.get("tool_results")
    else:
        tr = src
    return [e for e in (tr or []) if isinstance(e, dict)]


def tool_call_sequence(src: Any) -> list[str]:
    """turn 의 tool 호출 순서 (intent 명 리스트). 캡 적용."""
    seq = [str(e.get("tool") or e.get("intent") or "?") for e in _tool_results(src)]
    return seq[:_MAX_TOOL_SEQ]


def cypher_hop_count(src: Any) -> dict[str, Any]:
    """graph 호출들의 hop 깊이 집계."""
    entries = _tool_results(src)
    per = [(_str_tool(e), _hops_for(e)) for e in entries]
    graph_hops = [h for _, h in per if h > 0]
    return {
        "total_hops":    sum(graph_hops),
        "max_hop_depth": max(graph_hops) if graph_hops else 0,
        "n_graph_calls": len(graph_hops),
        "per_call":      [{"tool": t, "hops": h} for t, h in per if h > 0],
    }


def _str_tool(e: dict) -> str:
    return str(e.get("tool") or e.get("intent") or "?")


_VARLEN_RANGE_RE = re.compile(r"\*\s*\d*\s*\.\.\s*(\d+)")   # [:REL*1..3] → 3
_VARLEN_EXACT_RE = re.compile(r"\*\s*(\d+)(?!\s*\.)")        # [:REL*3]   → 3
_REL_RE = re.compile(r"-\s*\[")                              # 고정 관계 세그먼트


def hops_from_cypher(cypher: str | None) -> int:
    """cypher 문자열에서 hop 깊이 추정 (eval adapter 가 cypher 만 노출하는 경로용).

    가변 길이 패턴(``*1..3`` / ``*3``)이 있으면 그 상한, 없으면 고정 관계 세그먼트
    (``-[``) 개수. 결정적 휴리스틱 — evidence-count 프록시보다 직접적.
    """
    if not cypher or not isinstance(cypher, str):
        return 0
    var = [int(x) for x in _VARLEN_RANGE_RE.findall(cypher)]
    var += [int(x) for x in _VARLEN_EXACT_RE.findall(cypher)]
    if var:
        return max(var)
    return len(_REL_RE.findall(cypher))


def trace_hop_summary(src: Any) -> dict[str, Any]:
    """turn trace 임베딩용 요약 — hop_count(total) + 깊이 + tool sequence."""
    hops = cypher_hop_count(src)
    return {
        "hop_count":     hops["total_hops"],
        "max_hop_depth": hops["max_hop_depth"],
        "n_graph_calls": hops["n_graph_calls"],
        "tool_sequence": tool_call_sequence(src),
    }


__all__ = [
    "tool_call_sequence",
    "cypher_hop_count",
    "trace_hop_summary",
    "hops_from_cypher",
]
