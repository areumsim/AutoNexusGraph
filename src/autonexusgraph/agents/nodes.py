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
from typing import cast

from . import session
from ._domain_handler import call_handler_method, get_handler
from .policy import classify_question, turn_budget_exceeded
from .state import AgentState, QuestionKind
from .temporal import extract_year_hint, normalize_temporal_terms

log = logging.getLogger(__name__)


# 한국어 조사 — 회사명 lookup 전 어절 끝에서 제거 ('삼성전자의' → '삼성전자').
# 긴 것 먼저 (그리디) — '들의' 를 '의' 보다 먼저 떼어야 한다.
_KO_JOSA: tuple[str, ...] = (
    "으로서", "으로써", "에서의", "에게서", "들에게", "들의", "들은", "들이", "들을",
    "에서", "에게", "에는", "에도", "까지", "부터", "마다", "조차", "처럼", "만큼",
    "보다", "라도", "이나", "이란", "이라", "으로",
    "의", "은", "는", "이", "가", "을", "를", "에", "와", "과", "도", "만", "로", "들",
)
# substring(중간 일치) 약매치 차단 임계 — financials.lookup_company score:
#   100 corp_code / 90 stock / 80 exact name / 60 prefix / 40 substring.
# 공통명사('자회사'·'반도체')가 회사명 일부와 substring(40) 으로 오매치되는 것을 거른다.
_COMPANY_MIN_SCORE = 60


def _strip_josa(word: str) -> str:
    """어절 끝 조사 1개 제거. 어간이 2자 미만이 되면 원형 유지(과다 절단 방지)."""
    for j in _KO_JOSA:
        if word.endswith(j) and len(word) - len(j) >= 2:
            return word[: -len(j)]
    return word


