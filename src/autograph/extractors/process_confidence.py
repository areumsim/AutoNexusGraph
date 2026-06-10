"""산단공(15151075) 공정 row 단위 confidence 동적 격상 helper — PRD §3.5.1 SSOT.

`compute()` 본문 **구현 완료** (P0-B 시그니처 잠금 → 본 구현). 운영 wire-up
(`extractors/cross_validate.py::_VALIDATORS["CAUSED_BY_PROCESS"]`,
`scripts/upgrade_processes_confidence.py`) 은 BACKLOG PG-3 에서 별도 연결.

PRD §3.5.1 인용 — 7 시그널 → ``conf = clip(0.50 + Σ w_i · s_i − 0.20 · |conflicts|, 0.30, 1.00)``.
각 시그널 강도 ``s_i`` 는 [0,1] 로 정규화(float 신호=그대로, bool=1.0/0.0,
int M3=빈도 saturation). PRD 표기의 ``grade_i`` 는 ``s_i`` 강도에 흡수(신호값이 이미
출처 강도를 인코딩). 정적 등급표 ``_confidence.py::SOURCE_TO_GRADE`` 와
``validator.py::LOW_CONFIDENCE_THRESHOLD`` 는 무변경. 결과는
``anxg_auto.processes.confidence_score`` 컬럼에 row 단위 UPDATE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final


@dataclass
class ProcessSignals:
    """산단공 공정 row 한 건에 대한 외부 A/B 매칭 시그널 누적값 (PRD §3.5.1 표).

    각 필드는 cross_validate 파이프라인의 한 단계가 채운다. 시그널이 없으면 0/False
    그대로 — compute() 가 grade 0.0 으로 처리.
    """

    nhtsa_module:    float = 0.0    # M1 [0,1] — NHTSA Module taxonomy KO-EN 사전 매칭
    dart_cos:        float = 0.0    # M2 [0,1] — DART narrative BGE-M3 cosine
    oem_ir_hits:     int   = 0      # M3 int  — OEM IR/뉴스 regex mention 빈도
    ksic_match:      bool  = False  # M4 bool — KSIC C30xxx 산업분류 직접 매핑
    dart_product:    float = 0.0    # M5 [0,1] — DART plant_capacity.product_name 토큰 overlap
    recall_p4:       float = 0.0    # M6 [0,1] — NHTSA recall LLM P3 → CAUSED_BY_PROCESS P4 검증
    standard_match:  bool  = False  # M7 bool — KS X 9001 / ISO 18629 PSL manual seed 정확 매칭
    conflicts:       list[str] = field(default_factory=list)   # C1 — 충돌 시그널 ID 목록


W: Final[dict[str, float]] = {
    "M1": 0.15,
    "M2": 0.15,
    "M3": 0.10,
    "M4": 0.05,
    "M5": 0.10,
    "M6": 0.10,
    "M7": 0.05,
}

# 기준선·penalty·clip 경계 (PRD §3.5.1).
_BASE: Final[float] = 0.50
_CONFLICT_PENALTY: Final[float] = 0.20
_FLOOR: Final[float] = 0.30
_CEIL: Final[float] = 1.00
# M3(oem_ir_hits, int) saturation — N회 이상 멘션이면 강도 1.0. 설계선택(PRD 표는 빈도만 명시).
_M3_SATURATION: Final[int] = 3

# grade 임계 (내림차순).
_GRADE_THRESHOLDS: Final[tuple[tuple[float, str], ...]] = (
    (0.95, "A_candidate"),
    (0.80, "B"),
    (0.65, "needs_review"),
    (0.00, "C"),
)


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


def compute(sig: ProcessSignals) -> tuple[float, str, dict[str, float]]:
    """시그널 누적값 → (confidence, grade, signal-별 boost 기여도).

    ``conf = clip(0.50 + Σ w_i·s_i − 0.20·|conflicts|, 0.30, 1.00)``. 각 ``s_i`` 는
    [0,1] 강도(float=그대로 clip, bool=1.0/0.0, int M3=빈도 saturation).

    Returns
    -------
    confidence : float
        ``clip(0.50 + Σ w·s − 0.20·|conflicts|, 0.30, 1.00)``.
    grade : str
        ``"A_candidate"`` (≥0.95) / ``"B"`` (≥0.80) / ``"needs_review"`` (≥0.65) / ``"C"``.
    boosts : dict[str, float]
        시그널 ID(``"M1"``..``"M7"``) → boost 기여도 ``w_i·s_i``. 디버깅 / staging 추적용.
    """
    strengths: dict[str, float] = {
        "M1": _clip01(sig.nhtsa_module),
        "M2": _clip01(sig.dart_cos),
        "M3": _clip01(sig.oem_ir_hits / _M3_SATURATION) if sig.oem_ir_hits > 0 else 0.0,
        "M4": 1.0 if sig.ksic_match else 0.0,
        "M5": _clip01(sig.dart_product),
        "M6": _clip01(sig.recall_p4),
        "M7": 1.0 if sig.standard_match else 0.0,
    }
    boosts: dict[str, float] = {mid: W[mid] * strengths[mid] for mid in W}
    raw = _BASE + sum(boosts.values()) - _CONFLICT_PENALTY * len(sig.conflicts)
    confidence = max(_FLOOR, min(_CEIL, raw))

    grade = "C"
    for threshold, label in _GRADE_THRESHOLDS:
        if confidence >= threshold:
            grade = label
            break
    return confidence, grade, boosts


__all__ = ["ProcessSignals", "W", "compute"]
