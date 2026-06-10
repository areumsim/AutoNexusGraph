"""Provider fallback (FallbackLLMClient) 회귀 테스트 — 네트워크/실 SDK 호출 없음.

검증:
1. FallbackLLMClient — primary OK 시 fallback 미호출.
2. primary LLMError → fallback 으로 전환 (chat / chat_json).
3. 전부 실패 → 마지막 에러 raise.
4. LLMError 아닌 예외는 swallow 안 함 (그대로 전파).
5. chat_stream — 첫 청크 이전 실패 시 fallback.
6. get_llm_client — llm_fallback_provider 설정 시 FallbackLLMClient 로 묶음.
7. fallback 미설정 / 키 부재 시 단일 provider 동작 보존(무-wrap).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from autonexusgraph.llm.base import LLMClient, LLMError, LLMResponse, TokenUsage
from autonexusgraph.llm.fallback import FallbackLLMClient


class _Fake(LLMClient):
    """테스트용 LLMClient — 예외/응답을 주입."""

    def __init__(self, model: str, *, chat_exc=None, json_exc=None,
                 content: str = "ok", json_val=None) -> None:
        self.model = model
        self._chat_exc = chat_exc
        self._json_exc = json_exc
        self._content = content
        self._json_val = json_val if json_val is not None else {"ok": True}
        self.chat_calls = 0
        self.json_calls = 0
        self.stream_calls = 0

    def chat(self, messages, *, temperature=0.0, max_tokens=None, **kw) -> LLMResponse:
        self.chat_calls += 1
        if self._chat_exc:
            raise self._chat_exc
        return LLMResponse(content=self._content, usage=TokenUsage(model=self.model))

    def chat_stream(self, messages, *, temperature=0.0, max_tokens=None, **kw):
        self.stream_calls += 1
        if self._chat_exc:
            raise self._chat_exc          # 첫 next() 시점에 발생 → pre-chunk 실패 모사
        yield self._content

    def chat_json(self, messages, schema, *, temperature=0.0, **kw) -> dict:
        self.json_calls += 1
        if self._json_exc:
            raise self._json_exc
        return dict(self._json_val)


# ── 1~5) FallbackLLMClient 단위 ────────────────────────────────────
def test_chat_uses_primary_when_ok():
    prim = _Fake("claude", content="from-primary")
    back = _Fake("gpt")
    fb = FallbackLLMClient([prim, back])
    assert fb.chat([{"role": "user", "content": "hi"}]).content == "from-primary"
    assert prim.chat_calls == 1
    assert back.chat_calls == 0                     # fallback 미호출


def test_chat_falls_back_on_llmerror():
    prim = _Fake("claude", chat_exc=LLMError("primary down"))
    back = _Fake("gpt", content="from-fallback")
    fb = FallbackLLMClient([prim, back])
    assert fb.chat([{"role": "user", "content": "hi"}]).content == "from-fallback"
    assert prim.chat_calls == 1
    assert back.chat_calls == 1


def test_chat_json_falls_back_on_llmerror():
    prim = _Fake("claude", json_exc=LLMError("primary json down"))
    back = _Fake("gpt", json_val={"served_by": "fallback"})
    fb = FallbackLLMClient([prim, back])
    out = fb.chat_json([{"role": "user", "content": "hi"}], {"name": "X"})
    assert out == {"served_by": "fallback"}
    assert back.json_calls == 1


def test_all_fail_raises_last_error():
    prim = _Fake("claude", chat_exc=LLMError("e-primary"))
    back = _Fake("gpt", chat_exc=LLMError("e-fallback"))
    fb = FallbackLLMClient([prim, back])
    with pytest.raises(LLMError, match="e-fallback"):     # 마지막 에러 전파
        fb.chat([{"role": "user", "content": "hi"}])


def test_non_llmerror_propagates_without_fallback():
    """LLMError 가 아닌 예외(예: BudgetExceeded 류)는 잡지 않고 그대로 전파."""
    prim = _Fake("claude", chat_exc=ValueError("not an LLMError"))
    back = _Fake("gpt")
    fb = FallbackLLMClient([prim, back])
    with pytest.raises(ValueError):
        fb.chat([{"role": "user", "content": "hi"}])
    assert back.chat_calls == 0                     # fallback 시도 안 함


def test_chat_stream_falls_back_pre_chunk():
    prim = _Fake("claude", chat_exc=LLMError("stream down"))
    back = _Fake("gpt", content="streamed")
    fb = FallbackLLMClient([prim, back])
    assert "".join(fb.chat_stream([{"role": "user", "content": "hi"}])) == "streamed"
    assert back.stream_calls == 1


def test_model_is_primary():
    fb = FallbackLLMClient([_Fake("claude"), _Fake("gpt")])
    assert fb.model == "claude"


# ── 6~7) get_llm_client 통합 — 체인에 FallbackLLMClient 삽입 여부 ────
def _find_fallback(client) -> FallbackLLMClient | None:
    cur, seen = client, 0
    while cur is not None and seen < 10:
        if isinstance(cur, FallbackLLMClient):
            return cur
        cur = getattr(cur, "_inner", None)
        seen += 1
    return None


def _clear_settings():
    from autonexusgraph import config
    config.get_settings.cache_clear()               # type: ignore[attr-defined]


def test_get_llm_client_wraps_fallback_when_configured(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an-key")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "openai")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "gpt-4o-mini")
    _clear_settings()

    with patch("autonexusgraph.llm.anthropic_adapter.AnthropicClient",
               return_value=_Fake("claude-haiku-4-5-20251001")), \
         patch("autonexusgraph.llm.openai_adapter.OpenAIClient",
               return_value=_Fake("gpt-4o-mini")):
        from autonexusgraph.llm.base import get_llm_client
        client = get_llm_client(model="claude-haiku-4-5-20251001")

    fb = _find_fallback(client)
    assert fb is not None
    assert [c.model for c in fb._clients] == ["claude-haiku-4-5-20251001", "gpt-4o-mini"]


def test_get_llm_client_no_fallback_when_unset(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an-key")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "")
    _clear_settings()

    with patch("autonexusgraph.llm.anthropic_adapter.AnthropicClient",
               return_value=_Fake("claude-haiku-4-5-20251001")):
        from autonexusgraph.llm.base import get_llm_client
        client = get_llm_client(model="claude-haiku-4-5-20251001")
    assert _find_fallback(client) is None


def test_get_llm_client_no_fallback_when_key_missing(monkeypatch):
    """fallback provider 지정했지만 키 없음 → graceful skip (단일 provider)."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an-key")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "openai")
    _clear_settings()

    with patch("autonexusgraph.llm.anthropic_adapter.AnthropicClient",
               return_value=_Fake("claude-haiku-4-5-20251001")):
        from autonexusgraph.llm.base import get_llm_client
        client = get_llm_client(model="claude-haiku-4-5-20251001")
    assert _find_fallback(client) is None
