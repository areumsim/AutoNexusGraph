"""PERFORMED_AT 회사 귀속 공정 시드 loader 단위 테스트.

DB 없이 seed → row 변환(_build_rows)만 검증 — 실제 Neo4j 적재는 integration 영역.
회사 귀속 무결성(allowlist source_type / 7키 메타 / 산단공 step_id 비오염)을 강제.
"""

from __future__ import annotations

from autograph.loaders._neo4j_helpers import EDGE_META_KEYS
from autograph.loaders.load_performed_at import _build_rows, _norm
from autograph.ontology import load_performed_at_seed


def test_norm_strips_and_lowercases():
    assert _norm("  프레스 ") == "프레스"
    assert _norm("Paint") == "paint"


def test_real_seed_yields_at_least_30_edges():
    """DoD #19 — 실 seed 가 ≥ 30 PERFORMED_AT 엣지를 만든다."""
    rows = _build_rows(load_performed_at_seed())
    assert len(rows) >= 30


def test_every_row_has_7key_meta_for_allowlist():
    """모든 row 가 7키 메타(snapshot/schema 제외 5키 보유) + manual_seed allowlist."""
    rows = _build_rows(load_performed_at_seed())
    assert rows
    needed = set(EDGE_META_KEYS) - {"schema_version"}  # schema 는 helper default
    for r in rows:
        assert needed <= set(r), f"메타 누락: {needed - set(r)}"
        assert r["source_type"] == "manual_seed"          # 회사 귀속 허용 출처
        assert r["validated_status"] == "validated"
        assert r["confidence_score"] >= 0.5               # low_conf_validated 위반 방지


def test_step_id_is_company_attributed_not_sandang():
    """생성 step_id 는 'seed_' prefix — 산단공 'sd_' 익명 스텝과 분리(비오염)."""
    rows = _build_rows(load_performed_at_seed())
    for r in rows:
        assert r["step_id"].startswith("seed_")
        assert not r["step_id"].startswith("sd_")
        assert r["plant_code"] in r["step_id"]


def test_empty_seed_graceful():
    assert _build_rows({"processes": [], "mappings": []}) == []
    assert _build_rows({}) == []
