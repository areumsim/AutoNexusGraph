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

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TokenUsage:
    """토큰 사용량 — 비용 추적·평가용."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
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
    final_model = model if model else _resolve_model(s, role)
    if provider:
        final_provider = provider
    elif s.llm_provider != "auto":
        final_provider = s.llm_provider
    else:
        final_provider = detect_provider(final_model)

    key = _select_api_key(s, final_provider)

    if final_provider == "openai":
        from .openai_adapter import OpenAIClient
        inner: LLMClient = OpenAIClient(model=final_model, api_key=key, timeout=s.llm_timeout)
    elif final_provider == "anthropic":
        from .anthropic_adapter import AnthropicClient
        inner = AnthropicClient(model=final_model, api_key=key, timeout=s.llm_timeout)
    elif final_provider == "google":
        from .gemini_adapter import GeminiClient
        inner = GeminiClient(model=final_model, api_key=key, timeout=s.llm_timeout)
    elif final_provider == "local":
        from .local_adapter import LocalLLMClient
        inner = LocalLLMClient(
            model=final_model,
            base_url=s.local_llm_base_url,
            api_key=key or "EMPTY",
            timeout=s.llm_timeout,
        )
    else:
        raise LLMError(
            f"unknown LLM provider: {final_provider!r} (model={final_model!r})"
        )

    # 모든 LLM 호출이 누락 없이 cost_log.jsonl 에 기록되도록 wrap.
    # provider/메서드/budget_aware wrap 여부 무관 — 본 wrapper 가 항상 마지막에.
    from .cost_log import LoggingLLMClient
    caller_name = role or "anon"
    return LoggingLLMClient(inner, caller=caller_name)


def _resolve_model(settings: Any, role: str | None) -> str:
    """역할별 모델 override 결정."""
    if role:
        attr = f"llm_model_{role}"
        v = getattr(settings, attr, None)
        if v:
            return v
    return settings.llm_model
