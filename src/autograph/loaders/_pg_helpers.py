"""PG 로더 공통 헬퍼 — Neo4j 측 `_neo4j_helpers.py` 에 대응하는 PG 측 유틸.

현재 제공:
- ``savepoint_guard`` — row-level SAVEPOINT 보일러플레이트(SAVEPOINT/RELEASE/ROLLBACK)를
  흡수하는 context manager. 다수 로더(master/recall)가 행마다 동일 3줄을 반복하던 것을 대체.

비-제공 (의도적):
- id 발급(``COALESCE/GREATEST(MAX(id))+1``)은 테이블별로 **예약 id-공간이 다르고**
  (manufacturer ≥10^9 scoped / supplier ≥9e6 / manual mfr ≥2e9) SQL 형태(WHERE-range vs
  GREATEST)도 달라, 공통화하면 off-by-one 충돌 위험이 이득을 넘는다 → 각 로더 유지.
- chunk upsert 도 source 별 컬럼·dedup 키가 달라 공통화 보류.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

# SAVEPOINT 이름은 SQL 식별자라 파라미터 바인딩 불가 → f-string 보간.
# 호출부가 항상 리터럴 상수를 넘기지만, 식별자 형식만 허용해 보간 안전성을 강제.
_SAVEPOINT_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@contextmanager
def savepoint_guard(cur: Any, name: str, *,
                    errors: type[BaseException] | tuple[type[BaseException], ...] = Exception
                    ) -> Iterator[None]:
    """row-level SAVEPOINT 가드 — 본문 성공 시 RELEASE, ``errors`` 발생 시 ROLLBACK 후 재-raise.

    기존 로더가 행마다 반복하던::

        cur.execute("SAVEPOINT sp_x")
        try:
            <work>
            cur.execute("RELEASE SAVEPOINT sp_x")
            <성공 카운트>
        except _ROW_LEVEL_ERRORS as e:
            cur.execute("ROLLBACK TO SAVEPOINT sp_x")
            <에러 카운트>

    를 다음으로 대체한다 (SAVEPOINT/RELEASE/ROLLBACK 3줄만 흡수, 동작 동일)::

        try:
            with savepoint_guard(cur, "sp_x", errors=_ROW_LEVEL_ERRORS):
                <work>
            <성공 카운트>
        except _ROW_LEVEL_ERRORS as e:
            <에러 카운트>

    ROLLBACK 후 **재-raise** 하므로 호출부의 except 가 그대로 로깅/카운트/continue 를
    수행 — 제어 흐름 변화 없음. ``errors`` 밖 예외는 RELEASE/ROLLBACK 없이 그대로 전파
    (기존 ``except _ROW_LEVEL_ERRORS`` 가 다른 예외를 잡지 않던 것과 동일).

    Args:
        cur: 열린 psycopg cursor.
        name: SAVEPOINT 이름 (SQL 식별자, 리터럴 권장).
        errors: ROLLBACK 대상 예외 — 사이트별 상이(`_ROW_LEVEL_ERRORS` 또는 `Exception`).
    """
    if not _SAVEPOINT_NAME_RE.match(name):
        raise ValueError(f"invalid savepoint name: {name!r}")
    cur.execute(f"SAVEPOINT {name}")
    try:
        yield
        cur.execute(f"RELEASE SAVEPOINT {name}")
    except errors:
        cur.execute(f"ROLLBACK TO SAVEPOINT {name}")
        raise


__all__ = ["savepoint_guard"]
