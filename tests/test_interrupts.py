"""HITL interrupt — payload 형식·모호성 검출·응답 해석 검증 (PRD §7.5.6)."""

from __future__ import annotations

import pytest

from autonexusgraph.agents.interrupts import (
    SENSITIVE_KEYWORDS,
    InterruptUnavailable,
    coerce_clarification_response,
    coerce_sensitive_response,
    detect_sensitive_keyword,
    is_ambiguous_company,
    make_clarification_payload,
    make_sensitive_decision_payload,
    request_interrupt,
)


# ── is_ambiguous_company ────────────────────────────────────
def test_empty_or_single_candidate_not_ambiguous():
    assert not is_ambiguous_company([])
    assert not is_ambiguous_company([{"corp_code": "00126380", "score": 100}])


def test_two_candidates_close_score_ambiguous():
    candidates = [
        {"corp_code": "00126380", "name": "삼성전자(주)", "score": 100},
        {"corp_code": "00126362", "name": "삼성SDI", "score": 95},
    ]
    assert is_ambiguous_company(candidates)


def test_two_candidates_far_score_not_ambiguous():
    candidates = [
        {"corp_code": "00126380", "name": "삼성전자", "score": 100},
        {"corp_code": "99999999", "name": "삼성서비스마스터", "score": 30},
    ]
    assert not is_ambiguous_company(candidates)


def test_two_candidates_no_score_treated_as_ambiguous():
    """score 가 없는 환경 — 후보 여럿이면 보수적으로 모호 처리."""
    candidates = [
        {"corp_code": "00126380", "name": "X"},
        {"corp_code": "00126362", "name": "Y"},
    ]
    assert is_ambiguous_company(candidates)


def test_custom_margin():
    candidates = [
        {"score": 100}, {"score": 91},
    ]
    assert is_ambiguous_company(candidates, max_margin=0.10)
    assert not is_ambiguous_company(candidates, max_margin=0.05)


# ── make_clarification_payload ──────────────────────────────
def test_payload_structure():
    cands = [
        {"corp_code": "00126380", "name": "삼성전자", "stock_code": "005930", "market": "KOSPI"},
        {"corp_code": "00126362", "name": "삼성SDI", "stock_code": "006400", "market": "KOSPI"},
    ]
    p = make_clarification_payload("삼성", cands, thread_id="t1")
    assert p["kind"] == "company_clarification"
    assert "삼성" in p["prompt"]
    assert p["thread_id"] == "t1"
    assert len(p["candidates"]) == 2
    assert p["candidates"][0]["corp_code"] == "00126380"


def test_payload_truncates_to_limit():
    cands = [{"corp_code": f"{i:08d}", "name": f"C{i}"} for i in range(10)]
    p = make_clarification_payload("X", cands, limit=3)
    assert len(p["candidates"]) == 3


# ── coerce_clarification_response ───────────────────────────
def test_coerce_by_index():
    cands = [
        {"corp_code": "00126380", "name": "삼성전자"},
        {"corp_code": "00126362", "name": "삼성SDI"},
    ]
    assert coerce_clarification_response(1, cands) == "00126362"
    assert coerce_clarification_response({"index": 0}, cands) == "00126380"


def test_coerce_by_corp_code_dict():
    cands = [{"corp_code": "00126380"}]
    assert coerce_clarification_response({"corp_code": "00126362"}, cands) == "00126362"


def test_coerce_by_direct_corp_code_string():
    cands = [{"corp_code": "00126380"}]
    assert coerce_clarification_response("00164779", cands) == "00164779"


def test_coerce_by_name_match():
    cands = [
        {"corp_code": "00126380", "name": "삼성전자"},
        {"corp_code": "00126362", "name": "삼성SDI"},
    ]
    assert coerce_clarification_response("삼성SDI", cands) == "00126362"


def test_coerce_invalid_returns_none():
    cands = [{"corp_code": "00126380"}]
    assert coerce_clarification_response("invalid", cands) is None
    assert coerce_clarification_response(99, cands) is None
    assert coerce_clarification_response({}, cands) is None
    assert coerce_clarification_response(None, cands) is None


# ── request_interrupt ───────────────────────────────────────
# ── sensitive_decision payload + coerce ─────────────────────
def test_sensitive_decision_payload_structure():
    p = make_sensitive_decision_payload(
        answer_preview="삼성전자 영업이익 ...",
        plan_summary="finance+graph 2-hop",
        thread_id="t-1",
    )
    assert p["kind"] == "sensitive_decision"
    assert p["answer_preview"].startswith("삼성전자")
    assert p["plan_summary"] == "finance+graph 2-hop"
    assert p["thread_id"] == "t-1"
    assert "민감" in p["prompt"]


