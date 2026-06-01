"""python -m autonexusgraph.mcp — stdio MCP 서버 entry point.

mcp SDK 미설치 시 명확한 안내 후 exit 1.
"""

import sys


def main() -> int:
    try:
        from .server import main as _server_main
    except ImportError as e:
        print(f"[mcp] SDK 미설치 — pip install mcp 후 재시도. ({e})", file=sys.stderr)
        return 1
    _server_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
