"""축2 LLM 자율 planner — 화이트리스트 검증·폴백·안전가드 테스트.

LLM 은 mock. 검증 대상: (1) 자율 task DAG 산출 (2) 화이트리스트 강제(자유 cypher/SQL
금지) (3) 실패/비활성/빈결과/순환 시 룰 폴백 (4) planner_node 통합 토글.
"""

from __future__ import annotations

from unittest.mock import patch

from autonexusgraph.agents.llm_planner import try_llm_plan
from autonexusgraph.agents.nodes import planner_node


class _FakeJSONClient:
    model = "fake"

    def __init__(self, payload):
        self._payload = payload

    def chat_json(self, messages, schema, **kw):
        return self._payload


def _run_planner(payload, **state_extra):
    state = {"domain": "finance", "question": "q", "question_rewritten": "q",
             "llm_usage_usd": 0.0}
    state.update(state_extra)
    with patch("autonexusgraph.llm.base.get_llm_client",
               return_value=_FakeJSONClient(payload)), \
         patch("autonexusgraph.llm.budget_aware.budget_aware_client",
               side_effect=lambda c, **kw: c), \
         patch("autonexusgraph.config.turn_budget_for_domain", return_value=100.0):
        return try_llm_plan(state, kind="multi_hop", targets=["00126380"],
                            year_hint=2023, q="q"), state


# ── 자율 plan 산출 ──────────────────────────────────────────
def test_llm_plan_valid_dag_with_dependency():
    tasks, _ = _run_planner({"tasks": [
        {"id": "g1", "agent": "graph", "intent": "list_subsidiaries",
         "args": {"parent_corp_code": "00126380"}},
        {"id": "s1", "agent": "sql", "intent": "get_revenue",
         "args": {"corp_code": "00126380", "year": 2023}, "depends_on": ["g1"]},
    ]})
    assert [(t["agent"], t["intent"]) for t in tasks] == \
        [("graph", "list_subsidiaries"), ("sql", "get_revenue")]
    assert tasks[1]["depends_on"] == ["g1"]


# ── 화이트리스트 강제 (안전 게이트) ─────────────────────────
def test_llm_plan_drops_non_whitelisted_intent():
    """자유 cypher/SQL 금지 — 화이트리스트 밖 intent 는 drop + signal."""
    tasks, state = _run_planner({"tasks": [
        {"agent": "graph", "intent": "DROP_DATABASE", "args": {}},
        {"agent": "sql", "intent": "get_revenue",
         "args": {"corp_code": "00126380", "year": 2023}},
    ]})
    assert [t["intent"] for t in tasks] == ["get_revenue"]
    assert any("llm_planner_dropped" in s for s in state.get("safety_signals", []))


# ── 폴백 (None 반환 → 호출부가 룰 사용) ─────────────────────
def test_llm_plan_empty_falls_back():
    tasks, _ = _run_planner({"tasks": []})
    assert tasks is None


def test_llm_plan_all_invalid_falls_back():
    tasks, _ = _run_planner({"tasks": [{"agent": "bogus", "intent": "x"}]})
    assert tasks is None


def test_llm_plan_cycle_falls_back():
    tasks, state = _run_planner({"tasks": [
        {"id": "a", "agent": "sql", "intent": "get_revenue", "args": {},
         "depends_on": ["b"]},
        {"id": "b", "agent": "sql", "intent": "get_revenue", "args": {},
         "depends_on": ["a"]},
    ]})
    assert tasks is None
    assert any("llm_planner_cycle" in s for s in state.get("safety_signals", []))


def test_llm_plan_strips_orphan_dependency():
    tasks, _ = _run_planner({"tasks": [
        {"id": "s1", "agent": "sql", "intent": "get_revenue", "args": {},
         "depends_on": ["ghost"]},
    ]})
    assert tasks[0]["depends_on"] == []


class _CaptureClient:
    """user_msg 캡처용 — chat_json 메시지를 보관."""
    model = "fake"

    def __init__(self):
        self.last_user = ""

    def chat_json(self, messages, schema, **kw):
        self.last_user = next((m["content"] for m in messages if m["role"] == "user"), "")
        return {"tasks": []}


def _capture_prompt(q):
    cap = _CaptureClient()
    state = {"domain": "finance", "question": q, "question_rewritten": q, "llm_usage_usd": 0.0}
    with patch("autonexusgraph.llm.base.get_llm_client", return_value=cap), \
         patch("autonexusgraph.llm.budget_aware.budget_aware_client",
               side_effect=lambda c, **kw: c), \
         patch("autonexusgraph.config.turn_budget_for_domain", return_value=100.0):
        try_llm_plan(state, kind="ranking", targets=[], year_hint=2023, q=q, persons=["김영규"])
    return cap.last_user


