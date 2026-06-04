"""평가 어댑터 — 4 시스템 비교 매트릭스.

선택지: vector / graph / hybrid / sql_vec.
runner 는 --adapters=vector,graph,hybrid,sql_vec 식으로 호출.
"""

from .base import AgentAdapter, AgentResponse, Evidence
from .vector_adapter import VectorAdapter
from .graph_adapter import GraphAdapter
from .hybrid_adapter import HybridAdapter
from .sql_vec_adapter import SqlVecAdapter


# 이름으로 lookup — runner CLI 가 사용.
ADAPTER_REGISTRY: dict[str, type[AgentAdapter]] = {
    "vector":  VectorAdapter,
    "graph":   GraphAdapter,
    "hybrid":  HybridAdapter,
    "sql_vec": SqlVecAdapter,
}


def get_adapter(name: str, *,
                 rerank: bool = True,
                 llm_tier: str = "fast",
                 llm_planner: bool = False) -> AgentAdapter:
    """이름으로 어댑터 인스턴스 — 매트릭스 변수 (rerank/llm_tier/llm_planner) 옵션.

    PRD §10 DoD #17 (d) 축소 평가 매트릭스 셀 enumeration 용. 동일 어댑터를
    (rerank=True, rerank=False) 두 셀로 호출 가능. ``llm_planner`` (축2 ablation) 는
    agent planner 를 실제 경유하는 ``hybrid`` 어댑터에만 전달 — 타 어댑터(vector/graph/
    sql_vec)는 planner 미경유라 무의미하므로 미전달(기존 시그니처 보존).
    """
    cls = ADAPTER_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"unknown adapter: {name}. available={list(ADAPTER_REGISTRY)}")
    kwargs: dict = {"rerank": rerank, "llm_tier": llm_tier}
    if name == "hybrid":
        kwargs["llm_planner"] = llm_planner
    return cls(**kwargs)


__all__ = [
    "AgentAdapter", "AgentResponse", "Evidence",
    "VectorAdapter", "GraphAdapter", "HybridAdapter", "SqlVecAdapter",
    "ADAPTER_REGISTRY", "get_adapter",
]
