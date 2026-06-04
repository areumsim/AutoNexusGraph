"""LLM provider 자동 감지 + 전역 세션 비용 가드 회귀 테스트.

검증:
1. 모델명 prefix 로 provider 자동 결정 (gpt-* / claude-* / gemini-* / local-).
2. settings.llm_provider='auto' 일 때 모델별 dispatch.
3. provider-specific API key 가 모델에 맞게 자동 선택.
4. 글로벌 세션 트래커 — 한도 도달 시 모든 후속 호출 차단.
5. PRICING 표에 Gemini 모델 가격 등록 + cost_of_call 정확도.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── 1) detect_provider — 모델명 → provider ─────────────────────────
def test_detect_provider_openai():
    from autonexusgraph.llm.base import detect_provider
    assert detect_provider("gpt-4o") == "openai"
    assert detect_provider("gpt-4o-mini") == "openai"
    assert detect_provider("o1-preview") == "openai"
    assert detect_provider("o3-mini") == "openai"


def test_detect_provider_anthropic():
    from autonexusgraph.llm.base import detect_provider
    assert detect_provider("claude-sonnet-4-5") == "anthropic"
    assert detect_provider("claude-opus-4-7") == "anthropic"
    assert detect_provider("claude-haiku-4-5-20251001") == "anthropic"


def test_detect_provider_google():
    from autonexusgraph.llm.base import detect_provider
    assert detect_provider("gemini-2.5-pro") == "google"
    assert detect_provider("gemini-2.5-flash") == "google"
    assert detect_provider("gemini-1.5-flash-8b") == "google"


def test_detect_provider_local():
    from autonexusgraph.llm.base import detect_provider
    assert detect_provider("local-qwen-32b") == "local"
    assert detect_provider("qwen-2.5-7b") == "local"
    assert detect_provider("llama-3-8b") == "local"


def test_detect_provider_unknown_fallback_openai():
    """알 수 없는 모델은 openai 로 — 호출자가 명시 권장."""
    from autonexusgraph.llm.base import detect_provider
    assert detect_provider("unknown-2024") == "openai"


# ── 2) get_llm_client — dispatch 검증 (실제 SDK 호출 안 함) ─────────
def test_get_llm_client_explicit_provider_overrides_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    from autonexusgraph import config
    config.get_settings.cache_clear()                    # type: ignore[attr-defined]

    fake_client = MagicMock()
    with patch("autonexusgraph.llm.openai_adapter.OpenAIClient",
                return_value=fake_client) as m_openai:
        from autonexusgraph.llm.base import get_llm_client
        get_llm_client(model="claude-sonnet-4-5", provider="openai")
        m_openai.assert_called_once()


def test_get_llm_client_auto_dispatch_by_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anth-key")
    monkeypatch.setenv("OPENAI_API_KEY", "oai-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "ggl-key")
    from autonexusgraph import config
    config.get_settings.cache_clear()                    # type: ignore[attr-defined]

    fake = MagicMock()
    with patch("autonexusgraph.llm.anthropic_adapter.AnthropicClient",
                return_value=fake) as m_an, \
         patch("autonexusgraph.llm.openai_adapter.OpenAIClient",
                return_value=fake) as m_oa, \
         patch("autonexusgraph.llm.gemini_adapter.GeminiClient",
                return_value=fake) as m_ge:
        from autonexusgraph.llm.base import get_llm_client
        get_llm_client(model="claude-sonnet-4-5")
        get_llm_client(model="gpt-4o-mini")
        get_llm_client(model="gemini-2.5-flash")

    m_an.assert_called_once()
    assert m_an.call_args.kwargs.get("api_key") == "anth-key"
    m_oa.assert_called_once()
    assert m_oa.call_args.kwargs.get("api_key") == "oai-key"
    m_ge.assert_called_once()
    assert m_ge.call_args.kwargs.get("api_key") == "ggl-key"


def test_get_llm_client_uses_provider_specific_key(monkeypatch):
    """auto dispatch 시 모델에 맞는 provider 키 선택."""
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an-key")
    from autonexusgraph import config
    config.get_settings.cache_clear()                    # type: ignore[attr-defined]

    fake = MagicMock()
    with patch("autonexusgraph.llm.openai_adapter.OpenAIClient",
                return_value=fake) as m_oa:
        from autonexusgraph.llm.base import get_llm_client
        get_llm_client(model="gpt-4o-mini")
    assert m_oa.call_args.kwargs.get("api_key") == "oa-key"


def test_get_llm_client_empty_key_when_provider_unset(monkeypatch):
    """provider-specific 키 미설정(빈 문자열) 시 _select_api_key 가 ''."""
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    # pydantic settings 가 .env 의 값을 먼저 로드 — env var 로 명시 override.
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from autonexusgraph import config
    config.get_settings.cache_clear()                    # type: ignore[attr-defined]

    from autonexusgraph.llm.base import _select_api_key
    s = config.get_settings()
    assert _select_api_key(s, "openai") == ""


# ── 3) settings.llm_provider 가 'auto' 아니면 강제 적용 ────────────
def test_get_llm_client_explicit_provider_setting_overrides_model_detection(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    from autonexusgraph import config
    config.get_settings.cache_clear()                    # type: ignore[attr-defined]

    fake = MagicMock()
    with patch("autonexusgraph.llm.openai_adapter.OpenAIClient",
                return_value=fake) as m_oa, \
         patch("autonexusgraph.llm.anthropic_adapter.AnthropicClient",
                return_value=fake) as m_an:
        from autonexusgraph.llm.base import get_llm_client
        get_llm_client(model="claude-sonnet-4-5")
    m_oa.assert_called_once()
    m_an.assert_not_called()


# ── 4) PRICING — Gemini 모델 등록 + cost_of_call 정확도 ────────────
def test_pricing_includes_gemini_models():
    from autonexusgraph.llm.cost import PRICING
    for m in ("gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-flash"):
        assert m in PRICING, f"PRICING 에 {m} 없음"


def test_cost_of_call_gemini_flash():
    """gemini-2.5-flash: input $0.30/1M, output $2.50/1M. 1000+500 토큰 = $0.00155."""
    from autonexusgraph.llm.cost import cost_of_call
    c = cost_of_call("gemini-2.5-flash", 1000, 500)
    assert abs(c - 0.00155) < 1e-6, f"got {c}"


# ── 5) 전역 세션 트래커 — 영속(세션) 한도 도달 시 BudgetExceeded ──────────────
def test_session_tracker_uses_settings_hard_limit(monkeypatch):
    """LLM_SESSION_HARD_LIMIT_USD 가 영속 누적 가드(_session_limit_usd)로 enforce.

    (설계: per-turn/batch 한도 = llm_cost_hard_limit_usd, 영속/시간창 누적 한도 =
    llm_session_hard_limit_usd 로 분리. 과거엔 둘이 한 필드로 혼용돼 turn budget 이
    무력화되는 버그가 있었음.)
    """
    monkeypatch.setenv("LLM_SESSION_HARD_LIMIT_USD", "0.05")
    monkeypatch.delenv("LLM_COST_HARD_LIMIT_USD", raising=False)
    monkeypatch.setenv("LLM_COST_WINDOW_HOURS", "0")     # all-time (base 결정적)
    from autonexusgraph import config
    config.get_settings.cache_clear()                    # type: ignore[attr-defined]

    from autonexusgraph.llm import cost_tracker
    cost_tracker.reset_tracker()
    tracker = cost_tracker.get_session_tracker(caller="test", model="gpt-4o-mini")
    # 영속 세션 한도가 env 값으로 잡혀야 함
    assert abs(tracker._session_limit_usd - 0.05) < 1e-9

    # base + 이번 tracker 누적이 세션 한도를 넘으면 차단 (turn 한도와 무관하게)
    tracker.state.cost_usd = 0.06
    with pytest.raises(cost_tracker.BudgetExceeded):
        tracker.guard()
    cost_tracker.reset_tracker()


def test_session_tracker_singleton_across_callers(monkeypatch):
    monkeypatch.setenv("LLM_SESSION_HARD_LIMIT_USD", "10.0")
    from autonexusgraph import config
    config.get_settings.cache_clear()                    # type: ignore[attr-defined]

    from autonexusgraph.llm import cost_tracker
    cost_tracker.reset_tracker()
    t1 = cost_tracker.get_session_tracker(caller="A")
    t2 = cost_tracker.get_session_tracker(caller="B")
    assert t1 is t2
    cost_tracker.reset_tracker()
