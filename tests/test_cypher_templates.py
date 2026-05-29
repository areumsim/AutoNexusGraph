"""Cypher 템플릿 레지스트리 — 검증 규칙 + render 동작."""

from __future__ import annotations

import pytest

from autonexusgraph.tools.cypher_templates import (
    TEMPLATES,
    TemplateError,
    list_templates,
    register_templates,
    render_template,
    validate_template_spec,
)


# ── 레지스트리 자체 ─────────────────────────────────────────
def test_registry_non_empty():
    names = list_templates()
    assert "lookup_company" in names
    assert "find_paths_3hops" in names
    assert "get_subgraph_d1" in names


# ── 외부 도메인 (AUTO_TEMPLATES) 스펙 무결성 — drift 방지 ──
def test_auto_templates_pass_spec_validation():
    """autograph 의 AUTO_TEMPLATES 가 finance 와 동일 스키마를 따르는지 정적 검증."""
    from autograph.cypher_templates_auto import AUTO_TEMPLATES
    for name, spec in AUTO_TEMPLATES.items():
        # 잘못된 스펙은 import 가 아닌 본 시점에서 잡힘.
        validate_template_spec(name, spec)


def test_validate_template_spec_rejects_bad_shapes():
    # cypher 누락
    with pytest.raises(TemplateError):
        validate_template_spec("x", {"required_params": []})
    # cypher 빈 문자열
    with pytest.raises(TemplateError):
        validate_template_spec("x", {"cypher": "   "})
    # required_params 잘못된 타입
    with pytest.raises(TemplateError):
        validate_template_spec("x", {"cypher": "MATCH (n) RETURN n",
                                      "required_params": "abc"})
    # param_schema 의 spec 이 tuple 아님
    with pytest.raises(TemplateError):
        validate_template_spec("x", {"cypher": "MATCH (n) RETURN n",
                                      "param_schema": {"a": "wrong"}})


def test_register_templates_blocks_name_collision():
    reg = {"foo": {"cypher": "MATCH (n) RETURN n"}}
    new = {"foo": {"cypher": "MATCH (m) RETURN m"}}
    with pytest.raises(TemplateError, match="이름 충돌"):
        register_templates(reg, new)


def test_register_templates_validates_each_spec():
    reg: dict = {}
    bad = {"x": {"required_params": []}}  # cypher 없음
    with pytest.raises(TemplateError):
        register_templates(reg, bad)
    assert reg == {}  # 실패 시 등록 X


def test_every_template_has_required_keys():
    for name, spec in TEMPLATES.items():
        assert "cypher" in spec, name
        assert "required_params" in spec, name
        assert "param_schema" in spec, name


def test_no_write_keywords_in_any_template():
    """레지스트리의 모든 cypher 는 READ-ONLY 여야 함 — cypher_guard 가 잡지만 사전 검증."""
    from autonexusgraph.safety.cypher_guard import assert_read_only
    for name, spec in TEMPLATES.items():
        try:
            assert_read_only(spec["cypher"])
        except Exception as e:   # noqa: BLE001
            pytest.fail(f"{name}: cypher_guard 위반 — {e}")


# ── render_template ─────────────────────────────────────────
def test_render_basic_ok():
    cy, p = render_template(
        "lookup_company", {"q": "삼성전자", "limit": 5},
    )
    assert "$q" in cy and "$limit" in cy
    assert p["q"] == "삼성전자"
    assert p["limit"] == 5


def test_render_unknown_template_fails():
    with pytest.raises(TemplateError):
        render_template("ghost_template", {})


def test_render_missing_required_fails():
    with pytest.raises(TemplateError) as ei:
        render_template("lookup_company", {"q": "x"})
    assert "limit" in str(ei.value)


def test_render_type_mismatch_fails():
    with pytest.raises(TemplateError):
        render_template("lookup_company", {"q": "x", "limit": "five"})


def test_render_range_violation_fails():
    with pytest.raises(TemplateError):
        render_template("lookup_company", {"q": "x", "limit": 1000})   # > 500
    with pytest.raises(TemplateError):
        render_template("lookup_company", {"q": "x", "limit": 0})


def test_render_regex_corp_code_must_be_8_digits():
    with pytest.raises(TemplateError):
        render_template("list_subsidiaries", {"cc": "abc", "limit": 10})
    with pytest.raises(TemplateError):
        render_template("list_subsidiaries", {"cc": "12345", "limit": 10})
    # 정상 8자리
    cy, p = render_template("list_subsidiaries", {"cc": "00126380", "limit": 10})
    assert p["cc"] == "00126380"


def test_render_nullable_optional_param():
    """year 는 None 도 허용 (Cypher 에서 IS NULL 체크)."""
    cy, p = render_template(
        "list_subsidiaries",
        {"cc": "00126380", "year": None, "limit": 10},
    )
    assert p["year"] is None


def test_render_year_range():
    with pytest.raises(TemplateError):
        render_template(
            "list_subsidiaries",
            {"cc": "00126380", "year": 1800, "limit": 10},
        )


def test_render_min_pct_float_range():
    with pytest.raises(TemplateError):
        render_template(
            "get_major_shareholders",
            {"cc": "00126380", "min_pct": 150.0, "limit": 10},
        )
    cy, p = render_template(
        "get_major_shareholders",
        {"cc": "00126380", "min_pct": 5.0, "limit": 10},
    )
    assert p["min_pct"] == 5.0


def test_render_int_for_float_ok():
    """float param 에 int 입력은 통과."""
    cy, p = render_template(
        "get_major_shareholders",
        {"cc": "00126380", "min_pct": 5, "limit": 10},
    )
    assert p["min_pct"] == 5


def test_render_bool_not_accepted_as_int():
    """bool 이 int 자리에 들어가면 reject."""
    with pytest.raises(TemplateError):
        render_template(
            "list_subsidiaries",
            {"cc": "00126380", "limit": True},
        )


def test_render_find_paths_hops_registered():
    for h in (1, 3, 5):
        cy, p = render_template(
            f"find_paths_{h}hops",
            {"a": "00126380", "b": "00164779"},
        )
        assert f"*1..{h}" in cy


def test_render_find_paths_corp_code_regex():
    with pytest.raises(TemplateError):
        render_template("find_paths_3hops", {"a": "ABC", "b": "00164779"})


def test_render_subgraph_per_depth():
    for d in (1, 2, 3):
        cy, p = render_template(
            f"get_subgraph_d{d}",
            {"cc": "00126380", "limit": 50},
        )
        assert f"maxLevel: {d}" in cy


def test_render_ignores_extra_params():
    """schema 에 없는 param 은 무시 (호환성)."""
    cy, p = render_template(
        "lookup_company",
        {"q": "x", "limit": 5, "extra_unused": "ok"},
    )
    assert "extra_unused" in p   # 그대로 전달은 됨 (Neo4j 는 사용 안 함)
