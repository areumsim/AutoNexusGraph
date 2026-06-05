"""Human-in-the-Loop interrupt 페이로드 — PRD §7.5.6.

LangGraph ``interrupt()`` 를 통해 graph 가 멈추고 client 가 응답할 때까지 대기.
응답이 들어오면 graph 가 같은 thread 의 checkpoint 부터 재개한다.

사용 시점 (PRD):
1. Clarification — 모호한 회사명 ("삼성" → 삼성전자/SDS/SDI...) — Triage 단계
2. Cost approval — Planner 산출 비용이 한도 초과
3. Sensitive decision — 외부 보고용 / 민감 답변 — Synthesizer 직전

구현 상태:
- (1) clarification: ``make_clarification_payload`` + ``coerce_clarification_response`` 구현
- (2) cost_approval: ``make_cost_approval_payload`` + ``coerce_cost_response`` 구현 (nodes.py 가 호출)
- (3) sensitive_decision: ``make_sensitive_decision_payload`` + ``coerce_sensitive_response`` 구현.
  단 **trigger 정책 (어떤 답변을 sensitive 로 분류할지) 미정** — 호출처가 합의 후 synthesizer 직전에 연결.
  보수적 기본 (거절 = 미공개) — payload 빌더만 제공하므로 코드 경로상 비활성.

설계:
- langgraph 1.x 의 ``langgraph.types.interrupt`` import 우선
- langgraph 미설치 / 폴백 체인에서는 InterruptUnavailable 예외 → 호출부가 우아한
  다운그레이드 (1순위 후보 자동 선택 + state.fallback_used 경고).
"""

from __future__ import annotations

import logging
from typing import Any, Literal, TypedDict

logger = logging.getLogger(__name__)


InterruptKind = Literal[
    "company_clarification",
    "cost_approval",
    "sensitive_decision",
]


class InterruptPayload(TypedDict, total=False):
    """interrupt 호출 시 client 에게 yield 되는 페이로드."""
    kind: InterruptKind
    prompt: str                      # 사용자에게 보일 한국어 질문
    candidates: list[dict]           # company_clarification 용 후보 목록
    estimated_cost_usd: float        # cost_approval 용 예상 비용
    plan_summary: str                # cost_approval 용 plan 요약
    answer_preview: str              # sensitive_decision 용 답변 미리보기
    thread_id: str                   # resume 시 식별용


class InterruptUnavailable(RuntimeError):
    """langgraph interrupt API 사용 불가 — 호출부가 폴백 처리."""


def request_interrupt(payload: InterruptPayload) -> Any:
    """LangGraph interrupt 호출. 응답을 반환 (resume 값).

    langgraph 미설치 / fallback chain → InterruptUnavailable raise.
    """
    try:
        from langgraph.types import interrupt  # type: ignore[import-not-found]
    except ImportError:
        try:
            from langgraph.graph import interrupt  # type: ignore[attr-defined]
        except ImportError as exc:
            raise InterruptUnavailable("langgraph interrupt API 미사용 (폴백 환경)") from exc
    logger.info("[interrupt] kind=%s prompt=%r", payload.get("kind"),
                str(payload.get("prompt", ""))[:80])
    try:
        return interrupt(dict(payload))
    except RuntimeError as exc:
        # langgraph 는 설치됐으나 runnable context 밖에서 호출됨 (폴백 함수 체인이
        # langgraph 설치 환경에서 도는 경우 / 테스트). interrupt() 가
        # "Called get_config outside of a runnable context" RuntimeError 를 던진다.
        # ImportError 와 동일하게 우아한 다운그레이드로 통일 — 호출부가 1순위 자동선택.
        raise InterruptUnavailable(
            "langgraph interrupt 를 runnable context 밖에서 호출 — 폴백 처리"
        ) from exc


# ── Clarification — 모호한 회사명 ──────────────────────────
def is_ambiguous_company(candidates: list[dict],
                         *, max_margin: float = 0.10,
                         min_n: int = 2) -> bool:
    """후보 N>=min_n + 1·2위 score 차이 < max_margin 이면 모호.

    score 가 없으면 1·2위 이름이 다르고 결합 score 동률로 가정.
    """
    if not candidates or len(candidates) < min_n:
        return False
    scores = [float(c.get("score") or 0.0) for c in candidates[:2]]
    if scores[0] == 0.0 and scores[1] == 0.0:
        # score 없음 — 후보가 여럿이면 모호로 간주
        return True
    margin = scores[0] - scores[1]
    return margin < max_margin * max(scores[0], 1.0)


def make_clarification_payload(
    query: str,
    candidates: list[dict],
    *, thread_id: str = "",
    limit: int = 5,
) -> InterruptPayload:
    """후보 목록을 사용자가 선택할 수 있는 형태로 변환."""
    short = []
    for c in candidates[:limit]:
        short.append({
            "corp_code": c.get("corp_code"),
            "name": c.get("name") or c.get("corp_name") or "",
            "stock_code": c.get("stock_code"),
            "market": c.get("market"),
            "score": c.get("score"),
        })
    return {
        "kind": "company_clarification",
        "prompt": f'"{query}" 와 일치하는 회사가 여러 곳입니다. 어떤 곳을 의미하시나요?',
        "candidates": short,
        "thread_id": thread_id,
    }


