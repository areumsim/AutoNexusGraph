"""LLM 어댑터 추상 인터페이스.

모든 Provider(OpenAI/Anthropic/로컬)는 이 인터페이스를 구현한다.
비즈니스 로직은 이 인터페이스만 알면 되고, LLM 종류는 환경변수 LLM_PROVIDER 로 결정된다.

구현체는 후속 PR (Phase 1) 에서 추가:
- openai_adapter.OpenAIClient
- anthropic_adapter.AnthropicClient
- local_adapter.LocalLLMClient

PRD §5 (LLM 추상화 전략) 참조.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """토큰 사용량 — 비용 추적·평가용."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""

    def __add__(self, other: TokenUsage) -> TokenUsage:
        """집계 — 동일 모델만 합산을 권장. 다른 모델 혼합 시 model='mixed'.

        cost tracking 의 model 별 정확도를 위해 호출자가 가능하면 모델별로
        TokenUsage 를 분리해서 집계할 것. 본 메서드는 안전한 default 만 제공.
        """
        if not self.model:
            merged_model = other.model
        elif not other.model or self.model == other.model:
            merged_model = self.model
        else:
            merged_model = "mixed"
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
            model=merged_model,
        )


@dataclass
class LLMResponse:
    """동기 응답 표준 형식."""

    content: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    raw: Any = None  # provider-native response (디버깅용)


class LLMError(Exception):
    """LLM 호출 실패 (timeout, rate limit, invalid response 등)."""


