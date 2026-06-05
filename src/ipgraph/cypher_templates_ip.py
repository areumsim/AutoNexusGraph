"""IPGraph 전용 Cypher 템플릿 — finance/auto 의 ``TEMPLATES`` 와 동일 스키마.

자유 Cypher 금지. 본 모듈 export 인 ``IP_TEMPLATES`` 는 finance 의
``autonexusgraph.tools.cypher_templates.TEMPLATES`` 에 import 시점에 병합됨.

키 접두사: ``ip_*`` — finance/auto 키와 충돌 회피.
모든 쿼리 READ-ONLY (CREATE/MERGE/DELETE 금지).

라벨 매핑 (docs/ipgraph.md §2):
    Patent / Assignee / Inventor / CPCCode / Work / Institution / TechField

cap 강제 — get_citation_network 가 depth ≤ 2 + max_total ≤ 1000.
"""

from __future__ import annotations

# 공용 LIMIT/YEAR 상수는 core SSOT (autonexusgraph.tools.cypher_templates) 에서 import.
from autonexusgraph.tools.cypher_templates import (
    LIMIT_50 as _LIMIT_50,
    LIMIT_100 as _LIMIT_100,
    LIMIT_500 as _LIMIT_500,
    YEAR_RANGE as _YEAR,
)

# ip 전용 — topk 는 _LIMIT_50 alias, depth 는 citation 그래프 폭발 cap.
_LIMIT_TOPK = _LIMIT_50
_DEPTH_2    = (int, ("range", 1, 2))


