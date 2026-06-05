"""pgvector 의미검색 공통 코어 — 도메인 retrieve.py 의 embed→query→rerank 본문 SSOT.

``common.retrieve_base`` (pure helper, DB·LLM 의존 0) 와 달리 본 모듈은
DB(``get_pool``) + 임베딩(``get_embedding_client``) 에 의존한다. 그래서 core
패키지(autonexusgraph.tools) 에 둔다 — auto/ip 는 이미 ``autonexusgraph.db`` /
``autonexusgraph.embeddings`` 를 import 하므로 일관.

도메인별 **WHERE 절 · SELECT 컬럼 · ef_search** 는 호출자(각 도메인 ``_build_*`` +
``search_documents_*``)가 만들어 넘기고, 공통 plumbing (벡터 임베딩 → pgvector top-k →
BGE-Reranker fail-soft) 만 흡수. → finance/auto(/ip) 3중 복붙 → 1곳.

``ef_search``: HNSW 후보 폭. auto 처럼 도메인 청크가 전체의 소수라 기본 ef(40)로
source 필터 후 0 rows 가 나는 경우 호출자가 명시(예: 400). finance 처럼 다수 도메인은
``None``(미설정 = pg 기본). **도메인 데이터 분포 차이지 버그가 아님** — 파라미터로 노출.
"""

from __future__ import annotations

from typing import Any

from common.retrieve_base import cap_topk as _cap

from ..db.postgres import get_pool
from ..embeddings import EmbeddingError, get_embedding_client


def vector_search(
    *,
    query: str,
    where: str,
    params: dict[str, Any],
    select_columns: str,
    top_k: int,
    rerank: bool,
    rerank_candidate_multiplier: int = 3,
    ef_search: int | None = None,
) -> list[dict]:
    """벡터 유사도 top-k + (옵션) BGE-Reranker. 도메인 무관 공통 본문.

    Args:
        where: 도메인 ``_build_*`` 가 만든 WHERE 절 (``embedding IS NOT NULL`` 포함 가정).
        params: 동 named params. ``q``/``k`` 는 본 함수가 채운다(원본 비파괴 — 복사).
        select_columns: SELECT 컬럼 목록 (score 식 제외 — 본 함수가 append).
        rerank: True 시 top_k×multiplier 후보 → BGE-Reranker 재정렬. 서버 실패 시
            vector 유사도 fallback (fail-soft). PRD §10 DoD #17 (d) ablation 토글.
        ef_search: HNSW ef (None=pg 기본). 도메인 청크 희소 시 호출자가 상향.

    리턴 row: 도메인 SELECT 컬럼 + ``score`` + ``reranked``(bool).
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

    params = dict(params)   # 원본 비파괴 — 호출자 params 재사용 안전
    params["q"] = qvec
    effective_k = _cap(top_k * rerank_candidate_multiplier if rerank else top_k)
    params["k"] = effective_k

    sql = f"""
    SELECT {select_columns},
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
            if ef_search is not None:
                # SET 은 named param 미지원 — int 캐스팅으로 injection 안전.
                cur.execute(f"SET LOCAL hnsw.ef_search = {int(ef_search)}")
            cur.execute(sql, params)
            cols = [d.name for d in cur.description]
            hits = [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

    cap = _cap(top_k)
    # rerank 비활성 / 빈 결과 — vector 유사도 그대로 top_k 잘라 반환.
    if not rerank or not hits:
        for h in hits[:cap]:
            h["reranked"] = False
        return hits[:cap]

    # rerank 활성 — BGE-Reranker. 서버 실패 시 vector fallback (fail-soft).
    texts = [(h.get("text") or "") for h in hits]
    try:
        ranked = client.rerank(query, texts, top_k=cap)
    except EmbeddingError:
        for h in hits[:cap]:
            h["reranked"] = False
        return hits[:cap]
    out: list[dict] = []
    for r in ranked:
        idx = getattr(r, "index", None)
        if idx is None or idx >= len(hits):
            continue
        row = dict(hits[idx])
        row["score"] = float(getattr(r, "score", row.get("score", 0.0)))
        row["reranked"] = True
        out.append(row)
    return out


__all__ = ["vector_search"]
