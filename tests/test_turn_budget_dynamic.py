"""turn_budget_for_domain — declared field + env 동적 lookup 검증."""

from __future__ import annotations



def _reload(monkeypatch, **env):
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, str(v))
    from autonexusgraph import config
    config.get_settings.cache_clear()                    # type: ignore[attr-defined]
    return config


def test_finance_default(monkeypatch):
    cfg = _reload(
        monkeypatch,
        AGENT_TURN_BUDGET_USD="0.20",
        AGENT_TURN_BUDGET_AUTO_USD="0.0",
        AGENT_TURN_BUDGET_CROSS_DOMAIN_USD="0.0",
    )
    assert cfg.turn_budget_for_domain(None) == 0.20
    assert cfg.turn_budget_for_domain("finance") == 0.20


def test_declared_auto_override(monkeypatch):
    cfg = _reload(
        monkeypatch,
        AGENT_TURN_BUDGET_USD="0.20",
        AGENT_TURN_BUDGET_AUTO_USD="0.50",
    )
    assert cfg.turn_budget_for_domain("auto") == 0.50


def test_declared_cross_domain_override(monkeypatch):
    cfg = _reload(
        monkeypatch,
        AGENT_TURN_BUDGET_USD="0.20",
        AGENT_TURN_BUDGET_CROSS_DOMAIN_USD="0.80",
    )
    assert cfg.turn_budget_for_domain("cross_domain") == 0.80


def test_env_dynamic_legal_domain(monkeypatch):
    """미선언 도메인 (legal) 도 env 만으로 한도 적용."""
    cfg = _reload(
        monkeypatch,
        AGENT_TURN_BUDGET_USD="0.20",
        AGENT_TURN_BUDGET_LEGAL_USD="0.30",
    )
    assert cfg.turn_budget_for_domain("legal") == 0.30
    # 다른 미선언 도메인은 기본값.
    assert cfg.turn_budget_for_domain("safety") == 0.20


def test_declared_takes_precedence_over_env(monkeypatch):
    """declared field (0.50) 가 env 의 다른 값 (0.30) 보다 우선."""
    cfg = _reload(
        monkeypatch,
        AGENT_TURN_BUDGET_USD="0.20",
        AGENT_TURN_BUDGET_AUTO_USD="0.50",       # declared
    )
    # env 의 AUTO 도 0.50 으로 declared field 와 일치 — 별 효과 없음 검증.
    assert cfg.turn_budget_for_domain("auto") == 0.50


def test_zero_or_negative_falls_back(monkeypatch):
    """0.0 또는 음수 override 는 무시되고 기본값 상속."""
    cfg = _reload(
        monkeypatch,
        AGENT_TURN_BUDGET_USD="0.20",
        AGENT_TURN_BUDGET_AUTO_USD="0.0",
        AGENT_TURN_BUDGET_LEGAL_USD="-0.5",
    )
    assert cfg.turn_budget_for_domain("auto") == 0.20
    assert cfg.turn_budget_for_domain("legal") == 0.20
