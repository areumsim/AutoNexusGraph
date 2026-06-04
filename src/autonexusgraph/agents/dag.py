"""task DAG 보조 함수 — Supervisor / Send API 용.

PRD §7.5.3 의 tasks 스키마:
    {"id": str, "agent": AgentName, "intent": str, "args": dict,
     "depends_on": list[str], "status": TaskStatus, "result": Any}

DAG 자체는 list 로 직렬화돼 AgentState["tasks"] 에 들어간다 (LangGraph
state 가 dict 만 받기 때문에 graph object 는 안 만든다). 의존성·실행 순서는
이 모듈의 함수들이 결정한다.
"""

from __future__ import annotations

from typing import Iterable


def make_task(
    task_id: str,
    agent: str,
    intent: str,
    args: dict | None = None,
    depends_on: list[str] | None = None,
) -> dict:
    """tasks 항목 생성 — 기본 status='pending', result=None."""
    return {
        "id": task_id,
        "agent": agent,
        "intent": intent,
        "args": args or {},
        "depends_on": list(depends_on or []),
        "status": "pending",
        "result": None,
    }


def unblocked_tasks(tasks: list[dict]) -> list[dict]:
    """의존성 충족 + 아직 pending 인 task 들. Supervisor 가 다음 디스패치 대상."""
    done_ids = {t["id"] for t in tasks if t.get("status") == "done"}
    out: list[dict] = []
    for t in tasks:
        if t.get("status") != "pending":
            continue
        deps = t.get("depends_on") or []
        if all(d in done_ids for d in deps):
            out.append(t)
    return out


def all_done(tasks: list[dict]) -> bool:
    """모든 task 가 done / failed / skipped — Supervisor 가 다음 단계로 이동."""
    if not tasks:
        return True
    return all(t.get("status") in ("done", "failed", "skipped") for t in tasks)


def get_task(tasks: list[dict], task_id: str) -> dict | None:
    for t in tasks:
        if t.get("id") == task_id:
            return t
    return None


def update_status(tasks: list[dict], task_id: str, status: str,
                  result: object | None = None) -> list[dict]:
    """status / result 갱신. 원본 리스트를 in-place 수정 (state 도 같은 list 참조)."""
    for t in tasks:
        if t.get("id") == task_id:
            t["status"] = status
            if result is not None:
                t["result"] = result
            return tasks
    return tasks


def task_summary(tasks: list[dict]) -> dict:
    """디버그·로깅용 카운트."""
    out: dict[str, int] = {}
    for t in tasks:
        st = str(t.get("status") or "pending")
        out[st] = out.get(st, 0) + 1
    out["total"] = len(tasks)
    return out


def topologically_valid(tasks: list[dict]) -> bool:
    """순환 의존성이 없는지 — DAG 무결성 정적 검증."""
    ids = {t["id"] for t in tasks}
    # 알 수 없는 dep 참조 → invalid
    for t in tasks:
        for d in t.get("depends_on") or []:
            if d not in ids:
                return False
    # cycle 검출 — 간단한 DFS
    visited: set[str] = set()
    stack: set[str] = set()

    def _dfs(node: str, by_id: dict[str, dict]) -> bool:
        if node in stack:
            return False
        if node in visited:
            return True
        stack.add(node)
        for d in by_id[node].get("depends_on") or []:
            if not _dfs(d, by_id):
                return False
        stack.discard(node)
        visited.add(node)
        return True

    by_id = {t["id"]: t for t in tasks}
    return all(_dfs(t["id"], by_id) for t in tasks)


def filter_by_agent(tasks: Iterable[dict], agent: str) -> list[dict]:
    return [t for t in tasks if t.get("agent") == agent]


# ── (a) Closed-loop 데이터 흐름 — upstream 결과를 dependent task args 로 ──────
def _resolve_binding(result: object, spec: dict) -> object:
    """단일 바인딩 spec 을 upstream task 결과(result)로부터 값 추출.

    result 는 보통 list[dict] (graph/sql/research 결과 행들). field 미지정이면 행 자체.
    - collect=True → 모든 행의 field 값 list (None 제외)
    - index=N      → N 번째 행의 field 값
    - 기본          → 첫 행의 field 값
    참조 불가(미완료·None·index 초과·값 None) → spec["default"] (기본 None).
    """
    field = spec.get("field")
    if isinstance(result, list):
        rows = result
    elif result is None:
        rows = []
    else:
        rows = [result]

    def _pick(row: object) -> object:
        if field is None:
            return row
        return row.get(field) if isinstance(row, dict) else None

    if spec.get("collect"):
        return [x for x in (_pick(r) for r in rows) if x is not None]
    idx = int(spec.get("index") or 0)
    if 0 <= idx < len(rows):
        val = _pick(rows[idx])
        if val is not None:
            return val
    return spec.get("default")


def resolve_arg_bindings(state: dict, args: dict | None) -> dict:
    """task args 안의 upstream 결과 참조(``$from``)를 실제 값으로 치환.

    PRD §7.5.3 의 depends_on 을 **선언만** 이 아니라 **데이터가 흐르게** 만드는 핵심.
    worker 가 도구를 부르기 직전 호출 — dependent task 가 이미 done 된 upstream task 의
    결과를 args 로 받는다 (open-loop → closed-loop).

    바인딩 형식 — arg 값이 dict 이며 ``$from`` 키를 가지면 upstream 참조:
        {"$from": "g_1", "field": "child_corp_code"}                  # 첫 행 (scalar)
        {"$from": "g_1", "field": "child_corp_code", "collect": True} # 모든 행 (list)
        {"$from": "g_1", "field": "x", "index": 2}                    # 특정 행
        {"$from": "g_1"}                                              # 결과 전체

    upstream 결과는 ``state["task_results"][task_id]``. 바인딩이 아닌 값은 그대로 통과.
    항상 새 dict 반환 (원본 task args 불변).
    """
    results = state.get("task_results") or {}
    out: dict = {}
    for k, v in (args or {}).items():
        if isinstance(v, dict) and "$from" in v:
            out[k] = _resolve_binding(results.get(v.get("$from")), v)
        else:
            out[k] = v
    return out


__all__ = [
    "make_task",
    "unblocked_tasks",
    "all_done",
    "get_task",
    "update_status",
    "task_summary",
    "topologically_valid",
    "filter_by_agent",
    "resolve_arg_bindings",
]
