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


# ── 축6: 병렬 Send fan-in last-wins 손실 하드닝 ──────────────────
# 문제: 병렬 worker (Send-API) 가 각자 pre-fork state 사본에 자기 델타를 더해 반환하면
#   - last_wins → 한 worker 결과만 남고 동시 worker 결과 손실
#   - 순수 concat → 각 분기가 들고 온 pre-fork 부분이 중복
# 해결: key 로 dedupe 하는 concat/merge reducer. 공유 pre-fork 항목은 key 가 같아
# 멱등 흡수되고, 각 worker 의 새 항목만 누적된다. LangGraph 의 분기 격리(checkpointer
# 직렬화) 여부와 무관하게 정확 — 공유변이/격리 양쪽에서 같은 결과.
#
# clear 충돌 해소 (이전 롤백 사유): mark_replan/planner 의 "통째 비우기"가 merge
# reducer 와 충돌(빈 {} 이 merge 되어 clear 무력화). dict/list **서브클래스 마커**
# (_ClearedDict/_ClearedList)로 해결 — reducer 는 마커를 보면 교체(clear)하고, 함수체인
# (reducer 미적용)에선 그냥 빈 dict/list 로 동작하므로 노드 코드 무변경.
class _ClearedDict(dict):
    """reducer 에게 merge 대신 교체(clear)를 지시하는 빈 dict 마커."""


class _ClearedList(list):
    """reducer 에게 concat 대신 교체(clear)를 지시하는 빈 list 마커."""


def _merge_dict_dedup(old: Any, new: Any) -> dict:
    """task_results 용 — key(task_id) merge + clear 마커 인식.

    _ClearedDict 면 교체(replan 시 비우기). 그 외엔 ``_dict_merge`` 와 동일하게
    key 병합 — 병렬 worker 가 각자 task_id 로 적재하고 공유 pre-fork key 는 멱등.
    """
    if isinstance(new, _ClearedDict):
        return {}
    return _dict_merge(old, new)


def _concat_dedup_by(key: str):
    """list[dict] 용 reducer 팩토리 — key 로 dedupe 하는 concat + clear 마커 인식.

    evidence_chunks(key='id') / tool_results(key='task_id') 처럼 병렬 worker 가
    누적하는 list. 각 분기가 들고 온 공유 pre-fork 항목은 key 동일 → 1회만 보존,
    worker 별 새 항목은 모두 누적. key 없는 항목(legacy executor / fallback)은
    dedupe 대상 외 — 그대로 보존(순차 단일 노드 컨텍스트라 중복 없음).
    """
    def _reducer(old: Any, new: Any) -> list:
        if isinstance(new, _ClearedList):
            return []
        if old is None:
            return list(new) if isinstance(new, list) else []
        if new is None:
            return list(old) if isinstance(old, list) else []
        if isinstance(old, list) and isinstance(new, list):
            out: list = []
            seen: set = set()
            for item in list(old) + list(new):
                k = item.get(key) if isinstance(item, dict) else None
                if k is not None:
                    if k in seen:
                        continue
                    seen.add(k)
                out.append(item)
            return out
        return new
    return _reducer


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
    # 평가 매트릭스 (README §10 DoD #17 (d)) 의 rerank on/off ablation 셀이 이 값을
    # run_agent 인자로 주입 → research_worker 가 search_documents(rerank=...) 에 전파.
    rerank: Annotated[bool | None, _last_wins]
    # 축2 LLM 자율 planner ablation — entry 에서만 set. None=config(AGENT_LLM_PLANNER) 기본,
    # True/False=이 turn 한정 override. 평가 매트릭스가 룰 vs LLM planner 셀 분리에 사용.
    llm_planner: Annotated[bool | None, _last_wins]

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
    # 누적 키 — 병렬 worker (Send-API) 결과를 fan-in 시 손실 없이 누적 (축6 하드닝).
    # dedupe reducer 가 공유 pre-fork 항목을 key 로 멱등 흡수하고 worker 별 새 항목만
    # 누적 → last_wins 의 "동시 worker 결과 손실"·순수 concat 의 "pre-fork 중복" 동시 회피.
    # clear (replan 비우기) 는 _ClearedDict/_ClearedList 마커로 처리 (이전 롤백 사유 해소).
    # 함수체인 (reducer 미적용) 은 worker 순차 mutate 로 기존과 동일 동작.
    task_results: Annotated[dict, _merge_dict_dedup]
    tool_results: Annotated[list[dict], _concat_dedup_by("task_id")]
    evidence_chunks: Annotated[list[dict], _concat_dedup_by("id")]
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
    # (b) Result-aware replan — Validator 실패 시 mark_replan 이 채우고 planner 가 읽어
    # 전략을 바꾼다. {"n", "prev_kind", "prev_issues", "prev_tools", "prev_grounding"}.
    # 없으면(=첫 turn) 룰 planner 기본 동작. n_replans 와 짝으로 폐회로 증거.
    replan_hint: Annotated[dict, _last_wins]

    # Human-in-the-Loop (PRD §7.5.6)
    pending_interrupt: Annotated[dict, _last_wins]
    interrupt_response: Annotated[Any, _last_wins]
    interrupt_handled: Annotated[bool, _last_wins]

    # 메타·비용
    llm_usage_usd: Annotated[float, _last_wins]
    n_replans: Annotated[int, _last_wins]
    aborted_reason: Annotated[str, _last_wins]
