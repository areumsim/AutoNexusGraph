"""process_confidence.compute() 구현 검증 (PRD §3.5.1).

ProcessSignals import + 가중 W 합 + compute 의 수식/clip/grade 동작.
"""

from __future__ import annotations

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


def test_compute_no_signals_is_base_grade_c() -> None:
    """시그널 0 → 기준선 0.50, grade C, 모든 boost 0."""
    conf, grade, boosts = compute(ProcessSignals())
    assert conf == 0.50
    assert grade == "C"
    assert all(v == 0.0 for v in boosts.values())
    assert set(boosts) == set(W)


def test_compute_all_max_signals_is_a_candidate() -> None:
    """모든 시그널 최대 → 0.50 + 0.70 = 1.20 → clip 1.00 → A_candidate."""
    sig = ProcessSignals(
        nhtsa_module=1.0, dart_cos=1.0, oem_ir_hits=10, ksic_match=True,
        dart_product=1.0, recall_p4=1.0, standard_match=True,
    )
    conf, grade, boosts = compute(sig)
    assert conf == 1.00
    assert grade == "A_candidate"
    assert abs(sum(boosts.values()) - 0.70) < 1e-9


def test_compute_conflicts_penalty() -> None:
    """충돌 1건당 −0.20. 강신호 2개(0.50+0.30=0.80) − 0.20 = 0.60 → needs_review 아래(C)."""
    base = ProcessSignals(nhtsa_module=1.0, dart_cos=1.0)        # boost 0.30
    conf0, grade0, _ = compute(base)
    assert abs(conf0 - 0.80) < 1e-9 and grade0 == "B"
    conf1, grade1, _ = compute(ProcessSignals(nhtsa_module=1.0, dart_cos=1.0, conflicts=["C1"]))
    assert abs(conf1 - 0.60) < 1e-9 and grade1 == "C"


def test_compute_grade_thresholds() -> None:
    """B(≥0.80) / needs_review(≥0.65) 경계."""
    # 0.50 + M1·0.15 + M2·0.15 + M5·0.10 = 0.50 + 0.40·... 조정해 0.65 만들기
    # M1=1,M2=1 → 0.80 (B), M1=1,M5=1 → 0.50+0.15+0.10=0.75 (needs_review)
    _, g_b, _ = compute(ProcessSignals(nhtsa_module=1.0, dart_cos=1.0))
    assert g_b == "B"
    _, g_nr, _ = compute(ProcessSignals(nhtsa_module=1.0, dart_product=1.0))
    assert g_nr == "needs_review"


def test_compute_clip_floor() -> None:
    """충돌 다수로 0.30 floor clip."""
    conf, grade, _ = compute(ProcessSignals(conflicts=["a", "b", "c"]))   # 0.50 − 0.60 = −0.10
    assert conf == 0.30
    assert grade == "C"


def test_m3_saturation_and_clip() -> None:
    """M3 int 빈도: 3회 이상 → 강도 1.0(saturation), 음수 float 신호는 0 clip."""
    _, _, b_full = compute(ProcessSignals(oem_ir_hits=3))
    _, _, b_over = compute(ProcessSignals(oem_ir_hits=100))
    assert abs(b_full["M3"] - W["M3"]) < 1e-9          # 3회 = 만점 boost
    assert b_full["M3"] == b_over["M3"]                # saturation
    _, _, b_neg = compute(ProcessSignals(dart_cos=-0.5))
    assert b_neg["M2"] == 0.0                          # 음수 clip
