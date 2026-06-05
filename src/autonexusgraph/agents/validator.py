"""Validator 노드 + Replan 신호 — PRD §7.5.5.

검증 항목 (6개):
1. completeness (answer_too_short): 답변이 너무 짧거나 빈 답이면 fail (< _MIN_ANSWER_LENGTH)
2. self-reported insufficient: 답변이 "정보 부족" / "데이터 없음" 자기 신고면 early pass
   (replan 의미 없음 — 데이터 자체가 없는 상황)
3. language (language_non_korean): 한국어 비율이 너무 낮으면 fail (language_guard.check_korean)
4. grounding overlap: token overlap < HARD_FAIL 이면 fail (verify_answer_grounding 사용).
   narrative / multi_hop 질문은 grounding warning 만 추가 (hard fail 아님)
5. financial number safety (hallucinated_numbers): 답변에 등장한 큰 숫자가 도구 결과 / evidence
   에서 나온 수치인지 cross-check — 환각 방지 (PRD §7.3 "재무 수치는 절대 LLM 이 생성하지 않는다").
   number_guard 와 SSOT 공유 (_number_patterns.py)
6. edge confidence (PRD §6.7 / §7.0): tool_results 의 graph 엣지 confidence 가 모두 < 0.5 면
   hard fail (low_confidence_edges_only — 단독 근거 금지). 일부만 미달이면 soft warning.

검증 실패 시 state["validation_status"]="failed", state["validation_issues"] 채움.
graph.run_agent 가 n_replans < MAX 이면 planner 부터 재실행.
"""

from __future__ import annotations

import logging

from ._number_patterns import (
    collect_numbers_from_state,
    extract_big_numbers as _extract_big_numbers,
    numbers_from_tool_results as _numbers_from_tool_results,  # noqa: F401 — tests/ 호환 re-export alias
)
from .grounding import verify_answer_grounding
from .state import AgentState, _ClearedDict, _ClearedList

log = logging.getLogger(__name__)

# PRD §7.5.5 — replan 무한 루프 방지
MAX_REPLANS = 2

_MIN_ANSWER_LENGTH = 15

# PRD §6.7 / §7.0 — confidence < 0.5 엣지는 단독 근거 금지.
# 그래프 tool 결과에 ``confidence`` 또는 ``confidence_score`` 컬럼이 노출되면
# 본 임계값으로 검사. 모든 행이 미달이면 hard fail, 일부만 미달이면 soft warn.
LOW_CONFIDENCE_THRESHOLD = 0.5

# 큰 숫자 정규식·추출 함수는 모두 ``_number_patterns`` (SSOT) 에 정의되어 있다.
# number_guard (pre-synth) 와 validator (post-synth) 가 같은 헬퍼를 거치므로
# ``hallucinated_numbers`` 검사에 사용되는 화이트리스트가 어긋날 수 없다.
# ``_numbers_from_tool_results`` 는 외부 (tests/) 호환용 alias.


def validator_node(state: AgentState) -> AgentState:
    """답변 합성 후 검증. validation_status / validation_issues 갱신.

    PRD §7.5.5: Validator → failed → Planner replan (count<2).
    """
    from ..safety.language_guard import check_korean

    issues: list[str] = []
    answer = state.get("answer") or ""

    # 1) 답변 길이
    if len(answer.strip()) < _MIN_ANSWER_LENGTH:
        issues.append("answer_too_short")

    # 2) "정보 부족" 자기 신고는 valid — replan 의미 없음
    if "정보 부족" in answer or "데이터 없음" in answer or "정보가 부족" in answer:
        state["validation_status"] = "passed"
        state["validation_issues"] = ["self_reported_insufficient"]
        log.info("[validator] self-reported insufficient — passed without replan")
        return state

    # 3) 한국어 비율 가드
    ok_ko, ratio = check_korean(answer)
    if not ok_ko:
        issues.append(f"language_non_korean_{ratio:.2f}")

    # 4) Grounding (이미 synthesizer 가 채워둘 수 있음 — None 이면 직접 계산.
    # 빈 dict {} 도 falsy 라 'or' 는 재계산 유발 → 'is None' 으로 명확화).
    grounding = state.get("grounding")
    if grounding is None:
        grounding = verify_answer_grounding(
            answer=answer,
            evidence_chunks=state.get("evidence_chunks") or [],
        )
    state["grounding"] = grounding
    if not grounding.get("ok"):
        # narrative / multi_hop 류 질문은 evidence 가 핵심. 도구 결과만 있고 evidence 없는
        # 경우(structural 등)는 hard fail 대신 warning.
        kind = state.get("question_kind")
        if kind in ("narrative", "multi_hop") and grounding.get("warnings"):
            issues.extend([f"grounding:{w}" for w in grounding["warnings"]])

    # 5) 재무 수치 환각 가드 — 답변에 등장한 큰 숫자는 tool_results 또는 evidence
    # 본문에 존재해야 함. number_guard 의 approved set 와 동일한 합집합.
    answer_nums = _extract_big_numbers(answer)
    if answer_nums:
        safe_nums = collect_numbers_from_state(state)
        hallucinated = answer_nums - safe_nums
        if hallucinated:
            issues.append(f"hallucinated_numbers:{sorted(hallucinated)[:3]}")

    # 6) confidence 게이트 (PRD §6.7 / §7.0) — 그래프 tool 결과에 노출된 엣지
    #    confidence 가 모두 임계값 미만이면 hard fail. 일부만 미달이면 soft warn.
    #    confidence 컬럼이 없는 finance 쿼리 결과는 검사 대상 아님.
    conf_check = _check_edge_confidence(state)
    if conf_check == "all_low":
        issues.append(f"low_confidence_edges_only:lt_{LOW_CONFIDENCE_THRESHOLD}")
    elif conf_check == "some_low":
        issues.append(f"low_confidence_edges_mixed:lt_{LOW_CONFIDENCE_THRESHOLD}")

    state["validation_issues"] = issues
    if issues:
        # 'low_overlap_but_cited' 같은 soft warning 만 있으면 passed 로 통과.
        # 'low_confidence_edges_only' 는 PRD §6.7 단독 근거 금지 — hard fail.
        # 'low_confidence_edges_mixed' 는 soft warning (다른 A/B 출처와 결합).
        hard = [i for i in issues if (
            i.startswith("hallucinated_numbers")
            or i.startswith("language_non_korean")
            or i == "answer_too_short"
            or i.startswith("low_confidence_edges_only")
        )]
        state["validation_status"] = "failed" if hard else "passed"
        if hard:
            log.warning("[validator] failed: %s", hard)
        else:
            log.info("[validator] passed with soft warnings: %s", issues)
    else:
        state["validation_status"] = "passed"
        log.info("[validator] passed clean")
    return state


