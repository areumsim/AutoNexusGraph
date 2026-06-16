"""축2: LLM 자율 planner — 룰 템플릿 대신 LLM 이 task DAG 를 제안 (plan-and-execute).

diagnosis(축2 미흡): planner/triage 가 LLM 0 룰엔진 — 도구 선택이 자율이 아니라 고정
분기였다. 이 모듈은 LLM 이 질문을 task DAG 로 분해하게 하되, **화이트리스트
검증**(workers._allowed_intents)을 안전 게이트로 강제한다. 자율성은 살리되 폭주는 막는다.

안전 원칙:
- opt-in (settings.agent_llm_planner). 기본 비활성 — 룰 planner 가 검증된 기본값.
- 화이트리스트 밖 intent 는 drop (cypher/SQL 자유생성 불가 — PRD §7.5.9/§7.5.10 유지).
- topological 무결성(순환·미정의 dep) 위반 시 전체 폐기 → 룰 폴백.
- budget guard + fail-soft: LLM 실패/빈결과/예산초과 → None 반환 → 호출부가 룰 폴백.
- 잘못된 args 로 도구가 실패해도 validator→replan(b) / 빈결과 회복(d) 이 잡는다
  (closed-loop 와의 시너지 — LLM plan 이 안전하게 실패·복구된다).
"""

from __future__ import annotations

import logging
from typing import Any

from .dag import make_task, topologically_valid
from .state import AgentState

log = logging.getLogger(__name__)

_WORKER_AGENTS = ("research", "graph", "sql", "calculator")

# chat_json 강제 스키마 — task DAG.
PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "agent": {"type": "string", "enum": list(_WORKER_AGENTS)},
                    "intent": {"type": "string"},
                    "args": {"type": "object"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["agent", "intent"],
            },
        },
    },
    "required": ["tasks"],
}

_SYSTEM = (
    "당신은 그래프 RAG 시스템의 계획 에이전트다. 사용자 질문을 도구 task 들의 DAG 로 "
    "분해한다. 규칙:\n"
    "1) 아래 '허용 도구' 목록에 있는 (agent, intent) 만 사용. **intent 는 반드시 enum "
    "중 하나의 정확한 식별자**여야 한다 — 자연어 description 금지. 예: "
    "intent='lookup_company'(O) / intent='회사 매출 조회'(X — drop 됨).\n"
    "2) 의존이 있으면 depends_on 에 선행 task 의 id 를 넣어라(예: SQL 이 그래프 결과 필요).\n"
    "3) args 는 도구가 받는 인자명으로. 회사는 corp_code(8자리), 연도는 year(정수).\n"
    "4) calculator 사용 시 args 에 **반드시 expr(수식 문자열) 또는 aggregate+over(집계+값목록)** "
    "둘 중 하나를 채워라. 예: args={'expr': '(a-b)/b*100', 'variables': {'a': 100, 'b': 80}}.\n"
    "5) 불필요한 task 를 만들지 말고 질문에 답하기 위한 최소 DAG 만.\n"
    "6) 반드시 JSON 으로만 응답."
)


def _tool_catalog(state: AgentState) -> dict[str, list[str]]:
    """도메인별 허용 intent 목록 — 화이트리스트(workers._allowed_intents) 그대로."""
    from .workers import _allowed_intents
    cat: dict[str, list[str]] = {}
    for kind in ("graph", "sql", "research"):
        try:
            cat[kind] = sorted(_allowed_intents(state, kind))
        except Exception:   # noqa: BLE001 — handler 미등록/실패 흡수 → 빈 intent list (LLM planner 가 빈 카탈로그 받음)
            cat[kind] = []
    cat["calculator"] = ["evaluate", "aggregate"]   # 샌드박스 — intent 자유(검증 면제)
    return cat


