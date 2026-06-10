"""load_materials_metals — DB 없이 row builder + cypher shape 검증."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def seed():
    from autograph.loaders.materials.load_materials_metals import load_seed
    return load_seed()


def test_seed_loads_non_empty(seed):
    assert seed is not None, "materials_metals_seed.yaml 로드 실패"
    assert seed.get("materials"), "materials 비어있음"
    assert seed.get("module_to_materials"), "module_to_materials 비어있음"


def test_material_rows_shape(seed):
    from autograph.loaders.materials.load_materials_metals import _build_material_rows
    rows = _build_material_rows(seed)
    assert len(rows) == len(seed["materials"])
    for r in rows:
        # 필수 키
        for k in ("code", "name", "material_class",
                  "aliases", "typical_processes", "typical_modules"):
            assert k in r, f"row missing key {k}"
        assert r["material_class"] == "metal_alloy"
        # 리스트 필드는 list 타입 보장 (None → [] 변환).
        assert isinstance(r["aliases"], list)
        assert isinstance(r["typical_processes"], list)
        assert isinstance(r["typical_modules"], list)


def test_made_of_rows_flatten(seed):
    from autograph.loaders.materials.load_materials_metals import _build_made_of_rows
    rows = _build_made_of_rows(seed)
    # 모든 entry 의 materials 합산과 같아야 함.
    expected = sum(len(e.get("materials") or []) for e in seed["module_to_materials"])
    assert len(rows) == expected
    for r in rows:
        assert r["module_name"]
        assert r["material_code"]
        # material_code 가 실제 seed 의 materials key 안에 존재.
        assert r["material_code"] in seed["materials"], \
            f"unknown material_code in mapping: {r['material_code']}"


def test_made_of_rows_use_anxg_module_label():
    """`_MERGE_MADE_OF` Cypher 가 namespace 프리픽스 라벨 사용 (회귀 가드).

    namespace 격리 commit fb1c925 후속 — bare `:Module` / `:Material` 잔재 차단.
    """
    from autograph.loaders.materials import load_materials_metals as L
    assert "Anxg_Module" in L._MERGE_MADE_OF
    assert "Anxg_Material" in L._MERGE_MADE_OF
    assert ":Module" not in L._MERGE_MADE_OF  # bare 잔재 없음
    assert ":Material" not in L._MERGE_MADE_OF.replace("Anxg_Material", "")


def test_made_of_includes_7key_edge_meta():
    """PRD §6.7 — 7-key meta 모두 SET. namespace 격리 후속 회귀 가드."""
    from autograph.loaders.materials import load_materials_metals as L
    for k in ("source_type", "source_id", "confidence_score",
              "validated_status", "snapshot_year",
              "extraction_method", "schema_version"):
        assert f"r.{k}" in L._MERGE_MADE_OF, f"missing edge meta: {k}"


def test_constraint_uses_anxg_label():
    from autograph.loaders.materials import load_materials_metals as L
    assert "Anxg_Material" in L._CONSTRAINT_MATERIAL


def test_made_of_uses_candidate_grade():
    """MADE_OF 엣지 default conf = 0.50 (C) — OEM 매칭 추론. validated_status='candidate'.

    docstring 기재된 등급 정합 (OEM IR/MSDS 들어오면 격상) 의 회귀 가드.
    """
    from autograph.loaders.materials import load_materials_metals as L
    assert L._CONF_EDGE_C == 0.50


def test_dry_run_returns_preview():
    """dry_run=True → DB 호출 없이 preview dict 반환."""
    from autograph.loaders.materials.load_materials_metals import run
    out = run(dry_run=True, snapshot_year=2026)
    assert out["snapshot_year"] == 2026
    assert "preview" in out
    assert out["preview"]["n_materials"] >= 9    # L6-2 시드 하한
    assert out["preview"]["n_made_of_rows"] >= 10
    # stats 는 dry_run 에서도 module_mappings_seen 채워짐
    assert out["stats"]["module_mappings_seen"] >= 10
    # 실제 적재는 안 함
    assert out["stats"]["materials_merged"] == 0
    assert out["stats"]["made_of_merged"] == 0


def test_run_returns_stats_dict_shape():
    """LoadStats 직렬화 형태 — JSON 출력용."""
    from autograph.loaders.materials.load_materials_metals import LoadStats
    s = LoadStats()
    d = s.__dict__
    for k in ("materials_merged", "module_mappings_seen", "made_of_merged",
              "made_of_skipped_no_module", "errors"):
        assert k in d


def test_seed_path_missing_returns_none(tmp_path):
    """seed 미존재 시 graceful skip (None 반환)."""
    from autograph.loaders.materials.load_materials_metals import load_seed
    fake = tmp_path / "no_such.yaml"
    assert load_seed(fake) is None
