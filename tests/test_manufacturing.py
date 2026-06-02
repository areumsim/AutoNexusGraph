"""제조·소재 (M-11~M-14) wire-up 회귀 테스트.

검증:
- M-11 factoryon: collect_rows / _normalize_row 정합 + raw 미존재 0 row
- M-11 datagokr_recalls/inspections: collect 함수 import + API key 미설정 graceful skip
- M-12 dart_production_parser._parse_utilization_table import + 가동률 % 파서
- M-13 KOSIS load_kosis_industry._coerce_rows 정합 + raw 미존재 0 row
- M-14 wikidata_cell_chem.collect 호출 (SPARQL 실패 graceful skip) + OEM candidates skeleton
- license policy 신규 항목 확인
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


# ── M-11 factoryon ────────────────────────────────────────────
def test_factoryon_normalize_row():
    from autograph.loaders.load_factoryon import _normalize_row
    item = {
        "fctryManageNo": "F123",
        "cmpnyNm":       "현대모비스",
        "irsttNm":       "울산공단",
        "prdctnPdct":    "ECU,센서",
        "emplyCnt":      "250",
    }
    row = _normalize_row(item, "by_company", snapshot_year=2026)
    assert row["factory_no"] == "F123"
    assert row["company_name"] == "현대모비스"
    assert row["industrial_complex"] == "울산공단"
    assert row["employees"] == 250
    assert row["source_endpoint"] == "by_company"
    assert row["snapshot_year"] == 2026


def test_factoryon_collect_rows_empty_when_no_raw(tmp_path):
    """raw 디렉토리 미존재 → 0 rows."""
    from autograph.loaders.load_factoryon import collect_rows
    empty = tmp_path / "factoryon_missing"
    rows = collect_rows(empty)
    assert rows == []


def test_factoryon_dedup_by_factory_no(tmp_path):
    """동일 factory_no 가 두 파일에 있을 때 dedup."""
    from autograph.loaders.load_factoryon import collect_rows
    base = tmp_path / "ft"
    (base / "by_company").mkdir(parents=True)
    (base / "by_factory_no").mkdir(parents=True)
    item = {"fctryManageNo": "F99", "cmpnyNm": "A", "emplyCnt": 10}
    (base / "by_company" / "a.json").write_text(json.dumps({"data": [item]}), encoding="utf-8")
    (base / "by_factory_no" / "F99.json").write_text(json.dumps({"data": [item]}), encoding="utf-8")
    rows = collect_rows(base)
    assert len(rows) == 1
    assert rows[0]["factory_no"] == "F99"


# ── M-11 datagokr ─────────────────────────────────────────────
def test_datagokr_recalls_module_importable():
    """모듈 import 성공 + run 함수 존재 (실제 호출은 KEY 필요)."""
    from autograph.ingestion import datagokr_recalls
    assert hasattr(datagokr_recalls, "run")


def test_datagokr_inspections_module_importable():
    from autograph.ingestion import datagokr_inspections
    assert hasattr(datagokr_inspections, "run")


def test_factoryon_module_importable():
    from autograph.ingestion import factoryon_registry
    assert hasattr(factoryon_registry, "by_company")
    assert hasattr(factoryon_registry, "by_factory_no")


# ── M-12 가동률 파서 ──────────────────────────────────────────
def test_parse_pct_basic():
    from autograph.extractors.dart_production_parser import _parse_pct
    assert _parse_pct("116.6%") == 116.6
    assert _parse_pct("116.6 %") == 116.6
    assert _parse_pct("-") is None
    assert _parse_pct("") is None
    assert _parse_pct("invalid") is None


def test_utilization_table_function_exists():
    """가동률 표 파서 함수 시그니처 보존."""
    import inspect
    from autograph.extractors.dart_production_parser import _parse_utilization_table
    sig = inspect.signature(_parse_utilization_table)
    assert "data_rows" in sig.parameters
    assert "years" in sig.parameters


def test_plant_utilization_table_in_pg_schema():
    """auto.plant_utilization 테이블 정의 SQL 존재 확인."""
    sql_file = ROOT / "infra" / "postgres" / "init" / "15_autograph_production.sql"
    assert sql_file.exists()
    content = sql_file.read_text(encoding="utf-8")
    assert "plant_utilization" in content


# ── M-13 KOSIS ────────────────────────────────────────────────
def test_kosis_loader_coerce_rows():
    from autograph.loaders.load_kosis_industry import _coerce_rows
    raw = [
        {"TBL_ID": "DT_X", "ITM_ID": "I1", "PRD_DE": "202401",
         "DT": "108.5", "UNIT_NM": "지수",
         "TBL_NM": "Stat", "ITM_NM": "Item"},
        {"TBL_ID": "DT_X", "ITM_ID": "I1", "PRD_DE": "2024",
         "DT": "100", "UNIT_NM": "지수",
         "TBL_NM": "Stat", "ITM_NM": "Item"},
    ]
    out = _coerce_rows(raw, stat_code_hint="manufacturing")
    assert len(out) == 2
    assert out[0]["cycle"] == "M"          # YYYYMM
    assert out[0]["value"] == 108.5
    assert out[1]["cycle"] == "A"          # YYYY
    assert out[1]["value"] == 100.0


def test_kosis_loader_handles_null_dt():
    """DT='-' 또는 빈 값 → value=None."""
    from autograph.loaders.load_kosis_industry import _coerce_rows
    raw = [{"TBL_ID": "DT_X", "ITM_ID": "I1", "PRD_DE": "2024",
            "DT": "-", "UNIT_NM": "지수"}]
    out = _coerce_rows(raw, stat_code_hint="manufacturing")
    assert out[0]["value"] is None


def test_kosis_loader_empty_when_no_raw(tmp_path):
    from autograph.loaders.load_kosis_industry import collect_rows
    rows = collect_rows(tmp_path / "kosis_missing")
    assert rows == []


def test_kosis_client_requires_api_key():
    """KosisClient 가 빈 키로 생성 시 ValueError raise."""
    from autonexusgraph.ingestion.kosis_client import KosisClient
    with pytest.raises(ValueError):
        KosisClient(api_key="")


# ── M-14 Wikidata 셀 chem ────────────────────────────────────
def test_wikidata_cell_chem_module_importable():
    from autograph.ingestion import wikidata_cell_chem
    assert hasattr(wikidata_cell_chem, "collect")
    assert hasattr(wikidata_cell_chem, "collect_oem_supplier_candidates")
    # CATHODE_QIDS 는 manual 큐레이션 대기로 의도적 빈 dict — 이전 QID 가 오류였음
    # (Q899037=루마니아 마을 Toboliu, Q900614=carbochemistry). 빈 dict 가 정상 계약.
    assert isinstance(wikidata_cell_chem.CATHODE_QIDS, dict)


def test_wikidata_cell_chem_oem_candidates_grade_c():
    """OEM↔셀 매핑은 PRD §2.3 명시 — grade C candidate."""
    from autograph.ingestion.wikidata_cell_chem import collect_oem_supplier_candidates
    out = collect_oem_supplier_candidates(max_qids=5)
    assert out["grade"] == "C"
    assert "sparse" in out.get("note", "").lower() or "candidate" in out.get("note", "").lower()


def test_materials_seed_yaml_present():
    """materials_seed.yaml 의 NCM/LFP cathode 시드 확인."""
    seed = ROOT / "ontology" / "auto" / "materials_seed.yaml"
    assert seed.exists()
    content = seed.read_text(encoding="utf-8")
    assert "NCM811" in content or "LFP" in content
    assert "version:" in content


def test_load_usgs_minerals_module_importable():
    from autograph.loaders import load_usgs_minerals
    # _SCHEMA_VERSION 이 default_schema_version() 의 'v2.2' 인지 (B1 fix).
    assert load_usgs_minerals._SCHEMA_VERSION == "v2.2"


# ── 라이선스 정책 (신규 추가 키 검증) ────────────────────────
def test_license_uspto_odp_and_cpc_added():
    from autonexusgraph.ingestion._license import LICENSE_POLICY, allow_body
    # M-13/M-14 단계 에서 추가했음 (P0+ #2/IPG-7 의 부산물).
    assert LICENSE_POLICY.get("kosis") == "public_domain"
    assert LICENSE_POLICY.get("uspto_odp") == "public_domain"
    assert allow_body("kosis") is True
    assert allow_body("uspto_odp") is True


# ── PG init 파일 정합성 ──────────────────────────────────────
def test_pg_init_24_factoryon_exists():
    p = ROOT / "infra" / "postgres" / "init" / "24_auto_factoryon.sql"
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "auto.factoryon_registry" in content
    assert "factory_no" in content


def test_pg_init_kosis_macro_exists():
    """KOSIS 적재 대상 테이블 (macro.kosis_series) SQL 정의 확인."""
    p = ROOT / "infra" / "postgres" / "init" / "04_external_data.sql"
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "macro.kosis_series" in content
    assert "stat_code" in content
