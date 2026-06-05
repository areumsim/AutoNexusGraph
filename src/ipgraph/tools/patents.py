"""IPGraph PG 정형 도구 — 특허 식별·출원인·CPC 집계.

자유 SQL 금지. 명세 = docs/ipgraph.md §4.

PG 미가용 환경 (CI / 테스트) 에서 fail-soft — 빈 list 또는 None 반환 + warning.
"""

from __future__ import annotations

import logging
from typing import Any

from autonexusgraph.db.postgres import get_pool

log = logging.getLogger(__name__)


# ── 1. lookup ────────────────────────────────────────────────────
def lookup_patent(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """특허 식별 — pub_no 정확 매칭 또는 title 부분 매칭.

    Args:
        query: 특허번호 또는 제목 키워드
        limit: 결과 행 수 (1~500)
    """
    if not query or not query.strip():
        return []
    limit = max(1, min(int(limit), 500))
    sql = """
    SELECT pub_no, app_no, title, filing_date, grant_date, kind,
           jurisdiction, source
      FROM anxg_ip.patents
     WHERE pub_no = %s OR title ILIKE %s
     ORDER BY filing_date DESC NULLS LAST
     LIMIT %s
    """
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (query, f"%{query}%", limit))
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:   # noqa: BLE001 — fail-soft 흡수 → [] 반환 (log 동반)
        log.warning("[ip.lookup_patent] PG 실패: %s", e)
        return []


def get_patent_info(pub_no: str) -> dict[str, Any] | None:
    """단일 특허 상세 + 출원인·CPC·발명자."""
    if not pub_no:
        return None
    sql = """
    SELECT p.pub_no, p.app_no, p.title, p.abstract, p.filing_date, p.grant_date,
           p.kind, p.jurisdiction, p.source,
           array_agg(DISTINCT a.name) FILTER (WHERE a.name IS NOT NULL) AS assignees,
           array_agg(DISTINCT c.cpc_code) FILTER (WHERE c.cpc_code IS NOT NULL) AS cpc_codes,
           array_agg(DISTINCT i.name) FILTER (WHERE i.name IS NOT NULL) AS inventors
      FROM anxg_ip.patents p
      LEFT JOIN anxg_ip.patent_assignees pa ON pa.pub_no = p.pub_no
      LEFT JOIN anxg_ip.assignees a         ON a.assignee_id = pa.assignee_id
      LEFT JOIN anxg_ip.patent_cpc c        ON c.pub_no = p.pub_no
      LEFT JOIN anxg_ip.patent_inventors pi ON pi.pub_no = p.pub_no
      LEFT JOIN anxg_ip.inventors i         ON i.inventor_id = pi.inventor_id
     WHERE p.pub_no = %s
     GROUP BY p.pub_no
    """
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (pub_no,))
            row = cur.fetchone()
            if not row:
                return None
            cols = [d.name for d in cur.description]
            return dict(zip(cols, row))
    except Exception as e:   # noqa: BLE001 — fail-soft 흡수 → None 반환 (log 동반)
        log.warning("[ip.get_patent_info] PG 실패: %s", e)
        return None


