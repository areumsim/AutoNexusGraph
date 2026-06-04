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
from autonexusgraph.agents.dag import make_task
from autonexusgraph.agents.nodes import (
    _build_context,
    planner_node,
    synthesizer_node,
    triage_node,
)
from autonexusgraph.agents.supervisor import supervisor_node
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
