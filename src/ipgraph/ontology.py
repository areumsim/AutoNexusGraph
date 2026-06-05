"""IPGraph (특허) 도메인 온톨로지 로더.

``ontology/ip/{entities,relations}.yaml`` 을 한 곳에서 로드 + pydantic strict validate
(PRD §10 DoD #17 (c)). autograph/ontology.py 와 동일 패턴.

호출자:
- ``loaders.load_*``       : 엣지 적재 시 §6.7 의무 메타 키 강제
- ``ipgraph.agent_handler``: identify_targets / plan_tasks 가 ontology 참조
- ``ipgraph.tools.*``      : Cypher 템플릿이 relation_endpoints 검증
"""

from __future__ import annotations

from pathlib import Path

from autonexusgraph.ontology.loaders import make_domain_loaders

# repo_root/ontology/ip/
_ONTOLOGY_DIR = Path(__file__).resolve().parents[2] / "ontology" / "ip"

# 공통 팩토리 바인딩 — autograph/ontology.py 와 동일 구현 1곳 (중복 제거).
_L = make_domain_loaders(_ONTOLOGY_DIR, entity_noun="ip entity")
_load_entities_file = _L._load_entities_file
_load_relations_file = _L._load_relations_file
load_entities = _L.load_entities
load_relations = _L.load_relations
load_edge_required_meta = _L.load_edge_required_meta
ontology_schema_version = _L.ontology_schema_version       # yaml 헤더 SoT (v2.2)
entity_key_property = _L.entity_key_property
entity_labels = _L.entity_labels
relation_types = _L.relation_types
relation_endpoints = _L.relation_endpoints


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
