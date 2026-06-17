"""DoD §10.7 dashboard 권위 출처 회귀 가드.

배경: dashboard 가 §10.7 을 소형 smoke matrix(잡음·S-7 pre-fix)에서 도출해 thesis
(+66pp CONFIRMED)를 ❌ FAIL 로 오표기하던 결함이 있었다. 생성기를 62문항 thesis gold
(graph_multihop_v0) eval-full 실측을 권위 출처로 쓰도록 근본 수정 — 본 가드가 회귀를 막는다.

주의: eval/reports/<run> 아티팩트는 git 비추적(런타임 산출물)이라, 부재 환경(CI 등)에선
skip. 아티팩트가 있는 개발 환경에서만 정합을 검증한다.
"""

from __future__ import annotations

import pytest

from eval.metrics.prd_dashboard import (
    _collect_thesis_audit,
    _thesis_from_authoritative_gold,
)


def test_thesis_authoritative_gold_composition() -> None:
    """권위 gold 실측이 있으면 hybrid·vector 합성 + 출처 명시 + 30%p 판정."""
    r = _thesis_from_authoritative_gold()
    if r is None:
        pytest.skip("thesis gold eval-full 아티팩트 부재 (git 비추적 — 개발 환경 전용)")
    assert r["status"] in ("pass", "fail")
    assert "graph_multihop_v0" in r["detail"]
    assert "hybrid" in r["detail"] and "vector" in r["detail"]
    assert "+30%p" in r["detail"]


def test_thesis_audit_not_misreported_from_smoke() -> None:
    """§10.7 최종 판정은 권위 실측을 따른다 — smoke matrix(잡음) ❌ 오표기 회귀 차단.

    아티팩트 존재 시: 현행 실측은 +69.4%p(>30) → pass 여야 한다.
    """
    if _thesis_from_authoritative_gold() is None:
        pytest.skip("thesis gold eval-full 아티팩트 부재")
    assert _collect_thesis_audit()["status"] == "pass"
