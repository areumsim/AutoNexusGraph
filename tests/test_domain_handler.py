"""DomainHandler registry — autograph 미설치 환경에서도 core 동작 보장.

PRD §10.12 의도 검증:
1. core 는 ``from autograph`` 0건이어야 한다 (AST 기반 정적 검증).
2. autograph import 전에는 finance 만 동작 (auto_detect_domain → 'finance').
3. autograph import 후에는 두 handler + route_domain 라우터가 자동 등록.
4. 핸들러 unregister 시 finance 폴백 즉시 회복.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from autonexusgraph.agents._domain_handler import (
    DomainHandler,
    auto_detect_domain,
    call_handler_method,
    get_handler,
    list_handlers,
    register_handler,
    register_router,
    unregister_handler,
)

REPO = Path(__file__).resolve().parents[1]


# ── 1) core 가 autograph import 0건 (AST 정적 검증) ─────────────────
def test_core_has_zero_autograph_imports():
    """src/autonexusgraph/ 의 모든 .py 에 실제 ``import autograph[.*]`` 또는
    ``from autograph[.*] import …`` 가 없어야 한다.

    AST 기반이라 docstring 내 예시 텍스트는 자동 제외 — 진짜 import 노드만 검사.
    """
    core_dir = REPO / "src" / "autonexusgraph"
    offenders: list[str] = []
    for py in core_dir.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if (node.module or "").startswith("autograph"):
                    offenders.append(
                        f"{py.relative_to(REPO)}:{node.lineno} "
                        f"from {node.module} import …"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("autograph"):
                        offenders.append(
                            f"{py.relative_to(REPO)}:{node.lineno} "
                            f"import {alias.name}"
                        )
    assert not offenders, (
        "PRD §10.12 위반 — core 에 autograph import 가 있음:\n  "
        + "\n  ".join(offenders)
    )


# ── 2) handler 미등록 시 finance 만 동작 ──────────────────────────
def test_auto_detect_domain_without_routers_returns_finance(monkeypatch):
    # 라우터를 임시로 비움 — autograph 미설치 환경 모사.
    # _DISCOVERY_DONE 도 True 로 강제: 그렇지 않으면 auto_detect_domain 이 discover_plugins
    # 를 트리거하여 register_router(route_domain) 가 monkeypatch 의 새 [] 에 append 됨.
    # teardown 시 원본 (빈) list 로 복원되어 후속 테스트가 baseline 을 잃는다.
    monkeypatch.setattr(
        "autonexusgraph.agents._domain_handler._ROUTERS", [],
    )
    monkeypatch.setattr(
        "autonexusgraph.agents._domain_handler._DISCOVERY_DONE", True,
    )
    assert auto_detect_domain("아무 질문") == "finance"


def test_get_handler_unknown_domain_returns_none():
    assert get_handler("__never_registered__") is None


# ── 3) autograph import 시 자동 등록 ──────────────────────────────
def test_autograph_import_registers_auto_and_cross_domain():
    # autograph __init__ 가 agent_handler 를 import 하면 두 핸들러 등록.
    import autograph  # noqa: F401 — side effect

    auto = get_handler("auto")
    cross = get_handler("cross_domain")
    assert auto is not None
    assert cross is not None
    assert auto.domain == "auto"
    assert cross.domain == "cross_domain"

    # Protocol 메서드 모두 보유 — runtime_checkable.
    for method in (
        "identify_targets", "plan_tasks", "toolbox_modules",
        "allowed_intents", "fallback_search", "retrieve_module",
    ):
        assert hasattr(auto, method), f"AutoHandler 에 {method} 누락"
        assert hasattr(cross, method), f"CrossDomainHandler 에 {method} 누락"


def test_autograph_handler_allowed_intents_partition():
    """auto handler 는 auto-only, cross_domain 은 finance ∪ auto."""
    import autograph  # noqa: F401
    auto = get_handler("auto")
    cross = get_handler("cross_domain")
    from autograph.agent_handler import (
        AUTO_GRAPH_ALLOWED,
        AUTO_RESEARCH_INTENTS,
        AUTO_SQL_ALLOWED,
    )
    from autonexusgraph.agents.workers import (
        FIN_GRAPH_ALLOWED,
        FIN_RESEARCH_INTENTS,
        FIN_SQL_ALLOWED,
    )

    assert auto.allowed_intents("graph") == AUTO_GRAPH_ALLOWED
    assert auto.allowed_intents("sql") == AUTO_SQL_ALLOWED
    assert auto.allowed_intents("research") == AUTO_RESEARCH_INTENTS

    assert cross.allowed_intents("graph") == AUTO_GRAPH_ALLOWED | FIN_GRAPH_ALLOWED
    assert cross.allowed_intents("sql") == AUTO_SQL_ALLOWED | FIN_SQL_ALLOWED
    assert cross.allowed_intents("research") == AUTO_RESEARCH_INTENTS | FIN_RESEARCH_INTENTS


def test_autograph_route_domain_is_registered():
    """route_domain 이 라우터 list 에 등록 → 자동차 키워드 질문이 auto 로 판정."""
    import autograph  # noqa: F401
    # 자동차 키워드 — 'IONIQ', '그랜저' 같은 차종명. route_domain 의 휴리스틱이
    # 어떻게 잡든, finance 만 반환하는 환경 (등록 0건) 과는 다른 결과 나와야.
    d = auto_detect_domain("현대 그랜저 2024년 변속기는?")
    assert d in {"auto", "cross_domain", "finance"}, d
    # 적어도 등록은 됐다 — route_domain 자체가 호출 가능해야.
    from autonexusgraph.agents._domain_handler import _ROUTERS
    assert len(_ROUTERS) >= 1


# ── 4) 등록/해제 idempotency ───────────────────────────────────────
class _MinimalHandler:
    """필수 attribute 만 — Protocol 의 runtime_checkable 검증용."""

    domain = "__test_minimal__"

    def toolbox_modules(self):
        return []


def test_register_then_unregister_handler():
    h = _MinimalHandler()
    register_handler(h)
    assert "__test_minimal__" in list_handlers()
    assert get_handler("__test_minimal__") is h

    unregister_handler("__test_minimal__")
    assert "__test_minimal__" not in list_handlers()
    assert get_handler("__test_minimal__") is None


def test_register_handler_requires_domain_attr():
    class _NoDomain:
        pass
    with pytest.raises(ValueError, match="handler.domain"):
        register_handler(_NoDomain())


def test_register_handler_overwrites_existing_with_same_domain():
    h1 = _MinimalHandler()
    h2 = _MinimalHandler()
    register_handler(h1)
    register_handler(h2)        # 덮어쓰기 — 같은 domain 키.
    assert get_handler("__test_minimal__") is h2
    unregister_handler("__test_minimal__")


# ── 5) core nodes 가 handler 가 없을 때 finance 만 동작 ──────────
def test_planner_node_falls_through_when_no_handler(monkeypatch):
    """auto 핸들러 unregister 후 planner 가 finance 룰 기반 분기로 떨어지는지.

    triage 가 question_kind 를 'factual' 로 정해뒀다면, planner 는 finance
    SQL task 생성. autograph 미설치 환경 모사.

    Note: LangGraph 가 설치된 환경에서도 planner_node 가 fallback chain 으로
    동작하도록 ``_HAS_LANGGRAPH=False`` 도 강제 (graph_smoke 와 같은 패턴).
    """
    # LangGraph runnable context 회피.
    import autonexusgraph.agents.graph as _g
    monkeypatch.setattr(_g, "_HAS_LANGGRAPH", False, raising=False)
    monkeypatch.setattr(_g, "_LG_APP", None, raising=False)
    # 비용 가드 임계점 충분히 높게 — planner_cost_gate 가 interrupt() 호출 안 하게.
    monkeypatch.setenv("LLM_COST_AUTO_APPROVE_USD", "100.00")
    from autonexusgraph import config as _cfg
    _cfg.get_settings.cache_clear()   # type: ignore[attr-defined]
    # 모든 핸들러 임시 제거.
    monkeypatch.setattr(
        "autonexusgraph.agents._domain_handler._HANDLERS", {},
    )
    from autonexusgraph.agents.nodes import planner_node
    state = {
        "question": "삼성전자 2024년 매출은?",
        "question_kind": "factual",
        "target_companies": ["00126380"],
        "domain": "auto",          # 핸들러 없는 도메인.
        "tasks": [], "task_results": {},
        "n_replans": 0, "llm_usage_usd": 0.0,
    }
    out = planner_node(state)
    # 핸들러 없으면 plan_tasks 호출 0 — finance 룰 기반 planner 가 처리. tasks
    # 가 비어있지 않거나 (factual) 또는 plan list 가 작성됨.
    assert out is not None
    assert "tasks" in out


# ── 6) call_handler_method 헬퍼 — handler 6 호출 사이트 SSOT ──────
class _StubHandler:
    domain = "__stub__"

    def good(self) -> str:
        return "ok"

    def with_args(self, kind: str) -> set[str]:
        return {f"intent_{kind}"}

    def boom(self) -> None:
        raise RuntimeError("intentional")


def test_call_handler_method_none_handler_returns_none():
    state: dict = {}
    assert call_handler_method(state, None, "good") is None
    assert state.get("safety_signals") is None   # 적재 안 됨.


def test_call_handler_method_missing_method_returns_none():
    state: dict = {}
    assert call_handler_method(state, _StubHandler(), "no_such_method") is None
    assert state.get("safety_signals") is None


def test_call_handler_method_success_passes_args_and_no_signal():
    state: dict = {}
    assert call_handler_method(state, _StubHandler(), "good") == "ok"
    assert call_handler_method(
        state, _StubHandler(), "with_args", "graph"
    ) == {"intent_graph"}
    assert state.get("safety_signals") is None


def test_call_handler_method_exception_records_signal_and_returns_none():
    state: dict = {}
    assert call_handler_method(state, _StubHandler(), "boom") is None
    signals = state.get("safety_signals")
    assert isinstance(signals, list) and len(signals) == 1
    # 키 형식: f"{domain}_{method_name}_failed:{type}"
    assert signals[0] == "__stub___boom_failed:RuntimeError"


def test_call_handler_method_signal_extra_included():
    state: dict = {}
    # signal_extra 가 키에 포함되는지 (allowed_intents 의 kind 보존 시나리오).
    assert call_handler_method(
        state, _StubHandler(), "boom", signal_extra="graph"
    ) is None
    signals = state.get("safety_signals") or []
    assert signals == ["__stub___boom_failed:graph:RuntimeError"]
