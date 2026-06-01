"""PRD §10 success criteria 의 임계값 SSOT.

여러 모듈 (runners/run_qa_eval, runners/run_matrix_smoke, metrics/latency,
metrics/main_hop_efficiency) 에 분산된 hardcoded 임계를 한 곳에 모은다.
각 임계가 어느 PRD 항목과 1:1 대응하는지 명시.

목적: PRD 임계 변경 시 한 파일만 갱신하면 모든 측정·리포트가 자동 동기.
"""

from __future__ import annotations

# ── PRD §10.7 — Hybrid vs Vector multi-hop EM 격차 ────────────
# 목표: hybrid 가 vector 대비 multi-hop EM (또는 F1) 에서 +30%p 이상 우위.
THESIS_DIFF_PP_TARGET: float = 30.0

# ── PRD §10.8 — Cross-Domain QA 4단계 EM 임계 (난이도별) ──────
# CD-L1 ~ CD-L4. 위(쉬움) → 아래(어려움).
CD_DIFFICULTY_TARGETS: dict[str, float] = {
    "CD-L1": 0.80,
    "CD-L2": 0.70,
    "CD-L3": 0.50,
    "CD-L4": 0.40,
}

# ── PRD §10.13 — Main-Hop Efficiency hybrid/vector ev_avg ratio ──
# 목표: hybrid 의 evidence 평균 카운트가 vector 의 70% 이하 (30%+ 감소).
MAIN_HOP_TARGET_RATIO: float = 0.7

# ── PRD §10.14 — Latency 임계 (초) ──────────────────────────────
# 도메인 내 8s 미만, Cross-Domain 12s 미만.
THRESHOLD_DOMAIN_INTERNAL_SEC: float = 8.0
THRESHOLD_CROSS_DOMAIN_SEC: float = 12.0


__all__ = [
    "THESIS_DIFF_PP_TARGET",
    "CD_DIFFICULTY_TARGETS",
    "MAIN_HOP_TARGET_RATIO",
    "THRESHOLD_DOMAIN_INTERNAL_SEC",
    "THRESHOLD_CROSS_DOMAIN_SEC",
]
