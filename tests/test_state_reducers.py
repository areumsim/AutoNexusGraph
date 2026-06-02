"""state.py reducer 회귀 — _last_wins / _list_extend / _list_concat / _dict_merge."""

from __future__ import annotations

from autonexusgraph.agents.state import (
    _dict_merge,
    _last_wins,
    _list_concat,
    _list_extend,
)


# ── _last_wins (legacy) ──────────────────────────────────────
def test_last_wins_takes_new():
    assert _last_wins("old", "new") == "new"
    assert _last_wins([1, 2], [3, 4]) == [3, 4]
    assert _last_wins({"a": 1}, {"b": 2}) == {"b": 2}


def test_last_wins_none_keeps_old():
    """new=None 인 worker partial return 보호."""
    assert _last_wins("old", None) == "old"
    assert _last_wins([1, 2], None) == [1, 2]


# ── _list_extend (M2 fix — safety_signals 누적) ──────────────
def test_list_extend_concatenates_unique():
    assert _list_extend(["a"], ["b"]) == ["a", "b"]
    assert _list_extend(["a", "b"], ["c", "d"]) == ["a", "b", "c", "d"]


def test_list_extend_dedupe_preserves_old_order():
    # 중복 회피 — old 우선순서 보존.
    assert _list_extend(["a", "b"], ["b", "c"]) == ["a", "b", "c"]
    assert _list_extend(["x"], ["x", "y", "x"]) == ["x", "y"]


def test_list_extend_handles_none():
    assert _list_extend(None, ["a"]) == ["a"]
    assert _list_extend(["a"], None) == ["a"]
    assert _list_extend(None, None) == []


def test_list_extend_empty_lists():
    assert _list_extend([], ["a"]) == ["a"]
    assert _list_extend(["a"], []) == ["a"]
    assert _list_extend([], []) == []


def test_list_extend_concurrent_worker_no_loss():
    """병렬 worker A/B 각자 다른 신호 적재 — fan-in 시 둘 다 보존 (M2 fix 핵심)."""
    worker_a_signals = ["finance_plan_failed:KeyError"]
    worker_b_signals = ["cost_approval_auto_passed:$0.5000"]
    merged = _list_extend(worker_a_signals, worker_b_signals)
    assert "finance_plan_failed:KeyError" in merged
    assert "cost_approval_auto_passed:$0.5000" in merged
    assert len(merged) == 2


def test_list_extend_falls_back_to_last_wins_for_non_list():
    # 비-list 충돌 시 last_wins 동등 (방어 코드).
    assert _list_extend("old", "new") == "new"
    assert _list_extend({"a": 1}, "new") == "new"


def test_list_extend_string_with_none_does_not_decompose():
    """N1 fix — string 을 list 로 분해하지 않음. None 처리에 isinstance 가드."""
    # 이전 버그: list("old") → ['o','l','d']. 신규: 비-list 면 [] 반환.
    assert _list_extend("old", None) == []
    assert _list_extend(None, "new") == []


def test_list_extend_dict_with_none_does_not_decompose():
    """dict 도 비-list — N1 fix 가 list 로 분해 회피."""
    assert _list_extend({"a": 1}, None) == []
    assert _list_extend(None, {"b": 2}) == []


# ── _list_concat (M2 잔존 fix — evidence_chunks / tool_results) ───
def test_list_concat_preserves_both_sides_no_dedupe():
    # dict 요소 list — dedupe 안 함, 양쪽 모두 유지.
    a = [{"chunk_id": 1, "text": "..."}]
    b = [{"chunk_id": 2, "text": "..."}]
    merged = _list_concat(a, b)
    assert merged == [{"chunk_id": 1, "text": "..."}, {"chunk_id": 2, "text": "..."}]
    assert len(merged) == 2


def test_list_concat_duplicates_allowed():
    """dict unhashable → set dedupe 불가. 같은 dict 가 두 워커에서 적재되면 양쪽 유지."""
    chunk = {"id": 1}
    merged = _list_concat([chunk], [chunk])
    assert len(merged) == 2


def test_list_concat_none_handling():
    assert _list_concat(None, [{"a": 1}]) == [{"a": 1}]
    assert _list_concat([{"a": 1}], None) == [{"a": 1}]
    assert _list_concat(None, None) == []


def test_list_concat_non_list_falls_back():
    assert _list_concat("x", "y") == "y"


def test_list_concat_multi_worker_evidence():
    """research_worker + graph_worker concurrent evidence 적재 — fan-in 시 둘 다 보존."""
    research_ev = [{"chunk_id": "r1", "score": 0.9}]
    graph_ev = [{"chunk_id": "g1", "score": 0.85}]
    merged = _list_concat(research_ev, graph_ev)
    chunk_ids = {c["chunk_id"] for c in merged}
    assert chunk_ids == {"r1", "g1"}


# ── _dict_merge (M2 잔존 fix — task_results) ─────────────────────
def test_dict_merge_combines_keys():
    a = {"task_1": {"status": "done", "result": "A"}}
    b = {"task_2": {"status": "done", "result": "B"}}
    merged = _dict_merge(a, b)
    assert merged == {
        "task_1": {"status": "done", "result": "A"},
        "task_2": {"status": "done", "result": "B"},
    }


def test_dict_merge_new_overrides_same_key():
    """같은 task_id 재실행 시 새 결과 채택 (예: replan)."""
    a = {"task_1": {"status": "failed"}}
    b = {"task_1": {"status": "done", "result": "X"}}
    assert _dict_merge(a, b) == {"task_1": {"status": "done", "result": "X"}}


def test_dict_merge_none_handling():
    assert _dict_merge(None, {"a": 1}) == {"a": 1}
    assert _dict_merge({"a": 1}, None) == {"a": 1}
    assert _dict_merge(None, None) == {}


def test_dict_merge_non_dict_falls_back():
    assert _dict_merge("x", "y") == "y"


def test_dict_merge_does_not_mutate_inputs():
    """immutability — old 입력이 변경되지 않아야 (LangGraph state 보존)."""
    a = {"t1": "A"}
    b = {"t2": "B"}
    _ = _dict_merge(a, b)
    assert a == {"t1": "A"}
    assert b == {"t2": "B"}
