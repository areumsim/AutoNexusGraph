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

from autonexusgraph.ontology.loaders import make_domain_loaders

# repo_root/ontology/auto/
_ONTOLOGY_DIR = Path(__file__).resolve().parents[2] / "ontology" / "auto"

# ── 공통 entities/relations 로더 (ipgraph/ontology.py 와 동일 구현 1곳) ──
# entity/relation 표준 헬퍼 10개는 도메인 무관 → autonexusgraph.ontology.loaders
# 팩토리로 단일화. 아래 바인딩으로 기존 module-level 함수명·시그니처 보존.
_L = make_domain_loaders(_ONTOLOGY_DIR)
_load_entities_file = _L._load_entities_file
_load_relations_file = _L._load_relations_file
load_entities = _L.load_entities
load_relations = _L.load_relations
load_edge_required_meta = _L.load_edge_required_meta
ontology_schema_version = _L.ontology_schema_version       # relations.yaml 헤더 SoT
entity_key_property = _L.entity_key_property
entity_labels = _L.entity_labels
relation_types = _L.relation_types
relation_endpoints = _L.relation_endpoints


# ── auto 도메인 전용 보조 yaml 로더 (공통 팩토리 범위 밖) ──
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

    회사 귀속 공정 시드 ((:Anxg_ProcessStep)-[:PERFORMED_AT]->(:Anxg_Plant)). 파일 부재 시
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
