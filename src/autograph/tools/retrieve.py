"""AutoGraph 의미 검색 — pgvector + 자동차 메타 필터.

finance 의 ``autonexusgraph.tools.retrieve.search_documents`` 와 동일 인덱스(anxg_vec.chunks)를 사용하되,
필터 키가 자동차 도메인용 (manufacturer_id / model_id / variant_id) 으로 확장.
"""

from __future__ import annotations

from typing import Any

from autonexusgraph.db.postgres import get_pool
from autonexusgraph.embeddings import EmbeddingError, get_embedding_client
from common.retrieve_base import DEFAULT_TOPK
from common.retrieve_base import cap_topk as _cap

# 자동차 청크의 source 컨벤션 (build_chunks_auto 와 일치).
# 2026-06-01 확장: oem_ir (IR/뉴스룸 본문) + dart_narrative (supplier OEM DART)
AUTO_SOURCES = ("nhtsa_recall", "nhtsa_complaint", "nhtsa_tsb",
                "wikipedia_auto", "oem_ir", "dart_narrative")


def _build_where(*,
                 manufacturer_id: int | list[int] | None,
                 model_id: int | list[int] | None,
                 variant_id: int | list[int] | None,
                 source: str | list[str] | None,
                 require_embedding: bool) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if require_embedding:
        clauses.append("embedding IS NOT NULL")
    # 자동차 도메인 한정 — finance 청크 (corp_code 있고 자동차 메타 없음) 제외.
    # 2026-06-01: oem_ir / dart_narrative 는 manufacturer_id=NULL 이지만
    # metadata->>'oem' 로 자동차 도메인 식별.
    clauses.append(
        "(manufacturer_id IS NOT NULL OR metadata->>'oem' IS NOT NULL)"
    )

    if manufacturer_id is not None:
        if isinstance(manufacturer_id, (list, tuple)):
            clauses.append("manufacturer_id = ANY(%(mfr_ids)s)")
            params["mfr_ids"] = list(manufacturer_id)
        else:
            clauses.append("manufacturer_id = %(mfr_id)s")
            params["mfr_id"] = int(manufacturer_id)
    if model_id is not None:
        if isinstance(model_id, (list, tuple)):
            clauses.append("model_id = ANY(%(model_ids)s)")
            params["model_ids"] = list(model_id)
        else:
            clauses.append("model_id = %(model_id)s")
            params["model_id"] = int(model_id)
    if variant_id is not None:
        if isinstance(variant_id, (list, tuple)):
            clauses.append("variant_id = ANY(%(variant_ids)s)")
            params["variant_ids"] = list(variant_id)
        else:
            clauses.append("variant_id = %(variant_id)s")
            params["variant_id"] = int(variant_id)
    if source is not None:
        if isinstance(source, (list, tuple)):
            clauses.append("source = ANY(%(sources)s)")
            params["sources"] = list(source)
        else:
            clauses.append("source = %(source)s")
            params["source"] = source
    else:
        clauses.append("source = ANY(%(sources)s)")
        params["sources"] = list(AUTO_SOURCES)

    return " AND ".join(clauses), params


def search_documents_auto(query: str, *,
                          top_k: int = DEFAULT_TOPK,
                          manufacturer_id: int | list[int] | None = None,
                          model_id: int | list[int] | None = None,
                          variant_id: int | list[int] | None = None,
                          source: str | list[str] | None = None,
                          rerank: bool = True,
                          rerank_candidate_multiplier: int = 3) -> list[dict]:
    """자동차 청크 의미 검색 + 메타 필터 + (옵션) BGE-Reranker.

    Args:
        rerank: True (기본) 시 vector top_k × multiplier 후보를 BGE-Reranker 재정렬.
            False 시 vector 유사도만. PRD §10 DoD #17 (d) ablation 셀 토글.
    """
    if not query or not query.strip():
        return []

    client = get_embedding_client()
    try:
        qvec = client.embed_one(query)
    except EmbeddingError as e:
        raise RuntimeError(
            f"임베딩 호출 실패. BGE-M3 서버(EMBEDDING_URL) 가동 확인. {e}"
        ) from e

    where, params = _build_where(
        manufacturer_id=manufacturer_id,
        model_id=model_id,
        variant_id=variant_id,
        source=source,
        require_embedding=True,
    )
    params["q"] = qvec
    effective_k = _cap(top_k * rerank_candidate_multiplier if rerank else top_k)
    params["k"] = effective_k
    sql = f"""
    SELECT id, manufacturer_id, model_id, variant_id, source, section,
           chunk_idx, text, token_count, metadata,
           1 - (embedding <=> %(q)s::vector) AS score
      FROM anxg_vec.chunks
     WHERE {where}
     ORDER BY embedding <=> %(q)s::vector
     LIMIT %(k)s
    """
    pool = get_pool()
    from pgvector.psycopg import register_vector
    with pool.connection() as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            # pgvector HNSW 의 ef_search 증가 (기본 40) — auto 청크가 finance 748k
            # 가운데 소수 (16k) 라 기본 ef 로는 source 필터 후 0 rows 발생.
            cur.execute("SET LOCAL hnsw.ef_search = 400")
            cur.execute(sql, params)
            cols = [d.name for d in cur.description]
            hits = [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

    if not rerank or not hits:
        for h in hits[:_cap(top_k)]:
            h["reranked"] = False
        return hits[:_cap(top_k)]

    texts = [(h.get("text") or "") for h in hits]
    try:
        ranked = client.rerank(query, texts, top_k=_cap(top_k))
    except EmbeddingError:
        for h in hits[:_cap(top_k)]:
            h["reranked"] = False
        return hits[:_cap(top_k)]
    out: list[dict] = []
    for r in ranked:
        idx = getattr(r, "index", None)
        if idx is None or idx >= len(hits):
            continue
        row = dict(hits[idx])
        row["score"] = float(getattr(r, "score", row.get("score", 0.0)) or 0.0)
        row["reranked"] = True
        out.append(row)
    return out


def search_by_metadata_auto(*,
                            manufacturer_id: int | None = None,
                            model_id: int | None = None,
                            variant_id: int | None = None,
                            source: str | list[str] | None = None,
                            limit: int = 50) -> list[dict]:
    where, params = _build_where(
        manufacturer_id=manufacturer_id,
        model_id=model_id,
        variant_id=variant_id,
        source=source,
        require_embedding=False,
    )
    params["limit"] = max(1, min(int(limit), 500))
    sql = f"""
    SELECT id, manufacturer_id, model_id, variant_id, source, section,
           chunk_idx, text, token_count, metadata
      FROM anxg_vec.chunks
     WHERE {where}
     ORDER BY id
     LIMIT %(limit)s
    """
    pool = get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]


def get_chunk_auto(chunk_id: int) -> dict | None:
    """단일 자동차 청크 + 메타. finance get_chunk 와 별도 export 로 명시화."""
    sql = """
    SELECT id, manufacturer_id, model_id, variant_id, source, section,
           chunk_idx, text, token_count, metadata
      FROM anxg_vec.chunks
     WHERE id = %s AND manufacturer_id IS NOT NULL
    """
    pool = get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, (chunk_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [d.name for d in cur.description]
        return dict(zip(cols, row, strict=False))


__all__ = [
    "search_documents_auto",
    "search_by_metadata_auto",
    "get_chunk_auto",
]
