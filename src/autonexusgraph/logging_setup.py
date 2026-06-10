"""애플리케이션 로깅 설정 — `settings.log_level` 1곳 적용 SSOT.

문제: `config.py::log_level="INFO"` 설정이 어디에도 **적용되지 않아**, FastAPI/Streamlit
기동 시 root logger 가 기본 WARNING 으로 남는다 → cost_tracker/supervisor/nodes/history 등
모든 `log.info(...)` 가 출력되지 않음 (관측성 무력화).

본 모듈의 `configure_logging()` 을 **장기 실행 진입점**(api/main, ui/app)에서 1회 호출하면
app logger(`autonexusgraph.*` / `autograph.*` / `ipgraph.*`)의 INFO 가 표면화된다.
CLI 스크립트는 자체 `basicConfig` 를 가지므로 호출 대상 아님 (중복 방지).
"""

from __future__ import annotations

import logging

_CONFIGURED = False


def configure_logging(level: str | None = None) -> None:
    """root logger 레벨을 `settings.log_level`(또는 인자) 로 맞춘다. 멱등.

    - root 에 핸들러가 없으면(plain uvicorn/streamlit) `basicConfig` 로 StreamHandler 부착.
    - 이미 핸들러가 있으면(uvicorn 이 자체 구성 등) 레벨만 상향 — app INFO 가 propagate.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    if level is None:
        try:
            from .config import get_settings
            level = get_settings().log_level
        except Exception:   # noqa: BLE001 — 설정 로드 실패 → INFO 기본 (로깅이 본질 막지 않게)
            level = "INFO"
    lvl = str(level or "INFO").upper()

    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=lvl,
            format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        )
    else:
        root.setLevel(lvl)
    _CONFIGURED = True


__all__ = ["configure_logging"]
