#!/usr/bin/env python3
"""PRD §10 DoD #17 (d) — 축소 평가 매트릭스 thin wrapper.

``eval.runners.run_matrix_smoke`` 가 실제 측정 로직. 본 wrapper 는 dod_audit 패턴
정합성 유지 + PYTHONPATH 설정만 담당.

기본 = simulation 모드 (LLM 비용 0, 10 cells = 8 base + 축2 hybrid planner ablation 2).
``--full`` 시 실 run_qa_eval (룰 vs LLM planner 정량 비교 포함).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from eval.runners.run_matrix_smoke import main   # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