# ── Triage ──────────────────────────────────────────────────
def triage_node(state: AgentState) -> AgentState:
    """질문 유형 분류 + 1차 회사 식별 + 상대 시간 정규화."""
    from ..safety import is_high_risk_injection, sanitize_user_input
    from ..tools.financials import lookup_company as lookup_pg
    from .rewriter import rewrite_query

    raw_q = state.get("question", "")
    # 1) 프롬프트 인젝션 신호 감지 + XML 경계 escape — 입력 → safety 통과 → 본 파이프라인
    safe_q, signals = sanitize_user_input(raw_q, context="agent_input")
    if signals:
        state["safety_signals"] = signals
    # 1-a) high-confidence 신호 (jailbreak / ignore previous / <|im_start|> 등) 가 단발이라도
    #      매칭되면 입력 거부 — planner/lookup/handler 호출 전에 short-circuit. synthesizer
    #      가 ``aborted_reason='prompt_injection'`` 분기로 결정적 거부 답변 생성.
    if is_high_risk_injection(raw_q):
        state["aborted_reason"] = "prompt_injection"
        state["question_kind"] = "unknown"
        state["target_companies"] = []
        state["tasks"] = []
        state["plan"] = []
        log.warning("[triage] prompt-injection 차단 — high-risk 신호: %s",
                    sorted({s.lower()[:40] for s in signals})[:3])
        return state
    q = safe_q
    # 2) 멀티턴 coreference 해소 — "그 중", "위 회사들" → 이전 turn 의 entity 풀어쓰기
    history = state.get("history") or []
    if history:
        q_rew, rewrite_audit = rewrite_query(question=q, history=history)
        if rewrite_audit.get("called"):
            state["rewrite_audit"] = rewrite_audit
            q = q_rew
    # 3) 한국어 상대 시간 정규화 — '작년'/'최근 3년' → 절대 연도 (rewrite 후에 적용)
    q_norm, temporal_audit = normalize_temporal_terms(q)
    if temporal_audit.get("applied") or state.get("rewrite_audit"):
        state["question_rewritten"] = q_norm
    if temporal_audit.get("applied"):
        state["temporal_audit"] = temporal_audit
        q = q_norm
    kind = classify_question(q)
    state["question_kind"] = kind

    # 회사 식별 — 모호성 검출 + (가능 시) HITL clarification (PRD §7.5.6)
    from .interrupts import (
        InterruptUnavailable,
        coerce_clarification_response,
        is_ambiguous_company,
        make_clarification_payload,
        request_interrupt,
    )

    thread_id = state.get("thread_id") or ""
    targets: list[str] = []
    interrupt_response = state.get("interrupt_response")

    # 사용자가 이미 clarification 답을 보냈으면 그것을 우선 적용 (재개 흐름)
    if interrupt_response and (state.get("pending_interrupt") or {}).get("kind") == "company_clarification":
        cands = (state.get("pending_interrupt") or {}).get("candidates") or []
        chosen = coerce_clarification_response(interrupt_response, cands)
        if chosen:
            targets = [chosen]
            state["interrupt_handled"] = True
            state["pending_interrupt"] = {}
            log.info("[triage] clarification 응답 적용: %s", chosen)

    # 후보 추출 — word 단위로 lookup, 각 word 가 모호하면 첫 모호 지점에서 interrupt
    if not targets:
        for word in q.split():
            if len(word) < 2:
                continue
            # 원형 → 매칭 실패 시 조사 제거형 재시도 ('삼성전자의' → '삼성전자').
            candidates = [word]
            stripped = _strip_josa(word)
            if stripped != word:
                candidates.append(stripped)
            hits = []
            for cand in candidates:
                try:
                    h = lookup_pg(cand, limit=5)
                except Exception:   # noqa: BLE001 — PG lookup 실패 흡수 → 빈 hits (다음 후보/word)
                    h = []
                if h:
                    hits = h
                    break
            if not hits:
                continue
            # 약매치(공통명사 substring 오선택) 차단 — 상위 hit score 가 임계 미만이면 skip.
            if (hits[0].get("score") or 0) < _COMPANY_MIN_SCORE:
                continue
            # 모호성 — 후보 ≥ 2 + score margin 작음
            if is_ambiguous_company(hits):
                payload = make_clarification_payload(
                    query=word, candidates=hits, thread_id=thread_id,
                )
                state["pending_interrupt"] = dict(payload)
                try:
                    resp = request_interrupt(payload)
                    chosen = coerce_clarification_response(resp, hits)
                    if chosen:
                        targets.append(chosen)
                        state["interrupt_handled"] = True
                        state["pending_interrupt"] = {}
                        continue
                except InterruptUnavailable:
                    # 폴백 체인 — 1순위 자동 선택 + 경고. (H4 fix) pending_interrupt
                    # 잔존 시 UI/API 가 "interrupt 진행 중" 오인 → 자동 해결 시 비움.
                    cc = str(hits[0].get("corp_code") or "")
                    if cc:
                        targets.append(cc)
                        state.setdefault("safety_signals", []).append(
                            f"ambiguous_company_auto_resolved:{word}->{cc}"
                        )
                        log.warning("[triage] interrupt 미지원 — '%s' 1순위(%s) 자동 선택", word, cc)
                    state["pending_interrupt"] = {}
                continue
            # 모호 X → 1순위 채택
            cc = str(hits[0].get("corp_code") or "")
            if cc and cc not in targets:
                targets.append(cc)
            if len(targets) >= 5:
                break

    # 세션 entity carry-over — 이번 turn 에 회사가 식별 안 되고 multi-turn 이면
    # 이전 세션의 target_companies/persons 를 borrow (PRD §7.6.2).
    prev = session.get(thread_id) if thread_id else None
    if not targets and prev and prev.target_companies:
        targets = list(prev.target_companies)
        state["session_carryover"] = True
        log.info("[triage] carry-over targets from session: %s", targets)

    state["target_companies"] = targets

    # ── 도메인 entity 식별 — 등록된 handler 에 위임 (PRD §10.12) ──
    # finance 외 도메인 (auto/cross_domain) 의 entity 식별은 외부 패키지(autograph)
    # 가 _domain_handler 에 등록한 handler.identify_targets 가 처리. core 는 외부
    # 패키지를 알지 못함. 미등록 도메인은 finance 만 진행.
    domain = str(state.get("domain") or "finance").lower()
    handler = get_handler(domain)
    # N3 fix: 원래 의도 복구 — handler 등록 ✓ + identify_targets 구현 ✓ 인 도메인만
    # carry-over 실행. identify_targets 미구현 도메인은 entity 식별 자체가 없어
    # carry-over 적용 의미 없음.
    if handler is not None and hasattr(handler, "identify_targets"):
        # handler.identify_targets 는 state 를 mutate 하므로 반환값 무시.
        # 실패 시 call_handler_method 가 None 반환 + signals 기록.
        call_handler_method(state, handler, "identify_targets", state, question=q)

        # 도메인 entity (vehicle/model/make) session carry-over — handler 가
        # 채우지 못한 경우 이전 turn 의 값을 빌림 (PRD §7.6.2).
        if prev:
            if not (state.get("target_vehicles") or []) and prev.target_vehicles:
                state["target_vehicles"] = list(prev.target_vehicles)
                state["session_carryover"] = True
                log.info("[triage:%s] carry-over target_vehicles: %s",
                         domain, state["target_vehicles"])
            if not (state.get("target_models") or []) and prev.target_models:
                state["target_models"] = list(prev.target_models)
                state["session_carryover"] = True
            if not (state.get("target_makes") or []) and prev.target_makes:
                state["target_makes"] = list(prev.target_makes)

    # 이번 turn 결과를 세션에 기록 (다음 turn 의 carry-over 재료)
    if thread_id:
        year_hint = extract_year_hint(state.get("question_rewritten") or q)
        session.update(
            thread_id,
            target_companies=targets if targets else None,
            target_vehicles=state.get("target_vehicles") or None,
            target_models=state.get("target_models") or None,
            target_makes=state.get("target_makes") or None,
            last_year=year_hint,
            last_question_kind=kind,
            last_question=q,
        )

    log.info("[triage] kind=%s targets=%s vehicles=%s",
             kind, targets, state.get("target_vehicles") or [])
    return state


# ── 축2: LLM 자율 planner 토글 ──────────────────────────────
def _llm_planner_enabled(state: AgentState | None = None) -> bool:
    """LLM planner 활성 여부 — state override(평가 ablation) > config(opt-in).

    state["llm_planner"] 가 True/False 면 그것을 우선(이 turn 한정). None/미설정이면
    settings.agent_llm_planner. 설정 로드 실패 시 안전하게 False.
    """
    if state is not None:
        override = state.get("llm_planner")
        if override is not None:
            return bool(override)
    try:
        from ..config import get_settings
        return bool(getattr(get_settings(), "agent_llm_planner", False))
    except Exception:   # noqa: BLE001 — [nodes] fail-soft 흡수 → False 반환
        return False


