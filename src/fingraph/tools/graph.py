"""Neo4j 그래프 탐색 도구 — 에이전트가 호출하는 사전 정의 함수.

자유 Cypher 금지(PRD §7.5.10). LLM 은 함수명 + 파라미터만 결정.
모든 함수는 dict / list[dict] 반환 → JSON serializable.

설계 원칙:
- 읽기 전용 (Cypher 의 CREATE/MERGE/DELETE 안 씀)
- 명시적 LIMIT — 그래프 폭발 방지
- entity_resolution: corp_code 우선, name 은 보조
- snapshot_year/date 필터 옵션 — 시점별 답변 가능
"""

from __future__ import annotations

from typing import Any

from ..db.neo4j import get_driver


# 그래프 폭발 가드 — 어떤 함수도 이 한도를 넘기지 못함.
DEFAULT_LIMIT = 50
HARD_LIMIT = 500


def _run(cypher: str, **params: Any) -> list[dict]:
    """READ 단일 쿼리 실행 → list[dict] (record.data())."""
    driver = get_driver()
    with driver.session() as session:
        result = session.run(cypher, **params)
        return [dict(r) for r in result]


def _cap(limit: int | None) -> int:
    """limit 정규화. None → DEFAULT, > HARD_LIMIT → HARD_LIMIT."""
    if limit is None or limit <= 0:
        return DEFAULT_LIMIT
    return min(limit, HARD_LIMIT)


# ── 회사 식별 ────────────────────────────────────────────────────────

def lookup_company(query: str, limit: int = 5) -> list[dict]:
    """이름·종목코드·corp_code 로 Neo4j Company 찾기.

    PG tools.financials.lookup_company 의 그래프 버전.
    Wikidata QID / Wikipedia title 도 부가정보로 반환.
    """
    cypher = """
    MATCH (c:Company)
    WHERE c.corp_code = $q
       OR c.stock_code = $q
       OR c.name = $q
       OR c.name CONTAINS $q
    RETURN c.corp_code AS corp_code,
           c.name      AS name,
           c.stock_code AS stock_code,
           c.wikidata_qid AS wikidata_qid,
           c.wikipedia_title_ko AS wikipedia_title_ko
    LIMIT $limit
    """
    return _run(cypher, q=query.strip(), limit=_cap(limit))


def lookup_person(name: str, birth_year: int | None = None,
                  limit: int = 5) -> list[dict]:
    """동명이인 안전 매칭. birth_year 없으면 (name, *) 모두 반환."""
    if birth_year is not None:
        cypher = """
        MATCH (p:Person {name: $name, birth_year: $by})
        OPTIONAL MATCH (p)-[:EXECUTIVE_OF]->(c:Company)
        WITH p, collect(DISTINCT c.name)[..5] AS sample_corps
        RETURN p.name AS name, p.birth_year AS birth_year,
               p.gender AS gender, sample_corps
        LIMIT $limit
        """
        return _run(cypher, name=name, by=birth_year, limit=_cap(limit))
    cypher = """
    MATCH (p:Person {name: $name})
    OPTIONAL MATCH (p)-[:EXECUTIVE_OF]->(c:Company)
    WITH p, collect(DISTINCT c.name)[..5] AS sample_corps
    RETURN p.name AS name, p.birth_year AS birth_year,
           p.gender AS gender, sample_corps
    ORDER BY p.birth_year DESC
    LIMIT $limit
    """
    return _run(cypher, name=name, limit=_cap(limit))


# ── 구조 그래프 탐색 ────────────────────────────────────────────────

def list_subsidiaries(parent_corp_code: str, *,
                      include_related: bool = False,
                      snapshot_year: int | None = None,
                      limit: int = DEFAULT_LIMIT) -> list[dict]:
    """모회사의 자회사 (50%+) — include_related=True 면 관계회사(5~50%) 도.

    snapshot_year 지정 시 그 연도의 보고서 기준 관계만.
    """
    rel = "SUBSIDIARY_OF|RELATED_TO" if include_related else "SUBSIDIARY_OF"
    cypher = f"""
    MATCH (child:Company)-[r:{rel}]->(parent:Company {{corp_code: $cc}})
    WHERE $year IS NULL OR r.rcept_year = $year
    RETURN child.corp_code AS child_corp_code,
           child.name      AS child_name,
           type(r)         AS relation,
           r.ownership_pct AS ownership_pct,
           r.snapshot_date AS snapshot_date
    ORDER BY r.ownership_pct DESC
    LIMIT $limit
    """
    return _run(cypher, cc=parent_corp_code, year=snapshot_year, limit=_cap(limit))


