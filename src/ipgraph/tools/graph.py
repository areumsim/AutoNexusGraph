"""IPGraph Neo4j 관계 탐색 — cypher 템플릿 경유 (자유 Cypher 금지).

명세 = docs/ipgraph.md §4. 모든 함수는 ``ip_*`` 템플릿을 사용하며 ``_run`` 의
READ-ONLY 정적 검사를 통과한다.

Neo4j 미가용 환경 (CI / 테스트) 에서 fail-soft — 빈 list 반환 + warning.
"""

from __future__ import annotations

import logging
from typing import Any

from autonexusgraph.tools.cypher_templates import render_template

log = logging.getLogger(__name__)


_DEFAULT_LIMIT = 50
_HARD_LIMIT = 500
_HARD_CITATION_LIMIT = 500   # per-side cap. depth ≤ 2 max_total ≤ 1000.


def _cap(limit: int | None, hard: int = _HARD_LIMIT) -> int:
    if limit is None or limit <= 0:
        return _DEFAULT_LIMIT
    return min(int(limit), hard)


def _run(cypher: str, **params: Any) -> list[dict]:
    """READ 단일 — cypher_guard 검사 + Neo4j 호출. fail-soft."""
    try:
        from autonexusgraph.safety.cypher_guard import assert_read_only
        from autonexusgraph.db.neo4j import get_session
    except Exception as e:   # noqa: BLE001 — [graph] fail-soft 흡수 → [] 반환 (log 동반)
        log.warning("[ip.graph._run] core import 실패: %s", e)
        return []
    try:
        assert_read_only(cypher)

        with get_session() as session:
            result = session.run(cypher, **params)
            return [dict(r) for r in result]
    except Exception as e:   # noqa: BLE001 — [graph] fail-soft 흡수 → [] 반환 (log 동반)
        log.warning("[ip.graph._run] cypher 실행 실패 (fail-soft): %s", e)
        return []


def _exec(template_name: str, **params: Any) -> list[dict]:
    cypher, bind = render_template(template_name, params)
    return _run(cypher, **bind)


# ── lookup ──────────────────────────────────────────────────────
def lookup_assignee_graph(query: str, limit: int = 10) -> list[dict]:
    """Neo4j :Assignee 노드 검색 — name 정확/부분 매칭."""
    return _exec("ip_lookup_assignee", q=query, limit=_cap(limit, 100))


def list_patents_of_assignee(assignee_id: str, *, limit: int = 50,
                              snapshot_year: int | None = None) -> list[dict]:
    """assignee 의 모든 특허 (filing_date 내림차순)."""
    # snapshot_year 는 본 단계에서 미사용 (필요 시 별도 템플릿).
    _ = snapshot_year
    return _exec("ip_list_patents_of_assignee",
                  assignee_id=assignee_id, limit=_cap(limit, _HARD_LIMIT))


def get_inventors_of_patent(pub_no: str, limit: int = 50) -> list[dict]:
    return _exec("ip_get_inventors_of_patent", pub_no=pub_no, limit=_cap(limit, 100))


def find_co_assignees(assignee_id: str, limit: int = 20) -> list[dict]:
    """같은 특허에 동시 등장한 다른 assignee — 공동 출원 네트워크."""
    return _exec("ip_find_co_assignees", assignee_id=assignee_id,
                  limit=_cap(limit, 100))


# ── CPC ────────────────────────────────────────────────────────
def list_patents_in_cpc(cpc_code: str, *, include_subclasses: bool = True,
                         limit: int = 50) -> list[dict]:
    """CPC 코드의 특허들. include_subclasses=True 면 SUBCLASS_OF 트리 (depth ≤ 4) 까지."""
    tmpl = "ip_list_patents_in_cpc_recursive" if include_subclasses else "ip_list_patents_in_cpc"
    return _exec(tmpl, cpc_code=cpc_code, limit=_cap(limit, _HARD_LIMIT))


def list_assignees_in_field(cpc_code: str, *, top_k: int = 20) -> list[dict]:
    """CPC 코드 분야의 상위 assignee."""
    return _exec("ip_list_assignees_in_field", cpc_code=cpc_code,
                  top_k=_cap(top_k, 50))


# ── Citation network — cap 강제 (depth ≤ 2, max_total ≤ 1000) ──
def get_citation_network(pub_no: str, *, depth: int = 1,
                          limit_nodes: int = 300,
                          max_total: int = 1000,
                          direction: str = "both") -> dict[str, Any]:
    """특허 인용 네트워크 — depth ≤ 2 강제 cap.

    Args:
        pub_no: 중심 특허 번호
        depth: 1 또는 2. 2 초과 입력은 2로 절단.
        limit_nodes: 각 방향 최대 노드 (per-side). 500 cap.
        max_total: 양쪽 합 max. 1000 cap (PRD §7.5.10 그래프 폭발 방지).
        direction: 'cited' | 'cites' | 'both'

    Returns: ``{"center": pub_no, "cited": [...], "citing": [...]}``
    """
    _ = direction  # 본 단계는 항상 both — template 분기 후속.
    depth = min(max(int(depth), 1), 2)
    per_side = min(int(limit_nodes), _HARD_CITATION_LIMIT)
    tmpl = "ip_citation_network_d2" if depth == 2 else "ip_citation_network_d1"
    if depth == 2:
        rows = _exec(tmpl, pub_no=pub_no, max_per_side=per_side)
    else:
        rows = _exec(tmpl, pub_no=pub_no, limit_each=per_side)
    if not rows:
        return {"center": pub_no, "cited": [], "citing": []}
    row = rows[0]
    cited = (row.get("cited") or [])[:max_total // 2]
    citing = (row.get("citing") or [])[:max_total // 2]
    return {"center": pub_no, "depth": depth, "cited": cited, "citing": citing}


def most_cited_patents(assignee_or_cpc: str, *, top_k: int = 10,
                        is_cpc: bool | None = None) -> list[dict]:
    """assignee_id 또는 cpc_code 기준 최다 인용 특허.

    is_cpc=None 시 헤더 문자 (영문 대문자 1글자) 가 CPC section 패턴이면 cpc 로 판정.
    """
    is_cpc_resolved = (is_cpc if is_cpc is not None
                        else (len(assignee_or_cpc) <= 8
                              and assignee_or_cpc[:1].isalpha()
                              and assignee_or_cpc[:1].isupper()))
    if is_cpc_resolved:
        return _exec("ip_most_cited_in_cpc",
                      cpc_code=assignee_or_cpc, top_k=_cap(top_k, 50))
    return _exec("ip_most_cited_patents",
                  assignee_id=assignee_or_cpc, top_k=_cap(top_k, 50))


__all__ = [
    "lookup_assignee_graph",
    "list_patents_of_assignee",
    "get_inventors_of_patent",
    "find_co_assignees",
    "list_patents_in_cpc",
    "list_assignees_in_field",
    "get_citation_network",
    "most_cited_patents",
]
