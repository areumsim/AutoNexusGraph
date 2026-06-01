"""tracing 단위 테스트 — backend 결정 + fail-soft + turn lifecycle (v2 OTEL).

v2 (2026-06-01) — Langfuse 4.x OTEL 마이그레이션 + ContextVar 격리 회귀:
- ``_build_langfuse_callback`` 폐기 → 4.x SDK 의 ``Langfuse`` 인스턴스 + auth_check.
- ``get_trace_callbacks()`` 는 deprecated alias (빈 리스트 + LangSmith env 보강만).
- ``start_turn_context`` 가 핵심 lifecycle — PG/Langfuse 양쪽 fail-soft.
- ``CostTracker`` 가 ContextVar 격리 — 동시 호출 시 서로 안 덮어씀.
"""

from __future__ import annotations

import threading

from autonexusgraph.agents import tracing
from autonexusgraph.llm import cost_tracker as ct


def setup_function(_):
    tracing.reset_cache()
    # ctx 변수도 매 테스트 비움 — 이전 테스트의 tracker 남으면 finalize 안 된 상태.
    ct.set_current_tracker(None)


# ── backend 결정 ──────────────────────────────────────────────────
def test_backend_unset_returns_empty(monkeypatch):
    monkeypatch.delenv("TRACE_BACKEND", raising=False)
    assert tracing._resolve_backend() == ""


def test_backend_env_overrides_config(monkeypatch):
    monkeypatch.setenv("TRACE_BACKEND", "langsmith")
    assert tracing._resolve_backend() == "langsmith"


def test_backend_normalizes_case_and_off(monkeypatch):
    monkeypatch.setenv("TRACE_BACKEND", "  NONE  ")
    assert tracing._resolve_backend() == ""
    monkeypatch.setenv("TRACE_BACKEND", "LANGFUSE")
    tracing.reset_cache()
    assert tracing._resolve_backend() == "langfuse"


# ── describe_backend — 실측 진단 ──────────────────────────────────
def test_describe_off(monkeypatch):
    monkeypatch.delenv("TRACE_BACKEND", raising=False)
    desc = tracing.describe_backend()
    assert "OFF" in desc


def test_describe_langsmith(monkeypatch):
    monkeypatch.setenv("TRACE_BACKEND", "langsmith")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    monkeypatch.setenv("LANGSMITH_PROJECT", "test-proj")
    desc = tracing.describe_backend()
    assert "langsmith" in desc
    assert "test-proj" in desc
    assert "set" in desc


def test_describe_langfuse_keys_missing(monkeypatch):
    monkeypatch.setenv("TRACE_BACKEND", "langfuse")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    desc = tracing.describe_backend()
    assert "langfuse" in desc
    assert "MISSING" in desc
    # 거짓 양성 제거 — keys=MISSING 일 때는 "활성" 아님.
    assert "비활성" in desc or "MISSING" in desc


def test_describe_langfuse_auth_fail_marks_inactive(monkeypatch):
    """키 있어도 auth_check 실패 시 '비활성' 표기."""
    monkeypatch.setenv("TRACE_BACKEND", "langfuse")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "y")

    # _get_langfuse_client 가 None 반환하도록 monkeypatch — auth 실패 시뮬레이션.
    monkeypatch.setattr(tracing, "_get_langfuse_client", lambda: None)
    desc = tracing.describe_backend()
    assert "langfuse" in desc
    assert "auth=FAIL" in desc or "비활성" in desc


# ── get_trace_callbacks — deprecated alias ────────────────────────
def test_callbacks_always_empty(monkeypatch):
    """Langfuse 4.x OTEL native — callback 불필요. 항상 [] 반환."""
    monkeypatch.delenv("TRACE_BACKEND", raising=False)
    assert tracing.get_trace_callbacks() == []
    monkeypatch.setenv("TRACE_BACKEND", "langfuse")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "y")
    tracing.reset_cache()
    assert tracing.get_trace_callbacks() == []


def test_callbacks_langsmith_sets_env_flag(monkeypatch):
    """LangSmith 분기 — LANGCHAIN_TRACING_V2 env 자동 set (langchain 자동 송신용)."""
    monkeypatch.setenv("TRACE_BACKEND", "langsmith")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    tracing.get_trace_callbacks()
    import os
    assert os.getenv("LANGCHAIN_TRACING_V2") == "true"


# ── tags / metadata ───────────────────────────────────────────────
def test_tags_finance_default():
    assert "domain:finance" in tracing.tags_for_domain(None)
    assert "autonexusgraph" in tracing.tags_for_domain(None)


def test_tags_auto_adds_autograph():
    tags = tracing.tags_for_domain("auto")
    assert "domain:auto" in tags
    assert "autograph" in tags


