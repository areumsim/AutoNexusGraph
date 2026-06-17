"""공통 Neo4j 적재 헬퍼.

§6.7 의 의무 메타 (source_type, source_id, confidence_score, validated_status,
snapshot_year, extraction_method, schema_version) 를 모든 엣지가 일관되게 가지도록
한 곳에서 강제한다. snapshot_year 와 schema_version 은 입력 dict 에 누락되면
helper 가 합리적 기본값으로 보강 (year=현재, schema_version=ontology 헤더).

**schema_version 단일 SoT**: PRD §10 DoD #17 (c) — `ontology/auto/relations.yaml`
헤더의 ``schema_version`` 이 SoT. `default_schema_version()` 가 본 헤더 값을 lazy
회수 (캐시). 적재 시점 코드에 버전 박지 마라 — yaml 만 바꾸면 자동 전파.

사용:
    >>> from ._neo4j_helpers import run_batched, edge_meta_cypher
    >>> session.run(
    ...     f"MATCH (a:Anxg_Module {{id:$mid}}), (b:Anxg_Supplier {{entity_id:$sid}}) "
    ...     f"MERGE (a)-[r:SUPPLIED_BY]->(b) "
    ...     f"SET {edge_meta_cypher('r')}",
    ...     mid=..., sid=..., source_id=..., source_type=..., ...
    ... )
"""

from __future__ import annotations

# 제네릭 로직은 common.neo4j_loader SSOT — 본 모듈은 **auto 도메인 ontology 바인딩**
# (meta keys + schema_version) thin 어댑터. run_batched 는 도메인 무관이라 그대로 re-export.
# (ipgraph 도 동일 패턴으로 common 을 자기 ontology 와 바인딩 — 이전의 ip→auto private
#  cross-import + schema_version cross-domain fallback 결함 해소. common/neo4j_loader.py 참조.)
from common.neo4j_loader import edge_meta_cypher as _edge_meta_cypher
from common.neo4j_loader import run_batched  # noqa: F401 — 도메인 무관, 재노출

from ..ontology import load_edge_required_meta, ontology_schema_version

# 의무 메타 키 — auto ontology SSOT.
EDGE_META_KEYS: tuple[str, ...] = load_edge_required_meta()


def default_schema_version() -> str:
    """현재 적재 시점의 기본 schema_version — auto ontology 헤더 SoT.

    ontology/auto/relations.yaml 의 ``schema_version`` 헤더 값을 lazy 회수 (캐시).
    헤더 미설정 시 'v0' (legacy) 반환. 호출자가 row dict 에 schema_version 박지
    않으면 본 값이 자동 보강된다 (edge_meta_cypher 의 coalesce).
    """
    return ontology_schema_version()


# 하위 호환 — DEFAULT_SCHEMA_VERSION 상수 참조하는 코드 보존. 단 본 상수는 임포트
# 시점 1회 평가되므로 yaml 헤더 변경 후에도 process restart 필요. 새 코드는
# default_schema_version() 함수 호출 권장.
DEFAULT_SCHEMA_VERSION = ontology_schema_version()


def edge_meta_cypher(rel_var: str = "r") -> str:
    """auto 도메인 의무 메타를 한 줄 SET 절로 (auto ontology 바인딩).

    rows 의 각 dict 는 EDGE_META_KEYS 모두 포함해야 한다. ``snapshot_year`` 와
    ``schema_version`` 만 누락 시 helper 가 보강 — schema_version 은 auto ontology
    헤더 (default_schema_version()) 자동 부여.
    """
    return _edge_meta_cypher(EDGE_META_KEYS, default_schema_version(), rel_var)


__all__ = [
    "EDGE_META_KEYS",
    "DEFAULT_SCHEMA_VERSION",      # deprecated — import-time snapshot
    "default_schema_version",      # lazy SoT — yaml 헤더에서 동적 회수
    "edge_meta_cypher",
    "run_batched",
]
