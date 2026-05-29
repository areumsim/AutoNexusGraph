"""synthesizer_node 의 LLM 실패 진단 — silent skip 방지 회귀 테스트.

배경: 이전엔 LLM_API_KEY 가 빈 값이면 synthesizer 의 ``except Exception`` 이
LLMError 를 swallow 하고 결정적 brief 로 답을 만들어 silent fallback. cost=$0,
tokens=0 으로 보고되지만 그 원인이 어디에도 명시 안 됨 → eval/QA 측정 결과의
신뢰성 문제.

수정: synth_status dict 에 (ok, llm_called, fallback_used, error_type, error)
구조화 보존. hybrid_adapter 가 AgentResponse.diagnostics 로 전파.

본 테스트는 silent skip 이 다시 들어오지 못하게 한다 (회귀 게이트).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _state_with_evidence():
    return {
        "question": "삼성전자 매출은?",
        "question_kind": "factual",
        "domain": "finance",
        "target_companies": ["00126380"],
        "tool_results": [
            {"tool": "get_revenue", "purpose": "factual:rev",
             "args": {}, "result": {"value": 300_000_000_000_000}},
        ],
        "evidence_chunks": [],
        "tasks": [], "task_results": {},
        "llm_usage_usd": 0.0,
        "n_replans": 0,
    }


# ── 1. LLM client 가 LLMError 면 synth_status.ok=False + error_type 명시 ──
def test_synth_records_llm_failure_in_status(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")          # 빈 키 — provider 가 raise
    monkeypatch.setenv("LLM_COST_AUTO_APPROVE_USD", "100.00")
    from autonexusgraph import config
    config.get_settings.cache_clear()              # type: ignore[attr-defined]

    from autonexusgraph.agents.nodes import synthesizer_node
    state = _state_with_evidence()
    out = synthesizer_node(state)

    assert "synth_status" in out, "synthesizer 가 synth_status 를 기록해야"
    status = out["synth_status"]
    # LLM 호출 0 + fallback 명시.
    assert status["ok"] is False
    assert status["llm_called"] is False
    assert status["fallback_used"] == "exception"
    # error_type 이 LLMError (또는 그 하위) — silent skip 방지의 본질.
    assert status["error_type"], "error_type 이 비어있으면 안 됨 — silent skip 회귀"
    # 답은 만들어진다 (eval 진행 보장 — fail-soft 유지).
    assert out.get("answer"), "답이 비어있으면 eval 이 모든 게 0 으로 측정됨"


# ── 2. 정상 호출 (LLM mock) 시 synth_status.ok=True ─────────────────
def test_synth_records_success_when_llm_works(monkeypatch):
    monkeypatch.setenv("LLM_COST_AUTO_APPROVE_USD", "100.00")

    class _FakeUsage:
        cost_usd = 0.005
        total_tokens = 250

    class _FakeResp:
        content = "삼성전자 2024년 매출은 약 300조원입니다. [출처: 00126380]"
        usage = _FakeUsage()

    class _FakeClient:
        model = "fake-model"
        def chat(self, *a, **kw): return _FakeResp()
        def chat_stream(self, *a, **kw): yield "x"
        def chat_json(self, *a, **kw): return {}

    with patch("autonexusgraph.llm.base.get_llm_client", return_value=_FakeClient()), \
         patch("autonexusgraph.llm.budget_aware.budget_aware_client",
               side_effect=lambda c, **kw: c):
        from autonexusgraph.agents.nodes import synthesizer_node
        state = _state_with_evidence()
        out = synthesizer_node(state)

    status = out["synth_status"]
    assert status["ok"] is True
    assert status["llm_called"] is True
    assert status["fallback_used"] is None
    assert status["error_type"] is None
    assert out.get("llm_usage_usd", 0.0) > 0.0, "cost 누적 안 됨"
    assert out.get("llm_tokens_used", 0) >= 250, "tokens 누적 안 됨"


# ── 3. budget exceeded 분기 — fallback_used='budget' ────────────────
def test_synth_records_budget_exceeded(monkeypatch):
    monkeypatch.setenv("LLM_COST_AUTO_APPROVE_USD", "100.00")

    from autonexusgraph.llm.cost_tracker import BudgetExceeded

    class _RaisingClient:
        model = "x"
        def chat(self, *a, **kw): raise BudgetExceeded("over $1")
        def chat_stream(self, *a, **kw): yield "x"
        def chat_json(self, *a, **kw): return {}

    with patch("autonexusgraph.llm.base.get_llm_client", return_value=_RaisingClient()), \
         patch("autonexusgraph.llm.budget_aware.budget_aware_client",
               side_effect=lambda c, **kw: c):
        from autonexusgraph.agents.nodes import synthesizer_node
        state = _state_with_evidence()
        out = synthesizer_node(state)

    status = out["synth_status"]
    assert status["ok"] is False
    assert status["llm_called"] is False
    assert status["fallback_used"] == "budget"
    assert status["error_type"] == "BudgetExceeded"
    assert out.get("aborted_reason") == "synth_budget"


# ── 4. hybrid_adapter 가 synth_status 를 diagnostics 로 전파 ──────────
def test_hybrid_adapter_propagates_synth_status_to_diagnostics():
    fake_state = {
        "question": "X", "answer": "deterministic brief",
        "question_kind": "factual",
        "synth_status": {
            "ok": False, "error_type": "LLMError",
            "error": "OPENAI api key 미설정",
            "llm_called": False, "fallback_used": "exception",
        },
        "llm_usage_usd": 0.0,
        "llm_tokens_used": 0,
        "target_companies": ["00126380"],
        "domain": "finance",
        "tool_results": [],
        "citations": [],
        "safety_signals": [],
    }
    with patch("autonexusgraph.agents.run_agent", return_value=fake_state):
        from eval.adapters.hybrid_adapter import HybridAdapter
        resp = HybridAdapter().query("X", domain="finance")

    d = resp.diagnostics
    assert d["synth_ok"] is False
    assert d["synth_llm_called"] is False
    assert d["synth_fallback_used"] == "exception"
    assert d["synth_error_type"] == "LLMError"
    assert resp.cost_usd == 0.0
    assert resp.tokens_used == 0


def test_hybrid_adapter_propagates_success_diagnostics():
    fake_state = {
        "question": "X", "answer": "real LLM answer",
        "question_kind": "factual",
        "synth_status": {
            "ok": True, "error_type": None, "error": None,
            "llm_called": True, "fallback_used": None,
        },
        "llm_usage_usd": 0.0075,
        "llm_tokens_used": 320,
        "target_companies": ["00126380"],
        "domain": "finance",
        "tool_results": [{"tool": "get_revenue"}],
        "citations": [],
    }
    with patch("autonexusgraph.agents.run_agent", return_value=fake_state):
        from eval.adapters.hybrid_adapter import HybridAdapter
        resp = HybridAdapter().query("X", domain="finance")

    assert resp.diagnostics["synth_ok"] is True
    assert resp.diagnostics["synth_llm_called"] is True
    assert resp.cost_usd > 0.0
    assert resp.tokens_used == 320
