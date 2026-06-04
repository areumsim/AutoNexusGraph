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


def _list_extend(old: Any, new: Any) -> list:
    """LangGraph reducer — list[str] append-only 의 안전 누적 (M2 fix, safety_signals 전용).

    safety_signals 처럼 **모든 분기에서 적재된 흔적을 보존**해야 하는 키 전용.
    병렬 worker (Send-API) 가 각자 신호를 적재하면 fan-in 시점에 둘 다 보존.
    중복은 set 매칭으로 회피 (순서는 old 우선).

    list[dict] (evidence_chunks / tool_results) 는 dedupe 불가 (dict unhashable)
    → ``_list_concat`` 사용. dict 는 ``_dict_merge``.

    Type safety (N1 fix): None / 비-list 입력은 list 로 분해되지 않도록 가드 —
    예) ``_list_extend("old", None)`` 이 ``['o','l','d']`` 되는 회귀 회피.
    """
    if old is None:
        return list(new) if isinstance(new, list) else []
    if new is None:
        return list(old) if isinstance(old, list) else []
    if isinstance(old, list) and isinstance(new, list):
        seen = set(old)
        return list(old) + [x for x in new if x not in seen]
    return new   # 비-list 충돌 — last_wins 동등 (정상 경로에선 도달 불가).


def _list_concat(old: Any, new: Any) -> list:
    """LangGraph reducer — list[dict] 의 안전 누적 (M2 잔존 fix).

    evidence_chunks / tool_results 처럼 dict 요소 list 가 multi-worker 에서
    적재되는 키 전용. dedupe 안 함 (dict unhashable) — 호출자가 의미 중복 회피
    필요 시 별도 처리.

    Send fan-out → fan-in 시점에 워커별 list 가 모두 보존 — last_wins 의
    "한 쪽 list 만 유지 / 다른 쪽 손실" 문제 회피.
    """
    if old is None:
        return list(new) if isinstance(new, list) else []
    if new is None:
        return list(old) if isinstance(old, list) else []
    if isinstance(old, list) and isinstance(new, list):
        return list(old) + list(new)
    return new


def _dict_merge(old: Any, new: Any) -> dict:
    """LangGraph reducer — dict key-merge (M2 잔존 fix).

    task_results 처럼 worker 별 다른 키 (task_id) 로 결과를 적재하는 dict.
    fan-in 시 ``dict.update`` 패턴 — new 의 키가 old 를 덮어씀 (같은 task_id 의
    재실행 결과는 새 값 채택). worker 들이 다른 task_id 를 처리하므로 정상 누적.
    """
    if old is None:
        return dict(new) if isinstance(new, dict) else {}
    if new is None:
        return dict(old) if isinstance(old, dict) else {}
    if isinstance(old, dict) and isinstance(new, dict):
        merged = dict(old)
        merged.update(new)
        return merged
    return new


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
    # 검색 재정렬 토글 — entry 에서만 set. None=기본(retrieve 도구 자체 default=True).
    # 평가 매트릭스 (PRD §10 DoD #17 (d)) 의 rerank on/off ablation 셀이 이 값을
    # run_agent 인자로 주입 → research_worker 가 search_documents(rerank=...) 에 전파.
    rerank: Annotated[bool | None, _last_wins]

    # 전처리 (rewriter / temporal 결과) — triage/rewriter 한 번만 set, worker read-only
    question_rewritten: Annotated[str, _last_wins]
    temporal_audit: Annotated[dict, _last_wins]
    rewrite_audit: Annotated[dict, _last_wins]
    # PRD §7.0 안전 신호 — 모든 분기 (handler 폴백·interrupt fallback·sensitive_blocked
    # 등) 에서 적재된 흔적 보존. concurrent worker 의 신호 손실 회피 — list-concat reducer.
    safety_signals: Annotated[list[str], _list_extend]

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
    #
    # (라-Δ rollback, 2026-06-02): _list_concat / _dict_merge reducer 적용 시도 →
    # validator.mark_replan / executor / planner 의 "통째 set 으로 clear" 패턴과
    # 충돌 (reducer 가 노드 return 마다 적용되어 clear 무력화). 작성자 의도 (별도
    # PR — workers.py 흐름 재설계 후 적용) 가 정합. reducer 함수 자체는
    # ``_list_concat`` / ``_dict_merge`` 로 모듈에 보존 — workers 리팩터 PR 에서 활용.
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