def list_parents(child_corp_code_or_name: str, *,
                 limit: int = DEFAULT_LIMIT) -> list[dict]:
    """이 회사가 자회사로 묶이는 모회사들. corp_code 또는 name 으로 매칭."""
    cypher = """
    MATCH (child:Company)-[r:SUBSIDIARY_OF]->(parent:Company)
    WHERE child.corp_code = $k OR child.name = $k
    RETURN parent.corp_code AS parent_corp_code,
           parent.name      AS parent_name,
           r.ownership_pct  AS ownership_pct,
           r.snapshot_date  AS snapshot_date
    ORDER BY r.snapshot_date DESC
    LIMIT $limit
    """
    return _run(cypher, k=child_corp_code_or_name, limit=_cap(limit))


def get_executives(corp_code: str, *,
                   role_contains: str | None = None,
                   snapshot_year: int | None = None,
                   limit: int = DEFAULT_LIMIT) -> list[dict]:
    """회사의 임원 목록.

    role_contains 는 다음 두 곳에서 substring 매칭:
      - r.role (DART 등기임원 구분: 사내이사/사외이사/감사위원/기타)
      - r.duty (DART 담당업무: '대표이사', '의장', 'CTO' 등 자유 텍스트)

    예: role_contains='대표' → duty 의 '대표이사' 까지 잡힘.
    """
    cypher = """
    MATCH (p:Person)-[r:EXECUTIVE_OF]->(c:Company {corp_code: $cc})
    WHERE ($role IS NULL
           OR r.role CONTAINS $role
           OR (r.duty IS NOT NULL AND r.duty CONTAINS $role))
      AND ($year IS NULL OR r.snapshot_year = $year)
    RETURN p.name        AS name,
           p.birth_year  AS birth_year,
           r.role        AS role,
           r.registered  AS registered,
           r.full_time   AS full_time,
           r.duty        AS duty,
           r.snapshot_year AS snapshot_year
    ORDER BY r.snapshot_year DESC, p.name
    LIMIT $limit
    """
    return _run(cypher, cc=corp_code, role=role_contains,
                year=snapshot_year, limit=_cap(limit))


def get_companies_of_person(name: str, birth_year: int | None = None, *,
                            role_contains: str | None = None,
                            limit: int = DEFAULT_LIMIT) -> list[dict]:
    """이 인물이 임원인 회사 목록 — 멀티 회사 임원 추적."""
    if birth_year is not None:
        match = "MATCH (p:Person {name: $name, birth_year: $by})-[r:EXECUTIVE_OF]->(c:Company)"
        params = {"name": name, "by": birth_year, "role": role_contains, "limit": _cap(limit)}
    else:
        match = "MATCH (p:Person {name: $name})-[r:EXECUTIVE_OF]->(c:Company)"
        params = {"name": name, "role": role_contains, "limit": _cap(limit)}
    cypher = match + """
    WHERE $role IS NULL OR r.role CONTAINS $role
    RETURN c.corp_code AS corp_code,
           c.name      AS company_name,
           r.role      AS role,
           r.snapshot_year AS snapshot_year
    ORDER BY r.snapshot_year DESC
    LIMIT $limit
    """
    return _run(cypher, **params)


def get_major_shareholders(corp_code: str, *,
                           min_pct: float = 0.0,
                           snapshot_year: int | None = None,
                           limit: int = DEFAULT_LIMIT) -> list[dict]:
    """회사의 최대주주(자연인 + 법인) — 지분율 내림차순."""
    cypher = """
    MATCH (h)-[r:MAJOR_SHAREHOLDER_OF]->(c:Company {corp_code: $cc})
    WHERE r.ownership_pct >= $min_pct
      AND ($year IS NULL OR r.snapshot_year = $year)
    RETURN labels(h)[0]   AS holder_kind,
           h.name         AS holder_name,
           h.corp_code    AS holder_corp_code,
           r.ownership_pct AS ownership_pct,
           r.relation     AS relation,
           r.snapshot_year AS snapshot_year
    ORDER BY r.ownership_pct DESC
    LIMIT $limit
    """
    return _run(cypher, cc=corp_code, min_pct=min_pct,
                year=snapshot_year, limit=_cap(limit))


# ── 멀티홉 탐색 ──────────────────────────────────────────────────────

