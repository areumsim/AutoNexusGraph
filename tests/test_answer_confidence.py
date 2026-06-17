"""answer_confidence 전파 — calibration 입력 생성 회귀 가드.

compute_answer_confidence: 인용 엣지 A/B/C 등급(confidence) 최소값 우선, 없으면 retrieval
score 평균, 둘 다 없으면 None. → eval pred.answer_confidence → calibrate_confidence.py.
"""

from __future__ import annotations

from autonexusgraph.agents.answering import compute_answer_confidence


def test_edge_confidence_min_wins() -> None:
    """graph 엣지 confidence 보유 시 최소값(가장 약한 인용 엣지) 반환."""
    st = {"tool_results": [{"result": [{"confidence": 0.95}, {"confidence": 0.50}]}],
          "citations": [{"score": 0.9}]}
    assert compute_answer_confidence(st) == 0.5   # edge min, retrieval 무시


def test_retrieval_mean_fallback() -> None:
    """엣지 confidence 부재 시 인용 retrieval score 평균."""
    st = {"tool_results": [{"result": [{"corp_code": "x"}]}],
          "citations": [{"score": 0.8}, {"score": 0.4}]}
    assert compute_answer_confidence(st) == 0.6


def test_none_when_no_signal() -> None:
    """엣지·retrieval 둘 다 없으면 None(calibration 표본 제외)."""
    assert compute_answer_confidence({"tool_results": [], "citations": []}) is None
    assert compute_answer_confidence({"tool_results": [{"result": []}], "citations": []}) is None


def test_clamped_0_1() -> None:
    st = {"tool_results": [], "citations": [{"score": 1.5}]}
    assert compute_answer_confidence(st) == 1.0
