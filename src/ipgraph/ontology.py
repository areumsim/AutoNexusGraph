"""IPGraph (특허) 도메인 온톨로지 로더.

``ontology/ip/{entities,relations}.yaml`` 을 한 곳에서 로드 + pydantic strict validate
(PRD §10 DoD #17 (c)). autograph/ontology.py 와 동일 패턴.

호출자:
- ``loaders.load_*``       : 엣지 적재 시 §6.7 의무 메타 키 강제
- ``ipgraph.agent_handler``: identify_targets / plan_tasks 가 ontology 참조
- ``ipgraph.tools.*``      : Cypher 템플릿이 relation_endpoints 검증
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from autonexusgraph.ontology import OntologyFile, load_and_validate


# repo_root/ontology/ip/
_ONTOLOGY_DIR = Path(__file__).resolve().parents[2] / "ontology" / "ip"


@lru_cache(maxsize=1)
def _load_entities_file() -> OntologyFile:
    return load_and_validate(_ONTOLOGY_DIR / "entities.yaml")


@lru_cache(maxsize=1)
def _load_relations_file() -> OntologyFile:
    return load_and_validate(_ONTOLOGY_DIR / "relations.yaml")


@lru_cache(maxsize=1)
def load_entities() -> dict[str, dict[str, Any]]:
    """entities.yaml → {label: spec}. raw dict 환원 — 기존 호출자 호환."""
    ont = _load_entities_file()
    return {label: spec.model_dump(by_alias=True, exclude_none=False)
            for label, spec in (ont.entities or {}).items()}


@lru_cache(maxsize=1)
def load_relations() -> dict[str, dict[str, Any]]:
    """relations.yaml → {rel_type: spec}."""
    ont = _load_relations_file()
    return {rt: spec.model_dump(by_alias=True, exclude_none=False)
            for rt, spec in (ont.relations or {}).items()}


@lru_cache(maxsize=1)
def load_edge_required_meta() -> tuple[str, ...]:
    ont = _load_relations_file()
    return tuple(ont.edge_required_meta or ())


@lru_cache(maxsize=1)
def ontology_schema_version() -> str:
    """yaml 헤더 schema_version SoT (v2.2)."""
    ont = _load_relations_file()
    return ont.schema_version or "v0"


def entity_key_property(label: str) -> str | list[str]:
    spec = load_entities().get(label)
    if not spec:
        raise KeyError(f"unknown ip entity label: {label}")
    return spec.get("key", "id")


def entity_labels() -> list[str]:
    return list(load_entities().keys())


def relation_types() -> list[str]:
    return list(load_relations().keys())


def relation_endpoints(rel_type: str) -> tuple[str, str]:
    spec = load_relations()[rel_type]
    return spec["from"], spec["to"]


__all__ = [
    "load_entities",
    "load_relations",
    "load_edge_required_meta",
    "ontology_schema_version",
    "entity_key_property",
    "entity_labels",
    "relation_types",
    "relation_endpoints",
]
