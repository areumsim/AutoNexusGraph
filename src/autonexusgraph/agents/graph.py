"""에이전트 그래프 — LangGraph StateGraph 우선 + 함수 체인 폴백.

PRD §7.5: Triage → Planner → Supervisor ↔ Workers (병렬) → Synthesizer → Validator (→ replan)
PRD §7.5.7: Send API 로 의존성 없는 task 병렬 디스패치 (langgraph 활성 시)
PRD §7.5.8: PG checkpoint (chat 스키마)
PRD §7.5.11: Tracing (Langfuse/LangSmith) per node
PRD §7.6.5: Streaming — UI node-by-node 진행 표시

런타임 분기:
- langgraph 설치됨 → StateGraph + conditional_edges + Send (병렬) + checkpointer + tracing
- langgraph 미설치 → Python 함수 체인 (동일 흐름·동일 state)

진입점:
- run_agent(question, thread_id, history)            — blocking
- run_agent_stream(...)                              — generator (node_name, partial_state)
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from .nodes import executor_node, planner_node, synthesizer_node, triage_node
from .state import AgentState
from .supervisor import (
    mid_execution_reflect,
    supervisor_done,
    supervisor_node,
    sup_send_directives,
)
from .tracing import start_turn_context
from .validator import MAX_REPLANS, mark_replan, should_replan, validator_node
from .workers import (
    calculator_worker,
    dispatch_one,
    graph_worker,
    research_worker,
    sql_worker,
)

log = logging.getLogger(__name__)


try:
    from langgraph.graph import END, StateGraph
    _HAS_LANGGRAPH = True
except ImportError:
    _HAS_LANGGRAPH = False

try:
    from langgraph.types import Command   # type: ignore[import-not-found]
    _HAS_COMMAND = True
except ImportError:
    _HAS_COMMAND = False


_LG_APP = None   # 컴파일된 LangGraph app 캐시 (lazy)


def _route_after_validator(state: AgentState) -> str:
    """validator → planner (replan) | finalize."""
    if should_replan(state):
        return "replan"
    return "end"


def _validator_with_replan_prep(state: AgentState) -> AgentState:
    state = validator_node(state)
    if should_replan(state):
        state = mark_replan(state)
    return state


def _finalize_failed(state: AgentState) -> AgentState:
    if state.get("validation_status") == "failed":
        issues = state.get("validation_issues") or []
        prefix = (
            f"⚠️ 검증 실패 (replan {state.get('n_replans')}/{MAX_REPLANS} 후): "
            f"{', '.join(issues[:3])}\n\n"
        )
        state["answer"] = prefix + (state.get("answer") or "(빈 응답)")
    return state


def _executor_legacy_fallback(state: AgentState) -> AgentState:
    """tasks DAG 가 비어 있으면 legacy flat plan 으로 실행 (호환).

    Planner 가 새 DAG 를 항상 산출하지만, 외부 호출자 / 테스트가 plan 만
    지정하는 경우를 위해 호환 경로 유지.
    """
    if not state.get("tasks") and state.get("plan"):
        return executor_node(state)
    return state


# ── LangGraph Send wrappers (병렬 worker 호출용) ─────────────
def _worker_wrap(worker_fn):
    """Send 에서 받은 state 의 _current_task 를 꺼내 worker 호출."""
    def _wrapped(state: AgentState) -> AgentState:
        task = state.get("_current_task")
        if task is None:
            return state
        # _current_task 은 Send 한정 — 결과 누적 후 제거
        out_state = worker_fn(state, task)
        out_state.pop("_current_task", None)
        return out_state
    _wrapped.__name__ = f"wrap_{worker_fn.__name__}"
    return _wrapped


def _build_langgraph_app():
    from .checkpointer import get_checkpointer

    workflow = StateGraph(AgentState)
    workflow.add_node("triage", triage_node)
    workflow.add_node("planner", planner_node)
    # Supervisor 노드: 라우팅 자체는 Send(sup_send_directives)가 처리하지만, 재진입마다
    # ReAct reflect 를 돌려 직전 batch 결과 기반 동적 task 를 생성한다(observe→act).
    # 각 worker 가 이 노드로 복귀(add_edge below)하므로 batch 사이 reflect 가 보장된다.
    def _supervisor_reflect(s: AgentState) -> AgentState:
        mid_execution_reflect(s)
        return s
    workflow.add_node("supervisor", _supervisor_reflect)
    workflow.add_node("worker_research", _worker_wrap(research_worker))
    workflow.add_node("worker_graph", _worker_wrap(graph_worker))
    workflow.add_node("worker_sql", _worker_wrap(sql_worker))
    workflow.add_node("worker_calculator", _worker_wrap(calculator_worker))
    workflow.add_node("executor_legacy", _executor_legacy_fallback)
    workflow.add_node("synthesizer", synthesizer_node)
    workflow.add_node("validator", _validator_with_replan_prep)
    workflow.add_node("finalize", _finalize_failed)

    workflow.set_entry_point("triage")
    workflow.add_edge("triage", "planner")
    workflow.add_edge("planner", "supervisor")

    # Supervisor → Send(여러 worker 병렬) | None → executor_legacy/synth 분기
    def _route_after_sup(state: AgentState):
        sends = sup_send_directives(state)
        if sends:
            return sends
        # tasks 가 비어 있으면 legacy executor 한 번 거치고 synthesizer 로
        if not state.get("tasks") and state.get("plan"):
            return "executor_legacy"
        return "synthesizer"

    workflow.add_conditional_edges(
        "supervisor",
        _route_after_sup,
        {
            "worker_research": "worker_research",
            "worker_graph": "worker_graph",
            "worker_sql": "worker_sql",
            "worker_calculator": "worker_calculator",
            "executor_legacy": "executor_legacy",
            "synthesizer": "synthesizer",
        },
    )

    # 각 worker 종료 후 supervisor 로 복귀 (DAG 의 다음 batch 디스패치)
    for w in ("worker_research", "worker_graph", "worker_sql", "worker_calculator"):
        workflow.add_edge(w, "supervisor")

    workflow.add_edge("executor_legacy", "synthesizer")
    workflow.add_edge("synthesizer", "validator")
    workflow.add_conditional_edges(
        "validator",
        _route_after_validator,
        {"replan": "planner", "end": "finalize"},
    )
    workflow.add_edge("finalize", END)

    checkpointer = get_checkpointer()
    app = workflow.compile(checkpointer=checkpointer)
    log.info(
        "LangGraph StateGraph compiled (checkpointer=%s, nodes=11, Send-API parallel workers)",
        type(checkpointer).__name__ if checkpointer else "None",
    )
    return app


def _get_langgraph_app():
    global _LG_APP
    if _LG_APP is None:
        _LG_APP = _build_langgraph_app()
    return _LG_APP


def _make_run_config(thread_id: str, *, state: dict | None = None) -> dict:
    """LangGraph app.invoke 에 넘길 config — checkpoint + LangSmith 태그.

    Langfuse 4.x 는 OTEL native ─ start_turn_context 의 ``start_as_current_observation``
    span 이 trace 책임. 본 config 는 LangSmith 자동 송신 (langchain 설치 시) 의
    tags/metadata 만 부착한다.
    """
    cfg: dict = {"configurable": {"thread_id": thread_id or "default"}}
    try:
        from .tracing import get_trace_callbacks, metadata_for_state, tags_for_domain
        # LangSmith env-flag 보강 (langchain 자동 송신용) — 부수효과 only.
        get_trace_callbacks()
        if state is not None:
            domain = state.get("domain") if isinstance(state, dict) else None
            cfg["tags"] = tags_for_domain(domain)
            cfg["metadata"] = metadata_for_state(state)
    except Exception as exc:   # noqa: BLE001
        log.debug("tracing config skip: %s", exc)
    return cfg


def _run_with_langgraph(state: AgentState) -> AgentState:
    app = _get_langgraph_app()
    config = _make_run_config(state.get("thread_id") or "default", state=state)
    result = app.invoke(state, config=config)
    return result   # type: ignore[return-value]


# ── 폴백 체인 (langgraph 미설치 환경) ──────────────────────────
def _run_with_fallback_chain(state: AgentState) -> AgentState:
    state = triage_node(state)
    while True:
        state = planner_node(state)
        # Supervisor (함수 모드) — DAG sequential dispatch
        if state.get("tasks"):
            state = supervisor_node(state)
        else:
            state = _executor_legacy_fallback(state)
        state = synthesizer_node(state)
        state = validator_node(state)
        if not should_replan(state):
            break
        state = mark_replan(state)
    return _finalize_failed(state)


def run_agent(question: str, *,
              thread_id: str = "default",
              history: list[dict] | None = None,
              domain: str | None = None,
              rerank: bool | None = None) -> AgentState:
    """단일 turn 실행 (blocking). PRD §10 DoD #17 (b) — turn 단위 token/cost/replan 적재.

    ``start_turn_context`` 가 ContextVar 격리된 CostTracker + Langfuse span 을
    enter/exit. 어떤 경로 (langgraph / 폴백 / 예외) 든 exit 시 PG ops.llm_usage 의
    meta JSONB 에 thread_id/turn_id/n_replans/domain 영구 적재.

    ``rerank`` (PRD §10 DoD #17 (d) 평가 매트릭스 ablation): None=기본(retrieve 도구
    default), True/False 명시 시 research_worker 가 search_documents(rerank=...) 로 전파.
    """
    state: AgentState = _init_state(question, thread_id, history, domain=domain,
                                    rerank=rerank)
    with start_turn_context(thread_id or "default", state) as turn:
        if _HAS_LANGGRAPH:
            try:
                result = _run_with_langgraph(state)
                turn.state = result   # type: ignore[assignment]
                return result
            except Exception as exc:   # noqa: BLE001
                log.warning("[run_agent] LangGraph 실행 실패 — 함수 체인 폴백: %s", exc)
        result = _run_with_fallback_chain(state)
        turn.state = result   # type: ignore[assignment]
        return result


def run_agent_stream(question: str, *,
                     thread_id: str = "default",
                     history: list[dict] | None = None,
                     domain: str | None = None,
                     rerank: bool | None = None
                     ) -> Iterator[tuple[str, AgentState]]:
    """노드별 partial state stream — UI/SSE 용 (PRD §7.6.5).

    yields (node_name, partial_state). 마지막은 ('__final__', final_state) 또는
    ('__interrupt__', state). generator close 시 ``start_turn_context.__exit__`` 가
    트리거되어 PG/Langfuse 적재 완료.
    """
    state: AgentState = _init_state(question, thread_id, history, domain=domain,
                                    rerank=rerank)
    with start_turn_context(thread_id or "default", state) as turn:
        # A1 (P0+ #1 결함 fix): 매 yield 직후 turn.state 갱신 — generator close /
        # client disconnect 시점에도 마지막 partial 까지 PG/Langfuse 에 기록되도록.
        # try/finally 만으로는 yield 도중 GeneratorExit 시 final 동기화 미보장.
        if _HAS_LANGGRAPH:
            try:
                for node_name, partial in _stream_with_langgraph(state):
                    turn.state = partial   # type: ignore[assignment]
                    yield (node_name, partial)
                return
            except Exception as exc:   # noqa: BLE001
                log.warning("[run_agent_stream] LangGraph stream 실패 — 함수 체인 폴백: %s", exc)
                state = _init_state(question, thread_id, history, domain=domain,
                                    rerank=rerank)
                turn.state = state   # type: ignore[assignment]
        for node_name, partial in _stream_with_fallback_chain(state):
            turn.state = partial   # type: ignore[assignment]
            yield (node_name, partial)


def _stream_with_langgraph(state: AgentState) -> Iterator[tuple[str, AgentState]]:
    app = _get_langgraph_app()
    config = _make_run_config(state.get("thread_id") or "default", state=state)
    final_state: AgentState = state
    interrupted = False
    for update in app.stream(state, config=config, stream_mode="updates"):
        if not isinstance(update, dict):
            continue
        # LangGraph 1.x: interrupt 발생 시 update key 가 "__interrupt__"
        if "__interrupt__" in update:
            interrupted = True
            interrupts = update["__interrupt__"]
            payload = _extract_interrupt_payload(interrupts)
            if payload:
                final_state["pending_interrupt"] = payload   # type: ignore[typeddict-unknown-key]
            yield ("__interrupt__", final_state)
            break
        for node_name, partial in update.items():
            if isinstance(partial, dict):
                final_state = {**final_state, **partial}   # type: ignore[misc]
            yield (node_name, final_state)
    if not interrupted:
        yield ("__final__", final_state)


def _extract_interrupt_payload(interrupts: Any) -> dict | None:
    """langgraph 의 interrupt 페이로드 추출. 다양한 버전·형식 호환."""
    if not interrupts:
        return None
    # 보통 list[Interrupt] 형태 — 첫 항목의 value 가 우리가 보낸 dict
    if isinstance(interrupts, list):
        for it in interrupts:
            v = getattr(it, "value", None) or getattr(it, "ns", None)
            if isinstance(v, dict):
                return v
            if isinstance(it, dict):
                return it
    if isinstance(interrupts, dict):
        return interrupts
    val = getattr(interrupts, "value", None)
    if isinstance(val, dict):
        return val
    return None


def run_agent_resume(thread_id: str, response: Any) -> AgentState:
    """interrupt 후 graph 재개 (blocking). PRD §7.5.6.

    동일 thread_id 의 checkpoint 에서 이어감 + Command(resume=response).
    resume 는 새 turn 으로 간주 — 별도의 ops.llm_usage row + Langfuse span.
    langgraph 미설치 환경 → InterruptUnavailable 우회: 호출자가 새 turn 으로
    response 를 question 에 합쳐 재호출하는 패턴 권장.
    """
    if not _HAS_LANGGRAPH or not _HAS_COMMAND:
        raise RuntimeError("LangGraph + Command 필요 — interrupt resume 미지원 환경")
    app = _get_langgraph_app()
    config = _make_run_config(thread_id)
    seed: dict = {"question": "(resume)", "domain": None,
                  "thread_id": thread_id}
    with start_turn_context(thread_id or "default", seed,
                            caller="agent_resume") as turn:
        final_state = app.invoke(Command(resume=response), config=config)
        turn.state = final_state if isinstance(final_state, dict) else {}
        return final_state   # type: ignore[return-value]


def run_agent_resume_stream(thread_id: str, response: Any
                             ) -> Iterator[tuple[str, AgentState]]:
    """interrupt 후 graph 재개 (streaming). SSE 용. 새 turn 으로 turn lifecycle 진입."""
    if not _HAS_LANGGRAPH or not _HAS_COMMAND:
        raise RuntimeError("LangGraph + Command 필요 — interrupt resume 미지원 환경")
    app = _get_langgraph_app()
    config = _make_run_config(thread_id)
    seed: dict = {"question": "(resume)", "domain": None,
                  "thread_id": thread_id}
    with start_turn_context(thread_id or "default", seed,
                            caller="agent_resume_stream") as turn:
        yield from _resume_stream_inner(app, response, config, turn)


def _resume_stream_inner(app: Any, response: Any, config: dict,
                          turn: Any) -> Iterator[tuple[str, AgentState]]:
    final_state: AgentState = {}   # type: ignore[assignment]
    interrupted = False
    for update in app.stream(Command(resume=response),
                              config=config, stream_mode="updates"):
        if not isinstance(update, dict):
            continue
        if "__interrupt__" in update:
            interrupted = True
            payload = _extract_interrupt_payload(update["__interrupt__"])
            if payload:
                final_state["pending_interrupt"] = payload   # type: ignore[typeddict-unknown-key]
            yield ("__interrupt__", final_state)
            break
        for node_name, partial in update.items():
            if isinstance(partial, dict):
                final_state = {**final_state, **partial}   # type: ignore[misc]
            yield (node_name, final_state)
    if not interrupted:
        yield ("__final__", final_state)
    # final state 를 turn 에 동기화 — finalize 시 n_replans/answer 추출 용.
    turn.state = final_state if isinstance(final_state, dict) else {}


def _stream_with_fallback_chain(state: AgentState) -> Iterator[tuple[str, AgentState]]:
    state = triage_node(state)
    yield ("triage", state)
    # 폴백 환경에서 모호성 감지 — interrupt 호출 못 했으면 pending_interrupt 만 채워졌을 것.
    # safety_signals 에 자동 해결 흔적이 있으면 그대로 진행, 없으면 사용자에 노출하고 stop.
    pi = state.get("pending_interrupt") or {}
    if pi and not state.get("interrupt_handled"):
        state["aborted_reason"] = "needs_clarification"
        yield ("__interrupt__", state)
        return
    while True:
        state = planner_node(state)
        yield ("planner", state)
        if state.get("tasks"):
            state = supervisor_node(state)
            yield ("supervisor", state)
        else:
            state = _executor_legacy_fallback(state)
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


def _init_state(question: str, thread_id: str, history: list[dict] | None,
                *, domain: str | None = None,
                rerank: bool | None = None) -> AgentState:
    """초기 state. domain 미지정 시 등록 라우터 검색 → 모두 None 이면 finance.

    domain 라우팅 흐름 (PRD §7.5.11 + §10.12):
        UI/streamlit (또는 eval adapter) — domain 명시 또는 None
            ↓ _init_state — _domain_handler.auto_detect_domain 호출 (None 일 때)
        state["domain"] = "finance" | "auto" | "cross_domain" (등록된 도메인 한정)
            ↓ agents/workers._toolbox_for — handler.toolbox_modules() 또는 finance tools
            ↓ agents/nodes — handler.identify_targets / plan_tasks / fallback_search
        cypher / SQL 호출

    core 는 외부 도메인 패키지 (예: autograph) 를 import 하지 않는다. 외부 패키지가
    register_handler + register_router 로 자기 자신을 등록. 외부 패키지의 자동
    적재는 ``_domain_handler.discover_plugins()`` 가 ENV
    ``AUTONEXUSGRAPH_DOMAIN_PLUGINS`` (csv, 기본 'autograph') 를 기반으로 처리.
    """
    if not domain:
        from ._domain_handler import auto_detect_domain
        domain = auto_detect_domain(question, hint=None)
    state: AgentState = {
        "thread_id": thread_id,
        "question": question,
        "history": history or [],
        "domain": domain,
        "llm_usage_usd": 0.0,
        "n_replans": 0,
        "validation_status": "pending",
        "tasks": [],
        "task_results": {},
    }
    if rerank is not None:
        state["rerank"] = rerank
    return state


__all__ = [
    "run_agent", "run_agent_stream",
    "run_agent_resume", "run_agent_resume_stream",
]
