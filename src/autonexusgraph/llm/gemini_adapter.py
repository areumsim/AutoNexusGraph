"""Google Gemini 어댑터 — gemini-2.5-pro / flash / 1.5 시리즈.

LLM_PROVIDER=google (또는 모델명 'gemini-*' 자동 감지) 일 때 사용.

JSON 구조화 출력은 ``response_mime_type='application/json'`` + ``response_schema``
조합 사용 (Gemini 공식 권장).

의존성: ``pip install google-genai`` (새 SDK; 옛 ``google-generativeai`` 와 별개).
미설치 환경에서도 본 패키지 import 는 가능 — 실제 client 인스턴스화 시점에 fail.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .base import LLMClient, LLMError, LLMResponse, TokenUsage


# 모델별 토큰 단가 (USD, 1M 토큰당) — ai.google.dev/pricing
# ≤200K input tokens 기본 가격. 그 이상은 별 가격이나 MVP 트래픽은 보통 lower tier.
_PRICING: dict[str, tuple[float, float]] = {
    "gemini-2.5-pro":        (1.25,  5.00),
    "gemini-2.5-flash":      (0.30,  2.50),
    "gemini-2.5-flash-lite": (0.10,  0.40),
    "gemini-1.5-pro":        (1.25,  5.00),
    "gemini-1.5-flash":      (0.075, 0.30),
    "gemini-1.5-flash-8b":   (0.0375, 0.15),
}


class GeminiClient(LLMClient):
    """Google Gemini API wrapper (google-genai SDK)."""

    def __init__(self, model: str, api_key: str, timeout: float = 120.0) -> None:
        if not api_key:
            raise LLMError(
                "Google API key 미설정 (.env: GOOGLE_API_KEY 또는 LLM_API_KEY)"
            )
        try:
            from google import genai  # lazy — pip install google-genai
        except ImportError as e:
            raise LLMError(
                "google-genai 패키지 미설치. `pip install google-genai` 후 재시도."
            ) from e

        self.model = model
        self._timeout = timeout
        # client 는 동기 호출 시 일반 메서드; 비동기는 client.aio 네임스페이스.
        self._client = genai.Client(api_key=api_key)

    # ── 메시지 변환 — Gemini 는 system 을 별도 인자로 받음 ────────────
    def _split_messages(
        self, messages: list[dict[str, str]],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """system 추출 + 나머지를 Gemini contents 형식으로 변환.

        Gemini contents 의 role 은 'user' | 'model' (assistant 가 아니다).
        """
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []
        for m in messages:
            role = m.get("role")
            content = m.get("content", "")
            if role == "system":
                if content:
                    system_parts.append(content)
                continue
            gem_role = "model" if role == "assistant" else "user"
            contents.append({"role": gem_role, "parts": [{"text": content}]})
        system = "\n\n".join(p for p in system_parts if p) or None
        return system, contents

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        system, contents = self._split_messages(messages)
        cfg: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            cfg["max_output_tokens"] = max_tokens
        if system is not None:
            cfg["system_instruction"] = system
        try:
            resp = self._client.models.generate_content(
                model=self.model,
                contents=contents,
                config=cfg,
                **kwargs,
            )
        except Exception as e:
            raise LLMError(f"Gemini chat failed: {e}") from e

        content = (resp.text or "") if hasattr(resp, "text") else ""
        usage = _build_usage(self.model, getattr(resp, "usage_metadata", None))
        return LLMResponse(content=content, usage=usage, raw=resp)

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        system, contents = self._split_messages(messages)
        cfg: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            cfg["max_output_tokens"] = max_tokens
        if system is not None:
            cfg["system_instruction"] = system
        try:
            stream = self._client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=cfg,
                **kwargs,
            )
            for chunk in stream:
                t = getattr(chunk, "text", "") or ""
                if t:
                    yield t
        except Exception as e:
            raise LLMError(f"Gemini stream failed: {e}") from e

    def chat_json(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """JSON 강제 — response_mime_type + response_schema 사용."""
        import json
        system, contents = self._split_messages(messages)
        # schema 가 {name, description, schema} wrapper 면 'schema' 만 추출.
        gem_schema = schema.get("schema", schema) if isinstance(schema, dict) else schema
        cfg: dict[str, Any] = {
            "temperature": temperature,
            "response_mime_type": "application/json",
            "response_schema": gem_schema,
        }
        max_tokens = kwargs.pop("max_tokens", None)
        if max_tokens is not None:
            cfg["max_output_tokens"] = max_tokens
        if system is not None:
            cfg["system_instruction"] = system
        try:
            resp = self._client.models.generate_content(
                model=self.model,
                contents=contents,
                config=cfg,
                **kwargs,
            )
        except Exception as e:
            raise LLMError(f"Gemini json failed: {e}") from e

        # Gemini 가 parsed 객체를 직접 줄 수도, text 만 줄 수도 있음 — 안전하게 둘 다 처리.
        parsed = getattr(resp, "parsed", None)
        if isinstance(parsed, dict):
            return parsed
        text = (resp.text or "") if hasattr(resp, "text") else ""
        if not text:
            raise LLMError("Gemini returned empty JSON response")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"Gemini JSON parse failed: {e}; text={text[:200]!r}") from e


def _build_usage(model: str, usage: Any) -> TokenUsage:
    if usage is None:
        return TokenUsage(model=model)
    prompt = int(getattr(usage, "prompt_token_count", 0) or 0)
    completion = int(getattr(usage, "candidates_token_count", 0) or 0)
    total = int(getattr(usage, "total_token_count", prompt + completion) or 0)
    in_per_1m, out_per_1m = _PRICING.get(model, (0.0, 0.0))
    cost = (prompt * in_per_1m + completion * out_per_1m) / 1_000_000
    return TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total or (prompt + completion),
        cost_usd=cost,
        model=model,
    )


__all__ = ["GeminiClient"]
