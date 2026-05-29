"""도메인 플러그인 자동 discovery 테스트 (PRD §10.12).

목적: ``api/main.py`` / ``eval/adapters/*`` / ``ui/app.py`` 가 ``autograph`` 를
explicit import 하지 않아도, agent 가 호출되는 순간 AutoHandler /
CrossDomainHandler / route_domain 이 등록되어 ``auto`` / ``cross_domain``
도메인이 실제로 동작해야 한다.

이전 결손: discovery 부재로 모든 도메인 라우팅이 ``finance`` 로 강제됨.
"""

from __future__ import annotations

import importlib
import os
import sys
from unittest import mock

import pytest

from autonexusgraph.agents import _domain_handler as DH


@pytest.fixture(autouse=True)
def _reset_registry():
    """각 테스트 전 registry/discovery 게이트 리셋.

    autograph 가 다른 테스트에서 미리 import 되어 있을 수 있으므로 sys.modules
    에서도 제거 — 본 테스트는 cold-start 시나리오를 검증한다.
    """
    saved_handlers = dict(DH._HANDLERS)
    saved_routers = list(DH._ROUTERS)
    DH._HANDLERS.clear()
    DH._ROUTERS.clear()
    DH._reset_discovery_for_test()
    # autograph 모듈도 unload — re-import 가 register_handler 다시 호출하게.
    for mod in list(sys.modules):
        if mod == "autograph" or mod.startswith("autograph."):
            sys.modules.pop(mod, None)
    yield
    DH._HANDLERS.clear()
    DH._HANDLERS.update(saved_handlers)
    DH._ROUTERS[:] = saved_routers
    DH._reset_discovery_for_test()


def test_discovery_loads_autograph_by_default():
    """ENV 미설정 → 기본값 'autograph' 자동 import."""
    loaded = DH.discover_plugins(force=True)
    assert "autograph" in loaded
    # AutoHandler 와 CrossDomainHandler 가 등록됐는지
    assert DH.get_handler("auto") is not None
    assert DH.get_handler("cross_domain") is not None
    # route_domain 라우터도 등록
    assert any(DH._ROUTERS)


def test_discovery_is_idempotent():
    """두 번째 호출은 no-op — register_handler 가 중복 실행되지 않음."""
    first = DH.discover_plugins(force=True)
    second = DH.discover_plugins(force=False)
    assert first == ["autograph"]
    assert second == []   # 두 번째는 idempotent guard 로 빈 list


def test_get_handler_triggers_discovery():
    """get_handler('auto') 첫 호출이 discovery 를 강제 실행해야 한다."""
    # cold start — registry 비어있고 _DISCOVERY_DONE=False
    assert "auto" not in DH._HANDLERS
    handler = DH.get_handler("auto")
    # discovery 가 자동 실행되면 autograph 등록 → handler 반환
    assert handler is not None
    assert handler.domain == "auto"


def test_auto_detect_domain_triggers_discovery():
    """auto_detect_domain 첫 호출도 discovery 실행 — auto 키워드 자동 인식."""
    # discovery 전에는 routers 가 비어 finance 만 반환할 것이지만, 함수 안에서
    # discovery 가 트리거되므로 autograph 의 route_domain 이 활성화됨.
    domain = DH.auto_detect_domain("Tesla Model Y 2023 리콜 사례 알려줘", None)
    assert domain == "auto"


def test_discovery_skips_missing_plugin(monkeypatch):
    """ENV 에 존재하지 않는 모듈명을 넣어도 graceful skip."""
    monkeypatch.setenv("AUTONEXUSGRAPH_DOMAIN_PLUGINS",
                       "nonexistent_pkg_xyz,autograph")
    loaded = DH.discover_plugins(force=True)
    assert loaded == ["autograph"]   # 누락 모듈은 조용히 스킵
    assert DH.get_handler("auto") is not None


def test_discovery_handles_import_failure(monkeypatch):
    """existing 모듈이지만 import 중 raise 해도 다른 플러그인은 정상 처리."""
    # autograph 만 추가하고 fake 한 모듈에 대해서는 find_spec 이 None
    monkeypatch.setenv("AUTONEXUSGRAPH_DOMAIN_PLUGINS", "autograph")

    real_import = importlib.import_module
    orig_find = importlib.util.find_spec

    # autograph import 가 raise 하면 어떻게 되나
    def _import_module(name, *args, **kwargs):
        if name == "autograph":
            raise RuntimeError("simulated import failure")
        return real_import(name, *args, **kwargs)

    with mock.patch("autonexusgraph.agents._domain_handler.importlib.import_module",
                    side_effect=_import_module):
        loaded = DH.discover_plugins(force=True)
    # 실패해도 빈 list — 호출자 진행
    assert loaded == []
    # finance fallback 정상 작동 확인
    assert DH.auto_detect_domain("삼성전자 매출", None) == "finance"


def test_discovery_env_override_disables_autograph(monkeypatch):
    """ENV 를 빈 값으로 설정 → 어떤 플러그인도 로드하지 않음 (finance only)."""
    monkeypatch.setenv("AUTONEXUSGRAPH_DOMAIN_PLUGINS", "")
    loaded = DH.discover_plugins(force=True)
    assert loaded == []
    assert DH.get_handler("auto") is None
    # 자동차 키워드여도 finance 로 폴백
    assert DH.auto_detect_domain("Tesla Model Y 리콜", None) == "finance"


def test_init_state_uses_discovered_handler():
    """run_agent 가 호출하는 _init_state 가 자동차 도메인을 정확히 판정."""
    from autonexusgraph.agents.graph import _init_state
    state = _init_state(
        question="Hyundai Sonata 2024 리콜 사례",
        thread_id="t-disc-1",
        history=[],
        domain=None,
    )
    assert state["domain"] == "auto"
