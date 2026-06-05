"""Qdrant 클라이언트 헬퍼.

PRD §4.3 — Qdrant는 의미·서술형 청크 벡터 저장소.
"""

from __future__ import annotations

from functools import lru_cache

from ..config import get_settings


@lru_cache(maxsize=1)
def get_client():
    """QdrantClient 싱글톤. qdrant-client 패키지 필요 (pip install '.[db]')."""
    from qdrant_client import QdrantClient

    s = get_settings()
    if s.qdrant_api_key:
        return QdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key)
    return QdrantClient(url=s.qdrant_url)


def collection_name(base: str = "chunks") -> str:
    """namespace 격리 Qdrant 컬렉션 명. **컬렉션 생성/조회는 이 헬퍼로** (하드코딩 금지).

    공유 Qdrant 서버에서 프로젝트별 컬렉션을 분리한다. config `qdrant_collection`
    (env `QDRANT_COLLECTION`, 기본 `anxg_chunks`) 가 기본 청크 컬렉션. 다른 base 는
    `<app_namespace>_<base>` 로 파생.
    """
    s = get_settings()
    if base == "chunks":
        return s.qdrant_collection
    return f"{s.app_namespace}_{base}"


def ping() -> bool:
    """연결 헬스체크 — 컬렉션 리스트 호출."""
    try:
        client = get_client()
        client.get_collections()
        return True
    except Exception:
        return False
