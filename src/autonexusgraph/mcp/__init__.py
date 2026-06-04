"""AutoNexusGraph 의 MCP (Model Context Protocol) 서버 — README §10 DoD #17 (a).

외부 에이전트 (Claude Desktop, Cline, OpenAI Agents SDK) 가 typed tool pool 을
MCP 프로토콜로 호출 가능. domain-agnostic — auto/finance/(ip) 도구 모두 자동 discover.

설계:
- ``build_tool_manifest()`` — Python 함수 → MCP Tool spec (자동 type hint 변환)
- ``mcp`` SDK 미설치 환경 fail-soft. ``audit-mcp`` 가 SKIPPED + exit 0.
- 노출 도구는 결정적(DB/graph/SQL) 조회 — per-call LLM 비용 없음. 외부 MCP 호출은
  ``start_turn_context`` 밖에서 실행되어 활성 turn tracker 가 없다. 만약 어떤 도구가
  내부적으로 LLM 클라이언트를 호출하면 ``get_session_tracker`` 가 그 시점에 lazy 로
  ContextVar tracker 를 생성해 세션 한도 가드가 적용된다 (별도 wrapper 불필요).
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
