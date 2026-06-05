"""Worker 노드 4종 — Research / Graph / SQL / Calculator (PRD §7.5.2).

각 worker:
- AgentState + 자기 task 1개 받음
- 자기 도메인 도구만 호출 (도구 외 접근 금지 — 라우팅 단계에서 검증)
- result 채워서 task 갱신
- worker 실패는 state["aborted_reason"] 안 채움 — task.status="failed" 만 표시
  (Supervisor 가 다른 task 로 계속 진행, Validator 가 최종 판단)

PRD §7.5.11 — Calculator 의 Python sandbox 는 e2b/daytona 인프라 도입 시 교체.
이번 PR 은 ``_safe_calculator()`` 의 numexpr 기반 한정 evaluator — exec/eval/import/
attribute access 모두 금지. 사칙연산·비교·numpy 함수만 허용.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .dag import resolve_arg_bindings, update_status
from .state import AgentState

log = logging.getLogger(__name__)


# ── Domain-aware allowed intent + toolbox ────────────────────
# finance 도메인 화이트리스트 — core 의 SSOT. auto 화이트리스트는 외부 패키지
# (autograph) 가 자기 handler 에 보유. core 는 인지하지 않음 (PRD §10.12).
FIN_GRAPH_ALLOWED = {
    "list_subsidiaries", "list_parents", "get_executives",
    "get_companies_of_person", "get_major_shareholders",
    "find_paths", "get_subgraph", "list_mentioning_news",
    "list_cooccurring", "list_group_members", "lookup_person",
}
FIN_SQL_ALLOWED = {
    "lookup_company", "get_company_info", "get_revenue",
    "get_operating_income", "get_balance_sheet_item",
    "compare_companies", "list_companies_by_market",
}
FIN_RESEARCH_INTENTS = {"search_documents", "search_by_metadata", "get_chunk"}


def _domain(state: AgentState) -> str:
    return str(state.get("domain") or "finance").lower()


def _toolbox_for(state: AgentState):
    """도메인별 tool 함수 풀. handler 등록 도메인은 handler.toolbox_modules,
    그 외 (또는 finance) 는 core 의 tools 패키지만.

    handler 호출 실패는 ``call_handler_method`` 가 log + safety_signals 적재
    후 None 반환 → finance 폴백.
    """
    from ._domain_handler import call_handler_method, get_handler
    d = _domain(state)
    result = call_handler_method(state, get_handler(d), "toolbox_modules")
    if result is not None:
        return result
    from .. import tools as fin_tb
    return [fin_tb]


def _resolve_tool(state: AgentState, intent: str):
    """intent 이름으로 도메인별 toolbox 에서 함수 검색."""
    for tb in _toolbox_for(state):
        fn = getattr(tb, intent, None)
        if fn is not None:
            return fn
    return None


def _allowed_intents(state: AgentState, kind: str) -> set[str]:
    """kind 별 (graph|sql|research) 화이트리스트 — handler 가 자기 분량 보유.

    handler 호출 실패는 ``call_handler_method`` 가 log + safety_signals 적재.
    signal_extra=kind 로 어떤 kind 에서 실패했는지 보존.
    """
    from ._domain_handler import call_handler_method, get_handler
    d = _domain(state)
    result = call_handler_method(state, get_handler(d), "allowed_intents", kind,
                                 signal_extra=kind)
    if result is not None:
        return result
    # finance 기본 화이트리스트.
    if kind == "graph":
        return FIN_GRAPH_ALLOWED
    if kind == "sql":
        return FIN_SQL_ALLOWED
    if kind == "research":
        return FIN_RESEARCH_INTENTS
    return set()


def _maybe_inject_rerank(state: AgentState, fn, args: dict) -> None:
    """state['rerank'] (평가 매트릭스 ablation) → 검색 함수 args 에 전파.

    None (기본 production) 이면 미주입 → 도구 자체 default(rerank=True) 사용.
    함수가 ``rerank`` 파라미터를 받을 때만 주입 — get_chunk/search_by_metadata 등
    rerank 없는 retrieve 함수에 TypeError 를 내지 않도록 inspect 로 가드.
    args 에 이미 값이 있으면 보존(setdefault).
    """
    rr = state.get("rerank")
    if rr is None or fn is None:
        return
    try:
        import inspect
        if "rerank" in inspect.signature(fn).parameters:
            args.setdefault("rerank", rr)
    except (TypeError, ValueError):   # signature 추출 불가 — 안전하게 미주입.
        pass


# ── Research worker ─────────────────────────────────────────
def research_worker(state: AgentState, task: dict) -> AgentState:
    """벡터 검색 (pgvector + 메타 필터).

    submodule import 패턴 — 테스트에서 patch('autonexusgraph.tools.retrieve.search_documents')
    또는 patch('autograph.tools.retrieve.search_documents_auto') 가 정상 작동하도록.
    """
    from ..tools.retrieve import get_chunk, search_by_metadata, search_documents

    intent = task.get("intent") or "search"
    args = resolve_arg_bindings(state, task.get("args"))   # (a) closed-loop 데이터 흐름
    domain = _domain(state)

    # 도메인 handler 의 retrieve 모듈에 해당 intent 가 있으면 그쪽 위임.
    # (autograph 의 search_documents_auto / search_by_metadata_auto / get_chunk_auto 등)
    from ._domain_handler import call_handler_method, get_handler
    retrieve_mod = call_handler_method(state, get_handler(domain), "retrieve_module")
    fn = getattr(retrieve_mod, intent, None) if retrieve_mod else None
    if fn is not None:
        args.setdefault("query", state.get("question_rewritten") or state.get("question", ""))
        _maybe_inject_rerank(state, fn, args)
        try:
            out = fn(**args)
            _record(state, task, status="done", result=out)
            if isinstance(out, list):
                state.setdefault("evidence_chunks", []).extend(out)
        except Exception as exc:   # noqa: BLE001 — worker tool 호출 실패 흡수 → log + 다음 task 진행
            log.warning("[research:%s] %s failed: %s", domain, intent, exc)
            _record(state, task, status="failed", result={"error": str(exc)})
        return state

    # finance (또는 unknown intent) — 기존 동작 보존.
    try:
        if intent == "search_documents":
            _maybe_inject_rerank(state, search_documents, args)
            out = search_documents(**args)
        elif intent == "search_by_metadata":
            out = search_by_metadata(**args)
        elif intent == "get_chunk":
            out = get_chunk(**args)
        else:
            # 기본은 search_documents — args 에 query 가 있어야 함
            args.setdefault("query", state.get("question_rewritten") or state.get("question", ""))
            _maybe_inject_rerank(state, search_documents, args)
            out = search_documents(**args)
        _record(state, task, status="done", result=out)
        if isinstance(out, list):
            state.setdefault("evidence_chunks", []).extend(out)
    except Exception as exc:   # noqa: BLE001 — worker tool 호출 실패 흡수 → log + 다음 task 진행
        log.warning("[research] %s failed: %s", intent, exc)
        _record(state, task, status="failed", result={"error": str(exc)})
    return state


# ── Graph worker ────────────────────────────────────────────
def graph_worker(state: AgentState, task: dict) -> AgentState:
    """Neo4j 관계 탐색 (cypher_guard 통과). args 의 intent 가 함수명. 도메인 인식."""
    intent = task.get("intent") or ""
    args = resolve_arg_bindings(state, task.get("args"))   # (a) closed-loop 데이터 흐름

    allowed = _allowed_intents(state, "graph")
    if intent not in allowed:
        _record(state, task, status="skipped",
                result={"error": f"graph intent 미허용 (domain={_domain(state)}): {intent!r}"})
        return state
    fn = _resolve_tool(state, intent)
    if fn is None:
        _record(state, task, status="failed", result={"error": f"no such tool: {intent}"})
        return state
    try:
        out = fn(**args)
        _record(state, task, status="done", result=out)
        if intent == "get_subgraph":
            state["graph_subgraph"] = out
    except Exception as exc:   # noqa: BLE001 — worker tool 호출 실패 흡수 → log + 다음 task 진행
        log.warning("[graph] %s failed: %s", intent, exc)
        _record(state, task, status="failed", result={"error": str(exc)})
    return state


# ── SQL worker ──────────────────────────────────────────────
def sql_worker(state: AgentState, task: dict) -> AgentState:
    """PG 정형 조회. 사전 정의 함수 풀만 (PRD §7.5.10). 도메인 인식."""
    intent = task.get("intent") or ""
    args = resolve_arg_bindings(state, task.get("args"))   # (a) closed-loop 데이터 흐름

    allowed = _allowed_intents(state, "sql")
    if intent not in allowed:
        _record(state, task, status="skipped",
                result={"error": f"sql intent 미허용 (domain={_domain(state)}): {intent!r}"})
        return state
    fn = _resolve_tool(state, intent)
    if fn is None:
        _record(state, task, status="failed", result={"error": f"no such tool: {intent}"})
        return state
    try:
        out = fn(**args)
        _record(state, task, status="done", result=out)
    except Exception as exc:   # noqa: BLE001 — worker tool 호출 실패 흡수 → log + 다음 task 진행
        log.warning("[sql] %s failed: %s", intent, exc)
        _record(state, task, status="failed", result={"error": str(exc)})
    return state


# ── Calculator worker ───────────────────────────────────────
# 안전 evaluator — exec/eval/import/attribute access 금지.
# Python sandbox (e2b/daytona) 도입 전 1차 구현. 사칙연산·비교·numpy 함수만.
_EXPR_ALLOWED_RE = re.compile(
    r"^[\d\s\.,\+\-\*\/\%\(\)\<\>\=\!\&\|\^a-zA-Z_]+$"
)


def calculator_worker(state: AgentState, task: dict) -> AgentState:
    """수식 평가. task.args:
       - expr: str — 평가할 수식 (필수)
       - variables: dict[str, number] — expr 안 변수 바인딩 (선택)
       - aggregate: 'sum'|'mean'|'max'|'min'|'count' + over: list — 집계 (선택)
    """
    args = resolve_arg_bindings(state, task.get("args"))   # (a) closed-loop — over 등 upstream 바인딩

    try:
        if "aggregate" in args and "over" in args:
            result = _aggregate(args["aggregate"], args["over"])
        else:
            result = _safe_calculator(
                args.get("expr") or "",
                args.get("variables") or {},
            )
        _record(state, task, status="done", result={"value": result})
    except Exception as exc:   # noqa: BLE001 — worker tool 호출 실패 흡수 → log + 다음 task 진행
        log.warning("[calculator] failed: %s", exc)
        _record(state, task, status="failed", result={"error": str(exc)})
    return state


def _safe_calculator(expr: str, variables: dict) -> float:
    """numexpr 기반 안전 평가. numexpr 미설치 시 ImportError 가 그대로 raise.

    eval() fallback 은 의도적으로 제거 — guarded eval 도 잠재 우회 경로 (e.g.
    f-string, walrus) 가 있어 sandbox 가 아닌 환경에서 사용 위험.
    """
    if not expr or not isinstance(expr, str):
        raise ValueError("expr 필요")
    # 1차 정적 가드 — 허용 문자만
    if not _EXPR_ALLOWED_RE.match(expr):
        raise ValueError(f"허용되지 않은 문자 포함: {expr!r}")
    # 위험 키워드 차단
    BAD = ("import", "exec", "eval", "open", "__", "lambda", "compile",  # noqa: N806 — 지역 상수(블랙리스트)
           "globals", "locals", "vars", "getattr", "setattr", "delattr",
           "type", "object", "subprocess", "os.")
    for w in BAD:
        if w in expr:
            raise ValueError(f"금지 키워드: {w}")
    # 변수 타입 검증 — number 만
    safe_vars: dict[str, float] = {}
    for k, v in (variables or {}).items():
        if not isinstance(k, str) or not k.isidentifier():
            raise ValueError(f"식별자 아닌 변수: {k!r}")
        if not isinstance(v, (int, float)):
            raise ValueError(f"숫자 아닌 변수값: {k}={v!r}")
        safe_vars[k] = float(v)

    try:
        import numexpr  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "calculator_worker 는 numexpr 의존 — `pip install numexpr` 필요. "
            "(eval() fallback 은 보안상 제거됨)"
        ) from e
    return float(numexpr.evaluate(expr, local_dict=safe_vars, global_dict={}).item())


def _aggregate(op: str, values: list) -> float:
    nums = [float(v) for v in values if isinstance(v, (int, float))]
    if not nums:
        return 0.0
    if op == "sum":
        return sum(nums)
    if op == "mean":
        return sum(nums) / len(nums)
    if op == "max":
        return max(nums)
    if op == "min":
        return min(nums)
    if op == "count":
        return float(len(nums))
    raise ValueError(f"미지원 집계: {op}")


# ── 공통 기록 헬퍼 ──────────────────────────────────────────
def _record(state: AgentState, task: dict, *,
            status: str, result: Any) -> None:
    """task.status / task.result 갱신 + state.task_results / tool_results 누적."""
    tasks = state.get("tasks") or []
    update_status(tasks, task["id"], status, result=result)
    task_results = state.setdefault("task_results", {})
    task_results[task["id"]] = result
    # 기존 호환 — synthesizer 가 tool_results 를 참조하므로 그대로 채움
    state.setdefault("tool_results", []).append({
        "tool": task.get("intent"),
        "purpose": task.get("intent"),
        "args": task.get("args"),
        "result": result,
        "agent": task.get("agent"),
        "task_id": task.get("id"),
        "status": status,
    })


# ── Worker 디스패치 테이블 ──────────────────────────────────
WORKER_BY_AGENT = {
    "research": research_worker,
    "graph": graph_worker,
    "sql": sql_worker,
    "calculator": calculator_worker,
}


def dispatch_one(state: AgentState, task: dict) -> AgentState:
    """단일 task 의 agent 에 맞는 worker 호출. agent 미지정 시 skipped."""
    agent = task.get("agent")
    worker = WORKER_BY_AGENT.get(str(agent))
    if worker is None:
        _record(state, task, status="skipped",
                result={"error": f"unknown agent: {agent!r}"})
        return state
    return worker(state, task)


__all__ = [
    "research_worker",
    "graph_worker",
    "sql_worker",
    "calculator_worker",
    "dispatch_one",
    "WORKER_BY_AGENT",
]
