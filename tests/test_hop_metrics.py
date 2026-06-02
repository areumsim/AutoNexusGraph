"""E-3 per-turn hop 메트릭 + main_hop_efficiency 실제 hop 경로 테스트."""

from __future__ import annotations

from autonexusgraph.agents import hop_metrics as hm


def _tr(tool, agent="graph", args=None, **extra):
    return {"tool": tool, "agent": agent, "args": args or {}, **extra}


# ── hop 도출 ─────────────────────────────────────────────────────────
def test_find_paths_uses_max_hops_clamped():
    assert hm._hops_for(_tr("find_paths", args={"max_hops": 3})) == 3
    assert hm._hops_for(_tr("find_paths", args={"max_hops": 99})) == 5   # clamp 5
    assert hm._hops_for(_tr("find_paths", args={"max_hops": 0})) == 1    # clamp 1


def test_get_subgraph_uses_depth_clamped():
    assert hm._hops_for(_tr("get_subgraph", args={"depth": 2})) == 2
    assert hm._hops_for(_tr("get_subgraph", args={"depth": 9})) == 3     # clamp 3


def test_name_parse_when_no_args():
    assert hm._hops_for(_tr("find_paths_4hops", args={})) == 4
    assert hm._hops_for(_tr("get_subgraph_d2", args={})) == 2


def test_graph_default_one_hop():
    assert hm._hops_for(_tr("auto_investigation_recall_chain", args={})) == 1


def test_non_graph_zero_hops():
    assert hm._hops_for(_tr("get_financials", agent="sql", args={"year": 2023})) == 0
    assert hm._hops_for(_tr("calculate", agent="calculator", args={})) == 0


def test_bad_args_fallback():
    assert hm._hops_for(_tr("find_paths", args={"max_hops": "x"})) == 1   # clamp lo on bad int


# ── 집계 ─────────────────────────────────────────────────────────────
def test_cypher_hop_count_aggregate():
    trs = [
        _tr("find_paths", args={"max_hops": 3}),
        _tr("get_subgraph", args={"depth": 2}),
        _tr("get_financials", agent="sql", args={}),
    ]
    out = hm.cypher_hop_count(trs)
    assert out["total_hops"] == 5
    assert out["max_hop_depth"] == 3
    assert out["n_graph_calls"] == 2
    assert len(out["per_call"]) == 2


def test_tool_call_sequence_order_and_cap():
    trs = [_tr(f"t{i}", agent="sql") for i in range(60)]
    seq = hm.tool_call_sequence(trs)
    assert seq[0] == "t0" and len(seq) == hm._MAX_TOOL_SEQ   # 50 cap


def test_trace_hop_summary_from_state():
    state = {"tool_results": [_tr("find_paths", args={"max_hops": 2}),
                              _tr("get_financials", agent="sql")]}
    s = hm.trace_hop_summary(state)
    assert s["hop_count"] == 2 and s["max_hop_depth"] == 2 and s["n_graph_calls"] == 1
    assert s["tool_sequence"] == ["find_paths", "get_financials"]


def test_summary_handles_non_dict_and_empty():
    assert hm.trace_hop_summary(None)["hop_count"] == 0
    assert hm.trace_hop_summary({})["tool_sequence"] == []


# ── cypher 문자열 hop 도출 (eval adapter 경로) ──────────────────────
def test_hops_from_cypher_varlen_range():
    assert hm.hops_from_cypher("MATCH (a)-[:OWNS*1..3]->(b) RETURN b") == 3


def test_hops_from_cypher_varlen_exact():
    assert hm.hops_from_cypher("MATCH (a)-[:R*2]->(b) RETURN b") == 2


def test_hops_from_cypher_fixed_segments():
    cy = "MATCH (a)-[:X]->(b)-[:Y]->(c) RETURN c"
    assert hm.hops_from_cypher(cy) == 2


def test_hops_from_cypher_empty():
    assert hm.hops_from_cypher(None) == 0
    assert hm.hops_from_cypher("") == 0
    assert hm.hops_from_cypher("RETURN 1") == 0


# ── main_hop_efficiency 실제 hop 경로 ───────────────────────────────
def test_main_hop_efficiency_uses_true_hops():
    from eval.metrics.main_hop_efficiency import main_hop_efficiency

    rows = [
        {"adapter": "vector", "qid": "q1", "evidence": [1, 2, 3], "hop_count": 0},
        {"adapter": "hybrid", "qid": "q1", "evidence": [1, 2], "hop_count": 3},
    ]
    out = main_hop_efficiency(rows)
    assert out["vector"]["hop_avg"] == 0.0
    assert out["hybrid"]["hop_avg"] == 3.0
    # vector hop_avg=0 → hybrid_vs_vector_hops 미생성 (0 나눗셈 방지)
    assert "hybrid_vs_vector_hops" not in out

    rows2 = [
        {"adapter": "vector", "qid": "q1", "evidence": [1], "hop_count": 4},
        {"adapter": "hybrid", "qid": "q1", "evidence": [1], "hop_count": 2},
    ]
    out2 = main_hop_efficiency(rows2)
    hvv = out2["hybrid_vs_vector_hops"]
    assert hvv["ratio"] == 0.5 and hvv["target_met"] is True   # 2/4 = 0.5 ≤ 0.7
