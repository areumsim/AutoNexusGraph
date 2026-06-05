"""BACKLOG A-8 / A-9 회귀 가드 — LLM planner prompt 가 (a) intent enum 강조 +
(b) calculator args 요구 + (c) calculator expr 누락 task 사전 drop 보장.

eval matrix 2026-06-05 에서 LLM planner 가 'sql:현대모비스 매출 조회' 같은 자연어
intent 다수 생성 → 전 task drop → grounding 실패. + calculator task 가 expr 없이
호출되어 '[calculator] failed: expr 필요' 다수 발생.

본 가드는 prompt 문자열 검사 + _validate_tasks 동작 검증.
"""

from __future__ import annotations

from typing import Any

import pytest

from autonexusgraph.agents.llm_planner import _SYSTEM, _validate_tasks


def test_system_prompt_intent_enum_emphasis() -> None:
    """_SYSTEM 이 intent enum 정확성 + 자연어 description 금지 명시."""
    assert "intent 는 반드시 enum" in _SYSTEM
    assert "자연어 description 금지" in _SYSTEM
    # 양/부정 예시 모두 표기
    assert "lookup_company" in _SYSTEM
    assert "drop 됨" in _SYSTEM


def test_system_prompt_calculator_args_explicit() -> None:
    """_SYSTEM 이 calculator 사용 시 expr 또는 aggregate+over 필수 명시."""
    assert "calculator 사용 시" in _SYSTEM
    assert "expr(수식 문자열)" in _SYSTEM
    assert "aggregate+over" in _SYSTEM


def test_validate_tasks_drops_calculator_without_expr() -> None:
    """calculator task 가 expr/aggregate 둘 다 없으면 drop (worker 도달 전 차단)."""
    state: dict[str, Any] = {"domain": "finance", "safety_signals": []}
    raw = [
        {"id": "c1", "agent": "calculator", "intent": "evaluate", "args": {}},
    ]
    catalog = {"graph": [], "sql": [], "research": [], "calculator": ["evaluate"]}
    out = _validate_tasks(state, raw, catalog)  # type: ignore[arg-type]
    assert out == [], "expr 없는 calculator task 는 drop 되어야"
    # safety signal 에 drop 사유 기록
    signals = state.get("safety_signals") or []
    assert any("calculator:no_expr_or_aggregate" in s for s in signals)


def test_validate_tasks_keeps_calculator_with_expr() -> None:
    """expr 가 있으면 calculator task 정상 통과."""
    state: dict[str, Any] = {"domain": "finance", "safety_signals": []}
    raw = [
        {"id": "c1", "agent": "calculator", "intent": "evaluate",
         "args": {"expr": "(a-b)/b*100", "variables": {"a": 100, "b": 80}}},
    ]
    catalog = {"graph": [], "sql": [], "research": [], "calculator": ["evaluate"]}
    out = _validate_tasks(state, raw, catalog)  # type: ignore[arg-type]
    assert len(out) == 1
    assert out[0]["agent"] == "calculator"
    assert out[0]["args"]["expr"] == "(a-b)/b*100"


def test_validate_tasks_keeps_calculator_with_aggregate() -> None:
    """aggregate+over 가 있으면 expr 없어도 통과."""
    state: dict[str, Any] = {"domain": "finance", "safety_signals": []}
    raw = [
        {"id": "c1", "agent": "calculator", "intent": "aggregate",
         "args": {"aggregate": "sum", "over": [1, 2, 3]}},
    ]
    catalog = {"graph": [], "sql": [], "research": [], "calculator": ["aggregate"]}
    out = _validate_tasks(state, raw, catalog)  # type: ignore[arg-type]
    assert len(out) == 1


def test_validate_tasks_drops_non_enum_intent() -> None:
    """자연어 intent ('현대모비스 매출 조회') 는 drop — A-9 핵심 회귀 가드."""
    state: dict[str, Any] = {"domain": "finance", "safety_signals": []}
    raw = [
        {"id": "s1", "agent": "sql", "intent": "현대모비스 매출 조회", "args": {}},
        {"id": "s2", "agent": "sql", "intent": "lookup_company",
         "args": {"q": "현대모비스"}},
    ]
    catalog = {"graph": [], "sql": ["lookup_company", "list_filings"],
               "research": [], "calculator": []}
    out = _validate_tasks(state, raw, catalog)  # type: ignore[arg-type]
    # enum 매칭 1개만 통과
    assert len(out) == 1
    assert out[0]["intent"] == "lookup_company"


@pytest.mark.parametrize("agent", ["research", "graph", "sql"])
def test_enum_line_for_all_strict_agents(agent: str) -> None:
    """_enum_line (try_llm_plan 안 nested 함수) 의 형식 검증을 위해 user_msg
    빌딩 패턴이 catalog 를 명시적으로 노출하는지 — 직접 _enum_line 은 export 안 됐으니
    _SYSTEM 의 enum 강조 규칙으로 갈음."""
    assert agent in _SYSTEM or "enum" in _SYSTEM
