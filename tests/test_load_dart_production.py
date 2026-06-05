"""DART 사업보고서 production loader 단위 테스트.

mock cursor / driver 로 DB 미가용 환경에서도 회귀 보호. 실제 zip 적재는
integration 영역.
"""

from __future__ import annotations

import zipfile
from unittest import mock


from autograph.extractors.dart_production_parser import PlantRow
from autograph.loaders import load_dart_production as L


# ── OEM_CORP_CODES 형태 ───────────────────────────────────────
def test_oem_corp_codes_whitelist_shape():
    """6 사 등록 + 각 항목 (name, alias_for_mfr) 필드."""
    assert len(L.OEM_CORP_CODES) == 6
    for cc, meta in L.OEM_CORP_CODES.items():
        assert isinstance(cc, str) and cc.isdigit() and len(cc) == 8
        assert "name" in meta
        assert "alias_for_mfr" in meta


def test_oem_corp_codes_hyundai_present():
    """현대차 corp_code 정확."""
    assert "00164742" in L.OEM_CORP_CODES
    assert L.OEM_CORP_CODES["00164742"]["alias_for_mfr"] == "HYUNDAI"


# ── _is_vehicle_division ──────────────────────────────────────
def test_is_vehicle_division_explicit_match():
    assert L._is_vehicle_division("차량부문") is True
    assert L._is_vehicle_division("차량부문(대수)") is True


def test_is_vehicle_division_finance_excluded():
    assert L._is_vehicle_division("금융부문") is False
    assert L._is_vehicle_division("기타부문(억원)") is False


def test_is_vehicle_division_inherited_row():
    """ROWSPAN 상속 행 (division=None) — 직전 그룹이 차량부문이라 True."""
    assert L._is_vehicle_division(None) is True
    assert L._is_vehicle_division("") is True


# ── _resolve_plant_node_code ──────────────────────────────────
def test_resolve_plant_node_code_known_pair():
    assert L._resolve_plant_node_code("00164742", "HMC") == "HYU_ULSAN"
    assert L._resolve_plant_node_code("00164742", "HMMA") == "HYU_MONTGOMERY"
    assert L._resolve_plant_node_code("00106641", "기아") == "KIA_HWASEONG"


def test_resolve_plant_node_code_unmapped_returns_none():
    """plants.yaml 미등록 plant — None (Neo4j 엣지 skip).

    2026-06-01 plants.yaml 확장으로 HMI/HTMV 등은 이제 매핑됨.
    완전히 미정의 가상 라벨로 회귀 보호.
    """
    assert L._resolve_plant_node_code("00164742", "NONEXISTENT_LABEL") is None
    assert L._resolve_plant_node_code("99999999", "HMC") is None


def test_resolve_plant_node_code_strips_whitespace():
    assert L._resolve_plant_node_code("00164742", "  HMC  ") == "HYU_ULSAN"


def test_resolve_plant_node_code_normalizes_internal_whitespace():
    """DART XML 의 'HMMA / HMGMA' / 'HMMA/ HMGMA' 등 공백 변형 — 2026-06-01 신규.

    dict 키는 정규형 'HMMA/HMGMA' 만 등록. _normalize_dart_plant_label 이
    raw 입력을 정규형으로 변환 후 매칭.
    """
    # raw 변형 3 가지 모두 같은 결과
    assert L._resolve_plant_node_code("00164742", "HMMA / HMGMA") == "HYU_METAPLANT"
    assert L._resolve_plant_node_code("00164742", "HMMA/ HMGMA") == "HYU_METAPLANT"
    assert L._resolve_plant_node_code("00164742", "HMMA/HMGMA")  == "HYU_METAPLANT"
    # 정규화 함수 자체
    assert L._normalize_dart_plant_label("HMMA / HMGMA") == "HMMA/HMGMA"
    assert L._normalize_dart_plant_label("HMMA/ HMGMA") == "HMMA/HMGMA"
    assert L._normalize_dart_plant_label("  HMC  ") == "HMC"
    assert L._normalize_dart_plant_label("") == ""


# ── _merge_capa_and_actual ────────────────────────────────────
def test_merge_combines_same_plant_and_year():
    capa = [PlantRow(business_division="차량부문", plant_code="HMC",
                     plant_region="한국", year=2024, value=1700000.0)]
    prod = [PlantRow(business_division="차량부문", plant_code="HMC",
                     plant_region="한국", year=2024, value=1900000.0)]
    out = L._merge_capa_and_actual(capa, prod)
    assert ("HMC", 2024) in out
    row = out[("HMC", 2024)]
    assert row["capa_units"] == 1700000
    assert row["actual_units"] == 1900000


def test_merge_skips_invalid_rows():
    """year=0 또는 plant_code='' 인 행은 skip."""
    capa = [PlantRow(plant_code="", year=2024, value=1.0)]
    prod = [PlantRow(plant_code="HMC", year=0, value=2.0)]
    out = L._merge_capa_and_actual(capa, prod)
    assert out == {}


