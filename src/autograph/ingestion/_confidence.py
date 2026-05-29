"""출처 신뢰도 → confidence_score 단일 매핑 (PRD §3.5 / §13 #4).

PRD v2.1 §3.5 의 "출처별 신뢰도 등급" 표를 코드 SSOT 로 옮긴 모듈. 로더·추출기·
validator 가 동일한 매핑을 참조해 그래프 confidence 가 의도와 어긋나지 않게
한다 (drift 차단).

PRD §3.5 (정량):

| 출처                              | 등급   | 기본 confidence |
|---|---|---|
| NHTSA / 자동차리콜센터 공식 리콜      | A     | 0.95 |
| NHTSA vPIC                       | A     | 0.95 |
| KNCAP / NCAP / Euro NCAP          | A     | 0.95 |
| Wikidata                          | B     | 0.80 |
| Wikipedia                         | B~C   | 0.70 |
| 부품사 IR (공식 공시)              | B     | 0.75 |
| 매뉴얼 / 브로셔                    | B     | 0.75 |
| LLM 추출 (P3)                     | C     | 0.50 |
| 커뮤니티 / 분해 자료               | C     | 0.40 |
| 수동 검토 확정                     | A+    | 1.00 |

PRD §3.5 (정성 — `validated_status` 승급 정책):
- ``SUPPLIED_BY`` 등 공급 관계: A 또는 B 출처 + P4 cross-validate → ``validated``
- 그 외: ``candidate`` 또는 ``needs_review``
- C 등급 단독 출처는 절대 ``validated`` 금지

본 모듈의 매핑 변경 = PRD 변경. 변경 시 PRD v2.X 문서와 동기화 필요.
"""

from __future__ import annotations

from enum import Enum
from typing import Final


class SourceGrade(str, Enum):
    """PRD §3.5 출처 신뢰도 등급."""

    A_PLUS = "A+"   # 수동 검토 확정
    A      = "A"    # 공식 정부·공공 API (NHTSA / 자동차리콜센터 / NCAP / vPIC)
    B      = "B"    # Wikidata / 공식 공시 / 매뉴얼
    B_TO_C = "B~C"  # Wikipedia 등 위키 본문
    C      = "C"    # LLM 추출 / 커뮤니티


# ── 출처 ID → 등급 ────────────────────────────────────────────────
# 신규 출처를 추가할 때는 본 dict 에 한 줄 추가하고, PRD §3.5 표도 함께 갱신.
SOURCE_TO_GRADE: Final[dict[str, SourceGrade]] = {
    # A 등급 — 공공 API / 공식 인증
    "nhtsa_recall":        SourceGrade.A,
    "nhtsa_vpic":          SourceGrade.A,
    "nhtsa_complaint":     SourceGrade.A,
    "nhtsa_safety":        SourceGrade.A,
    "nhtsa_investigation": SourceGrade.A,
    "ncap":                SourceGrade.A,
    "kncap":               SourceGrade.A,
    "euro_ncap":           SourceGrade.A,
    "katri":               SourceGrade.A,
    "car_go_kr":           SourceGrade.A,
    "datagokr_recall":     SourceGrade.A,
    "datagokr_inspection": SourceGrade.A,
    "epa_fueleconomy":     SourceGrade.A,
    "sec_oem":             SourceGrade.A,
    # B 등급 — Wikidata / 공식 공시 / 매뉴얼
    "wikidata":            SourceGrade.B,
    "wikidata_p176":       SourceGrade.B,
    "ir_disclosure":       SourceGrade.B,
    "manual":              SourceGrade.B,
    "brochure":            SourceGrade.B,
    "manual_supplier_seed": SourceGrade.B,
    # B~C 등급 — Wikipedia 등 위키 본문
    "wikipedia":           SourceGrade.B_TO_C,
    "wikipedia_auto":      SourceGrade.B_TO_C,
    # C 등급 — LLM 추출 / 커뮤니티
    "llm_extraction":      SourceGrade.C,
    "llm_p3":              SourceGrade.C,
    "community":           SourceGrade.C,
    "teardown":            SourceGrade.C,
    # A+ — 수동 검토 확정
    "manual_curation":     SourceGrade.A_PLUS,
    "reviewed":            SourceGrade.A_PLUS,
}


