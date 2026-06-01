"""IPGraph Cross-Domain Bridge — assignee_id ↔ corp_code 매핑.

docs/ipgraph.md §4 — ip.assignee_corp_map join 테이블 활용.
``bridge.corp_entity`` 직접 변경 0 → core 스키마 보존 (§10.12).

Cross-Domain 시연:
- CD-L3: "현대모비스 R&D비 (finance) 대비 ADAS(CPC B60W) 출원 추세 (ip)"
- CD-L4: "삼성SDI 배터리 특허(H01M) + 영업이익 + 그 셀 쓰는 OEM 리콜"
"""

from __future__ import annotations

import logging
from typing import Any

from autonexusgraph.db.postgres import get_pool

log = logging.getLogger(__name__)


def bridge_assignee_to_corp(assignee_id: str) -> dict[str, Any] | None:
    """assignee_id → 매핑된 corp_code (있다면).

    우선순위: reviewed_status='reviewed' AND confidence_score DESC.
    """
    if not assignee_id:
        return None
    sql = """
    SELECT m.assignee_id,
           m.corp_code,
           c.corp_name,
           m.match_type,
           m.confidence_score,
           m.reviewed_status
      FROM ip.assignee_corp_map m
      LEFT JOIN master.companies c ON c.corp_code = m.corp_code
     WHERE m.assignee_id = %s
       AND m.reviewed_status <> 'rejected'
     ORDER BY (m.reviewed_status = 'reviewed') DESC,
              m.confidence_score DESC
     LIMIT 1
    """
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (assignee_id,))
            row = cur.fetchone()
            if not row:
                return None
            cols = [d.name for d in cur.description]
            return dict(zip(cols, row))
    except Exception as e:   # noqa: BLE001
        log.warning("[ip.bridge_assignee_to_corp] PG 실패: %s", e)
        return None


def bridge_corp_to_assignee(corp_code: str,
                             *,
                             include_candidates: bool = False
                             ) -> list[dict[str, Any]]:
    """corp_code → 매핑된 assignee 목록 (다대다 가능).

    Args:
        include_candidates: True 시 'auto'(candidate) 까지. False 시 'reviewed' 만.
    """
    if not corp_code:
        return []
    status_filter = (
        "m.reviewed_status IN ('auto', 'reviewed')"
        if include_candidates
        else "m.reviewed_status = 'reviewed'"
    )
    sql = f"""
    SELECT m.assignee_id,
           a.name AS assignee_name,
           a.country,
           m.match_type,
           m.confidence_score,
           m.reviewed_status
      FROM ip.assignee_corp_map m
      JOIN ip.assignees a ON a.assignee_id = m.assignee_id
     WHERE m.corp_code = %s
       AND {status_filter}
     ORDER BY m.confidence_score DESC
    """
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (corp_code,))
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:   # noqa: BLE001
        log.warning("[ip.bridge_corp_to_assignee] PG 실패: %s", e)
        return []


def cross_query_ip(corp_code: str,
                    *,
                    cpc: str | None = None,
                    year_range: tuple[int, int] | None = None
                    ) -> dict[str, Any]:
    """CD-L3/L4 패키지 쿼리 — 한 줄 호출로 IP ↔ finance 묶음.

    Args:
        corp_code: master.companies.corp_code
        cpc: CPC 코드 (prefix 매칭) — 없으면 전체 분야
        year_range: (from, to) inclusive

    Returns:
        {
            "corp_code", "corp_name",
            "assignees": [{assignee_id, name, n_patents}],
            "total_patents", "n_assignees_matched"
        }
    """
    if not corp_code:
        return {"corp_code": corp_code, "assignees": [],
                "total_patents": 0, "n_assignees_matched": 0}

    assignees = bridge_corp_to_assignee(corp_code, include_candidates=True)
    if not assignees:
        return {"corp_code": corp_code, "assignees": [],
                "total_patents": 0, "n_assignees_matched": 0}

    # 각 assignee 의 특허 수 — list_patents_by_assignee 재사용 대신 단일 SQL.
    assignee_ids = [a["assignee_id"] for a in assignees]
    params: list[Any] = [assignee_ids]
    clauses: list[str] = ["pa.assignee_id = ANY(%s)"]
    if cpc:
        clauses.append("EXISTS (SELECT 1 FROM ip.patent_cpc pc "
                       "WHERE pc.pub_no = p.pub_no AND pc.cpc_code LIKE %s)")
        params.append(f"{cpc}%")
    if year_range:
        clauses.append("EXTRACT(YEAR FROM p.filing_date) BETWEEN %s AND %s")
        params.extend([year_range[0], year_range[1]])
    where = " AND ".join(clauses)
    sql = f"""
    SELECT pa.assignee_id, COUNT(DISTINCT p.pub_no) AS n_patents
      FROM ip.patents p
      JOIN ip.patent_assignees pa ON pa.pub_no = p.pub_no
     WHERE {where}
     GROUP BY pa.assignee_id
    """
    counts: dict[str, int] = {}
    try:
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            for r in cur.fetchall():
                counts[r[0]] = int(r[1])
    except Exception as e:   # noqa: BLE001
        log.warning("[ip.cross_query_ip] PG 실패: %s", e)

    enriched = [
        {**a, "n_patents": counts.get(a["assignee_id"], 0)}
        for a in assignees
    ]
    enriched.sort(key=lambda x: -x["n_patents"])
    total = sum(counts.values())
    return {
        "corp_code":            corp_code,
        "corp_name":            assignees[0].get("assignee_name") if assignees else None,
        "assignees":            enriched,
        "total_patents":        total,
        "n_assignees_matched":  len(assignees),
        "cpc_filter":           cpc,
        "year_range":           list(year_range) if year_range else None,
    }


__all__ = [
    "bridge_assignee_to_corp",
    "bridge_corp_to_assignee",
    "cross_query_ip",
]
