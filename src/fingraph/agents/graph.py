"""에이전트 그래프 — 단순 함수 체인 (LangGraph 대체).

LangGraph 도입 시 본 파일을 다음으로 교체:

    from langgraph.graph import StateGraph, END
    g = StateGraph(AgentState)
    g.add_node("triage", triage_node)
    g.add_node("planner", planner_node)
    g.add_node("executor", executor_node)
    g.add_node("synthesizer", synthesizer_node)
    g.set_entry_point("triage")
    g.add_edge("triage", "planner")
    g.add_edge("planner", "executor")
    g.add_edge("executor", "synthesizer")
    g.add_edge("synthesizer", END)
    app = g.compile(checkpointer=PgCheckpointer(...))

지금은 langgraph 미설치 — 단순 sequence. AgentState 인터페이스는 동일.
"""

from __future__ import annotations

from .nodes import executor_node, planner_node, synthesizer_node, triage_node
from .state import AgentState


def run_agent(question: str, *,
              thread_id: str = "default",
              history: list[dict] | None = None) -> AgentState:
    """단일 대화 turn 실행. 호출 후 state 반환."""
    state: AgentState = {
        "thread_id": thread_id,
        "question": question,
        "history": history or [],
        "llm_usage_usd": 0.0,
        "n_replans": 0,
    }
    state = triage_node(state)
    state = planner_node(state)
    state = executor_node(state)
    state = synthesizer_node(state)
    return state


__all__ = ["run_agent"]