# ── (b) Result-aware replan adaptation ──────────────────────
def _replan_escalate_kind(kind: str, hint: dict) -> str:
    """직전 실패 원인에 따라 question_kind 를 승격 — 같은 계획 재시도 대신 다른 전략.

    - grounding / answer_too_short / 저신뢰 엣지 → 근거 부족 → multi_hop/narrative 로 확장
      (graph+sql+research 조합으로 evidence 보강).
    - hallucinated_numbers → 자유서술 확장은 역효과(환각 가능성↑) → 정형 소스 유지
      (narrative 였으면 structural 로 축소, 그 외 kind 유지).
    """
    issues = hint.get("prev_issues") or []
    if any(str(i).startswith("hallucinated_numbers") for i in issues):
        return "structural" if kind == "narrative" else kind
    _ESCALATE = {  # noqa: N806 — 지역 상수(매핑)
        "factual": "multi_hop",
        "structural": "multi_hop",
        "narrative": "multi_hop",
        "multi_hop": "multi_hop",
        "unknown": "narrative",
    }
    return _ESCALATE.get(kind, "narrative")


def _apply_replan_widen(state: AgentState) -> None:
    """replan 시 retrieval 폭 확대 — research task 의 top_k 를 배수 증가(상한 20).

    replan 횟수 n 이 클수록 더 넓게 검색. handler/finance 양 경로의 산출 tasks 에
    공통 적용되도록 ``_planner_cost_gate`` 진입 시 호출.
    """
    hint = state.get("replan_hint") or {}
    if not hint:
        return
    n = int(hint.get("n") or 1)
    for t in state.get("tasks") or []:
        if not isinstance(t, dict) or t.get("agent") != "research":
            continue
        args = t.setdefault("args", {})
        cur = int(args.get("top_k") or 6)
        args["top_k"] = min(cur + 4 * n, 20)


