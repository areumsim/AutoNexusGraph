"""도메인 온톨로지 로더 팩토리 — autograph / ipgraph 공통 구현 (중복 제거).

``ontology/<domain>/{entities,relations}.yaml`` 를 pydantic strict-validate
(PRD §10 DoD #17 (c)) 한 뒤 raw dict 로 환원하는 10개 헬퍼는 auto·ip 도메인이
동일했다. 본 팩토리가 ``ontology_dir`` 파라미터화로 1회 정의 → 각 도메인 모듈은
``make_domain_loaders(dir)`` 의 결과를 module-level 함수로 바인딩한다.

각 도메인 모듈은 자신의 ``entities.yaml`` 이 import 시점에 검증되도록 ``load_entities``
등을 그대로 노출한다. lru_cache 는 팩토리 호출 1회당 closure 단위로 격리된다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import OntologyFile, load_and_validate


@dataclass(frozen=True)
class DomainOntologyLoaders:
    """``make_domain_loaders`` 가 반환하는 함수 묶음 — 도메인 모듈이 바인딩."""
    _load_entities_file: Callable[[], OntologyFile]
    _load_relations_file: Callable[[], OntologyFile]
    load_entities: Callable[[], dict[str, dict[str, Any]]]
    load_relations: Callable[[], dict[str, dict[str, Any]]]
    load_edge_required_meta: Callable[[], tuple[str, ...]]
    ontology_schema_version: Callable[[], str]
    entity_key_property: Callable[[str], str | list[str]]
    entity_labels: Callable[[], list[str]]
    relation_types: Callable[[], list[str]]
    relation_endpoints: Callable[[str], tuple[str, str]]


def make_domain_loaders(ontology_dir: Path,
                        *, entity_noun: str = "entity") -> DomainOntologyLoaders:
    """``ontology_dir`` 의 entities/relations.yaml 로더 묶음 생성.

    Args:
        ontology_dir: ``.../ontology/<domain>`` 디렉토리.
        entity_noun: ``entity_key_property`` 의 KeyError 메시지용 명사
            (예: 'entity' / 'ip entity') — 기존 도메인별 메시지 보존.
    """

    @lru_cache(maxsize=1)
    def _load_entities_file() -> OntologyFile:
        """entities.yaml 의 pydantic-validated OntologyFile 캐시."""
        return load_and_validate(ontology_dir / "entities.yaml")

    @lru_cache(maxsize=1)
    def _load_relations_file() -> OntologyFile:
        """relations.yaml 의 pydantic-validated OntologyFile 캐시."""
        return load_and_validate(ontology_dir / "relations.yaml")

    @lru_cache(maxsize=1)
    def load_entities() -> dict[str, dict[str, Any]]:
        """entities.yaml → {label: spec}. raw dict 환원 — 기존 호출자 호환."""
        ont = _load_entities_file()
        return {label: spec.model_dump(by_alias=True, exclude_none=False)
                for label, spec in (ont.entities or {}).items()}

    @lru_cache(maxsize=1)
    def load_relations() -> dict[str, dict[str, Any]]:
        """relations.yaml → {rel_type: spec}. raw dict 환원 — 기존 호출자 호환."""
        ont = _load_relations_file()
        return {rt: spec.model_dump(by_alias=True, exclude_none=False)
                for rt, spec in (ont.relations or {}).items()}

    @lru_cache(maxsize=1)
    def load_edge_required_meta() -> tuple[str, ...]:
        """relations.yaml::edge_required_meta — 모든 엣지가 가져야 할 속성 키."""
        ont = _load_relations_file()
        return tuple(ont.edge_required_meta or ())

    @lru_cache(maxsize=1)
    def ontology_schema_version() -> str:
        """relations.yaml 헤더의 schema_version SoT. 없으면 'v0' (legacy)."""
        ont = _load_relations_file()
        return ont.schema_version or "v0"

    def entity_key_property(label: str) -> str | list[str]:
        """라벨의 자연 키 속성명 (단일 str 또는 복합 list[str])."""
        spec = load_entities().get(label)
        if not spec:
            raise KeyError(f"unknown {entity_noun} label: {label}")
        return spec.get("key", "id")

    def entity_labels() -> list[str]:
        """ontology 가 정의한 모든 라벨."""
        return list(load_entities().keys())

    def relation_types() -> list[str]:
        """ontology 가 정의한 모든 관계 타입."""
        return list(load_relations().keys())

    def relation_endpoints(rel_type: str) -> tuple[str, str]:
        """관계 from→to 라벨."""
        spec = load_relations()[rel_type]
        return spec["from"], spec["to"]

    return DomainOntologyLoaders(
        _load_entities_file=_load_entities_file,
        _load_relations_file=_load_relations_file,
        load_entities=load_entities,
        load_relations=load_relations,
        load_edge_required_meta=load_edge_required_meta,
        ontology_schema_version=ontology_schema_version,
        entity_key_property=entity_key_property,
        entity_labels=entity_labels,
        relation_types=relation_types,
        relation_endpoints=relation_endpoints,
    )


__all__ = ["DomainOntologyLoaders", "make_domain_loaders"]