def test_merge_handles_capa_only():
    capa = [PlantRow(plant_code="HMC", year=2024, value=1000000.0)]
    out = L._merge_capa_and_actual(capa, [])
    row = out[("HMC", 2024)]
    assert row["capa_units"] == 1000000
    assert row["actual_units"] is None


def test_merge_handles_production_only():
    prod = [PlantRow(plant_code="HMC", year=2024, value=900000.0)]
    out = L._merge_capa_and_actual([], prod)
    row = out[("HMC", 2024)]
    assert row["capa_units"] is None
    assert row["actual_units"] == 900000


# ── _iter_corp_zips — tmp_path 기반 ───────────────────────────
def test_iter_corp_zips_yields_zips(tmp_path, monkeypatch):
    """gracefully scans corp/<cc>/documents/*.zip"""
    fake_root = tmp_path / "dart_bulk" / "corp" / "00164742" / "documents"
    fake_root.mkdir(parents=True)
    (fake_root / "20240101.zip").write_bytes(b"PK\x05\x06" + b"\x00" * 18)
    (fake_root / "20240202.zip").write_bytes(b"PK\x05\x06" + b"\x00" * 18)

    class FakeSettings:
        ingest_raw_dir = tmp_path

    monkeypatch.setattr(L, "get_settings", lambda: FakeSettings())
    result = list(L._iter_corp_zips("00164742"))
    assert len(result) == 2
    assert all(p.suffix == ".zip" for _, p in result)


def test_iter_corp_zips_missing_dir_returns_empty(tmp_path, monkeypatch):
    class FakeSettings:
        ingest_raw_dir = tmp_path / "nope"

    monkeypatch.setattr(L, "get_settings", lambda: FakeSettings())
    assert list(L._iter_corp_zips("99999999")) == []


# ── _read_main_xml — 실제 zip 만들어 검증 ─────────────────────
def test_read_main_xml_matched_name(tmp_path):
    p = tmp_path / "20240101.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("20240101.xml", "<DOCUMENT/>")
    assert L._read_main_xml(p) == "<DOCUMENT/>"


def test_read_main_xml_underscore_fallback(tmp_path):
    """본명 XML 없으면 첫 underscore-없는 XML."""
    p = tmp_path / "20240101.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("20240101_supplement.xml", "<SUPPLEMENT/>")
        zf.writestr("20240101.xml", "<MAIN/>")
    out = L._read_main_xml(p)
    assert out == "<MAIN/>"


def test_read_main_xml_corrupted_zip_returns_none(tmp_path):
    p = tmp_path / "bad.zip"
    p.write_bytes(b"not a zip")
    assert L._read_main_xml(p) is None


def test_read_main_xml_no_xml_returns_none(tmp_path):
    p = tmp_path / "20240101.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("only.txt", "no xml here")
    assert L._read_main_xml(p) is None


# ── _resolve_manufacturer_id with mocks ───────────────────────
def test_resolve_manufacturer_id_uses_bridge_first(monkeypatch):
    """anxg_bridge.corp_entity 에 매핑이 있으면 그것을 우선."""
    fake_cur = mock.MagicMock()
    fake_cur.fetchone.return_value = (498,)
    fake_conn = mock.MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cur

    monkeypatch.setattr("autonexusgraph.db.postgres.get_connection",
                        lambda: fake_conn)
    assert L._resolve_manufacturer_id("00164742") == 498


def test_resolve_manufacturer_id_falls_back_to_alias(monkeypatch):
    """bridge miss → master_manufacturers.name = alias 매칭."""
    fake_cur = mock.MagicMock()
    # 1st query (bridge) miss, 2nd (alias) hit
    fake_cur.fetchone.side_effect = [None, (441,)]
    fake_conn = mock.MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cur

    monkeypatch.setattr("autonexusgraph.db.postgres.get_connection",
                        lambda: fake_conn)
    assert L._resolve_manufacturer_id("00164742") == 441
    # 두 번 호출됨 (bridge + alias)
    assert fake_cur.execute.call_count == 2


def test_resolve_manufacturer_id_no_alias_no_bridge_returns_none(monkeypatch):
    """alias_for_mfr=None 인 supplier (예: 한온) — bridge miss 후 None."""
    fake_cur = mock.MagicMock()
    fake_cur.fetchone.return_value = None
    fake_conn = mock.MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cur

    monkeypatch.setattr("autonexusgraph.db.postgres.get_connection",
                        lambda: fake_conn)
    assert L._resolve_manufacturer_id("00161125") is None