# ── Planner ─────────────────────────────────────────────────
def planner_node(state: AgentState) -> AgentState:
    """질문 유형 + 회사 → task DAG (PRD §7.5.2 / §7.5.3).

    룰 기반 1차 구현 (LLM upgrade 는 별도 PR). question_kind 별 패턴:
      factual    : SQL 단발 (get_revenue/get_op) — 회사 수만큼 병렬
      structural : Graph 다발 (list_subsidiaries/get_executives/get_major_shareholders) 병렬
      narrative  : Research 단발
      multi_hop  : Graph + SQL + Research 조합 — SQL 은 Graph 결과에 의존
      unknown    : Research 단발 안전 default

    여전히 ``state["plan"]`` (flat list) 도 채워서 executor 폴백 호환.
    """
    from .dag import make_spawn_task, make_task
    from .state import _ClearedDict, _ClearedList

    # 축6: 누적 채널 per-turn 리셋 — 마커로 reducer 에 교체 지시. checkpointer 다중턴
    # 잔류·병렬 fan-in 누적 오염 방지. 함수체인(reducer 미적용)에선 빈 컬렉션과 동일.
    # planner 가 gather 단계 시작점이므로 여기서 비우면 workers 가 깨끗이 누적.
    state["task_results"] = _ClearedDict()
    state["tool_results"] = _ClearedList()
    state["evidence_chunks"] = _ClearedList()

    # triage 가 입력 거부를 결정 (prompt_injection 등) — task 생성 건너뛰고
    # synthesizer 가 결정적 거부 답변을 생성하도록 위임.
    if state.get("aborted_reason") == "prompt_injection":
        state["tasks"] = []
        state["plan"] = []
        return state

    kind = state.get("question_kind") or "unknown"
    targets = state.get("target_companies") or []
    year_hint = extract_year_hint(state.get("question_rewritten") or state.get("question", ""))
    q = state.get("question_rewritten") or state.get("question", "")

    # (b) replan 이면 직전 실패(replan_hint)를 반영해 전략(kind) 승격 — 동일 계획
    # 재시도 회피. 첫 turn 은 replan_hint 없음 → 룰 planner 기본 동작 유지.
    replan_hint = state.get("replan_hint") or {}
    if replan_hint:
        new_kind = _replan_escalate_kind(kind, replan_hint)
        if new_kind != kind:
            log.info("[planner] replan#%s — kind 승격 %s→%s (issues=%s)",
                     replan_hint.get("n"), kind, new_kind,
                     (replan_hint.get("prev_issues") or [])[:2])
        kind = cast(QuestionKind, new_kind)
        state["question_kind"] = kind

    # ── 축2: LLM 자율 planner (opt-in) ──────────────────────────────
    # 활성 시 LLM 이 화이트리스트 검증된 task DAG 를 제안. 성공하면 룰/handler 분기를
    # 건너뛴다. 실패/비활성/빈결과 → 아래 기존 로직으로 자연 폴백(안전 기본값 유지).
    # replan_hint 를 LLM 에 주입해 (b) 와 시너지 — 실패 반영 재계획.
    if _llm_planner_enabled(state):
        from .llm_planner import try_llm_plan
        llm_tasks = try_llm_plan(state, kind=kind, targets=targets,
                                 year_hint=year_hint, q=q, replan_hint=replan_hint)
        if llm_tasks:
            state["tasks"] = llm_tasks
            state["plan"] = [
                {"tool": t["intent"], "args": t["args"],
                 "purpose": f"{t['agent']}:{t['intent']}"}
                for t in llm_tasks if t.get("agent") != "_spawn"
            ]
            log.info("[planner] LLM 자율 plan 채택 — tasks=%d", len(llm_tasks))
            return _planner_cost_gate(state, kind, targets, len(llm_tasks))

    # ── 도메인 분기 — 등록 handler 에 plan 위임 (PRD §10.12) ─────────
    # finance 외 도메인은 외부 패키지가 등록한 handler.plan_tasks 가 task list 반환.
    # core 는 어떤 도메인이 있는지 알지 못함. autograph 미설치 시 등록 0건 → 아래
    # finance 룰 기반 planner 로 자연 폴백.
    domain = str(state.get("domain") or "finance").lower()
    handler = get_handler(domain)
    if handler is not None and hasattr(handler, "plan_tasks"):
        tasks: list[dict] = call_handler_method(state, handler, "plan_tasks", state, question=q)
        state["tasks"] = tasks or []
        # task_results 는 planner 진입부에서 이미 마커로 리셋됨 — 재대입 금지(마커 보존).
        state["plan"] = [
            {"tool": t["intent"], "args": t["args"],
             "purpose": f"{t['agent']}:{t['intent']}"}
            for t in (tasks or [])
        ]
        log.info("[planner:%s] tasks=%d", domain, len(state["tasks"]))
        return _planner_cost_gate(state, kind, targets, len(state["tasks"]))

    tasks = []
    tid = 0

    def _next_id(prefix: str) -> str:
        nonlocal tid
        tid += 1
        return f"{prefix}{tid}"

    # ── factual: SQL + vector 보강 ──────────────────────────
    if kind == "factual":
        for cc in targets:
            tasks.append(make_task(
                _next_id("sql_"), "sql", "get_revenue",
                {"corp_code": cc, "year": year_hint},
            ))
            tasks.append(make_task(
                _next_id("sql_"), "sql", "get_operating_income",
                {"corp_code": cc, "year": year_hint},
            ))
        # vector 보강 — SQL tool_result 만으론 synth 의 grounding(evidence_chunks 텍스트
        # 요구)이 통과 못 해 '정보 부족' 으로 떨어진다(2026-06-10 hybrid<<vector 해부).
        # vector adapter 와 동일 chunk 를 확보해 hybrid 이 SQL 값 + 본문 인용 둘 다 갖게 한다.
        if q:
            tasks.append(make_task(
                _next_id("r_"), "research", "search_documents",
                {
                    "query": q, "top_k": 6,
                    "corp_code": targets[0] if len(targets) == 1 else (targets or None),
                    "fiscal_year": year_hint,
                },
            ))

    # ── structural: Graph 다발 (회사별 병렬) ────────────────
    elif kind == "structural":
        for cc in targets:
            tasks.append(make_task(
                _next_id("g_"), "graph", "list_subsidiaries",
                {"parent_corp_code": cc, "limit": 20},
            ))
            tasks.append(make_task(
                _next_id("g_"), "graph", "get_executives",
                {"corp_code": cc, "limit": 30},
            ))
            tasks.append(make_task(
                _next_id("g_"), "graph", "get_major_shareholders",
                {"corp_code": cc, "limit": 10},
            ))

    # ── narrative: Research ────────────────────────────────
    elif kind == "narrative":
        if q:
            tasks.append(make_task(
                _next_id("r_"), "research", "search_documents",
                {
                    "query": q, "top_k": 6,
                    "corp_code": targets[0] if len(targets) == 1 else (targets or None),
                    "fiscal_year": year_hint,
                },
            ))

    # ── multi_hop: Graph 먼저 → SQL 집계 → Research 보완 ───
    elif kind == "multi_hop":
        graph_ids: list[str] = []
        for cc in targets:
            gid = _next_id("g_")
            graph_ids.append(gid)
            tasks.append(make_task(
                gid, "graph", "list_subsidiaries",
                {"parent_corp_code": cc, "limit": 30},
            ))
        for cc in targets:
            # 모회사 자체 매출 (parent revenue) — graph 완료 후 실행 (의존성 순서).
            tasks.append(make_task(
                _next_id("sql_"), "sql", "get_revenue",
                {"corp_code": cc, "year": year_hint},
                depends_on=graph_ids,
            ))
        # (a) Closed-loop 데이터 흐름: 발견된 자회사들의 매출 비교 — corp_codes 를
        # graph 결과(child_corp_code)에서 **런타임 도출**. depends_on 이 선언만이 아니라
        # 실제 데이터가 흐른다. year 없으면 compare_companies 가 동작 못 하므로 생략.
        if year_hint:
            for gid in graph_ids:
                tasks.append(make_task(
                    _next_id("sql_"), "sql", "compare_companies",
                    {"corp_codes": {"$from": gid, "field": "child_corp_code",
                                    "collect": True},
                     "year": year_hint, "metric": "revenue"},
                    depends_on=[gid],
                ))
        # ReAct mid-execution fan-out: 발견된 자회사마다 영업이익을 개별 조회.
        # compare(revenue 일괄)와 보완 차원 — 자회사 수를 plan 시점엔 모르므로 정적
        # DAG 로 표현 불가. supervisor 의 reflect 가 graph 완료 후 런타임에 펼친다.
        if year_hint:
            for gid in graph_ids:
                tasks.append(make_spawn_task(
                    _next_id("spawn_"), from_id=gid, for_each="child_corp_code",
                    agent="sql", intent="get_operating_income", arg="corp_code",
                    base_args={"year": year_hint},
                ))
        if q:
            tasks.append(make_task(
                _next_id("r_"), "research", "search_documents",
                {
                    "query": q, "top_k": 6,
                    "corp_code": targets[0] if len(targets) == 1 else (targets or None),
                    "fiscal_year": year_hint,
                },
            ))

    # ── unknown: 안전 default — research ────────────────────
    else:
        if q:
            tasks.append(make_task(
                _next_id("r_"), "research", "search_documents",
                {"query": q, "top_k": 6,
                 "corp_code": targets[0] if len(targets) == 1 else (targets or None)},
            ))

    state["tasks"] = tasks
    # task_results 는 planner 진입부에서 이미 마커로 리셋됨 — 재대입 금지(마커 보존).

    # 호환용 legacy plan — executor 폴백 (tasks 빈 경우 사용).
    # _spawn 템플릿은 reflect 전용 — 도구 호출 불가하므로 legacy plan 에서 제외.
    plan: list[dict] = []
    for t in tasks:
        if t.get("agent") == "_spawn":
            continue
        plan.append({
            "tool": t["intent"],
            "args": t["args"],
            "purpose": f"{t['agent']}:{t['intent']}",
        })
    state["plan"] = plan

    log.info("[planner] kind=%s targets=%d tasks=%d (DAG)",
             kind, len(targets), len(tasks))

    return _planner_cost_gate(state, kind, targets, len(tasks))


