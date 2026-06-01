"""에이전트 StateGraph 상태 정의.

LangGraph 도입 시 그대로 StateGraph[AgentState] 로 사용 가능한 형태.
현재는 langgraph 미설치 → graph.py 가 단순 함수 체인으로 동작.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict


QuestionKind = Literal["factual", "narrative", "structural", "multi_hop", "unknown"]

# PRD §7.5.2 / §7.5.3 — Supervisor 가 라우팅하는 worker agent 타입.
AgentName = Literal["research", "graph", "sql", "calculator"]
TaskStatus = Literal["pending", "running", "done", "failed", "skipped"]


def _last_wins(old: Any, new: Any) -> Any:
    """LangGraph reducer — concurrent update 충돌 회피용 last-wins.

    병렬 worker (Send-API) 가 같은 entry-only 키를 return state 에 포함해도
    충돌 없이 마지막 값 채택. new 가 None 이면 old 유지 (worker partial return 보호).

    worker 가 read-only 인 entry-only 키 (thread_id / question / domain / plan / tasks 등)
    에 적용. write 가 있는 키 (task_results / evidence_chunks 등) 에는 적용 금지.

    keep_first 가 아닌 last_wins 인 이유: LangGraph checkpointer 가 thread_id 별로 state
    보존 — multi-turn 시 새 turn 의 question 이 들어오면 그것을 채택해야 정상 동작.
    keep_first 면 첫 turn 의 question 이 영구 유지되어 후속 turn 들이 같은 질문 처리.
    """
    return new if new is not None else old


class AgentState(TypedDict, total=False):
    """conversation 한 turn 의 누적 상태."""

    # 입력 — entry 에서만 set, 병렬 worker (Send-API) 는 보존 (concurrent 충돌 회피)
    thread_id: Annotated[str, _last_wins]
    question: Annotated[str, _last_wins]
    history: Annotated[list[dict], _last_wins]
    domain: Annotated[str, _last_wins]
    target_vehicles: Annotated[list[int], _last_wins]
    target_models: Annotated[list[int], _last_wins]
    target_makes: Annotated[list[str], _last_wins]

    # 전처리 (rewriter / temporal 결과) — triage/rewriter 한 번만 set, worker read-only
    question_rewritten: Annotated[str, _last_wins]
    temporal_audit: Annotated[dict, _last_wins]
    rewrite_audit: Annotated[dict, _last_wins]
    safety_signals: Annotated[list[str], _last_wins]

    # Triage / Planner 결정 — planner 한 번 set, worker read-only
    question_kind: Annotated[QuestionKind, _last_wins]
    target_companies: Annotated[list[str], _last_wins]
    session_carryover: Annotated[bool, _last_wins]
    plan: Annotated[list[dict], _last_wins]
    tasks: Annotated[list[dict], _last_wins]
                                      #   {"id": str, "agent": AgentName, "intent": str,
                                      #    "args": dict, "depends_on": list[str],
                                      #    "status": TaskStatus, "result": Any}
    # 누적 키 — worker 가 state 전체 mutate 후 return (legacy 패턴). LangGraph
    # last_wins 면 병렬 worker 중복 누적 회피. 단 진짜 병렬 worker 결과 누적이
    # 필요한 경우는 supervisor 가 순차 dispatch — workers.py 리팩터는 별도 PR.
    task_results: Annotated[dict, _last_wins]
    tool_results: Annotated[list[dict], _last_wins]
    evidence_chunks: Annotated[list[dict], _last_wins]
    graph_subgraph: Annotated[dict, _last_wins]
    fallback_used: Annotated[bool, _last_wins]

    # 합성
    answer: Annotated[str, _last_wins]
    citations: Annotated[list[dict], _last_wins]
    visualizations: Annotated[list[dict], _last_wins]

    # Validation (PRD §7.5.5)
    validation_status: Annotated[str, _last_wins]
    validation_issues: Annotated[list[str], _last_wins]
    grounding: Annotated[dict, _last_wins]

    # Human-in-the-Loop (PRD §7.5.6)
    pending_interrupt: Annotated[dict, _last_wins]
    interrupt_response: Annotated[Any, _last_wins]
    interrupt_handled: Annotated[bool, _last_wins]

    # 메타·비용
    llm_usage_usd: Annotated[float, _last_wins]
    n_replans: Annotated[int, _last_wins]
    aborted_reason: Annotated[str, _last_wins]
