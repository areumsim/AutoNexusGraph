"""Y-1 보조 yaml strict 검증 테스트 — 실파일 PASS + extra='forbid' 드리프트 reject."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from scripts.audit.ontology_validate import (
    AUX_TARGETS,
    ExtractorsFile,
    PlantEntry,
    SystemEntry,
    _validate_aux,
)


def test_real_aux_files_validate():
    """저장소의 실제 보조 yaml 4개가 모두 strict-validate 통과 + 항목 > 0."""
    for label, path, model, attr in AUX_TARGETS:
        r = _validate_aux(label, path, model, attr)
        assert r["passed"], f"{label}: {r.get('reason')}"
        assert r["n_items"] > 0


def test_extra_forbid_rejects_field_drift():
    with pytest.raises(ValidationError):
        PlantEntry(code="X", name="x", manufacturer_name="HYUNDAI",
                   country="KR", typoo="drift")        # 미정의 키 → reject
    with pytest.raises(ValidationError):
        SystemEntry(code="X", name="x", bogus=1)


def test_required_fields_enforced():
    with pytest.raises(ValidationError):
        PlantEntry(code="X", name="x")                 # manufacturer_name/country 누락


def test_extractor_pass_alias_and_source_str_or_dict():
    # str source (cross_validate 류) 허용
    f1 = ExtractorsFile(version=1, extractors={"e": {"pass": "P3", "source": "P3 산출 + P2"}})
    assert f1.extractors["e"].pass_ == "P3"
    # dict source 허용 + out
    ExtractorsFile(version=1, extractors={
        "e": {"pass": "P2", "source": {"type": "api"}, "out": {"entities": ["A"], "relations": []}}})


def test_extractor_unknown_key_rejected():
    with pytest.raises(ValidationError):
        ExtractorsFile(version=1, extractors={"e": {"pass": "P2", "nonsense": 1}})


# ── Y-2: cross-domain cypher reference WARN ↔ ERROR ─────────────────
def test_strict_cross_promotes_cross_domain_ref_to_error():
    from scripts.audit.ontology_validate import (
        CYPHER_TEMPLATE_REGISTRIES,
        _load_all_yaml_relations,
        _validate_cypher_relations,
    )
    all_yaml = _load_all_yaml_relations()
    domain, imp, dn, rels = next(t for t in CYPHER_TEMPLATE_REGISTRIES if t[0] == "ip")

    warn = _validate_cypher_relations(domain, imp, dn, rels, all_yaml, strict_cross=False)
    strict = _validate_cypher_relations(domain, imp, dn, rels, all_yaml, strict_cross=True)

    # ip cypher 는 auto.SUPPLIED_BY 를 cross-domain 참조 (BACKLOG Y-2 예시)
    assert "SUPPLIED_BY" in warn["cross_domain_refs"]
    assert warn["passed"] is True            # 기본 WARN — gate 비차단
    assert strict["passed"] is False         # --strict-cross → ERROR
    assert strict["cross_domain_refs"] == warn["cross_domain_refs"]
