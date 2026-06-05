"""Ontology pydantic schema 검증 — PRD §10 DoD #17 (c).

- 정상 파일 통과
- extra='forbid' 키 reject
- 잘못된 enum reject
- relation.from / to 가 entities 미존재 시 reject
- edge_required_meta 7키 누락/잉여 reject
- schema_version 헤더 끌어올림 검증
- yaml의 date 자동파싱 / 복합 key (list) / finance properties+confidence 호환
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from autonexusgraph.ontology import (
    EDGE_REQUIRED_META_KEYS,
    OntologyValidationError,
    load_and_validate,
    validate_dict,
)

# ── 정상 (실제 SSOT) ──────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]


def test_auto_entities_loads():
    ont = load_and_validate(ROOT / "ontology" / "auto" / "entities.yaml")
    assert ont.schema_version == "v2.2"
    assert ont.domain == "automotive"
    assert ont.entities is not None
    assert "Manufacturer" in ont.entities
    assert ont.entities["Manufacturer"].bom_level == 0


def test_auto_relations_loads_and_cross_validates():
    ont = load_and_validate(ROOT / "ontology" / "auto" / "relations.yaml")
    assert ont.schema_version == "v2.2"
    # edge_required_meta 가 7키 SoT 와 일치 → load 통과 자체가 증거.
    assert ont.edge_required_meta is not None
    assert set(ont.edge_required_meta) == set(EDGE_REQUIRED_META_KEYS)


def test_finance_entities_loads_with_composite_key():
    """finance Person/Product 등 복합 키 (list[str]) 도 호환."""
    ont = load_and_validate(ROOT / "ontology" / "entities.yaml")
    assert ont.schema_version == "v2.2"
    # Person 의 key 는 ['name', 'birth_year']
    person = ont.entities["Person"]
    assert isinstance(person.key, list)
    assert "name" in person.key


def test_finance_relations_loads_with_properties_field():
    """finance relations.yaml 의 properties / confidence (auto 와 다른 패턴) 호환."""
    ont = load_and_validate(ROOT / "ontology" / "relations.yaml")
    assert ont.schema_version == "v2.2"
    sub_of = ont.relations["SUBSIDIARY_OF"]
    assert sub_of.properties is not None
    assert any(p.get("name") == "ownership_pct" for p in sub_of.properties)


# ── 음성 (rejected) ───────────────────────────────────────────────
def _yaml_to_dict(text: str) -> dict:
    return yaml.safe_load(textwrap.dedent(text))


def test_extra_key_rejected_in_entity():
    data = _yaml_to_dict("""
        version: 1
        schema_version: "v2.2"
        entities:
          Foo:
            description: test
            key: id
            required: [id]
            unknown_field: oops
    """)
    with pytest.raises(Exception) as exc:
        validate_dict(data)
    assert "extra" in str(exc.value).lower() or "unknown_field" in str(exc.value)


def test_invalid_cardinality_rejected():
    data = _yaml_to_dict("""
        version: 1
        schema_version: "v2.2"
        entities:
          A:
            description: a
            required: [id]
          B:
            description: b
            required: [id]
        relations:
          REL:
            from: A
            to: B
            cardinality: many-to-zero    # invalid enum
    """)
    with pytest.raises(Exception):
        validate_dict(data)


def test_relation_unknown_from_label_rejected():
    """relation.from 이 entities 에 없으면 cross-validation 실패."""
    data = _yaml_to_dict("""
        version: 1
        schema_version: "v2.2"
        entities:
          A:
            description: a
            required: [id]
          B:
            description: b
            required: [id]
        relations:
          REL:
            from: Z         # 미정의 라벨
            to: B
    """)
    with pytest.raises(Exception) as exc:
        validate_dict(data)
    assert "Z" in str(exc.value) or "label" in str(exc.value).lower()


def test_edge_required_meta_missing_key_rejected():
    """edge_required_meta 가 PRD §6.7 7키 와 다르면 reject."""
    data = _yaml_to_dict("""
        version: 1
        schema_version: "v2.2"
        edge_required_meta:
          - source_type
          - source_id
          # 5개 누락
    """)
    with pytest.raises(Exception) as exc:
        validate_dict(data)
    assert "edge_required_meta" in str(exc.value)


def test_edge_required_meta_extra_key_rejected():
    data = _yaml_to_dict("""
        version: 1
        schema_version: "v2.2"
        edge_required_meta:
          - source_type
          - source_id
          - confidence_score
          - validated_status
          - snapshot_year
          - extraction_method
          - schema_version
          - bogus_key             # 잉여
    """)
    with pytest.raises(Exception) as exc:
        validate_dict(data)
    assert "잉여" in str(exc.value) or "bogus_key" in str(exc.value)


def test_bom_level_out_of_range():
    data = _yaml_to_dict("""
        version: 1
        schema_version: "v2.2"
        entities:
          X:
            description: x
            required: [id]
            bom_level: 99
    """)
    with pytest.raises(Exception):
        validate_dict(data)


def test_confidence_default_out_of_range():
    data = _yaml_to_dict("""
        version: 1
        schema_version: "v2.2"
        entities:
          A:
            description: a
            required: [id]
          B:
            description: b
            required: [id]
        relations:
          REL:
            from: A
            to: B
            confidence_default: 1.5     # > 1.0
    """)
    with pytest.raises(Exception):
        validate_dict(data)


# ── schema_version 헤더 끌어올림 ──────────────────────────────────
def test_schema_version_header_optional_for_legacy():
    """schema_version 헤더가 없어도 OntologyFile 자체는 통과 (점진적 도입)."""
    data = _yaml_to_dict("""
        version: 1
        entities:
          A:
            description: a
            required: [id]
    """)
    ont = validate_dict(data)
    assert ont.schema_version is None
    assert ont.entities is not None


def test_yaml_unquoted_date_in_last_updated():
    """yaml 의 ``2026-05-28`` 자동 date 파싱도 통과 (str | date 허용)."""
    data = _yaml_to_dict("""
        version: 1
        schema_version: "v2.2"
        last_updated: 2026-05-28
        entities:
          A:
            description: a
            required: [id]
    """)
    ont = validate_dict(data)
    # last_updated 가 date 또는 str — 둘 다 OK
    assert ont.last_updated is not None


# ── load_and_validate ↔ OntologyValidationError ───────────────────
def test_load_and_validate_wraps_validation_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("entities:\n  X:\n    description: x\n    unknown: oops\n",
                   encoding="utf-8")
    with pytest.raises(OntologyValidationError) as exc:
        load_and_validate(bad)
    assert exc.value.path == bad


def test_load_and_validate_file_not_dict(tmp_path):
    p = tmp_path / "list.yaml"
    p.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(OntologyValidationError):
        load_and_validate(p)
