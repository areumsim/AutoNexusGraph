"""에이전트 시나리오 테스트 — "자율 루프가 닫히는가" 행동 검증 (진단 7축 후속).

각 시나리오는 LLM·DB 없이 실제 노드(planner/supervisor/validator/synthesizer/triage)를
구동하고 도구 I/O 만 mock 한다. 검증 대상은 이번 라운드에 보강한 에이전트성:
  (b) result-aware replan   — 2차 계획 ≠ 1차 (실패 반영)
  (a) open→closed loop      — graph 결과가 sql args 로 흐름 (depends_on 실질화)
  (c) memory→행동           — 세션/history 가 synth 프롬프트에 주입
  (d) 빈결과 회복            — DAG/worker 경로도 fallback 검색으로 회복

추가로 멀티홉 상태 일관성·clarification·예산초과 부분답변을 포함.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest

pytest.importorskip("numexpr", reason="calculator worker 가 numexpr 의존")

import autonexusgraph.tools as toolbox
from autonexusgraph.agents import session
from autonexusgraph.agents.dag import make_spawn_task, make_task
from autonexusgraph.agents.nodes import (
    _build_context,
    planner_node,
    synthesizer_node,
    triage_node,
)
from autonexusgraph.agents.supervisor import (
    MAX_DYNAMIC_TASKS,
    mid_execution_reflect,
    supervisor_node,
)
from autonexusgraph.agents.validator import mark_replan


# ── 공통 fake LLM ───────────────────────────────────────────
class _FakeUsage:
    cost_usd = 0.004
    total_tokens = 200


class _FakeResp:
    def __init__(self, content: str):
        self.content = content
        self.usage = _FakeUsage()


class _FakeClient:
    model = "fake-model"

    def __init__(self, content: str):
        self._content = content

    def chat(self, *a, **kw):
        return _FakeResp(self._content)


@contextmanager
def fake_llm(content: str = "충분히 긴 한국어 답변입니다. 근거 본문에 기반합니다. [출처: 00126380]"):
    with patch("autonexusgraph.llm.base.get_llm_client",
               return_value=_FakeClient(content)), \
         patch("autonexusgraph.llm.budget_aware.budget_aware_client",
               side_effect=lambda c, **kw: c), \
         patch("autonexusgraph.config.turn_budget_for_domain", return_value=100.0):
        yield


def _base_state(**extra):
    s = {"question": "q", "question_rewritten": "q", "tasks": [], "task_results": {},
         "llm_usage_usd": 0.0, "n_replans": 0, "domain": "finance",
         "interrupt_handled": True}   # cost-approval 게이트 skip
    s.update(extra)
    return s


# ── 시나리오 1: 단순 1-hop (factual) ────────────────────────
def test_s1_single_hop_factual():
    """factual → sql 단발. 실제 planner+supervisor, 도구만 mock."""
    state = _base_state(question="삼성전자 2023년 매출",
                        question_rewritten="삼성전자 2023년 매출",
                        question_kind="factual", target_companies=["00126380"])
    planner_node(state)
    intents = [t["intent"] for t in state["tasks"]]
    assert "get_revenue" in intents and "get_operating_income" in intents
    with patch.object(toolbox, "get_revenue",
                      lambda **kw: {"value": 258_000_000_000_000}, create=True), \
         patch.object(toolbox, "get_operating_income",
                      lambda **kw: {"value": 6_000_000_000_000}, create=True):
        supervisor_node(state)
    assert all(t["status"] == "done" for t in state["tasks"])


# ── 시나리오 2: 도메인내 멀티홉 + closed-loop (a) ───────────
def test_s2_multihop_closed_loop_data_flow():
    """multi_hop: graph list_subsidiaries → sql compare_companies(corp_codes=graph 결과)."""
    state = _base_state(question="삼성전자 자회사들의 매출 비교 2023",
                        question_rewritten="삼성전자 자회사들의 매출 비교 2023",
                        question_kind="multi_hop", target_companies=["00126380"])
    planner_node(state)
    intents = [t["intent"] for t in state["tasks"]]
    assert "list_subsidiaries" in intents
    assert "compare_companies" in intents   # closed-loop 비교 task 추가됨

    seen = {}

    def fake_compare(corp_codes, year, metric="revenue", **kw):
        seen["corp_codes"] = list(corp_codes)
        return [{"corp_code": c, "value": 100} for c in corp_codes]

    with patch.object(toolbox, "list_subsidiaries",
                      lambda **kw: [{"child_corp_code": "00111111"},
                                    {"child_corp_code": "00222222"}], create=True), \
         patch.object(toolbox, "get_revenue", lambda **kw: {"value": 1}, create=True), \
         patch.object(toolbox, "compare_companies", fake_compare, create=True), \
         patch("autonexusgraph.tools.retrieve.search_documents", lambda **kw: []):
        supervisor_node(state)

    # graph 가 발견한 자회사 corp_code 가 sql args 로 실제 흘렀다 (depends_on 실질화).
    assert seen.get("corp_codes") == ["00111111", "00222222"]


# ── 시나리오 3: 다단계(3-hop) 의존 체인 상태 일관성 ──────────
def test_s3_multistep_coherence_dependency_chain():
    """graph → sql → calculator 3-hop 의존 체인. 각 hop 결과가 다음 hop args 로 전달."""
    tasks = [
        make_task("g1", "graph", "list_subsidiaries",
                  {"parent_corp_code": "00126380", "limit": 10}),
        make_task("s1", "sql", "compare_companies",
                  {"corp_codes": {"$from": "g1", "field": "child_corp_code",
                                  "collect": True}, "year": 2023},
                  depends_on=["g1"]),
        make_task("c1", "calculator", "aggregate",
                  {"aggregate": "sum",
                   "over": {"$from": "s1", "field": "value", "collect": True}},
                  depends_on=["s1"]),
    ]
    state = _base_state(tasks=tasks)
    with patch.object(toolbox, "list_subsidiaries",
                      lambda **kw: [{"child_corp_code": "A"}, {"child_corp_code": "B"}],
                      create=True), \
         patch.object(toolbox, "compare_companies",
                      lambda corp_codes, year, **kw: [{"value": 10}, {"value": 20}],
                      create=True):
        supervisor_node(state)
    # 3-hop 끝까지 상태 유지 — calculator 가 sql 결과(10+20)를 집계.
    assert state["task_results"]["c1"]["value"] == 30.0
    assert all(t["status"] == "done" for t in tasks)


# ── 시나리오 4: 도구 일부러 실패 → 빈결과 회복 (d) ──────────
def test_s4_empty_results_recovery():
    """모든 worker 빈결과 → synthesizer 가 fallback 검색으로 evidence 회복."""
    state = _base_state(
        question="모호한 질의", question_rewritten="모호한 질의",
        question_kind="unknown", target_companies=["00126380"],
        tool_results=[{"tool": "get_revenue", "result": None},
                      {"tool": "list_subsidiaries", "result": []}],
        evidence_chunks=[],
    )
    with patch.object(toolbox, "search_documents",
                      lambda **kw: [{"id": "c1", "text": "회복된 본문 근거 다수"}],
                      create=True), \
         fake_llm("회복된 근거를 바탕으로 한 충분히 긴 한국어 답변입니다. [출처: 00126380]"):
        synthesizer_node(state)
    assert state.get("fallback_used") is True
    assert state.get("evidence_chunks")          # 회복으로 evidence 확보
    assert state["synth_status"]["ok"] is True   # 회복 후 LLM 합성 성공


# ── 시나리오 5: 모호 회사명 → clarification (폴백 자동해소) ──
def test_s5_ambiguous_company_clarification():
    """모호 회사 → interrupt 미지원 환경에서 1순위 자동선택 + safety_signal 기록."""
    session.clear()
    hits = [{"corp_code": "00111111", "name": "삼성전자", "score": 0.80},
            {"corp_code": "00222222", "name": "삼성SDI", "score": 0.79}]

    def fake_lookup(query, limit=5):
        return hits if query == "삼성" else []

    state = _base_state(question="삼성", question_rewritten="삼성",
                        thread_id="t-s5")
    with patch("autonexusgraph.tools.financials.lookup_company", fake_lookup), \
         patch("autonexusgraph.safety.is_high_risk_injection", return_value=False):
        triage_node(state)
    # 폴백 환경 — 1순위 자동선택 + 흔적 기록, pending_interrupt 비움(오인 방지).
    assert "00111111" in (state.get("target_companies") or [])
    assert any("ambiguous_company_auto_resolved" in s
               for s in (state.get("safety_signals") or []))
    assert not state.get("pending_interrupt")
    session.clear()


# ── 시나리오 6: 예산 초과 → 부분(결정적 brief) 답변 ─────────
def test_s6_budget_exceeded_partial_answer():
    """turn_budget 초과 → LLM 비호출, 결정적 brief 로 부분답변."""
    state = _base_state(
        question="삼성전자 매출", aborted_reason="turn_budget",
        tool_results=[{"tool": "get_revenue", "purpose": "factual",
                       "args": {}, "result": {"value": 258_000_000_000_000}}],
        evidence_chunks=[],
    )
    synthesizer_node(state)   # LLM mock 불필요 — 조기 분기
    assert state["answer"]
    assert "결정적 brief" in state["answer"] or "한도" in state["answer"]
    assert state["grounding"]["ok"] is False
    assert "budget_exceeded" in state["grounding"]["warnings"]


# ── 시나리오 7: multi-turn 후속질문 → 기억 활용 (c) ─────────
def test_s7_multiturn_memory_carryover_and_injection():
    """이전 turn entity 가 carry-over 되고, synth 프롬프트에 대화 맥락 주입."""
    session.clear()
    session.update("t-s7", target_companies=["00126380"], last_year=2023)
    state = _base_state(
        question="그 중 가장 큰 곳은?", question_rewritten="그 중 가장 큰 곳은?",
        thread_id="t-s7",
        history=[{"role": "user", "content": "삼성과 현대 매출 알려줘"},
                 {"role": "assistant", "content": "삼성전자 2023년 매출은 258조..."}],
    )
    with patch("autonexusgraph.tools.financials.lookup_company", lambda q, limit=5: []), \
         patch("autonexusgraph.safety.is_high_risk_injection", return_value=False):
        triage_node(state)
    # 이번 turn 에 회사 식별 못 함 → 세션에서 carry-over.
    assert state.get("target_companies") == ["00126380"]
    assert state.get("session_carryover") is True
    # synth 컨텍스트에 이전 대화 + 세션 엔티티 주입.
    ctx = _build_context(state)
    assert "[이전 대화]" in ctx
    assert "companies=00126380" in ctx
    session.clear()


# ── 보너스: replan 이 result-aware 인가 (b) — 폐회로 핵심 증거 ─
def test_replan_is_result_aware_not_retry():
    """validator 실패 → mark_replan → planner 가 다른(승격된) 계획 생성. 동일계획 재시도 아님."""
    state = _base_state(question="삼성전자 2023년 매출",
                        question_rewritten="삼성전자 2023년 매출",
                        question_kind="factual", target_companies=["00126380"])
    planner_node(state)
    plan1 = sorted((t["agent"], t["intent"]) for t in state["tasks"])

    # grounding/짧은답변 실패 가정 → replan 컨텍스트 보존.
    state["validation_status"] = "failed"
    state["validation_issues"] = ["answer_too_short", "grounding:low_overlap"]
    state["grounding"] = {"ok": False, "warnings": ["low_overlap"]}
    mark_replan(state)
    assert state["replan_hint"]["prev_issues"]   # 실패 원인 보존됨

    planner_node(state)
    plan2 = sorted((t["agent"], t["intent"]) for t in state["tasks"])
    assert plan2 != plan1, "replan 이 동일 계획 재시도 — 폐회로 아님"
    # factual → multi_hop 승격으로 research evidence 추가 + retrieval 확대.
    assert state["question_kind"] == "multi_hop"
    assert any(t["agent"] == "research" for t in state["tasks"])
    rk = [t["args"].get("top_k") for t in state["tasks"] if t["agent"] == "research"]
    assert rk and rk[0] > 6   # widen 적용


# ── ReAct mid-execution replan (turn 내부 observe→act) ─────────
def _spawn_state(n_subs):
    """graph done + spawn 템플릿 — upstream 결과 n_subs 개 행."""
    g = make_task("g1", "graph", "list_subsidiaries", {})
    g["status"] = "done"
    sp = make_spawn_task("sp", "g1", "child_corp_code", "sql",
                         "get_operating_income", "corp_code", {"year": 2023})
    rows = [{"child_corp_code": f"{i:08d}"} for i in range(n_subs)]
    return {"tasks": [g, sp], "task_results": {"g1": rows},
            "llm_usage_usd": 0.0, "domain": "finance"}


def test_react_dynamic_fanout_through_supervisor():
    """graph 가 발견한 자회사 수만큼 supervisor 가 런타임에 task 생성·실행."""
    tasks = [
        make_task("g1", "graph", "list_subsidiaries", {"parent_corp_code": "00126380"}),
        make_spawn_task("sp", "g1", "child_corp_code", "sql",
                        "get_operating_income", "corp_code", {"year": 2023}),
    ]
    state = _base_state(tasks=tasks)
    calls = []
    with patch.object(toolbox, "list_subsidiaries",
                      lambda **kw: [{"child_corp_code": "00111111"},
                                    {"child_corp_code": "00222222"}], create=True), \
         patch.object(toolbox, "get_operating_income",
                      lambda corp_code, year, **kw: calls.append(corp_code)
                      or {"value": 1}, create=True):
        supervisor_node(state)
    dyn = [t for t in state["tasks"] if t.get("_dynamic")]
    assert len(dyn) == 2                         # 정적 plan 엔 없던 task 가 런타임 생성
    assert sorted(calls) == ["00111111", "00222222"]
    assert all(t["status"] == "done" for t in dyn)


def test_react_fanout_respects_max_cap():
    """MAX_DYNAMIC_TASKS 초과분은 drop + safety_signal 기록 (silent 절단 금지)."""
    state = _spawn_state(MAX_DYNAMIC_TASKS + 5)
    mid_execution_reflect(state)
    dyn = [t for t in state["tasks"] if t.get("_dynamic")]
    assert len(dyn) == MAX_DYNAMIC_TASKS
    assert any("mid_replan_capped" in s for s in state.get("safety_signals", []))


def test_react_fanout_budget_guard():
    """예산 초과 시 spawn 중단 — 템플릿 skipped, child 0."""
    state = _spawn_state(3)
    state["llm_usage_usd"] = 10 ** 9
    mid_execution_reflect(state)
    sp = next(t for t in state["tasks"] if t["agent"] == "_spawn")
    assert sp["status"] == "skipped"
    assert not [t for t in state["tasks"] if t.get("_dynamic")]


def test_react_no_reexpansion():
    """동일 upstream 재확장 방지 — reflect 반복 호출에도 child 수 불변 (무한 fan-out 차단)."""
    state = _spawn_state(2)
    assert mid_execution_reflect(state) is True
    assert mid_execution_reflect(state) is False
    assert len([t for t in state["tasks"] if t.get("_dynamic")]) == 2


def test_multihop_plan_emits_spawn_template():
    """planner multi_hop 이 정적 plan 에 ReAct spawn 템플릿을 포함 (production 연결)."""
    state = _base_state(question="삼성전자 자회사들의 매출 비교 2023",
                        question_rewritten="삼성전자 자회사들의 매출 비교 2023",
                        question_kind="multi_hop", target_companies=["00126380"])
    planner_node(state)
    spawn = [t for t in state["tasks"] if t.get("agent") == "_spawn"]
    assert spawn, "multi_hop 이 spawn 템플릿을 내야 함"
    assert spawn[0]["spawn"]["intent"] == "get_operating_income"
    # _spawn 은 legacy plan(도구 직접호출 목록)에서 제외돼야 함.
    assert all("spawn" not in str(p.get("tool")) for p in state.get("plan") or [])


# ── 축6: 병렬 Send fan-in last-wins 손실 하드닝 ────────────────
def test_fanin_reducers_dedup_and_clear():
    """dedup-concat/merge reducer — 손실 0·pre-fork 중복 0·clear 마커 동작."""
    from autonexusgraph.agents.state import (
        _ClearedDict,
        _ClearedList,
        _concat_dedup_by,
        _merge_dict_dedup,
    )
    concat = _concat_dedup_by("id")
    e0 = [{"id": "c0"}]
    ch = concat(concat(concat(None, e0), e0 + [{"id": "cA"}]), e0 + [{"id": "cB"}])
    assert [c["id"] for c in ch] == ["c0", "cA", "cB"]   # 동시 worker 보존, pre-fork 1회

    md = _merge_dict_dedup
    ch = md(md({"g": 0}, {"g": 0, "a": 1}), {"g": 0, "b": 2})
    assert ch == {"g": 0, "a": 1, "b": 2}

    # clear 마커 → 교체(replan 비우기); 비-마커 빈 컬렉션 → merge(비기여 worker 보호)
    assert concat([{"id": "x"}], _ClearedList()) == []
    assert md({"a": 1}, _ClearedDict()) == {}
    assert concat([{"id": "x"}], []) == [{"id": "x"}]
    assert md({"a": 1}, {}) == {"a": 1}


def test_langgraph_parallel_fanin_no_loss():
    """실제 LangGraph StateGraph + Send 병렬 — 4 worker 결과 전부 보존(손실 0)."""
    pytest.importorskip("langgraph")
    from langgraph.graph import END, StateGraph
    from langgraph.types import Send

    from autonexusgraph.agents.state import AgentState

    def fan(state):
        return {}

    def route(state):
        return [Send("work", {**state, "_cur": i}) for i in range(4)]

    def work(state):
        i = state["_cur"]
        ev = list(state.get("evidence_chunks") or [])
        ev.append({"id": f"c{i}"})           # pre-fork 사본 + 자기 델타(legacy 패턴)
        tr = dict(state.get("task_results") or {})
        tr[f"w{i}"] = i
        return {"evidence_chunks": ev, "task_results": tr}

    g = StateGraph(AgentState)
    g.add_node("fan", fan)
    g.add_node("work", work)
    g.set_entry_point("fan")
    g.add_conditional_edges("fan", route, ["work"])
    g.add_edge("work", END)
    app = g.compile()

    out = app.invoke({"evidence_chunks": [{"id": "pre"}],
                      "task_results": {"seed": -1}, "question": "q"})
    assert sorted(c["id"] for c in out["evidence_chunks"]) == \
        ["c0", "c1", "c2", "c3", "pre"]      # 4 병렬 전부 + pre 1회(중복 0)
    assert out["task_results"] == {"seed": -1, "w0": 0, "w1": 1, "w2": 2, "w3": 3}