def test_ranking_hint_only_on_ranking_questions():
    """수치 랭킹 힌트는 랭킹 키워드 질문에만 — 비-랭킹(GMH/GMI)엔 미노출(main 회귀 방지)."""
    # 'compare_companies' 는 SQL intent 카탈로그에 항상 등장 → 힌트 마커('수치 랭킹')로 게이팅 검증.
    rank_q = "김영규이 임원으로 재직하는 회사 중 2023년 매출이 가장 큰 회사는?"
    plain_q = "김영규이 임원으로 재직하는 회사의 자회사는 무엇인가?"
    rank_prompt = _capture_prompt(rank_q)
    assert "수치 랭킹" in rank_prompt                       # 랭킹 → 힌트 노출
    assert "collect" in rank_prompt                          # collect 바인딩 지침 포함
    assert "수치 랭킹" not in _capture_prompt(plain_q)       # 비-랭킹 → 미노출(main 회귀 방지)


def test_related_companies_hint_only_on_associate_questions():
    """관계기업·공동기업 힌트는 관계 키워드 질문에만 — 자회사(GMH) 질문엔 미노출."""
    # 'list_related_companies' 는 graph intent 카탈로그에 항상 등장 → 힌트 마커('[관계기업·공동기업]')로 검증.
    rel_q = "엘지디스플레이가 유의적인 영향력을 가지고 있는 피투자회사는 누구인가?"
    sub_q = "KCS의 모회사에서 임원으로 재직하는 사람은 누구인가?"
    assert "[관계기업·공동기업]" in _capture_prompt(rel_q)       # 관계기업 → 힌트 노출
    assert "[관계기업·공동기업]" not in _capture_prompt(sub_q)   # 비-관계기업 → 미노출


def test_llm_plan_budget_guard():
    """예산 초과 시 LLM 호출 없이 None (룰 폴백)."""
    def _boom(*a, **k):
        raise AssertionError("예산 초과인데 LLM 호출됨")
    state = {"domain": "finance", "question": "q", "question_rewritten": "q",
             "llm_usage_usd": 10 ** 9}
    with patch("autonexusgraph.llm.base.get_llm_client", _boom), \
         patch("autonexusgraph.config.turn_budget_for_domain", return_value=0.20):
        assert try_llm_plan(state, kind="factual", targets=["00126380"],
                            year_hint=2023, q="q") is None


# ── planner_node 통합 토글 ──────────────────────────────────
_BASE = dict(domain="finance", question="삼성 분석", question_rewritten="삼성 분석",
             question_kind="narrative", target_companies=["00126380"],
             llm_usage_usd=0.0, n_replans=0, interrupt_handled=True)


def test_planner_uses_llm_when_enabled():
    payload = {"tasks": [
        {"id": "g1", "agent": "graph", "intent": "list_subsidiaries",
         "args": {"parent_corp_code": "00126380"}},
        {"id": "r1", "agent": "research", "intent": "search_documents",
         "args": {"query": "q", "top_k": 6}, "depends_on": ["g1"]},
    ]}
    with patch("autonexusgraph.agents.nodes._llm_planner_enabled", return_value=True), \
         patch("autonexusgraph.llm.base.get_llm_client",
               return_value=_FakeJSONClient(payload)), \
         patch("autonexusgraph.llm.budget_aware.budget_aware_client",
               side_effect=lambda c, **kw: c), \
         patch("autonexusgraph.config.turn_budget_for_domain", return_value=100.0):
        state = dict(_BASE)
        planner_node(state)
    assert [(t["agent"], t["intent"]) for t in state["tasks"]] == \
        [("graph", "list_subsidiaries"), ("research", "search_documents")]
    # _spawn 아닌 legacy plan 도 채워짐.
    assert state["plan"] and all(p["tool"] for p in state["plan"])


def test_planner_falls_back_to_rules_when_disabled():
    """기본(flag off) — 룰 planner 동작, LLM 미호출."""
    def _boom(*a, **k):
        raise AssertionError("flag off 인데 LLM 호출됨")
    with patch("autonexusgraph.agents.nodes._llm_planner_enabled", return_value=False), \
         patch("autonexusgraph.llm.base.get_llm_client", _boom):
        state = dict(_BASE)
        planner_node(state)
    assert state["tasks"] and all(t["agent"] == "research" for t in state["tasks"])


def test_planner_llm_failure_falls_back_to_rules():
    """LLM 예외 → fail-soft → 룰 planner 로 답을 만든다(턴 안 죽음)."""
    class _BoomClient:
        model = "fake"
        def chat_json(self, *a, **k):
            raise RuntimeError("LLM down")
    with patch("autonexusgraph.agents.nodes._llm_planner_enabled", return_value=True), \
         patch("autonexusgraph.llm.base.get_llm_client", return_value=_BoomClient()), \
         patch("autonexusgraph.llm.budget_aware.budget_aware_client",
               side_effect=lambda c, **kw: c), \
         patch("autonexusgraph.config.turn_budget_for_domain", return_value=100.0):
        state = dict(_BASE)
        planner_node(state)
    assert state["tasks"]   # 룰 폴백으로 task 생성됨


def test_config_flag_default_off():
    """안전 기본값 — agent_llm_planner 기본 False."""
    from autonexusgraph.config import Settings
    assert Settings().agent_llm_planner is False
