"""에이전트 노드들 — Triage / Planner / Executor / Synthesizer.

각 노드는 AgentState → AgentState (mutation 후 return). LangGraph 도입 시 StateGraph 의
node 로 그대로 등록 가능.

cost guard 적용 원칙 (사용자 명시):
- 모든 LLM 노드 (Planner / Synthesizer 등) 는 budget_aware_client 사용.
- 노드 진입 시 turn_budget_exceeded(state) 체크 → 초과면 즉시 fallback 답변으로 점프.

현재 단계 (Phase 4 골격):
- Triage: 룰 기반 (LLM 0). policy.classify_question 만 호출.
- Planner: 룰 기반 (LLM 0) — policy.select_tools 만 호출. 향후 LLM 으로 업그레이드 가능.
- Executor: tools/ 함수 직접 호출. LLM 0.
- Synthesizer: LLM 호출 — 답변 합성.
"""

from __future__ import annotations

import logging
from typing import Any

from .policy import classify_question, select_tools, turn_budget_exceeded
from .state import AgentState


log = logging.getLogger(__name__)


# ── Triage ──────────────────────────────────────────────────
def triage_node(state: AgentState) -> AgentState:
    """질문 유형 분류 + 1차 회사 식별."""
    from ..tools.financials import lookup_company as lookup_pg

    q = state.get("question", "")
    kind = classify_question(q)
    state["question_kind"] = kind

    # 회사 식별 — 질문에서 회사명 후보 추출 + lookup_company
    targets: list[str] = []
    # 간단한 후보 추출: 명사 형태소가 없으므로 흔한 회사명 패턴 시도. 후속 LLM 보강 여지.
    for word in q.split():
        if len(word) >= 2:
            try:
                hits = lookup_pg(word, limit=1)
            except Exception:
                hits = []
            for h in hits:
                if h.get("corp_code") and h["corp_code"] not in targets:
                    targets.append(h["corp_code"])
                    break
        if len(targets) >= 5:
            break
    state["target_companies"] = targets
    log.info(f"[triage] kind={kind} targets={targets}")
    return state


# ── Planner ─────────────────────────────────────────────────
def planner_node(state: AgentState) -> AgentState:
    """질문 유형 + 회사 → 실행 계획. 현재는 룰 기반."""
    kind = state.get("question_kind") or "unknown"
    targets = state.get("target_companies") or []
    tools = select_tools(kind)

    plan: list[dict] = []

    if "lookup_company" in tools and targets:
        # 이미 triage 에서 식별. plan 에 굳이 안 넣음.
        pass

    if "list_subsidiaries" in tools and targets:
        for cc in targets:
            plan.append({"tool": "list_subsidiaries",
                         "args": {"parent_corp_code": cc, "limit": 20},
                         "purpose": "자회사 그래프"})

    if "get_executives" in tools and targets:
        for cc in targets:
            plan.append({"tool": "get_executives",
                         "args": {"corp_code": cc, "limit": 30},
                         "purpose": "임원진"})

    if "get_companies_of_person" in tools:
        # 멀티홉 인물 질문 — 룰로 인물명 추출은 어려우므로 사용자가 명시한 경우만 (후속 LLM)
        pass

    if "get_major_shareholders" in tools and targets:
        for cc in targets:
            plan.append({"tool": "get_major_shareholders",
                         "args": {"corp_code": cc, "limit": 10},
                         "purpose": "최대주주"})

    if "get_revenue" in tools and targets:
        for cc in targets:
            plan.append({"tool": "get_revenue",
                         "args": {"corp_code": cc, "year": _extract_year(state.get("question", ""))},
                         "purpose": "매출"})

    if "search_documents" in tools and state.get("question"):
        plan.append({
            "tool": "search_documents",
            "args": {
                "query": state["question"],
                "top_k": 6,
                "corp_code": targets[0] if len(targets) == 1 else (targets or None),
            },
            "purpose": "본문 의미 검색",
        })

    state["plan"] = plan
    log.info(f"[planner] {len(plan)} 단계 plan")
    return state


def _extract_year(q: str) -> int | None:
    import re
    m = re.search(r"(20\d{2})", q or "")
    return int(m.group(1)) if m else None


# ── Executor ────────────────────────────────────────────────
def executor_node(state: AgentState) -> AgentState:
    """plan 의 도구들을 순차 호출. 도구는 LLM 비호출."""
    from .. import tools as toolbox

    results: list[dict] = []
    evidence: list[dict] = []
    plan = state.get("plan") or []

    for step in plan:
        if turn_budget_exceeded(state):
            log.warning("[executor] turn budget exceeded — skip remaining")
            state["aborted_reason"] = "turn_budget"
            break
        tool_name = step.get("tool")
        args = step.get("args") or {}
        fn = getattr(toolbox, tool_name, None)
        if fn is None:
            log.warning(f"[executor] unknown tool: {tool_name}")
            continue
        try:
            out = fn(**args)
        except Exception as e:
            log.warning(f"[executor] {tool_name} failed: {e}")
            continue
        item = {"tool": tool_name, "purpose": step.get("purpose"), "args": args,
                "result": out}
        results.append(item)
        if tool_name == "search_documents":
            evidence.extend(out or [])

    state["tool_results"] = results
    state["evidence_chunks"] = evidence
    return state