def _check_edge_confidence(state: AgentState) -> str:
    """tool_results 안의 graph 엣지 confidence 검사 (PRD §6.7 / §7.0).

    Returns:
        - ``"none"``: confidence 필드를 노출한 엣지가 0건 (검사 불가)
        - ``"all_low"``: 모든 엣지 confidence < LOW_CONFIDENCE_THRESHOLD (hard fail)
        - ``"some_low"``: 일부만 미달 (soft warning — 다른 A/B 출처와 결합 가정)
        - ``"all_ok"``: 모두 임계값 이상

    `confidence` / `confidence_score` 컬럼이 노출된 행만 대상. graph 템플릿이
    이 두 alias 를 사용 — finance SQL 결과는 자연스럽게 검사 대상에서 빠짐.
    """
    confidences: list[float] = []
    for t in (state.get("tool_results") or []):
        if not isinstance(t, dict):
            continue
        result = t.get("result")
        rows = result if isinstance(result, list) else []
        for r in rows:
            if not isinstance(r, dict):
                continue
            val = r.get("confidence")
            if val is None:
                val = r.get("confidence_score")
            try:
                if val is not None:
                    confidences.append(float(val))
            except (TypeError, ValueError):
                continue

    if not confidences:
        return "none"
    n_low = sum(1 for c in confidences if c < LOW_CONFIDENCE_THRESHOLD)
    if n_low == 0:
        return "all_ok"
    if n_low == len(confidences):
        return "all_low"
    return "some_low"


def should_replan(state: AgentState) -> bool:
    """replan 트리거 — validator failed + n_replans < MAX."""
    if state.get("validation_status") != "failed":
        return False
    n = int(state.get("n_replans") or 0)
    if n >= MAX_REPLANS:
        log.warning("[validator] replan limit (%d) 도달 — 부분 답변 그대로 반환", n)
        return False
    return True


def mark_replan(state: AgentState) -> AgentState:
    """replan 카운터 증가 + 이전 도구 결과·DAG 클리어 (planner 가 새로 채움).

    (b) Result-aware replan: 도구/DAG 를 비우기 **전에** 실패 원인(validation_issues)과
    직전 계획(intent 목록·grounding 경고)을 ``replan_hint`` 에 보존한다. planner_node 가
    이를 읽어 같은 계획을 재시도하는 대신 전략을 바꾼다(kind 승격·retrieval 확대).
    이것이 "동일 계획 재시도(open-loop)" → "실패 반영 재계획(closed-loop)" 의 핵심.
    """
    n = int(state.get("n_replans") or 0) + 1
    state["n_replans"] = n
    state["replan_hint"] = {
        "n": n,
        "prev_kind": state.get("question_kind"),
        "prev_issues": list(state.get("validation_issues") or []),
        "prev_tools": [t.get("intent") for t in (state.get("tasks") or [])
                       if isinstance(t, dict)],
        "prev_grounding": list((state.get("grounding") or {}).get("warnings") or []),
    }
    # 축6: 누적 채널은 마커로 비워 reducer 가 교체(clear)하게 한다 (merge 무력화 방지).
    state["tool_results"] = _ClearedList()
    state["evidence_chunks"] = _ClearedList()
    state["plan"] = []
    state["tasks"] = []
    state["task_results"] = _ClearedDict()
    state["answer"] = ""
    state["citations"] = []
    state["validation_status"] = "pending"
    log.info("[validator] replan #%d 시작 — issues=%s", n,
             state["replan_hint"]["prev_issues"][:3])
    return state


__all__ = ["validator_node", "should_replan", "mark_replan", "MAX_REPLANS",
           "LOW_CONFIDENCE_THRESHOLD"]