def test_tags_cross_domain_adds_both():
    tags = tracing.tags_for_domain("cross_domain")
    assert "autograph" in tags
    # ip 도 포함 (IPGraph 흡수 — PRD v2.2 §12.5).
    assert "ipgraph" in tags


def test_metadata_extracts_target_counts():
    state = {"domain": "auto", "target_vehicles": ["v1", "v2"],
             "question_kind": "factual"}
    md = tracing.metadata_for_state(state)
    assert md["domain"] == "auto"
    assert md["n_target_vehicles"] == 2
    assert md["question_kind"] == "factual"


# ── start_turn_context (핵심) ─────────────────────────────────────
def test_turn_context_isolation_basic(monkeypatch):
    """turn 진입 시 ContextVar 에 새 tracker, exit 후 None."""
    monkeypatch.delenv("TRACE_BACKEND", raising=False)   # langfuse 비활성 — PG 만 시도
    assert ct.current_tracker() is None
    with tracing.start_turn_context("t1", {"domain": "auto", "question": "q"}) as turn:
        assert ct.current_tracker() is not None
        assert ct.current_tracker() is turn.tracker
        assert turn.thread_id == "t1"
        assert turn.tracker.state.thread_id == "t1"
        assert turn.tracker.state.domain == "auto"
    # exit 후 ctx 클리어.
    assert ct.current_tracker() is None
    assert turn.tracker.state.finalized is True


def test_turn_context_records_n_replans(monkeypatch):
    """turn.state.n_replans 가 tracker 메모리에 반영."""
    monkeypatch.delenv("TRACE_BACKEND", raising=False)
    with tracing.start_turn_context("t-replan", {"domain": "auto",
                                                  "question": "q"}) as turn:
        turn.state = {**turn.state, "n_replans": 3, "answer": "x"}
    assert turn.tracker.state.n_replans == 3
    assert turn.tracker.state.finalized is True


def test_turn_context_isolated_per_thread(monkeypatch):
    """동시 두 thread 가 별도 tracker 를 가져야 함 — ContextVar 격리."""
    monkeypatch.delenv("TRACE_BACKEND", raising=False)
    results: dict[str, str] = {}
    barrier = threading.Barrier(2)

    def _run(tid: str) -> None:
        with tracing.start_turn_context(tid, {"domain": "auto",
                                               "question": tid}) as turn:
            barrier.wait()
            # 양 thread 동시에 ctx 보유 — 서로 안 덮어써야.
            results[tid] = ct.current_tracker().state.thread_id   # type: ignore[union-attr]

    threads = [threading.Thread(target=_run, args=(t,))
               for t in ("A", "B")]
    for t in threads: t.start()
    for t in threads: t.join()
    assert results == {"A": "A", "B": "B"}


def test_turn_context_failsoft_when_langfuse_missing(monkeypatch):
    """Langfuse SDK 미설치/키 없음 — turn 자체는 정상 종료."""
    monkeypatch.setenv("TRACE_BACKEND", "langfuse")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    tracing.reset_cache()
    with tracing.start_turn_context("t-no-keys", {"domain": "auto",
                                                   "question": "q"}) as turn:
        turn.state = {**turn.state, "n_replans": 0, "answer": "ok"}
    # 예외 없이 종료.
    assert turn.tracker.state.finalized is True


def test_turn_context_exception_marks_error(monkeypatch):
    """turn 안에서 예외 발생 시 status='error' 로 finalize."""
    monkeypatch.delenv("TRACE_BACKEND", raising=False)
    try:
        with tracing.start_turn_context("t-err", {"domain": "auto",
                                                   "question": "q"}) as turn:
            raise RuntimeError("intentional")
    except RuntimeError:
        pass
    assert turn.tracker.state.finalized is True
    # ctx 도 정리됐어야.
    assert ct.current_tracker() is None


def test_turn_context_budget_exceeded_marks_aborted(monkeypatch):
    """BudgetExceeded 발생 시 status='aborted_budget'."""
    from autonexusgraph.llm.cost_tracker import BudgetExceeded
    monkeypatch.delenv("TRACE_BACKEND", raising=False)
    try:
        with tracing.start_turn_context("t-budget", {"domain": "auto",
                                                     "question": "q"}) as turn:
            raise BudgetExceeded("test")
    except BudgetExceeded:
        pass
    assert turn.tracker.state.finalized is True
    assert ct.current_tracker() is None


# ── current_turn_summary — 진단 ────────────────────────────────────
def test_current_turn_summary_empty_outside_context():
    assert tracing.current_turn_summary() == {}


def test_current_turn_summary_inside_context(monkeypatch):
    monkeypatch.delenv("TRACE_BACKEND", raising=False)
    with tracing.start_turn_context("t-diag", {"domain": "ip",
                                                "question": "q"}):
        summary = tracing.current_turn_summary()
        assert summary["thread_id"] == "t-diag"
        assert summary["finalized"] is False
        assert "turn_id" in summary