def find_paths(start_corp_code: str, end_corp_code: str,
               max_hops: int = 3) -> list[dict]:
    """두 회사 간 최단 경로 — 자회사·임원·주주 관계 통합 탐색.

    멀티홉 추론의 핵심: "X 와 Y 가 어떻게 연결돼 있나?" 답변.
    """
    hops = max(1, min(int(max_hops), 5))
    cypher = f"""
    MATCH p = shortestPath(
      (a:Company {{corp_code: $a}})-[*1..{hops}]-(b:Company {{corp_code: $b}})
    )
    RETURN [n IN nodes(p) | coalesce(n.name, n.corp_code)] AS node_path,
           [r IN relationships(p) | type(r)] AS rel_types,
           length(p) AS hops
    LIMIT 5
    """
    return _run(cypher, a=start_corp_code, b=end_corp_code)


def get_subgraph(corp_code: str, *,
                 depth: int = 1,
                 limit_nodes: int = 50) -> dict:
    """corp_code 중심 depth 이내 노드/엣지 — UI 시각화 + 컨텍스트 묶음용."""
    depth = max(1, min(int(depth), 3))
    cypher = f"""
    MATCH (center:Company {{corp_code: $cc}})
    CALL apoc.path.subgraphAll(center, {{maxLevel: {depth}, limit: $limit}})
    YIELD nodes, relationships
    RETURN nodes, relationships
    """
    # APOC 미설치 환경 fallback — 단순 1-hop 만.
    try:
        rows = _run(cypher, cc=corp_code, limit=limit_nodes)
        if not rows:
            return {"nodes": [], "edges": []}
        rec = rows[0]
        nodes = [{
            "id": n.element_id, "labels": list(n.labels),
            "name": n.get("name") or n.get("corp_code"),
            "corp_code": n.get("corp_code"),
        } for n in rec["nodes"]]
        edges = [{
            "type": r.type,
            "start": r.start_node.element_id,
            "end": r.end_node.element_id,
            "props": dict(r),
        } for r in rec["relationships"]]
        return {"nodes": nodes, "edges": edges}
    except Exception:
        # APOC 없을 때 폴백
        cypher2 = """
        MATCH (center:Company {corp_code: $cc})
        OPTIONAL MATCH (center)-[r1]-(n1)
        OPTIONAL MATCH (n1)-[r2]-(n2)
          WHERE n2 <> center AND $depth >= 2
        RETURN center, collect(DISTINCT n1)[..$limit] AS depth1,
               collect(DISTINCT n2)[..$limit] AS depth2,
               collect(DISTINCT r1) AS rels1,
               collect(DISTINCT r2) AS rels2
        """
        rows = _run(cypher2, cc=corp_code, depth=depth, limit=limit_nodes)
        return {"raw": rows[0] if rows else {}}


# ── 뉴스 / 그룹 컨텍스트 ────────────────────────────────────────────

def list_mentioning_news(corp_code: str, *,
                         limit: int = DEFAULT_LIMIT) -> list[dict]:
    """뉴스 멘션 — 시점별로 정렬."""
    cypher = """
    MATCH (n:NewsEvent)-[m:MENTIONS]->(c:Company {corp_code: $cc})
    RETURN n.article_hash AS article_hash,
           n.title        AS title,
           n.source       AS source,
           n.published_at AS published_at,
           n.url          AS url,
           m.confidence   AS confidence
    ORDER BY n.published_at DESC
    LIMIT $limit
    """
    return _run(cypher, cc=corp_code, limit=_cap(limit))


def list_cooccurring(corp_code: str, *,
                     min_count: int = 2,
                     limit: int = DEFAULT_LIMIT) -> list[dict]:
    """뉴스 공동 언급 — 같은 기사에 함께 나온 회사들."""
    cypher = """
    MATCH (a:Company {corp_code: $cc})-[r:CO_MENTIONED_WITH]-(b:Company)
    WHERE r.count >= $min
    RETURN b.corp_code AS corp_code,
           b.name      AS name,
           r.count     AS co_count,
           r.last_seen AS last_seen
    ORDER BY r.count DESC
    LIMIT $limit
    """
    return _run(cypher, cc=corp_code, min=min_count, limit=_cap(limit))


def list_group_members(group_name: str, *,
                       limit: int = DEFAULT_LIMIT) -> list[dict]:
    """공정위 기업집단의 계열사 목록."""
    cypher = """
    MATCH (c:Company)-[:BELONGS_TO_GROUP]->(g:Group {name: $g})
    RETURN c.corp_code AS corp_code, c.name AS name
    ORDER BY c.name
    LIMIT $limit
    """
    return _run(cypher, g=group_name, limit=_cap(limit))


__all__ = [
    "lookup_company", "lookup_person",
    "list_subsidiaries", "list_parents",
    "get_executives", "get_companies_of_person",
    "get_major_shareholders",
    "find_paths", "get_subgraph",
    "list_mentioning_news", "list_cooccurring",
    "list_group_members",
]
