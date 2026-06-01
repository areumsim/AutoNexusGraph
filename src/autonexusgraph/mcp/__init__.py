"""AutoNexusGraph 의 MCP (Model Context Protocol) 서버 — PRD §10 DoD #17 (a).

외부 에이전트 (Claude Desktop, Cline, OpenAI Agents SDK) 가 typed tool pool 을
MCP 프로토콜로 호출 가능. domain-agnostic — auto/finance/(ip) 도구 모두 자동 discover.

설계:
- ``build_tool_manifest()`` — Python 함수 → MCP Tool spec (자동 type hint 변환)
- ``mcp`` SDK 미설치 환경 fail-soft. ``audit-mcp`` 가 SKIPPED + exit 0.
- 도구 호출 시 cost_tracker 통합 (외부 에이전트 호출도 비용 가드 적용).
"""

from .discovery import (
    ToolSpec,
    build_tool_manifest,
    tool_function,
)

try:
    from .server import build_mcp_server, run_stdio_server   # type: ignore[attr-defined]
    _HAS_SERVER = True
except ImportError:
    _HAS_SERVER = False
    build_mcp_server = None        # type: ignore[assignment]
    run_stdio_server = None        # type: ignore[assignment]


__all__ = [
    "ToolSpec",
    "build_tool_manifest",
    "tool_function",
    "build_mcp_server",
    "run_stdio_server",
]
