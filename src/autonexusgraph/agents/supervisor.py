"""Supervisor 노드 — DAG 의존성 충족된 task 를 worker 로 라우팅 (PRD §7.5.2 / §7.5.7).

두 가지 실행 모드:
- 함수 체인 (langgraph 미설치) — supervisor 가 unblocked tasks 를 순차 dispatch.
  의존성 없는 task 도 sequential (LangGraph 가 있어야 진정한 병렬).
- LangGraph (StateGraph) — supervisor 가 ``Send`` 객체 리스트를 yield 하면
  langgraph 가 worker 노드들을 병렬 실행하고 다시 supervisor 로 합류.

turn budget / circuit breaker 체크는 worker 진입 직전에도 다시 한다 (worker 가
호출하는 도구 안에서 LLM 발생 가능).
"""

from __future__ import annotations

import logging

from .dag import (
    all_done,
    make_task,
    task_summary,
    topologically_valid,
    unblocked_tasks,
)
from .policy import turn_budget_exceeded
from .state import AgentState
from .workers import dispatch_one

log = logging.getLogger(__name__)

# ReAct 동적 fan-out 폭주 방지 — 한 turn 에 reflect 가 생성할 수 있는 child 총량 상한.
MAX_DYNAMIC_TASKS = 20


def mid_execution_reflect(state: AgentState) -> bool:
    """ReAct inner loop — 완료된 batch 결과를 관측해 bounded 후속 task 동적 생성.

    diagnosis(축1/3 open-loop의 남은 절반): planner 가 전체 DAG 를 선확정하고 도구
    결과를 보고 후속 task 를 바꾸지 못했다. 이 함수가 supervisor 재진입마다 돌며
    spawn 템플릿(agent="_spawn")의 upstream 이 done 이면 결과 행마다 child 를 펼친다 —
    정적 plan 으로는 크기를 알 수 없던 "발견 기반 확장"(observe→act).

    가드 (자율성 폭주 차단):
      - turn_budget_exceeded → spawn 중단(템플릿 skipped)
      - MAX_DYNAMIC_TASKS → 초과분 drop + safety_signal 기록(silent 절단 금지)
      - 템플릿을 done 으로 표시 → 동일 upstream 재확장 방지(무한 fan-out 차단)
      - child depends_on=[] (upstream 이미 done) → topological 무결성 유지

    Returns: 이번 호출에 child 를 하나라도 생성했으면 True.
    """
    tasks: list[dict] = state.get("tasks") or []
    results = state.get("task_results") or {}
    spawned_any = False

    for tmpl in tasks:
        if tmpl.get("agent") != "_spawn" or tmpl.get("status") != "pending":
            continue
        spec = tmpl.get("spawn") or {}
        from_id = spec.get("from")
        up = next((t for t in tasks if t.get("id") == from_id), None)
        if up is None or up.get("status") != "done":
            continue   # upstream 아직 미완료 — 다음 라운드까지 대기

        if turn_budget_exceeded(state):
            tmpl["status"] = "skipped"
            tmpl["result"] = {"error": "turn_budget"}
            continue

        rows = results.get(from_id)
        rows = rows if isinstance(rows, list) else ([rows] if rows else [])
        field = spec.get("for_each")
        values: list = []
        seen: set = set()
        for r in rows:
            v = r.get(field) if isinstance(r, dict) else None
            if v is not None and v not in seen:
                seen.add(v)
                values.append(v)

        remaining = MAX_DYNAMIC_TASKS - sum(1 for t in tasks if t.get("_dynamic"))
        capped = values[:max(0, remaining)]
        dropped = len(values) - len(capped)

        children: list[dict] = []
        for i, v in enumerate(capped):
            child = make_task(
                f"dyn_{tmpl['id']}_{i}", spec["agent"], spec["intent"],
                {**spec.get("base_args", {}), spec["arg"]: v},
            )
            child["_dynamic"] = True
            children.append(child)

        tasks.extend(children)
        tmpl["status"] = "done"
        tmpl["result"] = {"spawned": len(children), "dropped": dropped,
                          "from": from_id, "field": field}
        if dropped:
            state.setdefault("safety_signals", []).append(
                f"mid_replan_capped:{from_id}:+{len(children)}/-{dropped}")
            log.warning("[reflect] %s — MAX_DYNAMIC_TASKS 초과: %d spawn / %d drop",
                        from_id, len(children), dropped)
        else:
            log.info("[reflect] spawn %d children from %s.%s",
                     len(children), from_id, field)
        spawned_any = spawned_any or bool(children)

    return spawned_any