IP_TEMPLATES: dict[str, dict] = {
    # ── 식별 / lookup (5개) ─────────────────────────────────────
    "ip_lookup_patent": {
        "cypher": """
        MATCH (p:Anxg_Patent)
        WHERE p.pub_no = $q OR p.title CONTAINS $q OR p.abstract CONTAINS $q
        RETURN p.pub_no AS pub_no,
               p.title AS title,
               p.filing_date AS filing_date,
               p.grant_date AS grant_date,
               p.jurisdiction AS jurisdiction,
               p.kind AS kind
        ORDER BY p.filing_date DESC
        LIMIT $limit
        """,
        "required_params": ["q", "limit"],
        "param_schema": {"q": (str, None), "limit": _LIMIT_500},
    },

    "ip_lookup_assignee": {
        "cypher": """
        MATCH (a:Anxg_Assignee)
        WHERE a.name = $q OR a.name CONTAINS $q OR a.name_norm CONTAINS $q
        RETURN a.assignee_id AS assignee_id,
               a.name AS name,
               a.country AS country,
               a.type AS type,
               a.wikidata_qid AS wikidata_qid
        ORDER BY a.name
        LIMIT $limit
        """,
        "required_params": ["q", "limit"],
        "param_schema": {"q": (str, None), "limit": _LIMIT_100},
    },

    "ip_lookup_cpc": {
        "cypher": """
        MATCH (c:Anxg_CPCCode)
        WHERE c.code = $code OR c.title CONTAINS $code
        RETURN c.code AS code,
               c.level AS level,
               c.title AS title,
               c.parent_code AS parent_code
        ORDER BY c.code
        LIMIT $limit
        """,
        "required_params": ["code", "limit"],
        "param_schema": {"code": (str, None), "limit": _LIMIT_100},
    },

    "ip_get_patent_info": {
        "cypher": """
        MATCH (p:Anxg_Patent {pub_no: $pub_no})
        OPTIONAL MATCH (p)-[:ASSIGNED_TO]->(a:Anxg_Assignee)
        OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(c:Anxg_CPCCode)
        OPTIONAL MATCH (i:Anxg_Inventor)-[:INVENTED]->(p)
        RETURN p, collect(DISTINCT a) AS assignees,
               collect(DISTINCT c.code) AS cpc_codes,
               collect(DISTINCT i.name) AS inventors
        LIMIT 1
        """,
        "required_params": ["pub_no"],
        "param_schema": {"pub_no": (str, None)},
    },

    "ip_get_inventors_of_patent": {
        "cypher": """
        MATCH (i:Anxg_Inventor)-[:INVENTED]->(p:Anxg_Patent {pub_no: $pub_no})
        RETURN i.inventor_id AS inventor_id,
               i.name AS name,
               i.country AS country
        ORDER BY i.name
        LIMIT $limit
        """,
        "required_params": ["pub_no", "limit"],
        "param_schema": {"pub_no": (str, None), "limit": _LIMIT_100},
    },

    # ── Assignee 측 (6개) ───────────────────────────────────────
    "ip_list_patents_of_assignee": {
        "cypher": """
        MATCH (p:Anxg_Patent)-[:ASSIGNED_TO]->(a:Anxg_Assignee {assignee_id: $assignee_id})
        RETURN p.pub_no AS pub_no,
               p.title AS title,
               p.filing_date AS filing_date,
               p.jurisdiction AS jurisdiction
        ORDER BY p.filing_date DESC
        LIMIT $limit
        """,
        "required_params": ["assignee_id", "limit"],
        "param_schema": {"assignee_id": (str, None), "limit": _LIMIT_500},
    },

    "ip_assignee_patents_by_cpc": {
        "cypher": """
        MATCH (p:Anxg_Patent)-[:ASSIGNED_TO]->(a:Anxg_Assignee {assignee_id: $assignee_id})
        MATCH (p)-[:CLASSIFIED_AS]->(c:Anxg_CPCCode)
        WHERE c.code = $cpc_code OR c.code STARTS WITH $cpc_code
        RETURN p.pub_no AS pub_no,
               p.title AS title,
               p.filing_date AS filing_date,
               collect(DISTINCT c.code) AS cpc_codes
        ORDER BY p.filing_date DESC
        LIMIT $limit
        """,
        "required_params": ["assignee_id", "cpc_code", "limit"],
        "param_schema": {
            "assignee_id": (str, None),
            "cpc_code": (str, None),
            "limit": _LIMIT_500,
        },
    },

    "ip_assignee_filing_year_counts": {
        "cypher": """
        MATCH (p:Anxg_Patent)-[:ASSIGNED_TO]->(a:Anxg_Assignee {assignee_id: $assignee_id})
        WHERE p.filing_date IS NOT NULL
        WITH date(p.filing_date).year AS yr, count(p) AS n
        WHERE yr >= $year_from AND yr <= $year_to
        RETURN yr AS filing_year, n
        ORDER BY filing_year DESC
        LIMIT 50
        """,
        "required_params": ["assignee_id", "year_from", "year_to"],
        "param_schema": {
            "assignee_id": (str, None),
            "year_from": _YEAR,
            "year_to": _YEAR,
        },
    },

    "ip_find_co_assignees": {
        "cypher": """
        MATCH (p:Anxg_Patent)-[:ASSIGNED_TO]->(a1:Anxg_Assignee {assignee_id: $assignee_id})
        MATCH (p)-[:ASSIGNED_TO]->(a2:Anxg_Assignee)
        WHERE a2.assignee_id <> $assignee_id
        WITH a2, count(p) AS n_shared
        RETURN a2.assignee_id AS assignee_id,
               a2.name AS name,
               a2.country AS country,
               n_shared
        ORDER BY n_shared DESC
        LIMIT $limit
        """,
        "required_params": ["assignee_id", "limit"],
        "param_schema": {"assignee_id": (str, None), "limit": _LIMIT_100},
    },

    "ip_compare_assignees_volume": {
        "cypher": """
        MATCH (p:Anxg_Patent)-[:ASSIGNED_TO]->(a:Anxg_Assignee)
        WHERE a.assignee_id IN $assignee_ids
          AND p.filing_date IS NOT NULL
          AND date(p.filing_date).year = $year
        RETURN a.assignee_id AS assignee_id,
               a.name AS name,
               count(p) AS n_patents
        ORDER BY n_patents DESC
        """,
        "required_params": ["assignee_ids", "year"],
        "param_schema": {
            "assignee_ids": (list, ("len_range", 1, 20)),
            "year": _YEAR,
        },
    },

    "ip_count_patents_by_field": {
        "cypher": """
        MATCH (p:Anxg_Patent)-[:ASSIGNED_TO]->(a:Anxg_Assignee {assignee_id: $assignee_id})
        MATCH (p)-[:CLASSIFIED_AS]->(c:Anxg_CPCCode)
        WHERE c.code STARTS WITH $cpc_section
        RETURN c.code AS cpc_code, count(p) AS n_patents
        ORDER BY n_patents DESC
        LIMIT $limit
        """,
        "required_params": ["assignee_id", "cpc_section", "limit"],
        "param_schema": {
            "assignee_id": (str, None),
            "cpc_section": (str, None),
            "limit": _LIMIT_100,
        },
    },

    # ── CPC 측 (6개) ────────────────────────────────────────────
    "ip_list_patents_in_cpc": {
        "cypher": """
        MATCH (p:Anxg_Patent)-[:CLASSIFIED_AS]->(c:Anxg_CPCCode)
        WHERE c.code = $cpc_code
        RETURN p.pub_no AS pub_no,
               p.title AS title,
               p.filing_date AS filing_date
        ORDER BY p.filing_date DESC
        LIMIT $limit
        """,
        "required_params": ["cpc_code", "limit"],
        "param_schema": {"cpc_code": (str, None), "limit": _LIMIT_500},
    },

    "ip_list_patents_in_cpc_recursive": {
        # include_subclasses=True 일 때 SUBCLASS_OF 트리 따라 자식 CPC 도 매칭.
        # depth ≤ 4 cap.
        "cypher": """
        MATCH (root:Anxg_CPCCode {code: $cpc_code})
        MATCH (c:Anxg_CPCCode)-[:SUBCLASS_OF*0..4]->(root)
        MATCH (p:Anxg_Patent)-[:CLASSIFIED_AS]->(c)
        RETURN p.pub_no AS pub_no,
               p.title AS title,
               p.filing_date AS filing_date,
               c.code AS cpc_code
        ORDER BY p.filing_date DESC
        LIMIT $limit
        """,
        "required_params": ["cpc_code", "limit"],
        "param_schema": {"cpc_code": (str, None), "limit": _LIMIT_500},
    },

    "ip_cpc_descendants": {
        # 본 CPC 의 모든 자식 (depth ≤ 4).
        "cypher": """
        MATCH (root:Anxg_CPCCode {code: $cpc_code})
        MATCH (c:Anxg_CPCCode)-[:SUBCLASS_OF*1..4]->(root)
        RETURN c.code AS code,
               c.level AS level,
               c.title AS title
        ORDER BY c.code
        LIMIT $limit
        """,
        "required_params": ["cpc_code", "limit"],
        "param_schema": {"cpc_code": (str, None), "limit": _LIMIT_500},
    },

    "ip_list_assignees_in_field": {
        "cypher": """
        MATCH (p:Anxg_Patent)-[:CLASSIFIED_AS]->(c:Anxg_CPCCode)
        WHERE c.code = $cpc_code OR c.code STARTS WITH $cpc_code
        MATCH (p)-[:ASSIGNED_TO]->(a:Anxg_Assignee)
        WITH a, count(DISTINCT p) AS n_patents
        RETURN a.assignee_id AS assignee_id,
               a.name AS name,
               a.country AS country,
               n_patents
        ORDER BY n_patents DESC
        LIMIT $top_k
        """,
        "required_params": ["cpc_code", "top_k"],
        "param_schema": {"cpc_code": (str, None), "top_k": _LIMIT_TOPK},
    },

    "ip_cpc_parent_chain": {
        "cypher": """
        MATCH (c:Anxg_CPCCode {code: $cpc_code})
        OPTIONAL MATCH path = (c)-[:SUBCLASS_OF*1..6]->(root:Anxg_CPCCode)
        WHERE NOT (root)-[:SUBCLASS_OF]->()
        RETURN [n IN nodes(path) | {code: n.code, level: n.level, title: n.title}] AS chain
        LIMIT 1
        """,
        "required_params": ["cpc_code"],
        "param_schema": {"cpc_code": (str, None)},
    },

    "ip_cpc_top_fields_of_assignee": {
        "cypher": """
        MATCH (p:Anxg_Patent)-[:ASSIGNED_TO]->(a:Anxg_Assignee {assignee_id: $assignee_id})
        MATCH (p)-[:CLASSIFIED_AS]->(c:Anxg_CPCCode)
        WITH c, count(p) AS n
        RETURN c.code AS cpc_code,
               c.title AS title,
               n AS n_patents
        ORDER BY n DESC
        LIMIT $top_k
        """,
        "required_params": ["assignee_id", "top_k"],
        "param_schema": {"assignee_id": (str, None), "top_k": _LIMIT_TOPK},
    },

    # ── Citation 측 (4개) — depth ≤ 2, max_total ≤ 1000 cap ─────
    "ip_citation_network_d1": {
        "cypher": """
        MATCH (p:Anxg_Patent {pub_no: $pub_no})
        OPTIONAL MATCH (p)-[:CITES]->(cited:Anxg_Patent)
        OPTIONAL MATCH (citing:Anxg_Patent)-[:CITES]->(p)
        WITH p, collect(DISTINCT cited)[..$limit_each] AS cited_list,
                collect(DISTINCT citing)[..$limit_each] AS citing_list
        RETURN p.pub_no AS center,
               [c IN cited_list | {pub_no: c.pub_no, title: c.title}] AS cited,
               [c IN citing_list | {pub_no: c.pub_no, title: c.title}] AS citing
        LIMIT 1
        """,
        "required_params": ["pub_no", "limit_each"],
        "param_schema": {"pub_no": (str, None), "limit_each": _LIMIT_500},
    },

    "ip_citation_network_d2": {
        # depth ≤ 2 cap. max_total 후처리 (코드 level) 로 추가 cap.
        "cypher": """
        MATCH (p:Anxg_Patent {pub_no: $pub_no})
        OPTIONAL MATCH (p)-[:CITES*1..2]->(n1:Anxg_Patent)
        OPTIONAL MATCH (n2:Anxg_Patent)-[:CITES*1..2]->(p)
        WITH p,
             collect(DISTINCT n1)[..$max_per_side] AS cited_list,
             collect(DISTINCT n2)[..$max_per_side] AS citing_list
        RETURN p.pub_no AS center,
               [c IN cited_list | {pub_no: c.pub_no, title: c.title}] AS cited,
               [c IN citing_list | {pub_no: c.pub_no, title: c.title}] AS citing
        LIMIT 1
        """,
        "required_params": ["pub_no", "max_per_side"],
        "param_schema": {"pub_no": (str, None), "max_per_side": _LIMIT_500},
    },

    "ip_most_cited_patents": {
        "cypher": """
        MATCH (citing:Anxg_Patent)-[:CITES]->(p:Anxg_Patent)-[:ASSIGNED_TO]->(a:Anxg_Assignee {assignee_id: $assignee_id})
        WITH p, count(citing) AS n_citations
        RETURN p.pub_no AS pub_no,
               p.title AS title,
               p.filing_date AS filing_date,
               n_citations
        ORDER BY n_citations DESC
        LIMIT $top_k
        """,
        "required_params": ["assignee_id", "top_k"],
        "param_schema": {"assignee_id": (str, None), "top_k": _LIMIT_TOPK},
    },

    "ip_most_cited_in_cpc": {
        "cypher": """
        MATCH (citing:Anxg_Patent)-[:CITES]->(p:Anxg_Patent)-[:CLASSIFIED_AS]->(c:Anxg_CPCCode)
        WHERE c.code = $cpc_code OR c.code STARTS WITH $cpc_code
        WITH p, count(citing) AS n_citations
        RETURN p.pub_no AS pub_no,
               p.title AS title,
               n_citations
        ORDER BY n_citations DESC
        LIMIT $top_k
        """,
        "required_params": ["cpc_code", "top_k"],
        "param_schema": {"cpc_code": (str, None), "top_k": _LIMIT_TOPK},
    },

    # ── Cross-Domain (4개) — IP ↔ finance / auto ─────────────────
    "ip_cross_assignee_corp": {
        # anxg_ip.assignee_corp_map join via finance corp.
        "cypher": """
        MATCH (a:Anxg_Assignee {assignee_id: $assignee_id})
        OPTIONAL MATCH (a)-[:MAPPED_TO]->(c:Anxg_Company)
        RETURN a.assignee_id AS assignee_id,
               a.name AS assignee_name,
               c.corp_code AS corp_code,
               c.name AS corp_name
        LIMIT 1
        """,
        "required_params": ["assignee_id"],
        "param_schema": {"assignee_id": (str, None)},
    },

    "ip_cross_corp_to_patents": {
        # Company → MAPPED_TO Assignee → ASSIGNED_TO Patent (finance ↔ ip).
        "cypher": """
        MATCH (c:Anxg_Company {corp_code: $corp_code})
        OPTIONAL MATCH (c)<-[:MAPPED_TO]-(a:Anxg_Assignee)
        OPTIONAL MATCH (p:Anxg_Patent)-[:ASSIGNED_TO]->(a)
        WHERE p.filing_date IS NOT NULL
          AND date(p.filing_date).year >= $year_from
          AND date(p.filing_date).year <= $year_to
        WITH c, count(DISTINCT p) AS n_patents
        RETURN c.corp_code AS corp_code,
               c.name AS corp_name,
               n_patents
        LIMIT 1
        """,
        "required_params": ["corp_code", "year_from", "year_to"],
        "param_schema": {
            "corp_code": (str, None),
            "year_from": _YEAR,
            "year_to": _YEAR,
        },
    },

    "ip_cross_assignee_top_cpc_year": {
        # CD-L4 핵심 — 삼성SDI 의 H01M 특허 연도별 분포.
        "cypher": """
        MATCH (p:Anxg_Patent)-[:ASSIGNED_TO]->(a:Anxg_Assignee {assignee_id: $assignee_id})
        MATCH (p)-[:CLASSIFIED_AS]->(c:Anxg_CPCCode)
        WHERE (c.code = $cpc_code OR c.code STARTS WITH $cpc_code)
          AND p.filing_date IS NOT NULL
        WITH date(p.filing_date).year AS yr, count(DISTINCT p) AS n
        RETURN yr AS filing_year, n
        ORDER BY filing_year DESC
        LIMIT 30
        """,
        "required_params": ["assignee_id", "cpc_code"],
        "param_schema": {"assignee_id": (str, None), "cpc_code": (str, None)},
    },

    "ip_cross_oem_recall_via_supplier_patent": {
        # CD-L4+ — Patent (assignee) → Company (corp) → 공급사·OEM·리콜.
        # 본 템플릿은 ip 쪽만 — finance/auto bridge 는 별도 tool 호출.
        "cypher": """
        MATCH (a:Anxg_Assignee {assignee_id: $assignee_id})
        OPTIONAL MATCH (a)-[:MAPPED_TO]->(c:Anxg_Company)
        OPTIONAL MATCH (s:Anxg_Supplier {corp_code: c.corp_code})
        OPTIONAL MATCH (s)<-[:SUPPLIED_BY]-(comp)
        RETURN a.assignee_id AS assignee_id,
               c.corp_code AS corp_code,
               s.entity_id AS supplier_id,
               count(DISTINCT comp) AS n_components
        LIMIT 1
        """,
        "required_params": ["assignee_id"],
        "param_schema": {"assignee_id": (str, None)},
    },
}


__all__ = ["IP_TEMPLATES"]
