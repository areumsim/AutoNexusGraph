"""API 인증 + rate limit — O-1 (BACKLOG §5 / README §12.2).

설계 (정직 표기):
- **API key 헤더 인증.** ``X-API-Key: <token>`` 또는 ``Authorization: Bearer <token>``.
- 키 = ``API_KEYS`` env (comma-separated). 항목은 ``token:user_id`` 또는 bare
  ``token`` (bare 면 user_id 는 토큰 SHA-256 앞 12자로 자동 도출 — 토큰 자체를
  DB user_id 로 누설하지 않음).
- **키 미설정 시 open 모드** — dev Quickstart / 내부망 보존. 첫 요청에서 1회
  경고 로그, user_id = ``"anonymous"``. production 은 반드시 ``API_KEYS`` 설정.
- per-identity sliding-window rate limit (인증 시 user_id, open 모드는 client IP).
  ``API_RATE_LIMIT_PER_MIN`` = 0 이면 비활성. **in-memory** — 단일 인스턴스 한정,
  multi-instance 는 reverse proxy / redis 필요 (README §12.3).

본 모듈은 FastAPI ``Depends(authenticate)`` 의존성을 제공한다. 인증 + rate limit
통과 시 caller 의 ``user_id`` (str) 를 반환하고, 실패 시 401 / 429 를 raise 한다.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from ..config import get_settings

log = logging.getLogger(__name__)

ANONYMOUS = "anonymous"

_warned_open = False
_warn_lock = threading.Lock()


def parse_api_keys(raw: str) -> dict[str, str]:
    """``API_KEYS`` 문자열 → ``{token: user_id}`` 매핑.

    항목 형식: ``token:user_id`` (명시) 또는 bare ``token`` (user_id 자동 도출).
    공백·빈 항목은 무시. 멱등 (같은 입력 → 같은 매핑).
    """
    out: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            token, _, user = part.partition(":")
            token, user = token.strip(), user.strip()
            if not token:
                continue
            out[token] = user or _derive_user_id(token)
        else:
            out[part] = _derive_user_id(part)
    return out


def _derive_user_id(token: str) -> str:
    """bare 토큰 → 안정적 user_id (토큰 평문 누설 방지)."""
    return "u_" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def _extract_token(request: Request) -> str | None:
    """``X-API-Key`` 우선, 없으면 ``Authorization: Bearer``."""
    key = request.headers.get("x-api-key")
    if key and key.strip():
        return key.strip()
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        token = auth[7:].strip()
        return token or None
    return None


class RateLimiter:
    """per-identity 분당 sliding-window. ``per_min<=0`` 이면 무제한.

    in-memory (단일 인스턴스). thread-safe — sync 엔드포인트는 threadpool 에서
    동시 실행되므로 Lock 으로 보호.
    """

    def __init__(self, per_min: int) -> None:
        self.per_min = int(per_min)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, identity: str, *, now: float | None = None) -> bool:
        if self.per_min <= 0:
            return True
        now = time.monotonic() if now is None else now
        cutoff = now - 60.0
        with self._lock:
            dq = self._hits[identity]
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self.per_min:
                return False
            dq.append(now)
            return True


# ── 프로세스 단위 상태 (settings 에서 1회 빌드) ──────────────────────
_limiter: RateLimiter | None = None
_limiter_lock = threading.Lock()


def _get_limiter() -> RateLimiter:
    global _limiter
    with _limiter_lock:
        if _limiter is None:
            _limiter = RateLimiter(get_settings().api_rate_limit_per_min)
        return _limiter


def reset_state_for_test() -> None:
    """테스트가 settings 변경 후 호출 — limiter + open 경고 플래그 초기화."""
    global _limiter, _warned_open
    with _limiter_lock:
        _limiter = None
    with _warn_lock:
        _warned_open = False


def _warn_open_mode_once() -> None:
    global _warned_open
    if _warned_open:
        return
    with _warn_lock:
        if _warned_open:
            return
        _warned_open = True
    log.warning(
        "[api.auth] API_KEYS 미설정 — 인증 OPEN 모드 (모든 요청 anonymous 허용). "
        "외부 노출 환경은 반드시 API_KEYS 설정 필요 (README §12.2)."
    )


def authenticate(request: Request) -> str:
    """FastAPI 의존성 — 인증 + rate limit 통과 시 user_id 반환.

    실패: 401 (키 누락/오류) / 429 (rate limit 초과).
    """
    settings = get_settings()
    keys = parse_api_keys(settings.api_keys)

    if not keys:
        _warn_open_mode_once()
        user_id = ANONYMOUS
        identity = request.client.host if request.client else ANONYMOUS
    else:
        token = _extract_token(request)
        if not token or token not in keys:
            raise HTTPException(
                status_code=401,
                detail="invalid or missing API key (send X-API-Key or Authorization: Bearer)",
            )
        user_id = keys[token]
        identity = user_id

    if not _get_limiter().allow(identity):
        raise HTTPException(status_code=429, detail="rate limit exceeded — try again later")

    return user_id


__all__ = [
    "authenticate",
    "parse_api_keys",
    "RateLimiter",
    "reset_state_for_test",
    "ANONYMOUS",
]
