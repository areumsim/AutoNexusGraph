"""Tier 단축 패턴 — LLM_MODEL_FAST/SMART 2개로 모든 role 일괄 전환.

검증:
1. 비어있는 llm_model_<role> 이 tier 기본값으로 자동 채워짐.
2. 명시 override 가 tier 보다 우선.
3. FAST/SMART 한 줄 변경으로 모든 role 동시 전환 (OpenAI ↔ Gemini ↔ Claude).
4. tier 분류표가 SSOT — 새 role 추가 시 _ROLE_TIER 만 등록.
"""

from __future__ import annotations



def _reload_settings(monkeypatch, **env):
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, str(v))
    from autonexusgraph import config
    config.get_settings.cache_clear()                    # type: ignore[attr-defined]
    return config.get_settings()


_EMPTY_ROLES = {
    "LLM_MODEL_TRIAGE": "", "LLM_MODEL_PLANNER": "",
    "LLM_MODEL_SUPERVISOR": "", "LLM_MODEL_RESEARCH": "",
    "LLM_MODEL_GRAPH": "", "LLM_MODEL_SQL": "",
    "LLM_MODEL_CALCULATOR": "", "LLM_MODEL_VALIDATOR": "",
    "LLM_MODEL_SYNTHESIZER": "", "LLM_MODEL_JUDGE": "",
    "LLM_MODEL_TITLER": "",
}


def test_gemini_tier_fills_all_roles(monkeypatch):
    s = _reload_settings(
        monkeypatch,
        LLM_MODEL_FAST="gemini-2.5-flash",
        LLM_MODEL_SMART="gemini-2.5-pro",
        **_EMPTY_ROLES,
    )
    for r in ("triage", "supervisor", "research", "sql",
              "calculator", "validator", "titler"):
        assert getattr(s, f"llm_model_{r}") == "gemini-2.5-flash", r
    for r in ("planner", "graph", "synthesizer", "judge"):
        assert getattr(s, f"llm_model_{r}") == "gemini-2.5-pro", r


def test_openai_tier_fills_all_roles(monkeypatch):
    s = _reload_settings(
        monkeypatch,
        LLM_MODEL_FAST="gpt-4o-mini",
        LLM_MODEL_SMART="gpt-4o",
        **_EMPTY_ROLES,
    )
    assert s.llm_model_triage == "gpt-4o-mini"
    assert s.llm_model_planner == "gpt-4o"
    assert s.llm_model_synthesizer == "gpt-4o"
    assert s.llm_model_titler == "gpt-4o-mini"


def test_claude_tier_fills_all_roles(monkeypatch):
    s = _reload_settings(
        monkeypatch,
        LLM_MODEL_FAST="claude-haiku-4-5",
        LLM_MODEL_SMART="claude-sonnet-4-5",
        **_EMPTY_ROLES,
    )
    assert s.llm_model_triage == "claude-haiku-4-5"
    assert s.llm_model_planner == "claude-sonnet-4-5"


def test_mixed_tiers(monkeypatch):
    s = _reload_settings(
        monkeypatch,
        LLM_MODEL_FAST="gemini-2.5-flash",
        LLM_MODEL_SMART="claude-sonnet-4-5",
        **_EMPTY_ROLES,
    )
    assert s.llm_model_triage == "gemini-2.5-flash"
    assert s.llm_model_planner == "claude-sonnet-4-5"
    from autonexusgraph.llm.base import detect_provider
    assert detect_provider(s.llm_model_triage) == "google"
    assert detect_provider(s.llm_model_planner) == "anthropic"


def test_role_override_takes_precedence(monkeypatch):
    env = {**_EMPTY_ROLES, "LLM_MODEL_TRIAGE": "gpt-4o-mini"}
    s = _reload_settings(
        monkeypatch,
        LLM_MODEL_FAST="gemini-2.5-flash",
        LLM_MODEL_SMART="gemini-2.5-pro",
        **env,
    )
    assert s.llm_model_triage == "gpt-4o-mini"        # override
    assert s.llm_model_supervisor == "gemini-2.5-flash"
    assert s.llm_model_planner == "gemini-2.5-pro"


def test_role_tier_table_covers_all_role_fields():
    from autonexusgraph.config import Settings
    tier_map = Settings._ROLE_TIER  # type: ignore[attr-defined]
    declared = [
        name[len("llm_model_"):] for name in Settings.model_fields.keys()
        if name.startswith("llm_model_") and name not in (
            "llm_model_fast", "llm_model_smart",
        )
    ]
    missing = [r for r in declared if r not in tier_map]
    assert not missing, f"_ROLE_TIER 에 미등록 role: {missing}"
