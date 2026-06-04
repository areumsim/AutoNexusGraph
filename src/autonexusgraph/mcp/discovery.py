"""Tool 자동 discovery + type hint → JSON Schema 변환.

PRD §10 DoD #17 (a) — 외부 MCP 클라이언트에 typed tool pool 자동 노출
(finance 21 + auto 38 = 59 tools, BACKLOG S-1 SSOT; ``__all__`` 기준 자동 산정).

핵심:
- ``build_tool_manifest(domain)`` — 도메인별 tool 함수 list
- 각 함수의 ``inspect.signature`` + type hints → JSON Schema (pydantic TypeAdapter)
- docstring 첫 줄 = MCP Tool.description
- MCP SDK 와 독립적 — 본 모듈은 MCP SDK 없어도 import 가능 (server.py 만 분리).
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, get_type_hints


@dataclass(frozen=True)
class ToolSpec:
    """MCP Tool 표현 — domain-agnostic.

    ``server.py`` 가 본 spec 을 MCP SDK 의 Tool 객체로 변환. 본 spec 자체는
    SDK 의존 없음 → 테스트·audit 가 SDK 미설치 환경에서도 검증 가능.
    """
    name: str
    description: str
    fn: Callable[..., Any]
    domain: str           # 'auto' | 'finance' | 'cross'
    input_schema: dict[str, Any] = field(default_factory=dict)


# ── 도메인 → tool 함수 source 모듈 ────────────────────────────────
_DOMAIN_MODULES: dict[str, tuple[str, ...]] = {
    "finance": ("autonexusgraph.tools",),
    "auto":    ("autograph.tools",),
    # 'all' 은 두 도메인 합집합.
}


def tool_function(fn: Callable[..., Any], *,
                  name: str | None = None) -> ToolSpec:
    """단일 함수 → ToolSpec. type hints / docstring 자동 추출.

    Args:
        fn: 함수 객체.
        name: tool 이름 override — 모듈 export alias 보존용 (e.g.
            ``lookup_vehicle_graph`` alias 의 fn.__name__ 은 ``lookup_vehicle``).
            None 시 ``fn.__name__`` 사용.
    """
    tool_name = name if name is not None else fn.__name__
    doc = inspect.getdoc(fn) or ""
    description = doc.split("\n")[0].strip() or f"Tool: {tool_name}"
    schema = _signature_to_jsonschema(fn)
    # domain 판정 — fn 의 module path 로.
    mod = getattr(fn, "__module__", "") or ""
    if mod.startswith("autograph"):
        domain = "auto"
    elif mod.startswith("autonexusgraph"):
        domain = "finance"
    else:
        domain = "other"
    return ToolSpec(name=tool_name, description=description,
                    fn=fn, domain=domain, input_schema=schema)


def build_tool_manifest(domain: str = "all") -> list[ToolSpec]:
    """domain ('auto' | 'finance' | 'all') 별 ToolSpec 목록.

    각 모듈의 ``__all__`` 을 우선 적용. 없으면 module dict 의 non-underscore
    public callable 만.
    """
    domain = (domain or "all").lower()
    if domain == "all":
        modules = _DOMAIN_MODULES["finance"] + _DOMAIN_MODULES["auto"]
    elif domain in _DOMAIN_MODULES:
        modules = _DOMAIN_MODULES[domain]
    else:
        raise ValueError(f"unknown domain: {domain!r} (auto|finance|all)")

    specs: list[ToolSpec] = []
    seen_names: set[str] = set()
    for mod_path in modules:
        try:
            mod = __import__(mod_path, fromlist=["__all__"])
        except ImportError:
            continue
        exported: list[str] = list(getattr(mod, "__all__", None) or
                                    [n for n in dir(mod) if not n.startswith("_")])
        for name in exported:
            if name in seen_names:
                continue
            fn = getattr(mod, name, None)
            if not callable(fn) or inspect.isclass(fn):
                continue
            try:
                # module export name 보존 — alias (예: lookup_vehicle_graph) 도
                # 분리된 tool 이 되도록.
                spec = tool_function(fn, name=name)
            except Exception:   # noqa: BLE001
                # type hint 추출 실패 — skip.
                continue
            specs.append(spec)
            seen_names.add(name)
    return specs


# ── 내부: signature → JSON Schema ─────────────────────────────────
_PRIMITIVE_TYPES = {
    int:   {"type": "integer"},
    float: {"type": "number"},
    str:   {"type": "string"},
    bool:  {"type": "boolean"},
    bytes: {"type": "string", "format": "binary"},
}


def _signature_to_jsonschema(fn: Callable[..., Any]) -> dict[str, Any]:
    """함수 시그니처 → JSON Schema (MCP Tool.inputSchema 호환).

    제한:
    - 단순 타입 (int/float/str/bool) + Optional + List/Dict 기본만 처리.
    - 복잡 타입 (TypeAlias / TypedDict / 사용자 클래스) 는 ``{"type": "string"}`` fallback.
    """
    try:
        hints = get_type_hints(fn)
    except Exception:   # noqa: BLE001
        hints = {}
    sig = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL,
                          inspect.Parameter.VAR_KEYWORD):
            continue
        ann = hints.get(pname, param.annotation)
        properties[pname] = _annotation_to_schema(ann)
        if param.default is inspect.Parameter.empty:
            required.append(pname)
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def _annotation_to_schema(ann: Any) -> dict[str, Any]:
    """type annotation → JSON Schema fragment. Optional / list / dict 처리."""
    import types
    import typing
    if ann is inspect.Parameter.empty or ann is None or ann is type(None):
        return {"type": "string"}
    if ann in _PRIMITIVE_TYPES:
        return dict(_PRIMITIVE_TYPES[ann])
    origin = typing.get_origin(ann)
    args = typing.get_args(ann)
    # Optional[X] / Union[X, None] → X 의 schema (nullable 표기).
    # PEP 604 (``X | None``) 의 origin 은 ``types.UnionType`` — 본 코드베이스가
    # 광범위하게 쓰는 문법이므로 typing.Union 과 함께 처리해야 fallback 으로 안 샌다.
    if origin is typing.Union or origin is types.UnionType:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            base = _annotation_to_schema(non_none[0])
            return base   # JSON Schema 의 nullable 은 OpenAPI extension — 단순화.
        return {"anyOf": [_annotation_to_schema(a) for a in non_none]}
    # list[X] / List[X]
    if origin in (list, tuple):
        item = _annotation_to_schema(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": item}
    # dict[K, V]
    if origin is dict:
        return {"type": "object"}
    # fallback
    return {"type": "string"}


__all__ = [
    "ToolSpec",
    "build_tool_manifest",
    "tool_function",
]
