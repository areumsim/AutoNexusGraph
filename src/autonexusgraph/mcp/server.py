"""MCP stdio server — PRD §10 DoD #17 (a).

mcp SDK 가 설치된 환경에서만 import 성공. 미설치 시 ``__init__.py`` 의 fail-soft
가 처리.

설치:
    pip install mcp

실행:
    python -m autonexusgraph.mcp        # stdio (Claude Desktop / Cline 호환)
    MCP_DOMAIN=auto python -m autonexusgraph.mcp   # 도메인 한정
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

# import 실패 시 __init__.py 에서 catch.
from mcp.server import Server                        # type: ignore[import-not-found]
from mcp.server.stdio import stdio_server            # type: ignore[import-not-found]
from mcp.types import TextContent, Tool              # type: ignore[import-not-found]

from .discovery import ToolSpec, build_tool_manifest

log = logging.getLogger(__name__)


def build_mcp_server(domain: str = "all") -> tuple[Server, list[ToolSpec]]:
    """auto/finance/all 도구 풀 → MCP Server 인스턴스 + manifest 반환."""
    specs = build_tool_manifest(domain)
    name_to_spec: dict[str, ToolSpec] = {s.name: s for s in specs}

    server: Server = Server("autonexusgraph")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(name=s.name, description=s.description, inputSchema=s.input_schema)
            for s in specs
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        spec = name_to_spec.get(name)
        if spec is None:
            return [TextContent(type="text", text=f"unknown tool: {name}")]
        try:
            result = spec.fn(**(arguments or {}))
        except Exception as exc:   # noqa: BLE001
            return [TextContent(type="text", text=f"error: {exc}")]
        # 결과 정규화 — dict/list/scalar → JSON string.
        try:
            text = json.dumps(result, ensure_ascii=False, default=str, indent=2)
        except Exception:   # noqa: BLE001
            text = str(result)
        return [TextContent(type="text", text=text)]

    return server, specs


def run_stdio_server(domain: str | None = None) -> None:
    """stdio transport 로 서버 부팅 — Claude Desktop / Cline 등이 직접 실행."""
    d = (domain or os.getenv("MCP_DOMAIN") or "all").lower()
    server, specs = build_mcp_server(d)
    log.info("[mcp] booting stdio server — domain=%s tools=%d", d, len(specs))

    async def _serve() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(_serve())


def main() -> None:
    logging.basicConfig(level=os.getenv("MCP_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run_stdio_server()


if __name__ == "__main__":
    main()
