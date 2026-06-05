"""Neo4j 드라이버 헬퍼.

PRD §4.3 — Neo4j는 관계 중심(자회사/임원/산업) 저장소.
컨테이너 서비스명 `neo4j:7687` 으로 연결, 외부에선 `localhost:7687`.
"""

from __future__ import annotations

from functools import lru_cache

from ..config import get_settings


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
    except Exception:
        return False


def close() -> None:
    """드라이버 종료. 테스트 cleanup 용."""
    if get_driver.cache_info().currsize > 0:
        get_driver().close()
        get_driver.cache_clear()
