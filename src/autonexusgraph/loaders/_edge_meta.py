"""Edge meta SET 헬퍼 — PRD §6.7 7키 의무 cypher SoT (finance + ip loader 공용).

`autograph/loaders/_neo4j_helpers.py` 의 ``edge_meta_cypher(rel_var)`` 와 다른 패턴:
저쪽은 ``r.source_type`` 등을 그대로 SET (UNWIND $rows AS r 의 row dict 가 메타를
포함한다고 가정). 본 helper 는 **cypher 안 literal default** 패턴 — loader 가
domain 별 default 정책 (DART grade A=0.95, news rule=0.80 등) 을 명시하면 helper
가 ``coalesce(rel.key, default_literal)`` 절을 생성.

호출 예 (graph.py LISTED_IN):

    MERGE (c)-[rel:LISTED_IN]->(m)
    SET rel.source = 'krx',
        {edge_meta_set_clause(
            'rel',
            source_type='krx_master',
            confidence_score=0.95,
        )}

생성된 cypher fragment:

    rel.source_type       = coalesce(rel.source_type, 'krx_master'),
    rel.source_id         = coalesce(rel.source_id, 'krx_master'),
    rel.confidence_score  = coalesce(rel.confidence_score, 0.95),
    rel.validated_status  = coalesce(rel.validated_status, 'verified'),
    rel.snapshot_year     = coalesce(rel.snapshot_year, date().year),
    rel.extraction_method = coalesce(rel.extraction_method, 'deterministic'),
    rel.schema_version    = coalesce(rel.schema_version, 'v2.2')

`schema_version` 의 SoT 는 ``ontology/relations.yaml`` 헤더 — `v2.2` → `v2.3` 변경
시 helper 가 자동 회수 (lru_cache, process restart 시 재로드).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Final

# core ontology — finance + cross-domain 공통 schema_version SoT.
_ONTOLOGY_RELATIONS_YAML: Final[Path] = (
    Path(__file__).resolve().parents[3] / "ontology" / "relations.yaml"
)


@lru_cache(maxsize=1)
def default_schema_version() -> str:
    """``ontology/relations.yaml`` 헤더의 schema_version (core SoT).

    raw yaml 이 아니라 ``load_and_validate`` (pydantic strict) 경유 — finance
    relations.yaml 도 **소비 시점에 검증**된다 (auto/ip 와 동일 게이트, 검증 이원화
    해소). 헤더 없거나 파일/검증 실패 시 'v0' (legacy graceful). audit-ontology
    PASS 시 'v2.2'.
    """
    if not _ONTOLOGY_RELATIONS_YAML.is_file():
        return "v0"
    # OntologyValidationError 는 일부러 전파 — finance relations.yaml 이 스키마를
    # 위반하면 auto/ip 처럼 적재가 fail-loud (검증 우회 방지). 파일은 audit-ontology
    # 가 PASS 로 보증 → 정상 환경에선 예외 없음.
    from autonexusgraph.ontology import load_and_validate
    return load_and_validate(_ONTOLOGY_RELATIONS_YAML).schema_version or "v0"


def edge_meta_set_clause(
    rel_var: str,
    *,
    source_type: str,
    confidence_score: float,
    validated_status: str = "verified",
    extraction_method: str = "deterministic",
    snapshot_year_expr: str = "date().year",
    source_id_expr: str | None = None,
    schema_version: str | None = None,
) -> str:
    """PRD §6.7 7키 의무 메타 SET 절 — coalesce 로 기존 값 보존 + 누락 시 default.

    Args:
        rel_var: cypher 의 엣지 변수명 (예: "rel", "m").
        source_type: 출처 식별 (literal). 예: 'dart_otr_cpr_invstmnt' / 'krx_master' / 'news_yna'.
        confidence_score: 출처 등급 (PRD §3.5). A=0.95 / B=0.80 / C=0.50~0.70.
        validated_status: 'verified' (default — 공시) / 'candidate' (rule/LLM).
        extraction_method: 'deterministic' / 'rule_substring' / 'rule_aggregate' / 'llm' 등.
        snapshot_year_expr: snapshot_year 의 cypher 식 — `r.rcept_year` / `date(r.snapshot_date).year`
            / `datetime(n.published_at).year` 등. 기본은 `date().year` (적재 시점).
        source_id_expr: source_id 의 cypher 표현. None 이면 source_type literal 재사용.
        schema_version: 명시 시 우선. None → `default_schema_version()` lookup.

    Returns:
        7키 SET 절 cypher fragment. 호출처가 ``SET ... ,\\n    {clause}`` 형태로 연결.

    Security:
        모든 인자가 literal 또는 호출자 통제 cypher 식. 외부 입력 (사용자 query 등)
        을 직접 전달하지 말 것 — SQL injection 회피.
    """
    sv = schema_version or default_schema_version()
    sid = source_id_expr if source_id_expr else f"'{source_type}'"
    return (
        f"    {rel_var}.source_type       = coalesce({rel_var}.source_type, '{source_type}'),\n"
        f"    {rel_var}.source_id         = coalesce({rel_var}.source_id, {sid}),\n"
        f"    {rel_var}.confidence_score  = coalesce({rel_var}.confidence_score, {confidence_score}),\n"
        f"    {rel_var}.validated_status  = coalesce({rel_var}.validated_status, '{validated_status}'),\n"
        f"    {rel_var}.snapshot_year     = coalesce({rel_var}.snapshot_year, {snapshot_year_expr}),\n"
        f"    {rel_var}.extraction_method = coalesce({rel_var}.extraction_method, '{extraction_method}'),\n"
        f"    {rel_var}.schema_version    = coalesce({rel_var}.schema_version, '{sv}')"
    )


__all__ = ["default_schema_version", "edge_meta_set_clause"]
