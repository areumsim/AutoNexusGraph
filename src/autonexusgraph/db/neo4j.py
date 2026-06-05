"""Neo4j 드라이버 헬퍼.

PRD §4.3 — Neo4j는 관계 중심(자회사/임원/산업) 저장소.
컨테이너 서비스명 `neo4j:7687` 으로 연결, 외부에선 `localhost:7687`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..config import get_settings


def serialize_value(v: Any) -> Any:
    """neo4j.time.* / Duration 등 msgpack 비호환 객체를 ISO string 으로 변환.

    LangGraph checkpointer 가 ``msgpack`` 으로 AgentState 를 직렬화할 때
    ``neo4j.time.Date`` 같은 외부 타입은 'Type is not msgpack serializable: Date'
    로 실패해 함수체인 폴백을 유발한다 (eval matrix 2026-06-05 발견, BACKLOG A-7).
    원시 타입은 그대로, ``isoformat()`` 이 있으면 그것을, 그 외는 ``str()`` 으로 변환.
    """
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, list):
        return [serialize_value(x) for x in v]
    if isinstance(v, dict):
        return {k: serialize_value(x) for k, x in v.items()}
    iso = getattr(v, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:   # noqa: BLE001 — isoformat() 실패 시 str fallback
            pass
    return str(v)


def serialize_record(rec: Any) -> dict:
    """Neo4j ``Record`` → dict + value sanitize. ``_run`` 결과 row 표준 변환."""
    return {k: serialize_value(v) for k, v in dict(rec).items()}


@lru_cache(maxsize=1)
def get_driver():
    """neo4j.Driver 싱글톤. neo4j 패키지가 설치되어 있어야 한다 (pip install '.[db]')."""
    from neo4j import GraphDatabase  # 지연 import — 의존성 미설치 환경에서도 모듈 import 가능

    s = get_settings()
    return GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))


def get_session(**kwargs):
    """namespace 격리 Neo4j 세션. **모든 세션은 이 헬퍼로 열 것** (`get_driver().session()` 직접 호출 금지).

    공유 Neo4j 서버에서 프로젝트별 데이터를 격리하기 위해 `NEO4J_DATABASE` (config
    `neo4j_database`) 로 named database 를 주입한다. 빈 값이면 드라이버 기본 db (community
    단일 db / 로컬 dev) — 기존 동작 보존. Enterprise 공유 서버는 `autonexusgraph` 로 격리.
    (라벨 프리픽스 `Anxg_*` 와 병행해 단일 db community 에서도 격리.)

    호출자가 명시 `database=...` 를 주면 그대로 사용 (테스트에서 override 가능).
    """
    if "database" not in kwargs:
        s = get_settings()
        db = s.neo4j_database or None
        if db:
            kwargs["database"] = db
    return get_driver().session(**kwargs)


def ping() -> bool:
    """연결 헬스체크. 실패 시 False 반환."""
    try:
        with get_session() as session:
            result = session.run("RETURN 1 AS ok")
            return result.single()["ok"] == 1
    except Exception:   # noqa: BLE001 — Neo4j 미가용 흡수 → False (헬스체크)
        return False


def close() -> None:
    """드라이버 종료. 테스트 cleanup 용."""
    if get_driver.cache_info().currsize > 0:
        get_driver().close()
        get_driver.cache_clear()
