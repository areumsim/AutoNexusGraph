"""LLM 호출 비용 estimator + 모델별 가격표.

사용자 명시 원칙: 모든 LLM 호출은 실행 전 dry-run 으로 비용 추정 → 한도 비교 →
승인 가드 통과해야 실제 호출 가능. circuit breaker 는 cost_tracker.py 참조.

가격 단위: USD per 1M tokens (input / output 분리).
출처: 공식 가격 페이지. 갱신 시 본 파일만 수정하면 됨.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# ─── 모델별 가격표 (USD per 1M tokens) ───────────────────────────────
# (input_per_1m, output_per_1m)
PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o":              (2.50, 10.00),
    "gpt-4o-2024-11-20":   (2.50, 10.00),
    "gpt-4o-2024-08-06":   (2.50, 10.00),
    "gpt-4o-mini":         (0.15,  0.60),
    "gpt-4o-mini-2024-07-18": (0.15, 0.60),
    "gpt-4-turbo":         (10.00, 30.00),
    "gpt-4":               (30.00, 60.00),

    # Anthropic Claude
    "claude-opus-4-7":     (15.00, 75.00),
    "claude-opus-4-5":     (15.00, 75.00),
    "claude-sonnet-4-6":   (3.00,  15.00),
    "claude-sonnet-4-5":   (3.00,  15.00),
    "claude-haiku-4-5":    (1.00,   5.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),

    # Google Gemini (≤200K input tokens 기본 가격; 그 이상은 별 가격, 본 표는
    # MVP 트래픽 가정으로 lower tier 사용. 공식: ai.google.dev/pricing)
    "gemini-2.5-pro":       (1.25,  5.00),
    "gemini-2.5-flash":     (0.30,  2.50),
    "gemini-2.5-flash-lite":(0.10,  0.40),
    "gemini-1.5-pro":       (1.25,  5.00),
    "gemini-1.5-flash":     (0.075, 0.30),
    "gemini-1.5-flash-8b":  (0.0375, 0.15),

    # Local — 비용 0 (자체 GPU)
    "local":               (0.00, 0.00),
}


def _resolve_pricing(model: str) -> tuple[float, float]:
    """모델명 → (input, output) per 1M tokens.

    정확 매칭 우선, 없으면 prefix 매칭 (예: 'gpt-4o-2024-...' → 'gpt-4o').
    여전히 없으면 (1.0, 3.0) 을 보수적 fallback 으로 사용하고 경고.
    """
    if model in PRICING:
        return PRICING[model]
    # prefix fallback
    for key in PRICING:
        if model.startswith(key):
            return PRICING[key]
    # local 모델 패턴
    if model.startswith("local") or "qwen" in model.lower() or "llama" in model.lower():
        return (0.0, 0.0)
    # unknown — 보수적 fallback (over-estimate)
    return (1.0, 3.0)


@dataclass(frozen=True)
class CostEstimate:
    model: str
    n_calls: int
    input_tokens_per_call: float
    output_tokens_per_call: float
    total_input_tokens: int
    total_output_tokens: int
    cost_usd: float

    def format(self) -> str:
        return (
            f"[COST EST] {self.model} × {self.n_calls:,} calls × "
            f"~{self.input_tokens_per_call:.0f}/{self.output_tokens_per_call:.0f} tok "
            f"= ${self.cost_usd:.4f}"
        )


def estimate(
    model: str,
    n_calls: int,
    avg_input_tokens: float,
    avg_output_tokens: float,
) -> CostEstimate:
    """LLM 호출 batch 의 총 비용 추정 (USD)."""
    in_per_1m, out_per_1m = _resolve_pricing(model)
    total_in = int(n_calls * avg_input_tokens)
    total_out = int(n_calls * avg_output_tokens)
    cost = (total_in / 1_000_000) * in_per_1m + (total_out / 1_000_000) * out_per_1m
    return CostEstimate(
        model=model,
        n_calls=n_calls,
        input_tokens_per_call=avg_input_tokens,
        output_tokens_per_call=avg_output_tokens,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        cost_usd=cost,
    )


def cost_of_call(model: str, input_tokens: int, output_tokens: int) -> float:
    """단일 호출 비용 (실제 usage 기록 시 사용)."""
    in_per_1m, out_per_1m = _resolve_pricing(model)
    return (input_tokens / 1_000_000) * in_per_1m + (output_tokens / 1_000_000) * out_per_1m


# ─── 한도 정책 (셸 env > .env/settings > 코드 기본값) ─────────────────────
# 주의: .env 는 pydantic Settings 로만 로드되고 os.environ 에는 반영되지 않는다.
# 따라서 os.environ 만 보면 .env 값이 무시된다 (과거 버그). 아래 헬퍼는
# 셸 export(os.environ) → settings(.env) → 코드 기본값 순으로 resolve 한다.
def _resolve_float(env_key: str, settings_attr: str, default: float) -> float:
    raw = os.environ.get(env_key)
    if raw is not None:
        try:
            return float(raw)
        except ValueError:
            pass
    try:
        from ..config import get_settings
        v = getattr(get_settings(), settings_attr, None)
        if v is not None:
            return float(v)
    except Exception:   # noqa: BLE001 — 호출 실패 흡수 → default 반환
        pass
    return default


def get_hard_limit_usd(default: float = 5.00) -> float:
    """per-turn/batch hard limit — 단일 tracker(한 turn 또는 한 배치) 누적 한도."""
    return _resolve_float("LLM_COST_HARD_LIMIT_USD", "llm_cost_hard_limit_usd", default)


def get_session_limit_usd(default: float = 5.00) -> float:
    """영속(세션/일) 누적 한도 — cost_log.jsonl 기반, turn/process 리셋과 무관."""
    return _resolve_float("LLM_SESSION_HARD_LIMIT_USD", "llm_session_hard_limit_usd", default)


def get_cost_window_hours(default: float = 24.0) -> float:
    """영속 누적 한도 집계 시간창(시간). 0 이하면 전체 기간(all-time)."""
    return _resolve_float("LLM_COST_WINDOW_HOURS", "llm_cost_window_hours", default)


def get_auto_approve_usd(default: float = 0.50) -> float:
    """이하면 자동 진행, 초과면 --approve-cost 또는 prompt 필요."""
    return _resolve_float("LLM_COST_AUTO_APPROVE_USD", "llm_cost_auto_approve_usd", default)


def get_report_every(default: int = 10) -> int:
    """매 N 호출마다 누적 비용 로그."""
    return int(_resolve_float("LLM_COST_REPORT_EVERY", "llm_cost_report_every", default))


# ─── CLI 진입점 가드 ──────────────────────────────────────────────────
class BudgetCheck:
    """진입 전 cost gate.

    사용:
        gate = BudgetCheck.from_env(caller='p3_extract')
        est = estimate('gpt-4o-mini', n_calls=1200, avg_input=800, avg_output=300)
        print(est.format())
        gate.review(est, approve_cost=args.approve_cost,
                    max_cost_override=args.max_cost)
        # 통과하면 진행, 실패하면 SystemExit 또는 raise.
    """

    def __init__(self, caller: str, hard_limit: float, auto_approve: float) -> None:
        self.caller = caller
        self.hard_limit = hard_limit
        self.auto_approve = auto_approve

    @classmethod
    def from_env(cls, caller: str) -> BudgetCheck:
        return cls(caller, get_hard_limit_usd(), get_auto_approve_usd())

    def review(
        self,
        est: CostEstimate,
        *,
        approve_cost: bool = False,
        max_cost_override: float | None = None,
        dry_run: bool = False,
        interactive: bool = True,
    ) -> bool:
        """추정 비용을 가드와 비교 → 통과 / abort.

        통과: True 반환.
        abort: SystemExit (CLI 진입점) — 호출자가 이 함수 통과 후에만 실제 LLM 호출.

        rules:
            dry_run=True              → 통과 후 실제 호출 안 함 (호출자 책임)
            est <= auto_approve        → 자동 통과
            auto_approve < est < hard_limit  → approve_cost 필요 (없으면 abort)
            est >= hard_limit          → max_cost_override 없으면 abort
        """
        limit = max_cost_override if max_cost_override is not None else self.hard_limit
        approved_via = ""

        if est.cost_usd <= self.auto_approve:
            approved_via = "auto"
        elif est.cost_usd <= limit:
            if approve_cost:
                approved_via = "--approve-cost"
            elif interactive:
                ans = input(f"\n[COST GATE] 추정 ${est.cost_usd:.4f} > 자동승인 한도 ${self.auto_approve:.4f}. 진행? [y/N] ").strip().lower()
                if ans in ("y", "yes"):
                    approved_via = "interactive-yes"
                else:
                    print("[COST GATE] 사용자 거절. 종료.")
                    raise SystemExit(3)
            else:
                print(f"[COST GATE] 추정 ${est.cost_usd:.4f} > auto_approve ${self.auto_approve:.4f}. "
                      f"--approve-cost 필요 또는 --limit 줄이세요. 종료.")
                raise SystemExit(3)
        else:
            print(f"[COST GATE] 추정 ${est.cost_usd:.4f} ≥ hard_limit ${limit:.4f}. "
                  f"--max-cost 로 override 하거나 --limit 줄이세요. 종료.")
            raise SystemExit(3)

        print(f"[COST GATE] {est.format()}  → {approved_via} (limit ${limit:.4f})")
        if dry_run:
            print("[COST GATE] --dry-run: 실제 LLM 호출 안 함. 종료 코드 0")
            raise SystemExit(0)
        return True


__all__ = [
    "PRICING", "CostEstimate", "estimate", "cost_of_call",
    "get_hard_limit_usd", "get_session_limit_usd", "get_cost_window_hours",
    "get_auto_approve_usd", "get_report_every",
    "BudgetCheck",
]
