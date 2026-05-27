"""에이전트 그래프 — LangGraph StateGraph 우선 + 함수 체인 폴백.

PRD §7.5: Triage → Planner → Executor → Synthesizer → Validator (→ replan)
PRD §7.5.8: PG checkpoint (chat 스키마)
PRD §7.5.11: Tracing (Langfuse/LangSmith) per node
PRD §7.6.5: Streaming — UI node-by-node 진행 표시

런타임 분기:
- langgraph 설치됨 → 실제 StateGraph + conditional_edges (replan) + checkpointer + tracing callbacks
- langgraph 미설치 → Python 함수 체인 (이전과 동일 동작)

진입점:
- run_agent(question, thread_id, history) — 동기 호출 (api /chat 호환)
- run_agent_stream(question, thread_id, history) — generator, (node_name, partial_state) yield
"""

from __future__ import annotations

import logging
from typing import Iterator

from .nodes import executor_node, planner_node, synthesizer_node, triage_node
from .state import AgentState
from .validator import MAX_REPLANS, mark_replan, should_replan, validator_node

log = logging.getLogger(__name__)


try:
    from langgraph.graph import END, StateGraph
    _HAS_LANGGRAPH = True
except ImportError:
    _HAS_LANGGRAPH = False


_LG_APP = None   # 컴파일된 LangGraph app 캐시 (lazy)


def _route_after_validator(state: AgentState) -> str:
    """validator → planner (replan) | finalize.

    PRD §7.5.5: n_replans < MAX_REPLANS 이면서 validation_status=failed 일 때만 replan.
    """
    if should_replan(state):
        return "replan"
    return "end"


def _validator_with_replan_prep(state: AgentState) -> AgentState:
    """validator 통과 후 replan 으로 분기되는 경우 state 초기화도 함께."""
    state = validator_node(state)
    if should_replan(state):
        state = mark_replan(state)
    return state


def _finalize_failed(state: AgentState) -> AgentState:
    """MAX_REPLANS 도달 시 사용자에게 검증 실패 신호 노출."""
    if state.get("validation_status") == "failed":
        issues = state.get("validation_issues") or []
        prefix = (
            f"⚠️ 검증 실패 (replan {state.get('n_replans')}/{MAX_REPLANS} 후): "
            f"{', '.join(issues[:3])}\n\n"
        )
        state["answer"] = prefix + (state.get("answer") or "(빈 응답)")
    return state