# ── 등급 → 기본 confidence ────────────────────────────────────────
GRADE_TO_CONFIDENCE: Final[dict[SourceGrade, float]] = {
    SourceGrade.A_PLUS: 1.00,
    SourceGrade.A:      0.95,
    SourceGrade.B:      0.80,
    SourceGrade.B_TO_C: 0.70,
    SourceGrade.C:      0.50,
}

# 매뉴얼 / 브로셔 / IR 는 PRD 표에서 0.75 — B 의 sub 케이스로 본 모듈은 0.80 을
# 적용하고, 호출자가 `kind='ir'` / `'manual'` 같은 hint 로 다운그레이드를
# 명시할 수 있다. 명시 안 하면 등급 기본값을 사용.
KIND_OVERRIDE: Final[dict[str, float]] = {
    "ir":       0.75,
    "manual":   0.75,
    "brochure": 0.75,
}

# 커뮤니티 / 분해 자료 — PRD 표 0.40 (C 의 sub).
KIND_OVERRIDE.update({
    "community": 0.40,
    "teardown":  0.40,
})


# 단독 근거 금지 임계값 (PRD §6.7). validator.LOW_CONFIDENCE_THRESHOLD 와 일치.
SINGLE_SOURCE_FORBIDDEN_BELOW: Final[float] = 0.50


def grade_for(source_id: str) -> SourceGrade | None:
    """``source_id`` 의 PRD §3.5 등급. 미정 출처는 ``None`` — 호출자가 명시."""
    if not source_id:
        return None
    return SOURCE_TO_GRADE.get(str(source_id).strip().lower())


def confidence_for(source_id: str, *,
                   kind: str | None = None,
                   default: float | None = None) -> float:
    """출처 ID → PRD 기본 confidence.

    Args:
        source_id: ``SOURCE_TO_GRADE`` 키 (대소문자 무관). 미정 시 default.
        kind: ``KIND_OVERRIDE`` 키 (예: 'ir', 'manual', 'community'). 등급보다 우선.
        default: 매핑 실패 시 반환할 fallback. None 이면 ``0.50`` (C 등급) 가정.

    Returns:
        0.0 ~ 1.0 confidence_score.
    """
    if kind:
        k = kind.strip().lower()
        if k in KIND_OVERRIDE:
            return float(KIND_OVERRIDE[k])
    grade = grade_for(source_id)
    if grade is None:
        if default is not None:
            return float(default)
        return float(GRADE_TO_CONFIDENCE[SourceGrade.C])
    return float(GRADE_TO_CONFIDENCE[grade])


def validated_status_for(source_id: str, *,
                         cross_validated: bool = False,
                         manual_reviewed: bool = False) -> str:
    """PRD §3.5 + §6.7 의 ``validated_status`` 승급 정책.

    - 수동 검토 확정 → ``validated``
    - 공급 관계 (A/B 출처 + P4 통과) → ``validated``
    - C 등급 단독 → 절대 ``validated`` 금지 → ``candidate``
    - 그 외 → ``candidate``
    """
    if manual_reviewed:
        return "validated"
    grade = grade_for(source_id)
    if grade is None:
        return "needs_review"
    if grade == SourceGrade.A_PLUS:
        return "validated"
    if cross_validated and grade in (SourceGrade.A, SourceGrade.B):
        return "validated"
    if grade == SourceGrade.C and not cross_validated:
        # PRD §3.5 — C 등급 단독 출처는 validated 금지
        return "candidate"
    return "candidate"


__all__ = [
    "SourceGrade",
    "SOURCE_TO_GRADE",
    "GRADE_TO_CONFIDENCE",
    "KIND_OVERRIDE",
    "SINGLE_SOURCE_FORBIDDEN_BELOW",
    "grade_for",
    "confidence_for",
    "validated_status_for",
]
