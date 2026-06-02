"""산단공(15151075) 공정 row 단위 confidence 동적 격상 helper — PRD §3.5.1 SSOT.

본 파일은 **P0-B 의 시그니처만** 정의한다. 구현 본문 (`compute` 의 수식 + 등급 판정)은
PR-P3-B 에서 채워진다. 다른 모듈(`scripts/upgrade_processes_confidence.py`, 향후
`extractors/cross_validate.py::_VALIDATORS["CAUSED_BY_PROCESS"]` 등) 가 본 모듈을 import
한다는 약속만 잠근다.

PRD §3.5.1 인용 — 8 시그널 → ``conf = clip(0.50 + Σ w_i · s_i · grade_i − 0.20 · |conflicts|, 0.30, 1.00)``.
정적 등급표 ``_confidence.py::SOURCE_TO_GRADE`` 와 ``validator.py::LOW_CONFIDENCE_THRESHOLD``
는 무변경. 본 helper 의 결과는 ``auto.processes.confidence_score`` 컬럼에 row 단위 UPDATE.
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


def compute(sig: ProcessSignals) -> tuple[float, str, dict[str, float]]:
    """시그널 누적값 → (confidence, grade, signal-별 boost 기여도).

    **시그니처만 잠금 (P0-B). 본문은 PR-P3-B 에서 구현한다.**

    Returns
    -------
    confidence : float
        ``clip(0.50 + Σ w·s·grade − 0.20·|conflicts|, 0.30, 1.00)``.
    grade : str
        ``"A_candidate"`` (≥0.95) / ``"B"`` (≥0.80) / ``"needs_review"`` (≥0.65) / ``"C"``.
    boosts : dict[str, float]
        시그널 ID(``"M1"``..``"M7"``) → boost 기여도. 디버깅 / staging 추적용.
    """
    raise NotImplementedError(
        "process_confidence.compute() — signature locked in P0-B, implementation in PR-P3-B"
    )


__all__ = ["ProcessSignals", "W", "compute"]