def coerce_clarification_response(
    response: Any,
    candidates: list[dict],
) -> str | None:
    """resume 값을 corp_code 로 정규화. dict / int / str 모두 수용.

    return: 선택된 corp_code 또는 None (인식 불가)
    """
    if not response:
        return None
    if isinstance(response, dict):
        cc = response.get("corp_code")
        if isinstance(cc, str) and cc:
            return cc
        idx = response.get("index")
        if isinstance(idx, int) and 0 <= idx < len(candidates):
            return str(candidates[idx].get("corp_code") or "")
    if isinstance(response, int) and 0 <= response < len(candidates):
        return str(candidates[response].get("corp_code") or "")
    if isinstance(response, str):
        # corp_code 8자리 직접 입력
        if response.isdigit() and len(response) == 8:
            return response
        # 이름으로 매칭 — 후보 중 정확히 일치
        for c in candidates:
            if (c.get("name") or "") == response or (c.get("corp_name") or "") == response:
                return str(c.get("corp_code") or "")
    return None


# ── Cost approval ─────────────────────────────────────────
def make_cost_approval_payload(
    *,
    estimated_cost_usd: float,
    plan_summary: str,
    thread_id: str = "",
) -> InterruptPayload:
    """planner 비용 추정이 한도 초과 시 발동."""
    return {
        "kind": "cost_approval",
        "prompt": f"이 질문 처리에 예상 ${estimated_cost_usd:.4f} 소요됩니다. 진행할까요?",
        "estimated_cost_usd": float(estimated_cost_usd),
        "plan_summary": plan_summary,
        "thread_id": thread_id,
    }


def coerce_cost_response(response: Any) -> bool:
    """resume 값을 승인/거절 boolean 으로 정규화.

    True/False / "y"·"yes"·"ok"·"approve" / dict{"approved": bool}.
    인식 불가 → False (보수적: 비용 발생 거부).
    """
    if response is True:
        return True
    if response is False or response is None:
        return False
    if isinstance(response, dict):
        v = response.get("approved")
        if isinstance(v, bool):
            return v
    if isinstance(response, str):
        s = response.strip().lower()
        if s in ("y", "yes", "ok", "approve", "approved", "true", "1", "승인"):
            return True
        if s in ("n", "no", "deny", "reject", "false", "0", "거절", "취소"):
            return False
    return False


# ── Sensitive decision (외부 보고용 / 민감 답변 — Synthesizer 직전) ──
# PRD §9 비목표 인접 키워드 — 답변/질문에 등장 시 외부 노출 전 사용자 승인 요청.
# 매우 보수적 집합 — 추가 시 false-positive 영향 검토 (synthesizer 답변 차단 부작용).
SENSITIVE_KEYWORDS: tuple[str, ...] = (
    # 투자 자문 (PRD §9 영구 비목표 1)
    "투자 자문", "매매 신호", "추천 종목", "예상 수익", "수익률 전망",
    # 법적 조언 / 권고
    "법적 조언", "법적 권고", "법률 자문",
    # 가격 / 주가 예측 (PRD §1 "재무 수치는 LLM 이 생성하지 않는다" 인접)
    "주가 예측", "가격 예측",
)


def detect_sensitive_keyword(answer: str, question: str = "") -> str | None:
    """답변 (+ 선택적 질문) 에 sensitive 키워드 존재 시 첫 매칭 반환.

    호출처 (synthesizer_node 끝) 가 None 이면 게이트 통과, str 이면 interrupt 발동.
    매우 보수적 — false-positive 시 답변이 차단되므로 SENSITIVE_KEYWORDS 추가는
    실제 케이스 누적 후 의사결정.
    """
    if not answer:
        return None
    text = f"{answer}\n{question or ''}"
    for kw in SENSITIVE_KEYWORDS:
        if kw in text:
            return kw
    return None


def make_sensitive_decision_payload(
    *,
    answer_preview: str,
    plan_summary: str = "",
    thread_id: str = "",
) -> InterruptPayload:
    """민감 답변 게이트 — synthesizer 가 답변을 노출하기 전 사용자 확인 단계.

    trigger 정책 (어떤 답변을 민감으로 분류) 은 호출처가 결정한다 — 본 함수는
    payload 생성만 담당. 호출 예시:

        if should_gate_for_sensitive(answer):
            payload = make_sensitive_decision_payload(
                answer_preview=answer[:200], plan_summary=plan_brief
            )
            try:
                resp = request_interrupt(payload)
                approved = coerce_sensitive_response(resp)
            except InterruptUnavailable:
                approved = False   # 보수적 — interrupt 불가 시 미공개
            if not approved:
                state["answer"] = "민감 답변으로 분류되어 공개 보류됨"
    """
    return {
        "kind": "sensitive_decision",
        "prompt": "이 답변은 민감/외부 보고 후보로 분류됐습니다. 공개해도 되겠습니까?",
        "answer_preview": str(answer_preview)[:500],
        "plan_summary": plan_summary,
        "thread_id": thread_id,
    }


def coerce_sensitive_response(response: Any) -> bool:
    """resume 값을 공개 승인/거절 boolean 으로 정규화.

    True/False / "y"·"yes"·"approve"·"공개" / dict{"approved": bool}.
    인식 불가 → **False** (보수적: 미공개 — 민감 답변은 기본 차단).
    """
    if response is True:
        return True
    if response is False or response is None:
        return False
    if isinstance(response, dict):
        v = response.get("approved")
        if isinstance(v, bool):
            return v
    if isinstance(response, str):
        s = response.strip().lower()
        if s in ("y", "yes", "ok", "approve", "approved", "true", "1", "공개", "승인"):
            return True
        if s in ("n", "no", "deny", "reject", "false", "0", "비공개", "거절", "취소"):
            return False
    return False


__all__ = [
    "InterruptKind",
    "InterruptPayload",
    "InterruptUnavailable",
    "request_interrupt",
    "is_ambiguous_company",
    "make_clarification_payload",
    "coerce_clarification_response",
    "make_cost_approval_payload",
    "coerce_cost_response",
    "make_sensitive_decision_payload",
    "coerce_sensitive_response",
    "SENSITIVE_KEYWORDS",
    "detect_sensitive_keyword",
]
