"""Provider fallback wrapper — 1차 provider 실패(LLMError) 시 보조 provider 자동 전환.

``get_llm_client()`` 가 ``llm_fallback_provider`` 설정 시 ``[primary, fallback]`` adapter
를 이 wrapper 로 묶는다. **BudgetAware/Logging 의 안쪽(innermost)** 에 위치하므로 비용
가드·기록은 실제 응답한 adapter 기준 1회만 발생한다.

설계 메모 (실제 코드 검증 기반):
- ``LLMError`` 만 잡고 다음 client 로 넘어간다 — 그 외 예외는 그대로 전파.
  ``BudgetExceeded`` 는 ``Exception`` (LLMError 아님) 이고 BudgetAware 가 이 wrapper
  *바깥에서* raise 하므로 여기로 오지 않는다 → 예산 한도는 영향 없음.
- ``chat`` / ``chat_json``: 1차 실패 시 다음 client 시도, 전부 실패면 마지막 에러 raise.
- ``chat_stream``: **첫 청크 이전** 에 실패할 때만 fallback. 이미 청크를 호출자에게
  yield 한 뒤에는 깨끗한 재시작이 불가능하므로 그대로 전파한다. (배치 평가 경로는
  chat/chat_json 만 사용 → 이 한계는 평가에 영향 없음.)
- ``self.model`` 은 primary 모델. 바깥 wrapper (BudgetAware/Logging) 가 생성 시 ``.model``
  을 캐시하므로 per-call 교체는 어차피 전달되지 않는다(문서화된 한계). ``chat`` 응답
  비용은 ``resp.usage.model`` 로 정확하게 산정되고, ``chat_json`` 추정 비용만 primary
  모델 단가로 계산된다(드문 fallback 경로에 한함).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from .base import LLMClient, LLMError, LLMResponse

logger = logging.getLogger(__name__)


class FallbackLLMClient(LLMClient):
    """순서 있는 LLMClient 목록 — 앞에서부터 시도, ``LLMError`` 시 다음으로 전환."""

    def __init__(self, clients: list[LLMClient]) -> None:
        if not clients:
            raise ValueError("FallbackLLMClient: clients 가 비어 있음")
        self._clients = list(clients)
        self.model = clients[0].model

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        last: LLMError | None = None
        for i, c in enumerate(self._clients):
            try:
                return c.chat(messages, temperature=temperature,
                              max_tokens=max_tokens, **kwargs)
            except LLMError as e:
                last = e
                if i + 1 < len(self._clients):
                    logger.warning("LLM chat fallback %s→%s: %s",
                                   c.model, self._clients[i + 1].model, e)
        assert last is not None   # clients 비어있지 않음 보장 → 루프가 ≥1회 돈다
        raise last

    def chat_json(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        last: LLMError | None = None
        for i, c in enumerate(self._clients):
            try:
                return c.chat_json(messages, schema, temperature=temperature, **kwargs)
            except LLMError as e:
                last = e
                if i + 1 < len(self._clients):
                    logger.warning("LLM chat_json fallback %s→%s: %s",
                                   c.model, self._clients[i + 1].model, e)
        assert last is not None
        raise last

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        last: LLMError | None = None
        for i, c in enumerate(self._clients):
            gen = c.chat_stream(messages, temperature=temperature,
                                max_tokens=max_tokens, **kwargs)
            try:
                first = next(gen)
            except StopIteration:
                return                      # 빈 스트림 — 정상 종료
            except LLMError as e:           # 첫 청크 이전 실패 → 다음 client 시도
                last = e
                if i + 1 < len(self._clients):
                    logger.warning("LLM chat_stream fallback %s→%s (pre-chunk): %s",
                                   c.model, self._clients[i + 1].model, e)
                continue
            # 첫 청크 확보 — 이후는 그대로 흘려보냄(중간 에러는 전파, 재시작 불가).
            yield first
            yield from gen
            return
        assert last is not None
        raise last


__all__ = ["FallbackLLMClient"]
