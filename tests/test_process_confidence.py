"""P0-B 시그니처 잠금 검증 (구현은 PR-P3-B).

PRD §3.5.1 의 helper 가 import 가능 + 가중 W 합이 이론 max boost 와 일치 +
compute() 가 호출 시 NotImplementedError 로 즉시 fail (P3-B 미구현 명확화).
"""

from __future__ import annotations

import pytest

from autograph.extractors.process_confidence import ProcessSignals, W, compute


def test_signature_dataclass_defaults() -> None:
    """ProcessSignals 의 8 필드가 안전한 기본값 (시그널 없음 = 0/False/[]) 으로 초기화."""
    sig = ProcessSignals()
    assert sig.nhtsa_module == 0.0
    assert sig.dart_cos == 0.0
    assert sig.oem_ir_hits == 0
    assert sig.ksic_match is False
    assert sig.dart_product == 0.0
    assert sig.recall_p4 == 0.0
    assert sig.standard_match is False
    assert sig.conflicts == []


def test_weights_match_prd_3_5_1() -> None:
    """가중 W 합계 = 0.70 (PRD §3.5.1 이론 max boost — clip 시 0.95)."""
    assert set(W.keys()) == {"M1", "M2", "M3", "M4", "M5", "M6", "M7"}
    assert abs(sum(W.values()) - 0.70) < 1e-9


def test_compute_signature_locked_not_implemented() -> None:
    """compute() 는 P0-B 에서 시그니처만 — 호출 시 PR-P3-B 안내 메시지로 즉시 fail.

    이 가드가 있어야 P3-B 실수로 본문 누락 시 import 만 PASS 하고 runtime 에 silent
    0.0 / 빈 dict 반환하는 일이 안 생김.
    """
    sig = ProcessSignals(nhtsa_module=1.0, dart_cos=0.8)
    with pytest.raises(NotImplementedError, match="P3-B"):
        compute(sig)