def _handle_cost_resume(state: AgentState) -> bool:
    """이미 보낸 cost_approval 의 사용자 응답을 처리.

    Returns:
        True  — 응답 처리됨 (turn 진행 또는 중단 결정 완료)
        False — 보낸 적이 없거나 응답 미수신
    """
    from .interrupts import coerce_cost_response

    pi = state.get("pending_interrupt") or {}
    resp = state.get("interrupt_response")
    if not (pi.get("kind") == "cost_approval"
            and resp is not None
            and not state.get("interrupt_handled")):
        return False

    approved = coerce_cost_response(resp)
    state["interrupt_handled"] = True
    state["pending_interrupt"] = {}
    if not approved:
        state["aborted_reason"] = "cost_rejected"
        log.info("[planner] cost_approval 거절 — turn 종료")
    else:
        log.info("[planner] cost_approval 승인 (resume) — 진행")
    return True


def _request_cost_approval(state: AgentState, kind: str, targets: list,
                            n_tasks: int, domain: str) -> None:
    """새로운 cost approval 요청 — replan 첫 turn 일 때만."""
    from .cost_estimator import needs_cost_approval
    from .interrupts import (
        InterruptUnavailable,
        coerce_cost_response,
        make_cost_approval_payload,
        request_interrupt,
    )

    need, est = needs_cost_approval(state)
    if not need:
        return

    summary = (
        f"도메인: {domain}, 질문 유형: {kind}, 대상: {len(targets)}, "
        f"task: {n_tasks}개, 모델: {est.model} "
        f"(replan 최대 {est.replan_factor}회 포함)"
    )
    payload = make_cost_approval_payload(
        estimated_cost_usd=est.estimated_cost_usd,
        plan_summary=summary,
        thread_id=state.get("thread_id") or "",
    )
    state["pending_interrupt"] = dict(payload)
    try:
        approved = coerce_cost_response(request_interrupt(payload))
        state["interrupt_handled"] = True
        state["pending_interrupt"] = {}
        if not approved:
            state["aborted_reason"] = "cost_rejected"
            log.info("[planner] cost_approval 거절 — turn 종료")
    except InterruptUnavailable:
        # (H4 fix) 폴백 시 pending_interrupt 비움 — UI/API 오인 회피.
        state["pending_interrupt"] = {}
        state.setdefault("safety_signals", []).append(
            f"cost_approval_auto_passed:${est.estimated_cost_usd:.4f}"
        )
        log.warning("[planner] interrupt 미지원 — 추정 비용 $%.4f 자동 통과",
                    est.estimated_cost_usd)


def _planner_cost_gate(state: AgentState, kind: str, targets: list,
                       n_tasks: int) -> AgentState:
    """planner 의 cost-approval 게이트 — finance/auto/cross_domain 모두 공통.

    PRD §7.5.6 HITL. replan 중이거나 이미 승인된 turn 은 skip.
    """
    domain = str(state.get("domain") or "finance")

    # (b) replan retrieval 확대 — handler/finance 양 경로의 산출 tasks 에 공통 적용.
    _apply_replan_widen(state)

    if _handle_cost_resume(state):
        return state

    if not state.get("n_replans") and not state.get("interrupt_handled"):
        _request_cost_approval(state, kind, targets, n_tasks, domain)
    return state


