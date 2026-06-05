"""LLMClient wrapper — 호출마다 cost_tracker.record + 사전 tracker.guard.

사용자 명시 원칙 (memory: feedback-llm-cost-brake): 모든 LLM 호출은 비용 한도 가드를
거쳐야 한다. 호출자가 record 를 까먹는 실수를 방지하기 위해 LLMClient 자체를 wrapping.

사용:
    from autonexusgraph.llm.budget_aware import budget_aware_client

    client = budget_aware_client(get_llm_client(role='extractor'),
                                  caller='p3_extract', hard_limit=2.00)
    # 이후 client.chat/.chat_json/.chat_stream 호출 시 자동 record + guard.

호출자가 별도 패키지에서 tracker 를 control 하려면 wrap 안 하고
raw LLMClient + tracker.record 수동 호출도 가능.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

from .base import LLMClient, LLMResponse
from .cost_tracker import BudgetExceeded, CostTracker, get_tracker


class BudgetAwareLLMClient(LLMClient):
    """LLMClient delegating wrapper — 호출 전 guard, 호출 후 record."""

    def __init__(self, inner: LLMClient, tracker: CostTracker) -> None:
        self._inner = inner
        self._tracker = tracker
        self.model = inner.model

    def __getattr__(self, name: str):
        """알려지지 않은 속성은 inner 로 위임 (auto-wrap 시 LoggingLLMClient 가
        `_last_usage`/`set_caller` 등을 BA 경유로 찾게 함). _inner 미설정 시 무한
        재귀 방지."""
        if name == "_inner":
            raise AttributeError(name)
        return getattr(self._inner, name)

    def chat(self, messages, *, temperature=0.0, max_tokens=None,
             purpose: str | None = None, **kwargs) -> LLMResponse:
        self._tracker.guard()
        t0 = time.monotonic()
        resp = self._inner.chat(messages, temperature=temperature,
                                 max_tokens=max_tokens, **kwargs)
        latency_ms = int((time.monotonic() - t0) * 1000)
        self._tracker.record(
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
            model=resp.usage.model or self.model,
            purpose=purpose,
            latency_ms=latency_ms,
        )
        return resp

    def chat_stream(self, messages, *, temperature=0.0, max_tokens=None,
                    purpose: str | None = None, **kwargs) -> Iterator[str]:
        self._tracker.guard()
        # stream 은 provider 가 usage 를 노출 안 하는 경우가 많아 char/3 보수적 추정.
        # (과거: 여기서 record 를 안 해 스트리밍 비용이 tracker 누적에 빠져 guard 가
        # 영영 안 터지는 누수가 있었음 — finally 에서 종료/중단 시 1회 record.)
        from .cost import cost_of_call
        t0 = time.monotonic()
        chunks: list[str] = []
        try:
            for c in self._inner.chat_stream(messages, temperature=temperature,
                                             max_tokens=max_tokens, **kwargs):
                chunks.append(c)
                yield c
        finally:
            latency_ms = int((time.monotonic() - t0) * 1000)
            in_est = sum(len(m.get("content", "") or "") for m in messages) // 3
            out_est = sum(len(c) for c in chunks) // 3
            self._tracker.record(
                input_tokens=in_est,
                output_tokens=out_est,
                model=self.model,
                purpose=purpose,
                latency_ms=latency_ms,
            )

    def chat_json(self, messages, schema, *, temperature=0.0,
                  purpose: str | None = None, **kwargs) -> dict[str, Any]:
        self._tracker.guard()
        t0 = time.monotonic()
        # chat_json 은 LLMResponse 가 아닌 dict 반환 — provider 마다 usage 노출 다름.
        # OpenAI/Anthropic 어댑터에 _last_usage 추적이 없으면 input 기준으로 보수적 추정 필요.
        result = self._inner.chat_json(messages, schema, temperature=temperature, **kwargs)
        latency_ms = int((time.monotonic() - t0) * 1000)

        # last_usage 추출 시도 — adapter 가 노출하면 사용, 아니면 추정.
        usage = getattr(self._inner, "_last_usage", None)
        if usage is not None:
            self._tracker.record(
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                model=usage.model or self.model,
                purpose=purpose,
                latency_ms=latency_ms,
            )
        else:
            # 추정 fallback — messages 의 문자수 / 4 (한국어 더 빡빡하지만 보수적)
            est_in = sum(len(m.get("content", "")) for m in messages) // 3
            est_out = len(str(result)) // 3
            self._tracker.record(
                input_tokens=est_in,
                output_tokens=est_out,
                model=self.model,
                purpose=purpose,
                latency_ms=latency_ms,
            )
        return result


def _chain_has_budget_guard(client: LLMClient) -> bool:
    """client 의 wrap 체인(._inner 따라) 에 BudgetAwareLLMClient 가 이미 있는지.

    get_llm_client() 가 auto-wrap 으로 BudgetAwareLLMClient 를 끼우므로, 호출자가
    또 budget_aware_client 로 감싸면 같은 tracker 에 record 2회 → 이중 계산된다.
    이를 막기 위해 체인을 검사한다.
    """
    seen = 0
    cur: object | None = client
    while cur is not None and seen < 10:        # 깊이 가드
        if isinstance(cur, BudgetAwareLLMClient):
            return True
        cur = getattr(cur, "_inner", None)
        seen += 1
    return False


def budget_aware_client(
    inner: LLMClient,
    *,
    caller: str,
    hard_limit: float | None = None,
) -> LLMClient:
    """LLMClient + tracker 결합. idempotent — 이미 가드된 체인은 재-wrap 안 함.

    tracker tighten(hard_limit) 은 어느 경우든 수행하므로 호출자의 turn budget 은
    항상 반영된다.
    """
    tracker = get_tracker(caller=caller, model=inner.model, hard_limit=hard_limit)
    if _chain_has_budget_guard(inner):
        # auto-wrap 으로 이미 가드됨 — 한도만 tighten 하고 그대로 반환(이중 record 방지).
        return inner
    return BudgetAwareLLMClient(inner, tracker)


__all__ = [
    "BudgetAwareLLMClient", "budget_aware_client", "BudgetExceeded",
    "_chain_has_budget_guard",
]
