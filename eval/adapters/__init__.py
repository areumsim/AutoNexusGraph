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


def get_adapter(name: str) -> AgentAdapter:
    cls = ADAPTER_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"unknown adapter: {name}. available={list(ADAPTER_REGISTRY)}")
    return cls()


__all__ = [
    "AgentAdapter", "AgentResponse", "Evidence",
    "VectorAdapter", "GraphAdapter", "HybridAdapter", "SqlVecAdapter",
    "ADAPTER_REGISTRY", "get_adapter",
]