def test_sensitive_decision_truncates_preview_500():
    p = make_sensitive_decision_payload(answer_preview="가" * 600)
    assert len(p["answer_preview"]) == 500


def test_coerce_sensitive_bool_dict():
    assert coerce_sensitive_response(True) is True
    assert coerce_sensitive_response(False) is False
    assert coerce_sensitive_response(None) is False
    assert coerce_sensitive_response({"approved": True}) is True
    assert coerce_sensitive_response({"approved": False}) is False


def test_coerce_sensitive_string_korean_english():
    assert coerce_sensitive_response("yes") is True
    assert coerce_sensitive_response("공개") is True
    assert coerce_sensitive_response("승인") is True
    assert coerce_sensitive_response("no") is False
    assert coerce_sensitive_response("비공개") is False
    assert coerce_sensitive_response("거절") is False


def test_coerce_sensitive_unknown_defaults_to_false():
    # PRD §7.5.6 보수 정책 — 인식 불가는 미공개 (False).
    assert coerce_sensitive_response("maybe") is False
    assert coerce_sensitive_response(123) is False
    assert coerce_sensitive_response({"other_key": True}) is False


# ── detect_sensitive_keyword 휴리스틱 ────────────────────────
def test_detect_sensitive_empty_returns_none():
    assert detect_sensitive_keyword("") is None
    assert detect_sensitive_keyword("", "어떤 질문") is None


def test_detect_sensitive_investment_keyword():
    # PRD §9 영구 비목표 — 투자 자문 인접
    assert detect_sensitive_keyword("이 주식은 강력한 매매 신호입니다") == "매매 신호"
    assert detect_sensitive_keyword("추천 종목 3선") == "추천 종목"


def test_detect_sensitive_legal_keyword():
    assert detect_sensitive_keyword("이는 법적 조언이 아닙니다") == "법적 조언"


def test_detect_sensitive_prediction_keyword():
    assert detect_sensitive_keyword("내일 주가 예측") == "주가 예측"


def test_detect_sensitive_question_text_also_matched():
    # 질문에 키워드 있으면 답변 정상이어도 게이트 발동.
    assert detect_sensitive_keyword(
        "삼성전자 매출은 300조원입니다",
        question="투자 자문 부탁드립니다",
    ) == "투자 자문"


def test_detect_sensitive_clean_answer_returns_none():
    assert detect_sensitive_keyword(
        "삼성전자 2024 매출은 약 300조원입니다 [출처:00126380,2024]"
    ) is None


def test_sensitive_keywords_constant_non_empty():
    # 정책 회귀 가드 — 상수가 비어있으면 게이트가 무력화됨.
    assert isinstance(SENSITIVE_KEYWORDS, tuple) and len(SENSITIVE_KEYWORDS) >= 5


def test_request_interrupt_raises_when_langgraph_missing(monkeypatch):
    """langgraph.types.interrupt import 막아서 fallback 환경 시뮬."""
    import sys
    # langgraph 가 있어도 types.interrupt 만 막기는 어려우니, 호출 자체가 raise 하도록
    # interrupt 함수를 임시로 ImportError 던지게.
    try:
        from langgraph.types import interrupt as _real_interrupt  # noqa: F401
    except ImportError:
        # 이미 미설치 환경 — request_interrupt 가 InterruptUnavailable 던져야
        with pytest.raises(InterruptUnavailable):
            request_interrupt({"kind": "company_clarification", "prompt": "?", "candidates": []})
        return
    # 설치된 환경 — module 자체를 임시 제거
    saved = sys.modules.pop("langgraph.types", None)
    try:
        sys.modules["langgraph.types"] = None   # type: ignore[assignment]
        # 일부 환경에서 langgraph.graph.interrupt 가 별도로 있을 수 있어 그것까지 제거
        saved_graph = sys.modules.pop("langgraph.graph", None)
        sys.modules["langgraph.graph"] = None   # type: ignore[assignment]
        try:
            with pytest.raises(InterruptUnavailable):
                request_interrupt({"kind": "company_clarification", "prompt": "?", "candidates": []})
        finally:
            if saved_graph is not None:
                sys.modules["langgraph.graph"] = saved_graph
    finally:
        if saved is not None:
            sys.modules["langgraph.types"] = saved