# ── _sync_manufactured_at_to_neo4j ────────────────────────────
def test_manufactured_at_cypher_includes_year_in_merge_key():
    """MERGE 키에 snapshot_year 포함 — 시계열 보존 (2026-06-01 P0 fix).

    이전엔 MERGE (mm)-[r]->(p) 만 — 같은 plant 의 다년치가 한 edge 로
    collapse 되어 history 91% 손실. 본 fix 로 MERGE 키에 year 포함.
    """
    assert "snapshot_year: r.snapshot_year" in L._MANUFACTURED_AT_CYPHER, \
        "MERGE 키에 snapshot_year 누락 — 시계열 손실 회귀"


def test_sync_manufactured_at_creates_rows_for_mapped_plants(monkeypatch):
    """Mapped plant (HMC → HYU_ULSAN) 만 cypher row 생성."""
    monkeypatch.setattr(L, "_resolve_manufacturer_id", lambda cc: 441)

    # driver mock
    session = mock.MagicMock()
    driver = mock.MagicMock()
    driver.session.return_value.__enter__.return_value = session
    monkeypatch.setattr("autonexusgraph.db.neo4j.get_driver", lambda: driver)

    capacity = [PlantRow(business_division="차량부문", plant_code="HMC",
                          plant_region="한국", year=2024, value=1700000.0)]
    production = [PlantRow(business_division="차량부문", plant_code="HMC",
                            plant_region="한국", year=2024, value=1900000.0)]

    out = L._sync_manufactured_at_to_neo4j(
        capacity_rows=capacity, production_rows=production,
        corp_code="00164742", rcept_no="TEST_RCEPT")

    assert out["edges_created"] == 1
    assert out["plants_skipped"] == 0
    session.run.assert_called_once()
    # rows kwarg 안에 utilization_pct 계산 검증
    rows = session.run.call_args.kwargs["rows"]
    assert len(rows) == 1
    assert rows[0]["capa_units"] == 1700000
    assert rows[0]["actual_units"] == 1900000
    # 1900000 / 1700000 * 100 ≈ 111.76
    assert rows[0]["utilization_pct"] == round(1900000 / 1700000 * 100, 2)
    assert rows[0]["source_type"] == "dart_business_report"
    assert rows[0]["confidence_score"] == 0.80


def test_sync_manufactured_at_skips_unmapped_plants(monkeypatch, caplog):
    """plants.yaml 미등록 plant — edge 0 + 경고.

    2026-06-01 HMI/HTMV 등은 매핑되었으므로 가상 라벨 사용.
    """
    monkeypatch.setattr(L, "_resolve_manufacturer_id", lambda cc: 441)
    # driver mock (호출 안 되어야 함)
    session = mock.MagicMock()
    driver = mock.MagicMock()
    driver.session.return_value.__enter__.return_value = session
    monkeypatch.setattr("autonexusgraph.db.neo4j.get_driver", lambda: driver)

    capacity = [PlantRow(business_division="차량부문",
                          plant_code="NONEXISTENT_LABEL",
                          plant_region="인도", year=2024, value=750000.0)]
    out = L._sync_manufactured_at_to_neo4j(
        capacity_rows=capacity, production_rows=[],
        corp_code="00164742", rcept_no="TEST")
    assert out["edges_created"] == 0
    assert out["plants_skipped"] == 1


def test_sync_manufactured_at_no_mfr_id_short_circuits(monkeypatch):
    """manufacturer_id 미해결 (한온 등 supplier) — Neo4j 호출 자체 안 함."""
    monkeypatch.setattr(L, "_resolve_manufacturer_id", lambda cc: None)
    # driver 호출하면 안 됨 (회피 검증)
    driver_called = {"n": 0}
    def _bad_driver():
        driver_called["n"] += 1
        raise AssertionError("driver 호출 안 되어야 함")
    monkeypatch.setattr("autonexusgraph.db.neo4j.get_driver", _bad_driver)

    out = L._sync_manufactured_at_to_neo4j(
        capacity_rows=[PlantRow(plant_code="HMC", year=2024, value=1.0)],
        production_rows=[], corp_code="00161125", rcept_no="x")
    assert out["edges_created"] == 0
    assert driver_called["n"] == 0


# ── run() dry_run ─────────────────────────────────────────────
def test_run_dry_run_does_not_call_get_connection(monkeypatch, tmp_path):
    """dry_run=True → PG 미접속."""
    class FakeSettings:
        ingest_raw_dir = tmp_path
    monkeypatch.setattr(L, "get_settings", lambda: FakeSettings())

    with mock.patch("autonexusgraph.db.postgres.get_connection") as gc:
        L.run(corp_codes=["00164742"], sync_neo4j=False, dry_run=True)
        assert gc.call_count == 0


def test_run_dry_run_with_no_zips(monkeypatch, tmp_path):
    """zip 없으면 0 통계."""
    class FakeSettings:
        ingest_raw_dir = tmp_path
    monkeypatch.setattr(L, "get_settings", lambda: FakeSettings())
    out = L.run(corp_codes=["00164742"], sync_neo4j=False, dry_run=True)
    assert out["corp_codes_seen"] == 1
    assert out["zips_seen"] == 0
    assert out["zips_parsed"] == 0
