"""에이전트 (PRD §7.5) — Triage / Planner / Executor / Synthesizer.

진입점:
    from fingraph.agents import run_agent
    state = run_agent("삼성전자 2024년 매출은?")
    print(state["answer"], state["citations"])
"""

from .graph import run_agent
from .state import AgentState

__all__ = ["run_agent", "AgentState"]