def _build_langgraph_app():
    """LangGraph StateGraph 빌드 + 컴파일. 호출당 1회 (모듈 캐시)."""
    from .checkpointer import get_checkpointer

    workflow = StateGraph(AgentState)
    workflow.add_node("triage", triage_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("synthesizer", synthesizer_node)
    workflow.add_node("validator", _validator_with_replan_prep)
    workflow.add_node("finalize", _finalize_failed)

    workflow.set_entry_point("triage")
    workflow.add_edge("triage", "planner")
    workflow.add_edge("planner", "executor")
    workflow.add_edge("executor", "synthesizer")
    workflow.add_edge("synthesizer", "validator")
    workflow.add_conditional_edges(
        "validator",
        _route_after_validator,
        {"replan": "planner", "end": "finalize"},
    )
    workflow.add_edge("finalize", END)

    checkpointer = get_checkpointer()
    app = workflow.compile(checkpointer=checkpointer)
    log.info("LangGraph StateGraph compiled (checkpointer=%s)",
             type(checkpointer).__name__ if checkpointer else "None")
    return app


def _get_langgraph_app():
    global _LG_APP
    if _LG_APP is None:
        _LG_APP = _build_langgraph_app()
    return _LG_APP


def _make_run_config(thread_id: str) -> dict:
    """invoke / stream config — thread_id + tracing callbacks."""
    cfg: dict = {"configurable": {"thread_id": thread_id or "default"}}
    try:
        from .tracing import get_trace_callbacks
        cbs = get_trace_callbacks()
        if cbs:
            cfg["callbacks"] = cbs
    except Exception as exc:   # noqa: BLE001 — tracing 은 항상 fail-soft
        log.debug("tracing callbacks skip: %s", exc)
    return cfg


def _run_with_langgraph(state: AgentState) -> AgentState:
    """LangGraph StateGraph 실행 (blocking). thread_id 별 checkpoint."""
    app = _get_langgraph_app()
    config = _make_run_config(state.get("thread_id") or "default")
    result = app.invoke(state, config=config)
    return result   # type: ignore[return-value]


def _run_with_fallback_chain(state: AgentState) -> AgentState:
    """langgraph 미설치 환경 — Python 함수 체인. replan loop 포함."""
    state = triage_node(state)
    while True:
        state = planner_node(state)
        state = executor_node(state)
        state = synthesizer_node(state)
        state = validator_node(state)
        if not should_replan(state):
            break
        state = mark_replan(state)
    return _finalize_failed(state)


def run_agent(question: str, *,
              thread_id: str = "default",
              history: list[dict] | None = None) -> AgentState:
    """단일 대화 turn 실행. validator failed 시 최대 MAX_REPLANS 회 재계획."""
    state: AgentState = _init_state(question, thread_id, history)

    if _HAS_LANGGRAPH:
        try:
            return _run_with_langgraph(state)
        except Exception as exc:   # noqa: BLE001 — fail-soft, 폴백 체인으로
            log.warning("[run_agent] LangGraph 실행 실패 — 함수 체인 폴백: %s", exc)
            return _run_with_fallback_chain(state)
    return _run_with_fallback_chain(state)


def run_agent_stream(question: str, *,
                     thread_id: str = "default",
                     history: list[dict] | None = None
                     ) -> Iterator[tuple[str, AgentState]]:
    """노드 진행 상황을 스트리밍 — UI/SSE 용 (PRD §7.6.5).

    yield (node_name, partial_state) — 각 노드 종료 후. langgraph stream mode='updates'.
    마지막에 ('__final__', final_state) 1회.

    langgraph 미설치 환경 → 함수 체인을 노드 단위로 흉내내서 yield.
    """
    state: AgentState = _init_state(question, thread_id, history)

    if _HAS_LANGGRAPH:
        try:
            yield from _stream_with_langgraph(state)
            return
        except Exception as exc:   # noqa: BLE001
            log.warning("[run_agent_stream] LangGraph stream 실패 — 함수 체인 폴백: %s", exc)
            # 폴백 — 이미 일부 노드는 진행됐을 수 있으나 state 는 안전하게 reset
            state = _init_state(question, thread_id, history)
    yield from _stream_with_fallback_chain(state)


def _stream_with_langgraph(state: AgentState) -> Iterator[tuple[str, AgentState]]:
    app = _get_langgraph_app()
    config = _make_run_config(state.get("thread_id") or "default")
    final_state: AgentState = state
    for update in app.stream(state, config=config, stream_mode="updates"):
        # langgraph 의 update: {node_name: partial_state_dict}
        if not isinstance(update, dict):
            continue
        for node_name, partial in update.items():
            if isinstance(partial, dict):
                final_state = {**final_state, **partial}   # type: ignore[misc]
            yield (node_name, final_state)
    yield ("__final__", final_state)


def _stream_with_fallback_chain(state: AgentState) -> Iterator[tuple[str, AgentState]]:
    """노드 단위 yield + replan loop."""
    state = triage_node(state)
    yield ("triage", state)
    while True:
        state = planner_node(state)
        yield ("planner", state)
        state = executor_node(state)
        yield ("executor", state)
        state = synthesizer_node(state)
        yield ("synthesizer", state)
        state = validator_node(state)
        yield ("validator", state)
        if not should_replan(state):
            break
        state = mark_replan(state)
        yield ("replan", state)
    state = _finalize_failed(state)
    yield ("__final__", state)


def _init_state(question: str, thread_id: str, history: list[dict] | None) -> AgentState:
    return {
        "thread_id": thread_id,
        "question": question,
        "history": history or [],
        "llm_usage_usd": 0.0,
        "n_replans": 0,
        "validation_status": "pending",
    }


__all__ = ["run_agent", "run_agent_stream"]
