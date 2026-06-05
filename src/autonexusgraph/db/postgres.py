"""PostgreSQL 연결 헬퍼.

PRD §4.3 — PostgreSQL은 정확한 수치(재무) 저장소 + LangGraph 체크포인트.
psycopg3 사용 (psycopg[binary,pool]).

용도별 4가지:
- get_connection(): 단순 1-회 연결 (스크립트 / ping)
- get_pool(): 동시성 필요 시 (API/agent)
- transaction(): with 블록 context manager
- copy_from(): 대량 적재용 (loaders 가 사용)

**싱글톤 컨벤션**: `get_connection()` 과 `get_pool()` 둘 다 @lru_cache 로 프로세스 1개
재사용. 호출자는 `conn.close()` / `pool.close()` 호출 금지 (다음 호출자가 closed
인스턴스 받아 깨짐). 정리는 `close()` 가 `cache_clear()` 와 함께 일괄 처리. 손상된
인스턴스는 게이트 함수의 health check 가 자동 폐기·재생성.
"""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Iterator

from ..config import get_settings


@lru_cache(maxsize=1)
def _open_connection() -> Any:
    """psycopg.Connection 싱글톤 raw 생성. 호출자는 `get_connection()` 사용 (health check 우회 금지)."""
    import psycopg
    s = get_settings()
    return psycopg.connect(s.postgres_dsn)


def get_connection() -> Any:
    """psycopg.Connection 싱글톤 — 단순 작업용. **호출자 close() 금지**.

    psycopg 패키지가 설치되어 있어야 한다 (pip install '.[db]').

    Health check: cache 에 들어있는 conn 이 닫혔거나 끊겼으면(이전 호출자의
    fail-soft 후 손상 / 서버 disconnect) 자동으로 폐기·재생성. 호출자는 항상
    유효한 conn 을 받는다. lru_cache stale entry 방지의 핵심 게이트.
    """
    conn = _open_connection()
    if getattr(conn, "closed", False) or getattr(conn, "broken", False):
        # 손상된 cache entry 자동 폐기 — 다음 호출 (재귀 1단계) 가 새 conn 생성.
        _open_connection.cache_clear()
        conn = _open_connection()
    return conn


@lru_cache(maxsize=1)
def _open_pool():
    """ConnectionPool 싱글톤 raw 생성. 호출자는 `get_pool()` 사용 (health check 우회 금지)."""
    from psycopg_pool import ConnectionPool
    s = get_settings()
    return ConnectionPool(s.postgres_dsn, min_size=2, max_size=10, open=True)


def get_pool():
    """ConnectionPool 싱글톤 — 동시성 필요 시 (FastAPI, agent). **호출자 close() 금지**.

    Health check: pool 이 닫혔으면 (외부에서 close 됐거나 cache 가 stale)
    자동으로 폐기·재생성. 개별 connection 손상은 pool 내부가 처리 (re-connect).
    `get_connection()` 의 health check 와 대칭 — singleton + lru_cache 패턴 일관.
    """
    pool = _open_pool()
    if getattr(pool, "closed", False):
        _open_pool.cache_clear()
        pool = _open_pool()
    return pool


def ping() -> bool:
    """연결 헬스체크."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone()[0] == 1
    except Exception:   # noqa: BLE001 — PG 미가용 흡수 → False (헬스체크)
        return False


@contextmanager
def transaction() -> Iterator[Any]:
    """싱글톤 connection 의 트랜잭션. with 블록 종료 시 commit/rollback.

    사용:
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(...)

    rollback 실패 (conn 손상) 시 cache 무효화 — 다음 호출자가 새 conn 받음.
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:   # noqa: BLE001 — 트랜잭션 실패 boundary → rollback 시도 후 raise (silent 아님)
        try:
            conn.rollback()
        except Exception:   # noqa: BLE001 — rollback 실패 = conn 손상 → cache 폐기
            _open_connection.cache_clear()
        raise


def close() -> None:
    """싱글톤 정리 (테스트 cleanup)."""
    if _open_connection.cache_info().currsize > 0:
        try:
            _open_connection().close()
        except Exception:   # noqa: BLE001 — 이미 손상된 conn close 실패 흡수
            pass
        _open_connection.cache_clear()
    if _open_pool.cache_info().currsize > 0:
        try:
            _open_pool().close()
        except Exception:   # noqa: BLE001 — 이미 손상된 pool close 실패 흡수
            pass
        _open_pool.cache_clear()