# ── (d) 공통 빈결과 회복 — executor(legacy) + synthesizer(DAG) 양 경로 대칭 ──
def _attempt_fallback_recovery(state: AgentState) -> bool:
    """모든 도구가 빈 결과 + 검색 미수행 → 도메인 인식 fallback 검색으로 회복.

    diagnosis(축5): 이 회복이 legacy ``executor_node`` 에만 있고 DAG/worker 경로엔
    없어 비대칭이었다. state["tool_results"]/["evidence_chunks"] 를 직접 보고/갱신하므로
    두 경로에서 동일하게 호출 가능 — DAG 경로도 "정보 부족" 직행 대신 회복 시도.

    Returns:
        True  — 회복 검색이 결과를 반환해 evidence 누적됨 (fallback_used=True)
        False — 회복 불필요(이미 evidence 있음)·불가(검색 이미 수행·예산초과 등)·무소득
    """
    if state.get("aborted_reason") in ("turn_budget", "cost_rejected", "prompt_injection"):
        return False
    if state.get("evidence_chunks"):
        return False   # 이미 본문 근거 확보 — 회복 불필요
    results = state.get("tool_results") or []
    all_empty = all(not (r.get("result")) for r in results) if results else True
    searched_tools = {"search_documents", "search_documents_auto"}
    already_searched = any(r.get("tool") in searched_tools for r in results)
    if not all_empty or already_searched or not state.get("question"):
        return False

    from .. import tools as toolbox
    domain = str(state.get("domain") or "finance").lower()
    q_text = state.get("question_rewritten") or state["question"]
    fb_tool: str | None = None
    fb_fn = None
    fb_args: dict = {}
    # handler 가 (tool, fn, args) 제공하면 도메인 검색, 아니면 finance 기본.
    fb = call_handler_method(state, get_handler(domain), "fallback_search",
                             state, query=q_text)
    if fb is not None:
        fb_tool, fb_fn, fb_args = fb
        log.info("[recovery:%s] fallback via handler — tool=%s", domain, fb_tool)
    if fb_fn is None:
        fb_tool = "search_documents"
        fb_fn = getattr(toolbox, "search_documents", None)
        targets = state.get("target_companies") or []
        fb_args = {
            "query": q_text, "top_k": 6,
            "corp_code": targets[0] if len(targets) == 1 else (targets or None),
        }
        log.info("[recovery] all empty → fallback search_documents (finance)")
    if fb_fn is None:
        return False

    from .workers import _maybe_inject_rerank
    _maybe_inject_rerank(state, fb_fn, fb_args)
    try:
        fb_out = fb_fn(**fb_args)
    except Exception as e:   # noqa: BLE001 — [nodes] fail-soft 흡수 → False 반환 (log 동반)
        log.warning("[recovery] fallback %s failed: %s", fb_tool, e)
        return False
    if not fb_out:
        return False
    state.setdefault("tool_results", []).append({
        "tool": fb_tool, "purpose": "fallback_recovery",
        "args": fb_args, "result": fb_out,
    })
    state.setdefault("evidence_chunks", []).extend(fb_out)
    state["fallback_used"] = True
    log.info("[recovery:%s] %s → %d chunks 회복", domain, fb_tool, len(fb_out))
    return True


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
        fn = getattr(toolbox, tool_name or "", None)
        if fn is None:
            log.warning(f"[executor] unknown tool: {tool_name}")
            continue
        try:
            out = fn(**args)
        except Exception as e:   # noqa: BLE001 — tool 실행 실패 흡수 → log + 다음 step (executor 진행)
            log.warning(f"[executor] {tool_name} failed: {e}")
            continue
        item = {"tool": tool_name, "purpose": step.get("purpose"), "args": args,
                "result": out}
        results.append(item)
        if tool_name == "search_documents":
            evidence.extend(out or [])

    state["tool_results"] = results
    state["evidence_chunks"] = evidence
    # ── Fallback recovery — DAG/worker 경로와 공유하는 헬퍼로 위임 (축5 대칭화).
    # 모든 도구가 빈 결과 + 검색 미수행이면 도메인 인식 fallback 검색으로 회복.
    _attempt_fallback_recovery(state)
    return state