# ── 2. assignee 측 ───────────────────────────────────────────────
def list_patents_by_assignee(assignee_id: str,
                              *,
                              year_range: tuple[int, int] | None = None,
                              cpc: str | None = None,
                              limit: int = 50) -> list[dict[str, Any]]:
    """assignee 의 특허 목록 — 연도 / CPC 필터.

    Args:
        assignee_id: anxg_ip.assignees.assignee_id (USPTO assignee_id 또는 KIPRIS applicantNo)
        year_range: (from, to) inclusive — filing_date 기준
        cpc: CPC 코드 (prefix 매칭)
        limit: 결과 행 수 (1~500)
    """
    if not assignee_id:
        return []
    limit = max(1, min(int(limit), 500))
    params: list[Any] = [assignee_id]
    clauses: list[str] = ["pa.assignee_id = %s"]
    joins: list[str] = []
    if year_range:
        clauses.append("EXTRACT(YEAR FROM p.filing_date) BETWEEN %s AND %s")
        params.extend([year_range[0], year_range[1]])
    if cpc:
        joins.append("JOIN anxg_ip.patent_cpc pc ON pc.pub_no = p.pub_no")
        clauses.append("pc.cpc_code LIKE %s")
        params.append(f"{cpc}%")
    where = " AND ".join(clauses)
    join_sql = "\n".join(joins)
    sql = f"""
    SELECT p.pub_no, p.title, p.filing_date, p.jurisdiction
      FROM anxg_ip.patents p
      JOIN anxg_ip.patent_assignees pa ON pa.pub_no = p.pub_no
      {join_sql}
     WHERE {where}
     ORDER BY p.filing_date DESC NULLS LAST
     LIMIT %s
    """
    params.append(limit)
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:   # noqa: BLE001 — fail-soft 흡수 → [] 반환 (log 동반)
        log.warning("[ip.list_patents_by_assignee] PG 실패: %s", e)
        return []


def count_patents_by_field(assignee_id: str, cpc_section: str,
                            *,
                            year_range: tuple[int, int] | None = None
                            ) -> list[dict[str, Any]]:
    """assignee 가 CPC section 안에서 출원한 특허를 CPC 코드별로 집계."""
    if not assignee_id or not cpc_section:
        return []
    params: list[Any] = [assignee_id, f"{cpc_section}%"]
    extra = ""
    if year_range:
        extra = " AND EXTRACT(YEAR FROM p.filing_date) BETWEEN %s AND %s"
        params.extend([year_range[0], year_range[1]])
    sql = f"""
    SELECT pc.cpc_code, COUNT(p.pub_no) AS n_patents
      FROM anxg_ip.patents p
      JOIN anxg_ip.patent_assignees pa ON pa.pub_no = p.pub_no
      JOIN anxg_ip.patent_cpc pc       ON pc.pub_no = p.pub_no
     WHERE pa.assignee_id = %s
       AND pc.cpc_code LIKE %s
       {extra}
     GROUP BY pc.cpc_code
     ORDER BY n_patents DESC
     LIMIT 100
    """
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:   # noqa: BLE001 — fail-soft 흡수 → [] 반환 (log 동반)
        log.warning("[ip.count_patents_by_field] PG 실패: %s", e)
        return []


def compare_assignees_patent_volume(assignee_ids: list[str], year: int,
                                     *,
                                     cpc: str | None = None
                                     ) -> list[dict[str, Any]]:
    """assignee 간 출원량 비교 — 특정 연도, 선택적 CPC 필터."""
    if not assignee_ids:
        return []
    params: list[Any] = [list(assignee_ids), year]
    cpc_join = ""
    cpc_where = ""
    if cpc:
        cpc_join = "JOIN anxg_ip.patent_cpc pc ON pc.pub_no = p.pub_no"
        cpc_where = "AND pc.cpc_code LIKE %s"
        params.append(f"{cpc}%")
    sql = f"""
    SELECT pa.assignee_id, a.name, COUNT(DISTINCT p.pub_no) AS n_patents
      FROM anxg_ip.patents p
      JOIN anxg_ip.patent_assignees pa ON pa.pub_no = p.pub_no
      JOIN anxg_ip.assignees a         ON a.assignee_id = pa.assignee_id
      {cpc_join}
     WHERE pa.assignee_id = ANY(%s)
       AND EXTRACT(YEAR FROM p.filing_date) = %s
       {cpc_where}
     GROUP BY pa.assignee_id, a.name
     ORDER BY n_patents DESC
    """
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:   # noqa: BLE001 — fail-soft 흡수 → [] 반환 (log 동반)
        log.warning("[ip.compare_assignees_patent_volume] PG 실패: %s", e)
        return []


__all__ = [
    "lookup_patent",
    "get_patent_info",
    "list_patents_by_assignee",
    "count_patents_by_field",
    "compare_assignees_patent_volume",
]