class LLMClient(ABC):
    """모든 LLM Provider 의 공통 인터페이스.

    구현체는 다음 3가지 메서드를 반드시 제공한다:
    - chat: 단일 응답
    - chat_stream: 토큰 스트리밍
    - chat_json: 구조화 출력 (JSON Schema 강제)
    """

    model: str

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """일반 채팅 — 단일 응답 반환."""

    @abstractmethod
    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """스트리밍 — 토큰 단위 yield."""

    @abstractmethod
    def chat_json(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """구조화 출력 — JSON Schema 강제, dict 반환.

        Planner/Triage/Validator 등 의사결정 노드에서 사용.
        """


def detect_provider(model: str) -> str:
    """모델명 prefix → provider 자동 결정.

    Returns: 'openai' | 'anthropic' | 'google' | 'local'.
    알 수 없는 모델은 'openai' (가장 흔한 기본값) — 호출자가 명시 권장.
    """
    m = (model or "").lower()
    if m.startswith(("gpt-", "o1", "o3", "chatgpt")):
        return "openai"
    if m.startswith(("claude-", "claude_")):
        return "anthropic"
    if m.startswith(("gemini-", "gemini_")):
        return "google"
    if m.startswith(("local", "qwen", "llama", "mistral")):
        return "local"
    return "openai"


def _select_api_key(settings: Any, provider: str) -> str:
    """provider 별 API 키 선택 — 모델명 prefix 로 결정된 provider 의 키 반환.

    local provider 는 키 불필요 (빈 문자열 반환).
    """
    by_provider = {
        "openai":    getattr(settings, "openai_api_key", "") or "",
        "anthropic": getattr(settings, "anthropic_api_key", "") or "",
        "google":    getattr(settings, "google_api_key", "") or "",
    }
    return by_provider.get(provider, "")


# fallback provider 의 모델 미지정 시 기본 FAST 모델 (llm_fallback_model 비었을 때만).
_DEFAULT_FAST_MODEL: dict[str, str] = {
    "openai":    "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "google":    "gemini-2.5-flash",
}


def _build_adapter(provider: str, model: str, settings: Any) -> LLMClient:
    """provider+model → 구체 LLMClient adapter (auto-wrap 이전 raw). 키는 settings 에서 선택.

    primary 와 fallback 양쪽이 동일 경로로 생성되도록 switch 를 한 곳에 모은다.
    """
    key = _select_api_key(settings, provider)
    timeout = settings.llm_timeout
    if provider == "openai":
        from .openai_adapter import OpenAIClient
        return OpenAIClient(model=model, api_key=key, timeout=timeout)
    if provider == "anthropic":
        from .anthropic_adapter import AnthropicClient
        return AnthropicClient(model=model, api_key=key, timeout=timeout)
    if provider == "google":
        from .gemini_adapter import GeminiClient
        return GeminiClient(model=model, api_key=key, timeout=timeout)
    if provider == "local":
        from .local_adapter import LocalLLMClient
        return LocalLLMClient(
            model=model,
            base_url=settings.local_llm_base_url,
            api_key=key or "EMPTY",
            timeout=timeout,
        )
    raise LLMError(f"unknown LLM provider: {provider!r} (model={model!r})")


def _maybe_wrap_fallback(inner: LLMClient, primary_provider: str, settings: Any) -> LLMClient:
    """llm_fallback_provider 설정 시 [primary, fallback] 를 FallbackLLMClient 로 묶음.

    비활성/키 부재/동일 provider 면 inner 를 그대로 반환(기존 단일-provider 동작 보존).
    """
    fb_provider = (getattr(settings, "llm_fallback_provider", "") or "").strip()
    if not fb_provider or fb_provider == primary_provider:
        return inner
    # 키 부재(local 제외) → 조용히 비활성 (graceful skip).
    if fb_provider != "local" and not _select_api_key(settings, fb_provider):
        logger.debug("fallback provider %s 키 미설정 — fallback 비활성", fb_provider)
        return inner
    fb_model = (getattr(settings, "llm_fallback_model", "") or "").strip() \
        or _DEFAULT_FAST_MODEL.get(fb_provider, "")
    if not fb_model:
        logger.debug("fallback provider %s 기본 모델 없음 — fallback 비활성", fb_provider)
        return inner
    try:
        fb_inner = _build_adapter(fb_provider, fb_model, settings)
    except LLMError as exc:
        logger.debug("fallback adapter 생성 실패 (skip): %s", exc)
        return inner
    from .fallback import FallbackLLMClient
    logger.debug("provider fallback 활성: %s → %s(%s)",
                 inner.model, fb_provider, fb_model)
    return FallbackLLMClient([inner, fb_inner])


def get_llm_client(
    role: str | None = None,
    *,
    model: str | None = None,
    provider: str | None = None,
) -> LLMClient:
    """팩토리 — 모델명/provider 에 따라 적절한 LLMClient 반환.

    Args:
        role: 용도별 모델 매핑 키 (triage|planner|supervisor|research|graph|
              sql|calculator|validator|synthesizer|judge|titler 등).
              ``llm_model_<role>`` 설정값을 모델로 사용.
        model: 명시 override — role 무시하고 이 모델 사용.
        provider: 명시 override — 모델명 감지 결과를 무시하고 강제.

    Provider 결정 우선순위:
        1. 명시 인자 ``provider`` (있으면 그것)
        2. settings.llm_provider 가 'auto' 가 아니면 그 값
        3. 모델명 prefix 기반 자동 감지 (detect_provider)

    API 키 결정:
        provider 별 settings.{openai,anthropic,google}_api_key. local 은 키 불필요.
    """
    from ..config import get_settings

    s = get_settings()
    # Kill-switch — llm_enabled=False 면 모든 LLM 호출 차단 (llm_guard.py off).
    if not getattr(s, "llm_enabled", True):
        raise LLMError("LLM disabled (llm_enabled kill-switch). `make llm-on` 또는 "
                       ".env LLM_ENABLED=true 로 활성화.")
    final_model = model if model else _resolve_model(s, role)
    if provider:
        final_provider = provider
    elif s.llm_provider != "auto":
        final_provider = s.llm_provider
    else:
        final_provider = detect_provider(final_model)

    inner: LLMClient = _build_adapter(final_provider, final_model, s)
    # Provider fallback (옵션) — 1차 LLMError 시 보조 provider 로 자동 전환.
    # innermost 에 두어 BudgetAware 의 가드/기록이 실제 응답 adapter 기준 1회만 발생.
    inner = _maybe_wrap_fallback(inner, final_provider, s)

    # Auto-wrap — 모든 client 가 항상 비용 가드 + 영속 로그를 거치게 한다.
    #   inner(adapter) → BudgetAwareLLMClient(호출 전 guard, 후 record)
    #                  → LoggingLLMClient(cost_log.jsonl append) [최외곽]
    # 호출자가 budget_aware_client 로 또 감싸도 idempotent 하게 처리되어 이중 record
    # 안 됨(budget_aware.py 참조). 지연 import 로 base↔budget_aware 순환 회피.
    from .budget_aware import BudgetAwareLLMClient
    from .cost_log import LoggingLLMClient
    from .cost_tracker import get_session_tracker
    caller_name = role or "anon"
    tracker = get_session_tracker(caller=caller_name, model=final_model)
    return LoggingLLMClient(BudgetAwareLLMClient(inner, tracker), caller=caller_name)  # type: ignore[return-value]  # 위임 래퍼 — LLMClient 인터페이스 충족


def _resolve_model(settings: Any, role: str | None) -> str:
    """역할별 모델 override 결정."""
    if role:
        attr = f"llm_model_{role}"
        v = getattr(settings, attr, None)
        if v:
            return v
    return settings.llm_model