# ── Synthesizer ─────────────────────────────────────────────
def synthesizer_node(state: AgentState,
                     *, llm_role: str = "synthesizer") -> AgentState:
    """tool_results + evidence_chunks → 자연어 답변 (LLM).

    cost guard: budget_aware_client + tracker 자동 통합.
    aborted_reason 이 있으면 fallback 답변 (LLM 비호출).
    """
    # 비용/예산 초과 → LLM 호출 안 하고 결정적 brief 로 fallback.
    abort = state.get("aborted_reason")
    if abort == "turn_budget":
        from .answering import build_deterministic_brief
        state["answer"] = (
            "이번 응답에서 사전 정의된 LLM 비용 한도를 초과했습니다.\n"
            "도구 결과 기반 결정적 brief 를 제공합니다 (LLM 합성 없음):\n\n"
            + build_deterministic_brief(state)
        )
        state["citations"] = []
        state["grounding"] = {"ok": False, "warnings": ["budget_exceeded"]}
        return state
    if abort == "cost_rejected":
        # 사용자가 비용 승인을 거절 — LLM 호출 없이 명시적 응답
        state["answer"] = (
            "사용자가 예상 비용을 승인하지 않아 답변을 생성하지 않았습니다. "
            "비용 한도를 조정하거나(.env: LLM_COST_AUTO_APPROVE_USD) 더 적은 컨텍스트로 다시 시도해주세요."
        )
        state["citations"] = []
        state["grounding"] = {"ok": False, "warnings": ["cost_rejected"]}
        return state
    if abort == "prompt_injection":
        # triage 가 high-risk 인젝션 패턴을 감지 — LLM 비호출, 결정적 거부 답변.
        state["answer"] = (
            "입력에서 프롬프트 탈취 시도 패턴이 감지되어 답변을 거부했습니다. "
            "질문을 정상 형식으로 다시 작성해주세요."
        )
        state["citations"] = []
        state["grounding"] = {"ok": False, "warnings": ["prompt_injection"]}
        return state

    # (d) DAG/worker 경로 빈결과 회복 — synth 직전 단일 chokepoint(langgraph/폴백 공통).
    # 모든 worker 가 빈 결과만 냈으면 "정보 부족" 직행 대신 도메인 fallback 검색으로
    # evidence 확보 시도. executor(legacy) 와 동일 헬퍼 — 회복 경로 대칭화.
    if _attempt_fallback_recovery(state):
        log.info("[synth] 빈결과 회복 — fallback evidence %d chunks",
                 len(state.get("evidence_chunks") or []))

    # Pre-synth number guard (PRD §7.3) — 화이트리스트 + evidence 라벨링
    from .number_guard import (
        collect_approved_numbers,
        format_approved_for_prompt,
        sanitize_evidence_for_synth,
    )
    approved = collect_approved_numbers(state)
    sanitized_evidence = sanitize_evidence_for_synth(
        state.get("evidence_chunks") or [], approved,
    )

    # 도구 결과 + (정제된) evidence 를 요약해 LLM 입력으로
    context = _build_context(state, sanitized_evidence=sanitized_evidence)
    approved_line = format_approved_for_prompt(approved)
    messages = [
        {"role": "system", "content": (
            "당신은 한국 금융 분석가다. 사용자의 질문에 도구 출력과 본문 인용을 근거로 "
            "정확히 답변한다. 본문에 없는 내용은 추측하지 말 것.\n"
            "**중요 (재무 수치 가드):**\n"
            f"- 답변에 인용 가능한 정량 수치: {approved_line}\n"
            "- 그 외 숫자는 추정·합산·변환하지 말 것. 필요하면 '정보 부족' 으로 응답.\n"
            "- 본문 안 [검증불가:N] 표시 숫자는 답변에 절대 옮기지 말 것.\n"
            "- [수치:N] 표시는 검증된 수치 — 그대로 인용 가능.\n"
            "답변 끝에 [출처: corp_code, fiscal_year, section] 형식 인용을 붙인다."
        )},
        {"role": "user", "content": context},
    ]

    # synth 호출 상태를 state["synth_status"] 에 구조화 보존 — adapter / eval
    # 이 LLM 실패 여부를 즉시 알 수 있게 한다 (silent skip 방지). status 형식:
    #   {"ok": bool, "error_type": str|None, "error": str|None, "llm_called": bool,
    #    "fallback_used": "budget"|"exception"|None}
    state["synth_status"] = {
        "ok": False, "error_type": None, "error": None,
        "llm_called": False, "fallback_used": None,
    }
    try:
        from ..config import turn_budget_for_domain
        from ..llm.base import get_llm_client
        from ..llm.budget_aware import budget_aware_client
        from ..llm.cost_tracker import BudgetExceeded

        domain = state.get("domain")
        hard_limit = turn_budget_for_domain(domain)
        client = budget_aware_client(
            get_llm_client(role=llm_role),
            caller=f"agent_synthesize:{str(domain or 'finance').lower()}",
            hard_limit=hard_limit,
        )
        resp = client.chat(messages, temperature=0.2, max_tokens=1200,
                           purpose="synthesize")
        state["answer"] = resp.content
        state["llm_usage_usd"] = float(state.get("llm_usage_usd") or 0.0) + resp.usage.cost_usd
        # 토큰 사용량도 누적 — eval adapter 의 tokens_used 측정용.
        try:
            tok = int(getattr(resp.usage, "total_tokens", 0) or 0)
            state["llm_tokens_used"] = int(state.get("llm_tokens_used") or 0) + tok
        except (TypeError, ValueError):
            pass
        state["synth_status"] = {
            "ok": True, "error_type": None, "error": None,
            "llm_called": True, "fallback_used": None,
        }
    except BudgetExceeded as e:
        # 비용 한도 도달 — 결정적 brief 로 fallback (LLM 안 부름)
        from .answering import build_deterministic_brief
        state["answer"] = (
            "[LLM 비용 한도 도달 — 결정적 brief]\n\n"
            + build_deterministic_brief(state)
        )
        state["aborted_reason"] = "synth_budget"
        state["synth_status"] = {
            "ok": False, "error_type": "BudgetExceeded", "error": str(e),
            "llm_called": False, "fallback_used": "budget",
        }
    except Exception as e:    # noqa: BLE001 — [synth] LLM 합성 실패 흡수 → 결정적 brief 폴백 + state 에 실패 정보 명시 (eval 진행 보장)
        log.warning("[synth] LLM failed: %s: %s", type(e).__name__, e)
        from .answering import build_deterministic_brief
        state["answer"] = (
            f"[LLM 합성 실패: {type(e).__name__} — 결정적 brief]\n\n"
            + build_deterministic_brief(state)
        )
        state["synth_status"] = {
            "ok": False, "error_type": type(e).__name__, "error": str(e),
            "llm_called": False, "fallback_used": "exception",
        }

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

    # === sensitive_decision 게이트 (PRD §7.5.6 + §9 비목표 인접) ===
    # 키워드 휴리스틱 (interrupts.SENSITIVE_KEYWORDS) — 매칭 시 사용자 승인 요청.
    # interrupt 미지원 환경 (폴백 체인) 은 보수적 거절 → 답변 차단 메시지로 교체.
    # N2 fix: LLM 실패 fallback 답변 (build_deterministic_brief 결과) 은 게이트 skip
    # — synth_status.fallback_used 가 set 이면 LLM 이 생성한 답이 아닌 결정적 brief.
    from .interrupts import (
        InterruptUnavailable,
        coerce_sensitive_response,
        detect_sensitive_keyword,
        make_sensitive_decision_payload,
        request_interrupt,
    )
    _synth_status = state.get("synth_status") or {}
    _fb_used = _synth_status.get("fallback_used")
    hit = None
    if not _fb_used:
        hit = detect_sensitive_keyword(
            state.get("answer", ""), state.get("question", "")
        )
    if hit:
        payload = make_sensitive_decision_payload(
            answer_preview=str(state.get("answer", ""))[:500],
            plan_summary=f"sensitive_keyword={hit}",
            thread_id=str(state.get("thread_id", "")),
        )
        try:
            resp = request_interrupt(payload)
            sensitive_approved = coerce_sensitive_response(resp)
        except InterruptUnavailable:
            # 폴백 환경 — 보수적 거절 (외부 노출 회피).
            sensitive_approved = False
            state.setdefault("safety_signals", []).append(
                f"sensitive_blocked_fallback:{hit}"
            )
        if not sensitive_approved:
            log.warning("[synth] sensitive answer blocked — hit=%r", hit)
            state["answer"] = (
                f"민감/외부 보고 인접 답변으로 분류 ('{hit}') — 공개 보류됨. "
                "공시 또는 공식 IR 자료를 직접 참조하시길 권장합니다."
            )
            state["sensitive_blocked"] = True
            state.setdefault("safety_signals", []).append(
                f"sensitive_blocked:{hit}"
            )

    return state