def _validate_tasks(state: AgentState, raw_tasks: list, catalog: dict[str, list[str]]
                    ) -> list[dict]:
    """LLM 산출 task 들을 화이트리스트·구조 검증 후 정규화. 위반 task 는 drop."""
    from .workers import _allowed_intents

    allowed_by_kind = {
        "graph": set(_safe(lambda: _allowed_intents(state, "graph"))),
        "sql": set(_safe(lambda: _allowed_intents(state, "sql"))),
        "research": set(_safe(lambda: _allowed_intents(state, "research"))),
    }
    out: list[dict] = []
    used_ids: set[str] = set()
    dropped: list[str] = []
    for i, t in enumerate(raw_tasks or []):
        if not isinstance(t, dict):
            continue
        agent = str(t.get("agent") or "").strip()
        intent = str(t.get("intent") or "").strip()
        if agent not in _WORKER_AGENTS or not intent:
            dropped.append(f"{agent}:{intent}")
            continue
        # 화이트리스트 — graph/sql/research 는 강제, calculator 는 샌드박스라 면제.
        if agent in allowed_by_kind and intent not in allowed_by_kind[agent]:
            dropped.append(f"{agent}:{intent}")
            continue
        tid = str(t.get("id") or "").strip() or f"p{i+1}"
        while tid in used_ids:
            tid = f"{tid}_{i}"
        used_ids.add(tid)
        _args_raw = t.get("args")
        args = _args_raw if isinstance(_args_raw, dict) else {}
        # calculator 사전 가드 (BACKLOG A-8) — expr 도 aggregate 도 없으면 worker
        # 가 '[calculator] failed: expr 필요' 로 떨어지므로 미리 drop.
        if agent == "calculator" and not args.get("expr") and not args.get("aggregate"):
            dropped.append("calculator:no_expr_or_aggregate")
            continue
        deps = [str(d) for d in (t.get("depends_on") or []) if isinstance(d, (str, int))]
        out.append(make_task(tid, agent, intent, args, depends_on=deps))

    # depends_on 정합 — 산출 집합 밖을 가리키는 dep 제거(고아 참조 방지).
    ids = {t["id"] for t in out}
    for t in out:
        t["depends_on"] = [d for d in t["depends_on"] if d in ids and d != t["id"]]

    if dropped:
        state.setdefault("safety_signals", []).append(
            f"llm_planner_dropped:{','.join(dropped[:5])}")
        log.warning("[llm_planner] 화이트리스트 밖 %d task drop: %s",
                    len(dropped), dropped[:5])
    return out


