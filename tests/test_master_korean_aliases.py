"""한국어 alias backfill loader 테스트 — mock DB."""

from __future__ import annotations

from unittest import mock

import pytest

from autograph.loaders import load_master_korean_aliases as L


def test_existing_aliases_shape():
    """모든 alias dict 키는 NHTSA vPIC 표준 영문, 값은 한국어 list."""
    assert "HYUNDAI" in L.EXISTING_ALIASES
    assert "KIA" in L.EXISTING_ALIASES
    assert "CHEVROLET" in L.EXISTING_ALIASES   # 한국지엠 alias 대상
    for name, aliases in L.EXISTING_ALIASES.items():
        assert isinstance(aliases, list)
        assert all(isinstance(a, str) and a.strip() for a in aliases)


def test_hyundai_aliases_include_common_korean_variants():
    aliases = L.EXISTING_ALIASES["HYUNDAI"]
    # 자주 등장하는 한국어 변형
    assert "현대자동차" in aliases
    assert "현대차" in aliases
    assert "현대자동차주식회사" in aliases


def test_kia_aliases_include_korean_variants():
    aliases = L.EXISTING_ALIASES["KIA"]
    assert "기아" in aliases
    assert "기아자동차" in aliases


def test_kgm_oem_has_ssangyong_alias():
    """KGM 신규 entry 가 쌍용자동차 alias 포함 (사명 변경 대응)."""
    kgm = next((o for o in L.NEW_OEMS if o["name"] == "KGM"), None)
    assert kgm is not None
    assert "쌍용자동차" in kgm["aliases"]
    assert "쌍용차" in kgm["aliases"]
    assert "KG모빌리티" in kgm["aliases"]


def test_renault_korea_oem():
    rnk = next((o for o in L.NEW_OEMS if o["name"] == "RENAULT KOREA"), None)
    assert rnk is not None
    assert "르노코리아" in rnk["aliases"]
    assert "르노삼성자동차" in rnk["aliases"]


def test_new_oem_ids_in_manual_range():
    """신규 manufacturer_id ≥ 2_000_000_000 (manual 영역, 충돌 회피)."""
    for o in L.NEW_OEMS:
        assert o["manufacturer_id"] >= 2_000_000_000


def test_new_oems_have_kr_country():
    """신규 등록 entries 는 모두 한국 OEM."""
    for o in L.NEW_OEMS:
        assert o["country"] == "KR"


def test_run_dry_run_no_db_call(monkeypatch):
    """dry_run=True 면 get_connection 호출 0."""
    monkeypatch.setattr("autonexusgraph.db.postgres.get_connection",
                        lambda: pytest.fail("dry_run 시 DB 호출 안 됨"))
    out = L.run(dry_run=True)
    assert out["existing_to_update"] > 0
    assert out["new_oems"] == 2
    assert out["applied"] == 0


def test_backfill_only_empty_aliases():
    """EXISTING_ALIASES UPDATE 가 aliases='{}' OR NULL 조건 사용 — 수동 보강
    행은 건드리지 않음."""
    fake_cur = mock.MagicMock()
    fake_cur.fetchall.return_value = []
    fake_conn = mock.MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cur
    L._backfill_existing(fake_conn)
    sql_seen = [call[0][0] for call in fake_cur.execute.call_args_list]
    assert any("aliases = '{}' OR aliases IS NULL" in sql for sql in sql_seen), \
        "UPDATE 가 빈 aliases 조건 누락 — 수동 보강 행 덮어쓰기 위험"


def test_new_oems_uses_on_conflict():
    """신규 OEM INSERT 가 ON CONFLICT 절 보유 — 멱등."""
    fake_cur = mock.MagicMock()
    fake_cur.fetchone.return_value = (True,)
    fake_conn = mock.MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cur
    L._insert_new_oems(fake_conn)
    sql_seen = [call[0][0] for call in fake_cur.execute.call_args_list]
    assert any("ON CONFLICT" in sql for sql in sql_seen)
