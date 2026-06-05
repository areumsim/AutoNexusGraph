"""IPGraph pgvector 의미 검색 — 특허 abstract+claims 청크.

명세 = docs/ipgraph.md §4. autograph 의 retrieve 패턴과 동일 (rerank flag 1급).

anxg_vec.chunks 에서 ``source IN ('uspto_odp', 'kipris', 'openalex')`` 필터.
"""

from __future__ import annotations

import logging
from typing import Any

from autonexusgraph.db.postgres import get_pool
from autonexusgraph.tools._vector_search import vector_search
from common.retrieve_base import DEFAULT_TOPK

log = logging.getLogger(__name__)


# 본 도메인의 anxg_vec.chunks source 화이트리스트.
_IP_SOURCES = ("uspto_odp", "kipris", "openalex", "patent_abstract", "patent_claims")


def _build_where(*, assignee_id: str | None = None,
                  cpc: str | None = None,
                  jurisdiction: str | None = None,
                  source: str | list[str] | None = None,
                  require_embedding: bool = True) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    if require_embedding:
        clauses.append("embedding IS NOT NULL")
    # ip 도메인은 별도 metadata column 으로 식별.
    params: dict[str, Any] = {}
    if assignee_id:
        clauses.append("(metadata ->> 'assignee_id') = %(assignee_id)s")
        params["assignee_id"] = assignee_id
    if cpc:
        clauses.append("(metadata ->> 'cpc_code') LIKE %(cpc)s")
        params["cpc"] = f"{cpc}%"
    if jurisdiction:
        clauses.append("(metadata ->> 'jurisdiction') = %(jurisdiction)s")
        params["jurisdiction"] = jurisdiction
    if source is None:
        clauses.append("source = ANY(%(sources)s)")
        params["sources"] = list(_IP_SOURCES)
    elif isinstance(source, str):
        clauses.append("source = %(source)s")
        params["source"] = source
    else:
        clauses.append("source = ANY(%(sources)s)")
        params["sources"] = list(source)
    return " AND ".join(clauses), params


def search_patents(query: str, *,
                   top_k: int = DEFAULT_TOPK,
                   assignee_id: str | None = None,
                   cpc: str | None = None,
                   jurisdiction: str | None = None,
                   source: str | list[str] | None = None,
                   rerank: bool = True,
                   rerank_candidate_multiplier: int = 3) -> list[dict]:
    """특허 abstract+claims 의 벡터 의미 검색 + 메타 필터 + (옵션) rerank.

    PRD §10 DoD #17 (d) — rerank ablation 1급. False 시 vector 유사도만.

    ip 도메인 정책 = **fail-soft**: 임베딩/PG/rerank 실패 시 raise 대신 [] 반환(log 동반).
    공통 ``vector_search`` 는 raise 하므로 본 함수가 try 로 흡수.
    """
    where, params = _build_where(
        assignee_id=assignee_id, cpc=cpc, jurisdiction=jurisdiction,
        source=source, require_embedding=True,
    )
    # ef_search=400 — auto 와 동일 (ip 청크도 anxg_vec.chunks 의 소수).
    try:
        return vector_search(
            query=query, where=where, params=params,
            select_columns="id, source, section, chunk_idx, text, token_count, metadata",
            top_k=top_k, rerank=rerank,
            rerank_candidate_multiplier=rerank_candidate_multiplier,
            ef_search=400,
        )
    except Exception as e:   # noqa: BLE001 — ip fail-soft 정책 → [] 반환 (log 동반)
        log.warning("[ip.search_patents] 검색 실패 (fail-soft): %s", e)
        return []


def search_by_metadata_ip(*,
                           assignee_id: str | None = None,
                           cpc: str | None = None,
                           jurisdiction: str | None = None,
                           source: str | list[str] | None = None,
                           limit: int = 50) -> list[dict]:
    """필터만으로 특허 청크 fetch — 벡터 미사용."""
    where, params = _build_where(
        assignee_id=assignee_id, cpc=cpc, jurisdiction=jurisdiction,
        source=source, require_embedding=False,
    )
    if not where:
        where = "TRUE"
    params["limit"] = max(1, min(int(limit), 500))
    sql = f"""
    SELECT id, source, section, chunk_idx, text, token_count, metadata
      FROM anxg_vec.chunks
     WHERE {where}
     ORDER BY chunk_idx
     LIMIT %(limit)s
    """
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:   # noqa: BLE001 — [retrieve] fail-soft 흡수 → [] 반환 (log 동반)
        log.warning("[ip.search_by_metadata_ip] PG 실패: %s", e)
        return []


def get_chunk_ip(chunk_id: int) -> dict | None:
    """단일 청크 — 원문 + metadata."""
    sql = """
    SELECT id, source, section, chunk_idx, text, token_count, metadata
      FROM anxg_vec.chunks
     WHERE id = %s
       AND source = ANY(%s)
    """
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (int(chunk_id), list(_IP_SOURCES)))
            row = cur.fetchone()
            if not row:
                return None
            cols = [d.name for d in cur.description]
            return dict(zip(cols, row))
    except Exception as e:   # noqa: BLE001 — [retrieve] fail-soft 흡수 → None 반환 (log 동반)
        log.warning("[ip.get_chunk_ip] PG 실패: %s", e)
        return None


__all__ = [
    "search_patents",
    "search_by_metadata_ip",
    "get_chunk_ip",
]