def try_llm_plan(state: AgentState, *, kind: str, targets: list,
                 year_hint: int | None, q: str,
                 replan_hint: dict | None = None,
                 persons: list | None = None,
                 company_names: list | None = None,
                 makes: list | None = None) -> list[dict] | None:
    """LLM 으로 task DAG 제안 → 검증된 tasks 또는 None(폴백).

    None 반환 조건: 비활성·budget 초과·LLM 실패·빈/전부무효·topological 위반.
    """
    if not q:
        return None
    from .policy import turn_budget_exceeded
    if turn_budget_exceeded(state):
        return None

    catalog = _tool_catalog(state)
    targets_line = ", ".join(map(str, targets)) if targets else "(미식별)"
    persons_line = ", ".join(map(str, persons)) if persons else "(없음)"
    # 수치 랭킹 힌트는 랭킹 질문에만 노출 — 비-랭킹 질문(GMH/GMI 등)에 길게 실으면
    # planner 가 compare_companies 로 오라우팅돼 회귀(main 62 −24pp 관측). 키워드 게이트.
    _q_rank = q or ""
    _is_ranking = any(k in _q_rank for k in (
        "가장 큰", "가장 작은", "가장 높은", "가장 낮은", "최대", "최소",
        "가장 많은", "가장 적은", "최고", "최저"))
    # 관계기업·공동기업(지분법 피투자, 5~50%) 질문 — RELATED_TO. 자회사(SUBSIDIARY_OF)와 구분.
    _is_related = any(k in _q_rank for k in (
        "관계기업", "공동기업", "피투자", "지분법", "유의적인 영향력", "공동지배"))
    # 제조사 리콜 결함유형(auto 4-hop non-local) — Manufacturer→Model→Recall→DefectType.
    _is_defect = any(k in _q_rank for k in ("결함 유형", "결함유형", "결함 종류", "결함종류"))
    company_names_line = ", ".join(map(str, company_names)) if company_names else "(없음)"
    makes_line = ", ".join(map(str, makes)) if makes else "(없음)"
    hint_line = ""
    if replan_hint:
        issues = (replan_hint.get("prev_issues") or [])[:3]
        hint_line = (f"\n[이전 계획 실패] 이슈={issues} — 다른 전략(다른 도구/더 넓은 "
                     f"검색/추가 근거)으로 재계획하라.")
    # 각 agent 의 intent enum 을 강조 ([] 가 아닌 list 그대로 노출하면 LLM 이
    # 자연어 description 으로 오인하는 사례 다수 — eval matrix 2026-06-05 발견.
    # 명시적 "intent enum 정확히:" prefix 로 catalog 가 enum 임을 강조.
    def _enum_line(agent: str) -> str:
        items = catalog.get(agent) or []
        if not items:
            return f"- {agent}: (사용 가능 intent 없음 — 이 agent 호출 금지)"
        return f"- {agent} intent enum (정확히 하나 선택): {items}"

    user_msg = (
        f"[질문]\n{q}\n\n"
        f"[도메인] {state.get('domain') or 'finance'}\n"
        f"[질문유형(참고)] {kind}\n"
        f"[대상 회사 corp_code] {targets_line}\n"
        f"[대상 인물(이름)] {persons_line} — 인물 출발 질문이면 graph `get_companies_of_person`"
        f"(name=인물) 으로 소속 회사를 먼저 구하고, 후속 graph 도구의 corp_code 인자는"
        f" `{{\"$from\":\"<해당 task id>\",\"field\":\"corp_code\"}}` 바인딩으로 연결하라.\n"
        f"[대상 회사명(corp_code 미상)] {company_names_line} — corp_code 가 없는 출발 회사"
        f"(자회사 등)다. '…의 모회사' 질문이면 graph `list_parents`"
        f"(child_corp_code_or_name=회사명) 으로 모회사를 먼저 구하고, 후속 graph 도구"
        f"(`get_executives` 등)의 corp_code 인자는 `{{\"$from\":\"<list_parents task id>\","
        f"\"field\":\"parent_corp_code\"}}` 바인딩으로 연결하라.\n"
        f"[대상 제조사] {makes_line} — '…가 제조한 차종 중 리콜' 류 질문이면 graph "
        f"`list_recalled_models_by_manufacturer`(make_name=제조사) 한 번으로 리콜된 차종명을 구하라.\n"
        + (("[제조사 리콜 결함유형] '…제조사 차종 리콜의 결함 유형' 질문이면 graph "
            "`list_defect_types_by_manufacturer`(make_name=제조사) 한 번으로 결함유형을 구하라.\n")
           if _is_defect else "")
        + (("[관계기업·공동기업] '…의 관계기업/공동기업/피투자회사' 처럼 지분법 피투자(5~50%) "
            "회사를 묻는 질문이다. graph `list_related_companies`(corp_code=대상회사) 로 구하라 — "
            "`list_subsidiaries`(자회사=50%+)와 구분된다.\n") if _is_related else "")
        + ((
            "[수치 랭킹 — graph+SQL cross-store] 여러 회사를 수치로 비교·랭킹하는 질문이다. "
            "① 먼저 graph 로 후보 회사들을 구하고(예: `get_companies_of_person`·`list_subsidiaries`) "
            "② sql `compare_companies` 한 번으로 `corp_codes` 인자에 "
            "`{\"$from\":\"<graph task id>\",\"field\":\"corp_code\",\"collect\":true}` "
            "(collect=true 로 후보 전체를 리스트 전달) + year + metric('revenue'|'operating_income') 을 "
            "넣어 전 회사 값을 한 번에 받아라 — get_revenue 를 회사마다 따로 만들지 말 것(fan-out 미지원). "
            "calculator 도 만들지 말 것 — 최대/최소 선택은 합성 단계가 처리한다.\n"
        ) if _is_ranking else "")
        + f"[연도 hint] {year_hint if year_hint else '(없음)'}\n\n"
        f"[허용 도구]\n"
        f"{_enum_line('research')}\n"
        f"{_enum_line('graph')}\n"
        f"{_enum_line('sql')}\n"
        f"- calculator: args 에 'expr' (수식 문자열, 필수) 또는 'aggregate'+'over' "
        f"(집계 op + 값 list, 대안). expr 누락 시 task fail.\n"
        f"{hint_line}"
    )

    try:
        from ..config import turn_budget_for_domain
        from ..llm.base import get_llm_client
        from ..llm.budget_aware import budget_aware_client
        from ..llm.cost_tracker import BudgetExceeded
    except ImportError as exc:   # pragma: no cover
        log.debug("[llm_planner] llm import 실패 — 폴백: %s", exc)
        return None

    # planner LLM 은 cheap 하게 — turn budget 과 0.05 중 작은 값으로 hard_limit.
    hard = min(0.05, turn_budget_for_domain(state.get("domain")))
    try:
        client = budget_aware_client(
            get_llm_client(role="planner"), caller="agent_plan", hard_limit=hard,
        )
        result = client.chat_json(
            [{"role": "system", "content": _SYSTEM},
             {"role": "user", "content": user_msg}],
            PLAN_SCHEMA, temperature=0.0, purpose="plan",
        )
    except BudgetExceeded:
        state.setdefault("safety_signals", []).append("llm_planner_budget")
        return None
    except Exception as exc:   # noqa: BLE001 — fail-soft → 룰 폴백
        log.warning("[llm_planner] LLM 실패 (fail-soft): %s: %s",
                    type(exc).__name__, exc)
        return None

    raw_tasks = result.get("tasks") if isinstance(result, dict) else None
    if not isinstance(raw_tasks, list) or not raw_tasks:
        return None

    tasks = _validate_tasks(state, raw_tasks, catalog)
    if not tasks:
        return None
    if not topologically_valid(tasks):
        log.warning("[llm_planner] topological 무결성 위반 — 전체 폐기, 룰 폴백")
        state.setdefault("safety_signals", []).append("llm_planner_cycle")
        return None
    log.info("[llm_planner] LLM 자율 plan 채택 — tasks=%d", len(tasks))
    return tasks


def _safe(fn):
    try:
        return fn() or []
    except Exception:   # noqa: BLE001 — generic safe wrapper (fn 모든 실패 흡수 → 빈 list)
        return []


__all__ = ["try_llm_plan", "PLAN_SCHEMA"]
