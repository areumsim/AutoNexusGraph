"""master.entities 스키마 + 마이그레이션 unit 테스트.

PG 미연결 환경에서도 동작하도록 SQL 파일 텍스트 검증과 모듈 importability
중심으로 작성. 실제 PG round-trip 은 별도 integration 테스트가 담당.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
SQL_FILE = REPO / "infra" / "postgres" / "init" / "14_master_entities.sql"


# ── 1) SQL 스키마 파일 형태 검증 ────────────────────────────────────────

def test_sql_file_exists():
    assert SQL_FILE.exists(), f"missing: {SQL_FILE}"


def test_sql_defines_master_entities_table():
    text = SQL_FILE.read_text(encoding="utf-8")
    # PRD §4.5 필수 컬럼 — 누락 시 마이그·로더가 실패.
    required_columns = [
        "entity_id", "entity_type", "canonical_name", "wikidata_qid",
        "lei", "corp_code", "business_no", "cik",
        "nhtsa_model_id", "nhtsa_campaign_id", "car_go_kr_id",
        "source_priority", "confidence_score",
        "valid_from", "valid_to", "schema_version",
    ]
    create = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+master\.entities\s*\((.*?)\);",
        text, re.DOTALL,
    )
    assert create, "CREATE TABLE master.entities 정의 없음"
    body = create.group(1)
    for col in required_columns:
        assert re.search(rf"\b{col}\b", body), f"컬럼 누락: {col}"


def test_sql_entity_type_check_lists_eight_types():
    text = SQL_FILE.read_text(encoding="utf-8")
    expected = {
        "manufacturer", "supplier", "vehicle_model", "vehicle_variant",
        "component", "recall", "standard", "plant",
    }
    # CHECK (entity_type IN (...)) 절에서 모든 enum 값 등장 보장.
    chk = re.search(
        r"entity_type\s+IN\s*\(([^)]+)\)", text, re.DOTALL,
    )
    assert chk, "entity_type CHECK 절 없음"
    found = set(re.findall(r"'([a-z_]+)'", chk.group(1)))
    missing = expected - found
    assert not missing, f"entity_type CHECK 에서 누락된 타입: {missing}"


def test_sql_has_partial_indexes_for_external_ids():
    text = SQL_FILE.read_text(encoding="utf-8")
    # 각 외부 식별자 컬럼에 partial index 가 있어야 lookup 효율 ↑.
    for col in ("wikidata_qid", "corp_code", "lei", "business_no",
                "cik", "nhtsa_model_id", "nhtsa_campaign_id", "car_go_kr_id"):
        # WHERE col IS NOT NULL 형태의 partial index 확인.
        pattern = rf"CREATE INDEX[^;]+\({col}\)[^;]+WHERE\s+{col}\s+IS NOT NULL"
        assert re.search(pattern, text, re.IGNORECASE), \
            f"partial index 누락: {col}"


def test_sql_defines_active_view_and_updated_at_trigger():
    text = SQL_FILE.read_text(encoding="utf-8")
    assert re.search(r"CREATE OR REPLACE VIEW\s+master\.entities_active",
                     text), "entities_active 뷰 없음"
    assert "tg_entities_updated_at" in text, "updated_at 트리거 없음"


# ── 2) 마이그레이션 스크립트 구조 검증 ──────────────────────────────────

def test_migration_module_importable():
    """import 자체가 PG 연결 없이 성공해야 한다 (DB 핸들은 함수 내부에서만)."""
    mod = pytest.importorskip("scripts.migrate.migrate_entity_map_to_entities")
    assert hasattr(mod, "migrate"), "migrate() 함수 없음"
    assert hasattr(mod, "ID_TYPE_TO_COLUMN"), "ID_TYPE_TO_COLUMN 매핑 없음"


def test_migration_id_type_mapping_covers_required_external_ids():
    mod = pytest.importorskip("scripts.migrate.migrate_entity_map_to_entities")
    mapping = mod.ID_TYPE_TO_COLUMN
    # entity_map.id_type 의 표준 외부 키 4종이 모두 entities 컬럼으로 매핑돼야 한다.
    required = {"wikidata_qid", "lei", "business_no", "cik"}
    assert required.issubset(set(mapping.keys())), \
        f"미매핑 id_type: {required - set(mapping.keys())}"
    # 매핑 값은 entities 의 실제 컬럼명과 동일.
    sql = SQL_FILE.read_text(encoding="utf-8")
    for col in mapping.values():
        assert re.search(rf"\b{col}\s+VARCHAR", sql), \
            f"매핑 컬럼이 SQL 에 없음: {col}"


def test_migration_uses_on_conflict_for_idempotency():
    """재실행해도 row 가 중복 생성되지 않도록 ON CONFLICT 사용 보장."""
    mig = (REPO / "scripts" / "migrate"
           / "migrate_entity_map_to_entities.py").read_text(encoding="utf-8")
    assert "ON CONFLICT (entity_id) DO UPDATE" in mig, \
        "companies → entities upsert 가 멱등하지 않음"
    # entity_map enrich 도 NULL 컬럼만 채우는 가드 필요.
    assert re.search(r"WHERE.*IS NULL", mig, re.DOTALL), \
        "entity_map enrich 가 기존 값을 덮어쓸 위험"
