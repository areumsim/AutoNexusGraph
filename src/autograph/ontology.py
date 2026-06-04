"""AutoGraph 자동차 도메인 온톨로지 로더 (SSOT).

ontology/auto/{entities,relations,extractors,system_taxonomy,standards,plants}.yaml
을 한 곳에서 로드. 다음 모듈이 본 로더를 통해 SSOT 에 접근한다:

- ``loaders.neo4j_init``  : 라벨 + key 컬럼 → CONSTRAINT 자동 생성
- ``loaders.load_*``       : 엣지 적재 시 §6.7 의무 메타 키 강제
- ``extractors/*``         : 프롬프트에 entity/relation 표 주입 (schema-aware)
- ``extractors.cross_validate``: 관계 from/to 라벨 검증 + confidence_default

검증 (PRD §10 DoD #17 (c)): entities.yaml / relations.yaml 은 load 시점에
``autonexusgraph.ontology.OntologyFile`` 로 pydantic strict-validate. 미지정 키 /
잘못된 enum / 미존재 라벨 reference 는 import 시점에 reject. ``schema_version``
은 파일 헤더 1곳 SoT — ``ontology_schema_version()`` 헬퍼 노출.

주의: 본 로더는 ``autonexusgraph/`` (금융) 의 ``ontology/*.yaml`` 은 건드리지 않음.
finance 측은 자체 코드에서 직접 ``ontology/`` 를 읽는다 (변경 없음).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from autonexusgraph.ontology import OntologyFile, load_and_validate


# repo_root/ontology/auto/
_ONTOLOGY_DIR = Path(__file__).resolve().parents[2] / "ontology" / "auto"


@lru_cache(maxsize=1)
def _load_entities_file() -> OntologyFile:
    """entities.yaml 의 pydantic-validated OntologyFile 캐시."""
    return load_and_validate(_ONTOLOGY_DIR / "entities.yaml")


@lru_cache(maxsize=1)
def _load_relations_file() -> OntologyFile:
    """relations.yaml 의 pydantic-validated OntologyFile 캐시."""
    return load_and_validate(_ONTOLOGY_DIR / "relations.yaml")


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
    """온톨로지 헤더의 schema_version — 엣지 적재 helper 가 본 값을 자동 부여한다.

    relations.yaml 헤더의 ``schema_version`` 이 SoT. 없으면 'v0' (legacy)
    반환 — 점진적 도입 호환.
    """
    ont = _load_relations_file()
    return ont.schema_version or "v0"


@lru_cache(maxsize=1)
def load_extractors() -> dict[str, dict[str, Any]]:
    """extractors.yaml → {extractor_name: spec}."""
    data = yaml.safe_load((_ONTOLOGY_DIR / "extractors.yaml").read_text(encoding="utf-8"))
    return data["extractors"]


@lru_cache(maxsize=1)
def load_system_taxonomy() -> dict[str, dict[str, Any]]:
    """system_taxonomy.yaml → {code: {name, description, alias_codes}}.

    alias_codes 는 AI-Hub 로더가 'powertrain' 같은 raw code 를 canonical 'POWERTRAIN'
    으로 정규화할 때 참조.
    """
    data = yaml.safe_load((_ONTOLOGY_DIR / "system_taxonomy.yaml").read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for row in data["systems"]:
        out[row["code"]] = row
    return out


@lru_cache(maxsize=1)
def load_standards() -> list[dict[str, Any]]:
    """standards.yaml → [Standard rows]."""
    data = yaml.safe_load((_ONTOLOGY_DIR / "standards.yaml").read_text(encoding="utf-8"))
    return data["standards"]


@lru_cache(maxsize=1)
def load_plants() -> list[dict[str, Any]]:
    """plants.yaml → [Plant rows]."""
    data = yaml.safe_load((_ONTOLOGY_DIR / "plants.yaml").read_text(encoding="utf-8"))
    return data["plants"]


@lru_cache(maxsize=1)
def load_manufactured_at_seed() -> list[dict[str, Any]]:
    """manufactured_at_seed.yaml → [(model_name, manufacturer, plant_code, valid_from)]."""
    p = _ONTOLOGY_DIR / "manufactured_at_seed.yaml"
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    return data.get("mappings") or []


def load_performed_at_seed() -> dict[str, Any]:
    """performed_at_seed.yaml → {processes:[...], mappings:[...]}.

    회사 귀속 공정 시드 ((:ProcessStep)-[:PERFORMED_AT]->(:Plant)). 파일 부재 시
    빈 구조 — loader 가 graceful 0 건으로 종료.
    """
    p = _ONTOLOGY_DIR / "performed_at_seed.yaml"
    if not p.exists():
        return {"processes": [], "mappings": []}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {
        "processes": data.get("processes") or [],
        "mappings": data.get("mappings") or [],
    }


@lru_cache(maxsize=1)
def _alias_to_canonical_system() -> dict[str, str]:
    """raw system code (대소문자, alias) → canonical SCREAMING_SNAKE_CASE.

    AI-Hub / 매뉴얼 / LLM 산출에 등장하는 다양한 표기를 단일 코드로 모은다.
    """
    out: dict[str, str] = {}
    for code, row in load_system_taxonomy().items():
        out[code.upper()] = code
        out[code.lower()] = code
        for alias in row.get("alias_codes") or []:
            if alias:
                out[alias.upper()] = code
                out[alias.lower()] = code
    return out


def canonical_system_code(raw: str | None) -> str:
    """'powertrain' / 'ENGINE' / 'powertrain ' → 'POWERTRAIN'.

    매칭 실패 시 'UNKNOWN' 반환 (none/빈문자도 동일).
    """
    if not raw:
        return "UNKNOWN"
    key = raw.strip()
    if not key:
        return "UNKNOWN"
    table = _alias_to_canonical_system()
    return table.get(key, table.get(key.upper(), table.get(key.lower(), "UNKNOWN")))


def entity_key_property(label: str) -> str | list[str]:
    """라벨의 자연 키 속성명. neo4j_init 가 CONSTRAINT 만들 때 사용.

    반환 타입:
        - str: 단일 키 (auto 도메인 다수 — 'id', 'code', 'entity_id')
        - list[str]: 복합 키 (finance Person ['name', 'birth_year'] 등)

    호출자는 isinstance check 또는 ``_constraint`` (neo4j_init.py) 같은
    헬퍼로 분기.
    """
    spec = load_entities().get(label)
    if not spec:
        raise KeyError(f"unknown entity label: {label}")
    return spec.get("key", "id")


def entity_labels() -> list[str]:
    """ontology 가 정의한 자동차 도메인의 모든 라벨."""
    return list(load_entities().keys())


def relation_types() -> list[str]:
    """ontology 가 정의한 모든 관계 타입."""
    return list(load_relations().keys())


def relation_endpoints(rel_type: str) -> tuple[str, str]:
    """관계 from→to 라벨. cross_validate / prompt 에서 사용."""
    spec = load_relations()[rel_type]
    return spec["from"], spec["to"]


def render_entity_table_for_prompt() -> str:
    """LLM 프롬프트에 주입할 entity 타입 표 (markdown).

    relation_extract_auto.yaml 의 ``{entity_types_table}`` 자리에 들어간다.
    """
    lines = ["| 라벨 | 설명 | 키 |", "|---|---|---|"]
    for label, spec in load_entities().items():
        desc = (spec.get("description") or "").strip().splitlines()[0]
        lines.append(f"| {label} | {desc} | {spec.get('key', 'id')} |")
    return "\n".join(lines)


def render_relation_table_for_prompt(*, enabled_only: bool = True) -> str:
    """LLM 프롬프트의 ``{relation_types_table}`` 자리에 들어가는 표."""
    lines = ["| 관계 | From | To | 신뢰도 기본 | 비고 |",
             "|---|---|---|---|---|"]
    for rt, spec in load_relations().items():
        if enabled_only and not spec.get("enabled", True):
            continue
        note_bits = []
        if spec.get("class"):
            note_bits.append(spec["class"])
        if spec.get("provenance"):
            note_bits.append(spec["provenance"])
        lines.append(
            f"| {rt} | {spec['from']} | {spec['to']} | "
            f"{spec.get('confidence_default', 0.7):.2f} | {', '.join(note_bits)} |"
        )
    return "\n".join(lines)


__all__ = [
    "load_entities",
    "load_relations",
    "load_edge_required_meta",
    "load_extractors",
    "load_system_taxonomy",
    "load_standards",
    "load_plants",
    "load_manufactured_at_seed",
    "ontology_schema_version",
    "canonical_system_code",
    "entity_key_property",
    "entity_labels",
    "relation_types",
    "relation_endpoints",
    "render_entity_table_for_prompt",
    "render_relation_table_for_prompt",
]
