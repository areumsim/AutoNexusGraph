"""ProcessGraph (BoP) 에이전트 도구 — PRD_process_graph §5.

자유 SQL/Cypher 금지: SQL 은 ``_db`` 헬퍼, Cypher 는 ``AUTO_TEMPLATES`` 화이트리스트
경유(graph.py 와 동일 ``_exec``). 모든 결과에 grade(confidence) 노출 — 산단공 공정은
C(0.50, 합성/패턴) 이므로 답변 시 "패턴(합성)" 표시 필요.

데이터 현황(정직, 라벨 컨벤션: feedback_label_proceed):
- **동작** (실데이터, :Process 410 / :ProcessStep 550 / PRECEDES 410 / INSTANTIATES 550):
  ``lookup_process`` / ``get_process_info`` / ``list_process_route`` (PRECEDES 체인) /
  ``list_steps_of_process``.
- **(scaffold)** 빈결과 반환 — 함수 정의 + ``return []`` (출처 적재 + 매크로 등록 후 자연 활성):
  ``list_plants_of_process`` (PERFORMED_AT, 팩토리온 DATA_GO_KR_API_KEY 부재 → PR-P3-A),
  ``list_materials_of_process`` (CONSUMES_MATERIAL, materials_seed 매핑 부재 → P2-B),
  ``get_process_metrics`` (KAMP 미수집, PG 조회만 — ``anxg_auto.process_metrics`` 빈 시 빈 list).
- **(비전)** — 본 모듈에 함수 정의 없음, ``__all__`` 미포함:
  ``list_equipment_of_process`` (USES_EQUIPMENT, :Equipment 0 + 매핑 부재),
  ``get_processes_of_part`` (PRODUCED_BY, 산단공에 part_id 부재).
"""

from __future__ import annotations

import logging
from typing import Any

from autonexusgraph.tools.cypher_templates import render_template

from ._db import query_dicts

log = logging.getLogger(__name__)

DEFAULT_LIMIT = 20
HARD_LIMIT = 500


def _cap(limit: int | None, default: int = DEFAULT_LIMIT) -> int:
    if limit is None or limit <= 0:
        return default
    return min(int(limit), HARD_LIMIT)


def _exec(template_name: str, **params: Any) -> list[dict]:
    """화이트리스트 템플릿 렌더 + READ-only Cypher 실행 (graph.py 패턴 동일)."""
    from autonexusgraph.db.neo4j import get_session
    from autonexusgraph.safety.cypher_guard import assert_read_only
    cypher, bind = render_template(template_name, params)
    assert_read_only(cypher)

    with get_session() as session:
        return [dict(r) for r in session.run(cypher, **bind)]


# ── 식별·조회 (실데이터) ─────────────────────────────────────
def lookup_process(query: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """공정명 검색 → 공정유형(:Anxg_Process taxonomy) 단위 **distinct** 결과 (GROUP BY).

    cf. ``autograph.tools.spec.search_processes`` 는 row 단위 (동일 공정명이 여러
    factory_manage_no 에 반복되면 row 모두 반환). 본 함수는 distinct ``process_name_norm``
    1 행 — taxonomy 노드 단위 매칭에 적합 (≈410 행 상한, ``:Process`` 노드 수와 정렬).

    산단공 합성(grade C 0.50). 빈 query → 빈 list.
    """
    q = (query or "").strip()
    if not q:
        return []
    return query_dicts("""
        SELECT process_name_norm,
               MIN(process_name)     AS process_name,
               MIN(process_map_name) AS process_map_name,
               MIN(industry_code)    AS industry_code,
               0.50::numeric         AS confidence,
               'pattern_synthetic'   AS grade_note
          FROM anxg_auto.processes
         WHERE process_name_norm ILIKE '%%' || %(q)s || '%%'
            OR process_map_name  ILIKE '%%' || %(q)s || '%%'
         GROUP BY process_name_norm
         ORDER BY process_name_norm
         LIMIT %(lim)s
    """, {"q": q.lower(), "lim": _cap(limit)})


def get_process_info(process_name_norm: str) -> dict | None:
    """공정유형 단건 정보 + 인스턴스(ProcessStep) 수 (auto_proc_info)."""
    if not (process_name_norm or "").strip():
        return None
    rows = _exec("auto_proc_info", process_name_norm=process_name_norm)
    return rows[0] if rows else None


def list_process_route(step_id: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """시작 ProcessStep 의 PRECEDES 후속 경로 (depth cap=10, 폭발 방지)."""
    if not (step_id or "").strip():
        return []
    return _exec("auto_proc_route", step_id=step_id, limit=_cap(limit))


def list_steps_of_process(process_name_norm: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """공정유형을 인스턴스화한 ProcessStep 목록 (INSTANTIATES 역방향)."""
    if not (process_name_norm or "").strip():
        return []
    return _exec("auto_proc_steps_of_process",
                 process_name_norm=process_name_norm, limit=_cap(limit))


# ── 회사 귀속·자원 (엣지 enabled:false — 출처 확보 후 활성) ──
# PERFORMED_AT / CONSUMES_MATERIAL 은 현재 데이터 부재로 비활성. ontology_validate 가
# 비활성 엣지를 쓰는 템플릿을 거부하므로 템플릿 미등록 → 빈결과 직접 반환(API 표면 유지).
def list_plants_of_process(process_name_norm: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """공정 수행 공장 (PERFORMED_AT, 회사 귀속 A/B). 팩토리온 키 확보 전까지 빈결과."""
    return []


def list_materials_of_process(process_name_norm: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """공정 소비 소재 (CONSUMES_MATERIAL → L6). 산단공 출처 부재 → 빈결과."""
    return []


def get_process_metrics(process_name_norm: str | None = None,
                        process_category: str | None = None,
                        limit: int = DEFAULT_LIMIT) -> list[dict]:
    """공정 파라미터 분포(cycle_time/yield/defect, **익명·회사 비귀속** grade B).

    anxg_auto.process_metrics 조회. KAMP 미수집 시 빈결과(DATA_GO_KR_API_KEY 필요).
    """
    where: list[str] = []
    params: dict[str, Any] = {"lim": _cap(limit)}
    if (process_name_norm or "").strip():
        where.append("process_name_norm = %(n)s")
        params["n"] = process_name_norm
    if (process_category or "").strip():
        where.append("process_category = %(c)s")
        params["c"] = process_category
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    return query_dicts(f"""
        SELECT process_name_norm, process_category, metric_type, unit,
               value_mean, value_p50, value_p95, sample_count,
               confidence_score, 'pattern_anonymous' AS grade_note
          FROM anxg_auto.process_metrics{clause}
         ORDER BY process_category, metric_type
         LIMIT %(lim)s
    """, params)


__all__ = [
    "lookup_process",
    "get_process_info",
    "list_process_route",
    "list_steps_of_process",
    "list_plants_of_process",
    "list_materials_of_process",
    "get_process_metrics",
]
