"""PRD §3.5 / §13 #4 — 출처 신뢰도 → confidence SSOT 매핑 테스트."""

from __future__ import annotations

from autograph.ingestion._confidence import (
    GRADE_TO_CONFIDENCE,
    KIND_OVERRIDE,
    SINGLE_SOURCE_FORBIDDEN_BELOW,
    SOURCE_TO_GRADE,
    SourceGrade,
    confidence_for,
    grade_for,
    validated_status_for,
)


def test_prd_3_5_grade_confidence_table():
    """PRD §3.5 표의 정량 매핑 — 본 모듈이 SSOT."""
    assert GRADE_TO_CONFIDENCE[SourceGrade.A_PLUS] == 1.00
    assert GRADE_TO_CONFIDENCE[SourceGrade.A]      == 0.95
    assert GRADE_TO_CONFIDENCE[SourceGrade.B]      == 0.80
    assert GRADE_TO_CONFIDENCE[SourceGrade.B_TO_C] == 0.70
    assert GRADE_TO_CONFIDENCE[SourceGrade.C]      == 0.50


def test_grade_for_nhtsa_is_a():
    """공공 API 는 A 등급."""
    assert grade_for("nhtsa_recall") == SourceGrade.A
    assert grade_for("nhtsa_vpic")   == SourceGrade.A
    assert grade_for("kncap")        == SourceGrade.A


def test_grade_for_wikidata_is_b():
    assert grade_for("wikidata") == SourceGrade.B


def test_grade_for_wikipedia_is_b_to_c():
    assert grade_for("wikipedia") == SourceGrade.B_TO_C


def test_grade_for_llm_is_c():
    assert grade_for("llm_extraction") == SourceGrade.C
    assert grade_for("llm_p3")         == SourceGrade.C


def test_grade_for_unknown_returns_none():
    assert grade_for("nonexistent_source") is None
    assert grade_for("") is None


def test_confidence_for_uses_grade_default():
    assert confidence_for("nhtsa_recall") == 0.95
    assert confidence_for("wikidata")     == 0.80
    assert confidence_for("llm_p3")       == 0.50


def test_confidence_for_kind_override_ir():
    """IR / manual / brochure 는 B 의 sub 케이스로 0.75 (PRD §3.5)."""
    assert confidence_for("ir_disclosure", kind="ir")     == 0.75
    assert confidence_for("ir_disclosure", kind="manual") == 0.75


def test_confidence_for_kind_override_community():
    """커뮤니티 / 분해 자료는 C 의 sub 케이스로 0.40."""
    assert confidence_for("community", kind="community") == 0.40
    assert confidence_for("teardown",  kind="teardown")  == 0.40


def test_confidence_for_unknown_default_fallback():
    """미정 출처 — default 명시 시 그 값, 아니면 0.50 (C 기본) 가정."""
    assert confidence_for("nonexistent")               == 0.50
    assert confidence_for("nonexistent", default=0.30) == 0.30


def test_validated_status_manual_review_wins():
    """수동 검토는 다른 모든 조건을 덮어쓴다."""
    assert validated_status_for("llm_p3", manual_reviewed=True) == "validated"


def test_validated_status_a_plus_auto_validated():
    assert validated_status_for("manual_curation") == "validated"


def test_validated_status_supply_relation_cross_validated():
    """공급 관계 (A/B 출처) + cross-validate → validated (PRD §3.5)."""
    assert validated_status_for("nhtsa_recall", cross_validated=True) == "validated"
    assert validated_status_for("wikidata",     cross_validated=True) == "validated"


def test_validated_status_c_grade_single_source_forbidden():
    """C 등급 단독 출처는 절대 validated 금지 (PRD §3.5)."""
    assert validated_status_for("llm_p3") == "candidate"
    assert validated_status_for("llm_p3", cross_validated=False) == "candidate"


def test_validated_status_unknown_source_needs_review():
    assert validated_status_for("unknown_xyz") == "needs_review"


def test_single_source_threshold_matches_validator():
    """본 모듈의 단독 근거 금지 임계값과 validator 의 게이트 임계값이 일치 — drift 방지."""
    from autonexusgraph.agents.validator import LOW_CONFIDENCE_THRESHOLD
    assert SINGLE_SOURCE_FORBIDDEN_BELOW == LOW_CONFIDENCE_THRESHOLD


def test_all_sources_have_valid_grade():
    """SOURCE_TO_GRADE 의 모든 값이 SourceGrade enum 멤버."""
    for source_id, grade in SOURCE_TO_GRADE.items():
        assert isinstance(grade, SourceGrade), \
            f"{source_id}: not a SourceGrade — {grade!r}"


def test_kind_override_values_in_range():
    """KIND_OVERRIDE 값이 모두 [0.0, 1.0] 범위."""
    for kind, val in KIND_OVERRIDE.items():
        assert 0.0 <= val <= 1.0, f"{kind}={val} out of range"
