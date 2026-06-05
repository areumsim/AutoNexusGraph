"""LLM 비용 영속 로그 (cost_log.jsonl) 회귀 테스트.

검증 — 사용자 명시 "누락 없게":
1. append() 가 thread-safe JSONL 1줄씩.
2. iter_entries() 가 잘못된 라인 silent skip.
3. LoggingLLMClient — chat/stream/json 모든 메서드 누락 없이 기록.
4. provider 가 OpenAI / Anthropic / Google / Local 어떤 것이든 동일하게 기록.
5. get_llm_client 반환 client 가 LoggingLLMClient 로 항상 wrap.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def _patch_path(monkeypatch, tmp_path: Path) -> Path:
    log_path = tmp_path / "cost.jsonl"
    monkeypatch.setenv("LLM_COST_LOG_PATH", str(log_path))
    from autonexusgraph import config
    config.get_settings.cache_clear()                    # type: ignore[attr-defined]
    return log_path


def test_append_and_iter(monkeypatch, tmp_path):
    log_path = _patch_path(monkeypatch, tmp_path)
    from autonexusgraph.llm.cost_log import append, iter_entries

    append({"caller": "x", "model": "gpt-4o-mini",
            "input_tokens": 100, "output_tokens": 50, "cost_usd": 0.0001})
    append({"caller": "y", "model": "claude-haiku-4-5",
            "input_tokens": 200, "output_tokens": 80, "cost_usd": 0.0006})

    entries = list(iter_entries(log_path))
    assert len(entries) == 2
    assert entries[0]["caller"] == "x"
    assert entries[0]["provider"] == "openai"
    assert entries[1]["provider"] == "anthropic"
    assert "ts" in entries[0]


def test_iter_skips_malformed_lines(monkeypatch, tmp_path):
    log_path = _patch_path(monkeypatch, tmp_path)
    log_path.write_text(
        '{"caller":"a","cost_usd":0.001}\n'
        '!!! 잘못된 라인\n'
        '{"caller":"b","cost_usd":0.002}\n',
        encoding="utf-8",
    )
    from autonexusgraph.llm.cost_log import iter_entries
    es = list(iter_entries(log_path))
    assert [e["caller"] for e in es] == ["a", "b"]


def test_append_failure_does_not_raise(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_COST_LOG_PATH", "/proc/cannot_write_here.jsonl")
    from autonexusgraph import config
    config.get_settings.cache_clear()                    # type: ignore[attr-defined]
    from autonexusgraph.llm.cost_log import append
    append({"caller": "x", "cost_usd": 0.0001})


def test_logging_client_chat_records(monkeypatch, tmp_path):
    log_path = _patch_path(monkeypatch, tmp_path)
    from autonexusgraph.llm.base import LLMResponse, TokenUsage
    from autonexusgraph.llm.cost_log import LoggingLLMClient

    class FakeInner:
        model = "gpt-4o-mini"
        def chat(self, messages, **kw):
            return LLMResponse(
                content="hi", raw=None,
                usage=TokenUsage(prompt_tokens=10, completion_tokens=5,
                                  total_tokens=15, cost_usd=0.0005,
                                  model="gpt-4o-mini"),
            )
        def chat_stream(self, messages, **kw): yield "x"
        def chat_json(self, messages, schema, **kw): return {"ok": True}

    client = LoggingLLMClient(FakeInner(), caller="test_role")
    resp = client.chat([{"role": "user", "content": "ping"}])
    assert resp.content == "hi"

    es = [json.loads(ln) for ln in log_path.read_text().splitlines()]
    assert len(es) == 1
    e = es[0]
    assert e["caller"] == "test_role"
    assert e["model"] == "gpt-4o-mini"
    assert e["input_tokens"] == 10
    assert e["output_tokens"] == 5
    assert e["cost_usd"] == 0.0005
    assert e["method"] == "chat"
    assert "ts" in e


def test_logging_client_chat_stream_records(monkeypatch, tmp_path):
    log_path = _patch_path(monkeypatch, tmp_path)
    from autonexusgraph.llm.cost_log import LoggingLLMClient

    class FakeInner:
        model = "claude-haiku-4-5"
        def chat(self, *a, **kw): raise NotImplementedError
        def chat_stream(self, messages, **kw):
            yield from ["안", "녕", "하세요"]
        def chat_json(self, *a, **kw): raise NotImplementedError

    client = LoggingLLMClient(FakeInner(), caller="stream_test")
    out = list(client.chat_stream([{"role": "user", "content": "안녕"}]))
    assert out == ["안", "녕", "하세요"]

    es = [json.loads(ln) for ln in log_path.read_text().splitlines()]
    assert len(es) == 1
    assert es[0]["method"] == "chat_stream"
    assert es[0]["estimated"] is True


def test_logging_client_chat_json_records(monkeypatch, tmp_path):
    log_path = _patch_path(monkeypatch, tmp_path)
    from autonexusgraph.llm.cost_log import LoggingLLMClient

    class FakeInner:
        model = "gemini-2.5-flash"
        def chat(self, *a, **kw): raise NotImplementedError
        def chat_stream(self, *a, **kw): yield "x"
        def chat_json(self, messages, schema, **kw):
            return {"intent": "search", "args": {"q": "x"}}

    client = LoggingLLMClient(FakeInner(), caller="json_test")
    result = client.chat_json([{"role": "user", "content": "extract"}],
                              schema={"type": "object"})
    assert result["intent"] == "search"

    es = [json.loads(ln) for ln in log_path.read_text().splitlines()]
    assert len(es) == 1
    assert es[0]["method"] == "chat_json"


def test_get_llm_client_returns_logging_wrapper(monkeypatch, tmp_path):
    _patch_path(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    from autonexusgraph import config
    config.get_settings.cache_clear()                    # type: ignore[attr-defined]

    fake = MagicMock()
    fake.model = "gpt-4o-mini"
    with patch("autonexusgraph.llm.openai_adapter.OpenAIClient",
                return_value=fake):
        from autonexusgraph.llm.base import get_llm_client
        from autonexusgraph.llm.cost_log import LoggingLLMClient
        c = get_llm_client(model="gpt-4o-mini")
        assert isinstance(c, LoggingLLMClient)
        c.set_caller("custom_caller")
        assert c._caller == "custom_caller"


def test_all_providers_wrapped_with_logging(monkeypatch, tmp_path):
    _patch_path(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("GOOGLE_API_KEY", "x")
    from autonexusgraph import config
    config.get_settings.cache_clear()                    # type: ignore[attr-defined]

    fake = MagicMock()
    fake.model = "test"
    from autonexusgraph.llm.cost_log import LoggingLLMClient

    for model, target in [
        ("gpt-4o-mini",       "autonexusgraph.llm.openai_adapter.OpenAIClient"),
        ("claude-sonnet-4-5", "autonexusgraph.llm.anthropic_adapter.AnthropicClient"),
        ("gemini-2.5-flash",  "autonexusgraph.llm.gemini_adapter.GeminiClient"),
    ]:
        with patch(target, return_value=fake):
            from autonexusgraph.llm.base import get_llm_client
            c = get_llm_client(model=model)
            assert isinstance(c, LoggingLLMClient), f"{model} not wrapped"


def test_cost_history_summarize(monkeypatch, tmp_path):
    log_path = _patch_path(monkeypatch, tmp_path)
    from autonexusgraph.llm.cost_history import summarize
    from autonexusgraph.llm.cost_log import append, iter_entries

    for e in [
        {"caller": "synth",  "model": "gpt-4o",           "input_tokens": 1000, "output_tokens": 500, "cost_usd": 0.0075},
        {"caller": "synth",  "model": "gpt-4o",           "input_tokens": 800,  "output_tokens": 300, "cost_usd": 0.005},
        {"caller": "triage", "model": "claude-haiku-4-5", "input_tokens": 200,  "output_tokens": 80,  "cost_usd": 0.0006},
        {"caller": "judge",  "model": "gemini-2.5-flash", "input_tokens": 500,  "output_tokens": 100, "cost_usd": 0.0004},
    ]:
        append(e)

    s = summarize(iter_entries(log_path))
    assert s["total_calls"] == 4
    assert abs(s["total_cost"] - (0.0075 + 0.005 + 0.0006 + 0.0004)) < 1e-9
    assert "openai" in s["by_provider"]
    assert "anthropic" in s["by_provider"]
    assert "google" in s["by_provider"]
    assert s["by_caller"]["synth"]["calls"] == 2
    assert s["by_caller"]["triage"]["calls"] == 1
    assert s["by_model"]["gpt-4o"]["calls"] == 2


def test_cost_history_date_filter(monkeypatch, tmp_path):
    from datetime import date
    log_path = _patch_path(monkeypatch, tmp_path)
    lines = [
        json.dumps({"ts": "2026-05-01T10:00:00+00:00", "caller": "a",
                    "cost_usd": 0.001, "model": "gpt-4o"}),
        json.dumps({"ts": "2026-05-15T10:00:00+00:00", "caller": "b",
                    "cost_usd": 0.002, "model": "gpt-4o"}),
        json.dumps({"ts": "2026-05-29T10:00:00+00:00", "caller": "c",
                    "cost_usd": 0.003, "model": "gpt-4o"}),
    ]
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    from autonexusgraph.llm.cost_history import summarize
    from autonexusgraph.llm.cost_log import iter_entries

    s = summarize(
        iter_entries(log_path),
        from_date=date(2026, 5, 10),
        to_date=date(2026, 5, 20),
    )
    assert s["total_calls"] == 1
    assert s["by_caller"]["b"]["calls"] == 1
