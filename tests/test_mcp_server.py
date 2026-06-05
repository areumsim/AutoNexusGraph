"""MCP 래퍼 (PRD §10 DoD #17 (a)) — tool discovery + JSON Schema 변환 검증.

mcp SDK 미설치 환경에서도 통과해야 (discovery 는 SDK 무관). server.py 측은
SDK 설치 시에만 import 시도.
"""

from __future__ import annotations

from autonexusgraph.mcp import ToolSpec, build_tool_manifest
from autonexusgraph.mcp.discovery import (
    _annotation_to_schema,
    _signature_to_jsonschema,
    tool_function,
)


# ── discovery 기본 ──────────────────────────────────────────────
def test_build_tool_manifest_all_has_tools():
    specs = build_tool_manifest("all")
    assert len(specs) > 25     # finance + auto 합 ~52 (변동 가능)
    assert all(isinstance(s, ToolSpec) for s in specs)


def test_build_tool_manifest_domain_filter():
    fin = build_tool_manifest("finance")
    auto = build_tool_manifest("auto")
    assert all(s.domain == "finance" for s in fin)
    assert all(s.domain == "auto" for s in auto)


def test_tool_function_extracts_docstring_first_line():
    def my_tool(x: int, y: str = "hi") -> str:
        """Short description for MCP.

        Detailed body — should not be in description.
        """
        return f"{x}/{y}"
    spec = tool_function(my_tool)
    assert spec.description == "Short description for MCP."
    assert spec.name == "my_tool"


# ── JSON Schema 변환 ────────────────────────────────────────────
def test_signature_extracts_required_and_optional():
    def f(name: str, year: int, country: str = "KR") -> dict:
        """test."""
        return {}
    schema = _signature_to_jsonschema(f)
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"name", "year"}
    assert schema["properties"]["name"] == {"type": "string"}
    assert schema["properties"]["year"] == {"type": "integer"}
    assert schema["properties"]["country"] == {"type": "string"}


def test_annotation_optional_unwraps_to_inner():
    """``str | None`` → {'type': 'string'}."""
    schema = _annotation_to_schema(str | None)
    assert schema == {"type": "string"}


def test_annotation_list_of_str():
    schema = _annotation_to_schema(list[str])
    assert schema == {"type": "array", "items": {"type": "string"}}


def test_annotation_dict_to_object():
    schema = _annotation_to_schema(dict[str, int])
    assert schema == {"type": "object"}


def test_annotation_unknown_fallback():
    class Custom:
        pass
    schema = _annotation_to_schema(Custom)
    assert schema == {"type": "string"}


# ── ToolSpec 일관성 ─────────────────────────────────────────────
def test_all_specs_have_nonempty_name_and_schema():
    for s in build_tool_manifest("all"):
        assert s.name and isinstance(s.name, str)
        assert s.description
        assert s.input_schema.get("type") == "object"
        assert isinstance(s.input_schema.get("properties", {}), dict)


def test_specs_unique_by_name():
    specs = build_tool_manifest("all")
    names = [s.name for s in specs]
    assert len(names) == len(set(names))     # finance 와 auto 사이 중복 없음 보장


def test_finance_lookup_company_required_query():
    specs = {s.name: s for s in build_tool_manifest("finance")}
    if "lookup_company" in specs:
        s = specs["lookup_company"]
        assert "query" in s.input_schema.get("required", [])


# ── fail-soft: server module SDK 미설치 시 ───────────────────────
def test_server_module_failsoft_on_sdk_missing():
    """mcp SDK 가 없을 때 ``autonexusgraph.mcp.build_mcp_server`` 는 None."""
    from autonexusgraph import mcp as mcp_pkg
    try:
        import mcp  # noqa: F401
    except ImportError:
        # SDK 미설치 — fail-soft 검증.
        assert mcp_pkg.build_mcp_server is None
        assert mcp_pkg.run_stdio_server is None
    else:
        # SDK 설치 — 함수 객체.
        assert callable(mcp_pkg.build_mcp_server)