# ── Synthesizer ─────────────────────────────────────────────
def synthesizer_node(state: AgentState,
                     *, llm_role: str = "synthesizer") -> AgentState:
    """tool_results + evidence_chunks → 자연어 답변 (LLM).

    cost guard: budget_aware_client + tracker 자동 통합.
    aborted_reason 이 있으면 fallback 답변 (LLM 비호출).
    """
    # 비용/예산 초과 → LLM 호출 안 하고 결정적 brief 로 fallback.
    if state.get("aborted_reason") == "turn_budget":
        from .answering import build_deterministic_brief
        state["answer"] = (
            "이번 응답에서 사전 정의된 LLM 비용 한도를 초과했습니다.\n"
            "도구 결과 기반 결정적 brief 를 제공합니다 (LLM 합성 없음):\n\n"
            + build_deterministic_brief(state)
        )
        state["citations"] = []
        state["grounding"] = {"ok": False, "warnings": ["budget_exceeded"]}
        return state

    # 도구 결과 + evidence 를 요약해 LLM 입력으로
    context = _build_context(state)
    messages = [
        {"role": "system", "content": (
            "당신은 한국 금융 분석가다. 사용자의 질문에 도구 출력과 본문 인용을 근거로 "
            "정확히 답변한다. 본문에 없는 내용은 추측하지 말 것. "
            "수치는 도구 결과(get_revenue / get_operating_income 등) 만 인용하고, "
            "답변 끝에 [출처: corp_code, fiscal_year, section] 형식 인용을 붙인다."
        )},
        {"role": "user", "content": context},
    ]

    try:
        from ..llm.base import get_llm_client
        from ..llm.budget_aware import budget_aware_client
        from ..llm.cost_tracker import BudgetExceeded
        from ..config import get_settings

        settings = get_settings()
        client = budget_aware_client(
            get_llm_client(role=llm_role),
            caller="agent_synthesize",
            hard_limit=settings.agent_turn_budget_usd,
        )
        resp = client.chat(messages, temperature=0.2, max_tokens=1200,
                           purpose="synthesize")
        state["answer"] = resp.content
        state["llm_usage_usd"] = float(state.get("llm_usage_usd") or 0.0) + resp.usage.cost_usd
    except BudgetExceeded:
        # 비용 한도 도달 — 결정적 brief 로 fallback (LLM 안 부름)
        from .answering import build_deterministic_brief
        state["answer"] = (
            "[LLM 비용 한도 도달 — 결정적 brief]\n\n"
            + build_deterministic_brief(state)
        )
        state["aborted_reason"] = "synth_budget"
    except Exception as e:
        log.warning(f"[synth] LLM failed: {e}")
        from .answering import build_deterministic_brief
        state["answer"] = (
            f"[LLM 합성 실패: {type(e).__name__} — 결정적 brief]\n\n"
            + build_deterministic_brief(state)
        )

    # citations 추출
    cits: list[dict] = []
    for ch in state.get("evidence_chunks") or []:
        cits.append({
            "chunk_id": ch.get("id"),
            "corp_code": ch.get("corp_code"),
            "fiscal_year": ch.get("fiscal_year"),
            "section": ch.get("section"),
            "rcept_no": ch.get("rcept_no"),
            "score": ch.get("score"),
        })
    state["citations"] = cits[:10]

    # 답변 grounding 검증 — LLM 답변이 evidence 와 일치하는지
    from .grounding import verify_answer_grounding
    grounding = verify_answer_grounding(
        answer=state.get("answer", ""),
        evidence_chunks=state.get("evidence_chunks") or [],
    )
    state["grounding"] = grounding
    if not grounding["ok"]:
        log.warning(f"[synth] grounding failed: {grounding['warnings']}")
    return state


def _build_context(state: AgentState) -> str:
    """tool_results + evidence_chunks → LLM 입력 텍스트."""
    parts: list[str] = []
    parts.append(f"[질문]\n{state.get('question','')}\n")

    parts.append("[질문 유형] " + (state.get('question_kind') or 'unknown') + "\n")

    tools_out = state.get("tool_results") or []
    if tools_out:
        parts.append("[도구 결과]")
        for t in tools_out:
            preview = str(t.get("result"))[:1000]
            parts.append(f"- {t['tool']} ({t.get('purpose','')}): {preview}")
        parts.append("")

    ev = state.get("evidence_chunks") or []
    if ev:
        parts.append("[본문 인용]")
        for c in ev[:6]:
            parts.append(
                f"- corp={c.get('corp_code')} year={c.get('fiscal_year')} "
                f"sec={c.get('section','')[:30]} score={c.get('score'):.3f}\n"
                f"  {c.get('text','')[:400]}"
            )
        parts.append("")

    parts.append("위 근거만 사용해 한국어로 답변하고, 끝에 [출처:...] 인용을 남기세요. "
                  "근거 부족 시 '정보 부족' 으로 답하세요.")
    return "\n".join(parts)


__all__ = ["triage_node", "planner_node", "executor_node", "synthesizer_node"]