def _memory_block(state: AgentState) -> str:
    """(c) Multi-turn 기억 주입 (PRD §7.6.2) — 직전 대화 + 세션 entity 요약.

    diagnosis: 기억이 target_companies carry-over 외에는 어떤 LLM 프롬프트에도 안 실려
    사실상 stateless. 이 블록이 synth 입력에 이전 turn 맥락을 명시 주입해 후속질문
    ("그 중 가장 큰 곳은?", "작년은?")에 일관된 답을 가능케 한다.

    first turn(history 없음 + carry-over 없음)에는 빈 문자열 — 노이즈 회피.
    """
    history = state.get("history") or []
    carryover = bool(state.get("session_carryover"))
    if not history and not carryover:
        return ""
    parts: list[str] = []
    if history:
        hl: list[str] = []
        for h in history[-4:]:   # 직전 ~2 turn (user/assistant)
            if not isinstance(h, dict):
                continue
            role = h.get("role") or h.get("speaker") or ""
            content = str(h.get("content") or h.get("text") or "").strip()[:200]
            if content:
                hl.append(f"  {role}: {content}")
        if hl:
            parts.append("[이전 대화]\n" + "\n".join(hl))
    # 세션 entity 요약 — summarize() 를 실제로 연결 (이전엔 호출처 0건).
    try:
        prev = session.get(state.get("thread_id") or "")
        summ = session.summarize(prev) if prev else ""
        if summ:
            parts.append(f"[이어지는 컨텍스트 엔티티] {summ}")
    except Exception:   # noqa: BLE001 — 기억 주입 실패가 답변을 막지 않도록.
        pass
    if carryover:
        parts.append("(이번 질문은 이전 turn 의 대상 엔티티를 이어받았습니다 — "
                     "지시어는 그 엔티티로 해석하세요.)")
    return ("\n".join(parts) + "\n") if parts else ""


def _build_context(state: AgentState, *,
                    sanitized_evidence: list[dict] | None = None) -> str:
    """tool_results + evidence_chunks → LLM 입력 텍스트.

    sanitized_evidence 가 주어지면 그것을 사용 (number_guard 가 라벨링한 본문).
    None 이면 원본 evidence_chunks 그대로 (이전 호환).
    """
    parts: list[str] = []
    parts.append(f"[질문]\n{state.get('question','')}\n")

    mem = _memory_block(state)
    if mem:
        parts.append(mem)

    parts.append("[질문 유형] " + (state.get('question_kind') or 'unknown') + "\n")

    tools_out = state.get("tool_results") or []
    if tools_out:
        parts.append("[도구 결과]")
        for t in tools_out:
            preview = str(t.get("result"))[:1000]
            parts.append(f"- {t['tool']} ({t.get('purpose','')}): {preview}")
        parts.append("")

    ev = sanitized_evidence if sanitized_evidence is not None else (state.get("evidence_chunks") or [])
    if ev:
        parts.append("[본문 인용]")
        for c in ev[:6]:
            score = c.get('score')
            score_s = f"{score:.3f}" if isinstance(score, (int, float)) else "?"
            parts.append(
                f"- corp={c.get('corp_code')} year={c.get('fiscal_year')} "
                f"sec={(c.get('section') or '')[:30]} score={score_s}\n"
                f"  {(c.get('text') or '')[:400]}"
            )
        parts.append("")

    parts.append("위 근거만 사용해 한국어로 답변하고, 끝에 [출처:...] 인용을 남기세요. "
                  "근거 부족 시 '정보 부족' 으로 답하세요.")
    return "\n".join(parts)


__all__ = ["triage_node", "planner_node", "executor_node", "synthesizer_node"]