def supervisor_node(state: AgentState) -> AgentState:
    """함수 체인용 — unblocked tasks 를 모두 sequential dispatch.

    같은 turn 내에서 반복 호출되며 (StateGraph 의 self-loop 와 동일 효과), 더
    이상 unblocked 가 없으면 noop. ``all_done`` 검사로 종결 시점 결정.
    """
    # 사용자가 비용 승인을 거절했으면 worker 도 호출하지 않는다.
    if state.get("aborted_reason") == "cost_rejected":
        for t in state.get("tasks") or []:
            if t.get("status") == "pending":
                t["status"] = "skipped"
                t["result"] = {"error": "cost_rejected"}
        return state

    tasks: list[dict] = state.get("tasks") or []
    if not tasks:
        return state

    if not topologically_valid(tasks):
        log.warning("[supervisor] task DAG 순환·미정의 의존성 — 모두 skipped")
        for t in tasks:
            if t.get("status") == "pending":
                t["status"] = "skipped"
                t["result"] = {"error": "invalid_dag"}
        return state

    while True:
        if turn_budget_exceeded(state):
            log.warning("[supervisor] turn budget exceeded — 잔여 task skip")
            for t in tasks:
                if t.get("status") == "pending":
                    t["status"] = "skipped"
                    t["result"] = {"error": "turn_budget"}
            state["aborted_reason"] = "turn_budget"
            break

        # ReAct — 직전 batch 결과 관측 후 동적 task 생성(spawn 템플릿 펼침).
        mid_execution_reflect(state)

        ready = unblocked_tasks(tasks)
        if not ready:
            break
        # sequential — 의존성 없는 ready 도 한 번에 하나씩.
        # LangGraph Send 경로에서는 sup_send_directives() 가 병렬 dispatch 한다.
        for t in ready:
            if t.get("status") != "pending":
                continue
            t["status"] = "running"
            dispatch_one(state, t)
        # done/failed/skipped 로 옮겨졌으므로 다음 라운드의 unblocked 가 변동
    log.info("[supervisor] tasks done — summary=%s", task_summary(tasks))
    return state


def sup_send_directives(state: AgentState):
    """LangGraph Send API 용 — unblocked tasks 만큼 Send 객체 리스트.

    각 Send 는 worker 노드를 가리키며 args 로 자기 task 를 전달한다. 반환값이
    빈 리스트면 langgraph 가 conditional edge 의 'done' 경로로 이동한다.
    """
    try:
        from langgraph.types import Send  # type: ignore[import-not-found]
    except ImportError:
        try:
            from langgraph.graph import Send  # type: ignore[attr-defined]
        except ImportError:
            return []

    tasks: list[dict] = state.get("tasks") or []
    if not tasks or not topologically_valid(tasks):
        return []
    if turn_budget_exceeded(state):
        return []
    if state.get("aborted_reason") == "cost_rejected":
        return []

    ready = unblocked_tasks(tasks)
    if not ready:
        return []

    # worker 노드명은 graph.py 의 add_node 명과 일치해야 한다.
    NODE_BY_AGENT = {
        "research": "worker_research",
        "graph": "worker_graph",
        "sql": "worker_sql",
        "calculator": "worker_calculator",
    }
    sends = []
    for t in ready:
        agent = str(t.get("agent"))
        if agent == "_spawn":
            # spawn 템플릿은 reflect(supervisor 노드)가 처리 — Send 대상 아님.
            continue
        node = NODE_BY_AGENT.get(agent)
        if not node:
            t["status"] = "skipped"
            t["result"] = {"error": f"unknown agent: {t.get('agent')!r}"}
            continue
        t["status"] = "running"
        # 각 Send 는 child invocation 의 입력 state — task 와 전체 state 모두 전달
        sends.append(Send(node, {**state, "_current_task": t}))
    return sends


def supervisor_done(state: AgentState) -> str:
    """라우터 — 모든 task 완료면 'synth' 로, 아니면 'dispatch' 반복."""
    tasks = state.get("tasks") or []
    if not tasks or all_done(tasks):
        return "done"
    return "dispatch"


__all__ = ["supervisor_node", "sup_send_directives", "supervisor_done",
           "mid_execution_reflect", "MAX_DYNAMIC_TASKS"]
