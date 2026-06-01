"""PRD §10.7 thesis 계산 helper — Hybrid vs Vector multi-hop 격차.

여러 곳에서 hybrid/vector metric 의 +30%p 격차를 계산한다:
- ``eval/runners/run_qa_eval.py::compute_hybrid_vs_vector`` (single-run, summary dict 입력)
- ``eval/runners/run_matrix_smoke.py::compute_thesis_headline`` (matrix cells list 입력)

본 helper 는 두 함수가 공유하는 핵심 산식 (diff_pp + target_met) 만 책임. 입력 구조
차이로 함수 자체 통합은 불가, helper 추출이 단일 진실 보존 수단.
"""

from __future__ import annotations

from ._thresholds import THESIS_DIFF_PP_TARGET


def compute_diff_pp(hybrid: float, vector: float) -> tuple[float, bool]:
    """단일 metric (EM 또는 F1) 의 hybrid−vector 격차를 %p 로 환산 + target met 여부.

    Args:
        hybrid: hybrid 어댑터의 multi-hop metric (0~1 비율)
        vector: vector 어댑터의 multi-hop metric (0~1 비율)

    Returns:
        (diff_pp, target_met) — diff_pp 는 round(., 2), target_met 은 ``diff_pp >= 30.0``.
    """
    diff_pp = round((hybrid - vector) * 100.0, 2)
    return diff_pp, diff_pp >= THESIS_DIFF_PP_TARGET


__all__ = ["compute_diff_pp", "THESIS_DIFF_PP_TARGET"]
