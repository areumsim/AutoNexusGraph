"""Plant wiki enrichment loader 단위 테스트 — mock DB.

build_rows 의 메타 추출 로직 + ko 우선 정책 검증. 실제 Neo4j MERGE 는
integration 테스트 영역.
"""

from __future__ import annotations

from unittest import mock

import pytest

from autograph.loaders import load_plant_wiki_enrichment as L


def test_build_rows_extracts_code_from_uniq():
    """metadata.uniq = 'wikipedia_auto::ko::plants::HYU_ULSAN' → code=HYU_ULSAN."""
    fake_rows = [
        ("ko", "현대자동차 울산공장", "https://ko.wikipedia.org/wiki/현대자동차",
         "Q5928430", "1500",
         "제목: 현대자동차 울산공장\n\n본문 내용...",
         {"uniq": "wikipedia_auto::ko::plants::HYU_ULSAN"}),
    ]
    with mock.patch("autonexusgraph.db.postgres.get_pool") as gp:
        fake_cur = mock.MagicMock()
        fake_cur.fetchall.return_value = fake_rows
        fake_conn = mock.MagicMock()
        fake_conn.cursor.return_value.__enter__.return_value = fake_cur
        gp.return_value.connection.return_value.__enter__.return_value = fake_conn
        rows = L._build_rows()
    assert len(rows) == 1
    assert rows[0]["code"] == "HYU_ULSAN"
    assert rows[0]["wikipedia_url"].startswith("https://")
    assert rows[0]["lang"] == "ko"
    # description 에서 '제목:' 라인 제거
    assert "제목" not in rows[0]["description"]


def test_build_rows_ko_takes_precedence_over_en():
    """같은 plant 의 ko + en 양쪽 존재 시 ko 우선."""
    fake_rows = [
        ("ko", "한국 위키", "url-ko", "Q1", "100", "ko 본문",
         {"uniq": "wikipedia_auto::ko::plants::CODE_X"}),
        ("en", "English wiki", "url-en", "Q1", "200", "en body",
         {"uniq": "wikipedia_auto::en::plants::CODE_X"}),
    ]
    with mock.patch("autonexusgraph.db.postgres.get_pool") as gp:
        fake_cur = mock.MagicMock()
        fake_cur.fetchall.return_value = fake_rows
        fake_conn = mock.MagicMock()
        fake_conn.cursor.return_value.__enter__.return_value = fake_cur
        gp.return_value.connection.return_value.__enter__.return_value = fake_conn
        rows = L._build_rows()
    assert len(rows) == 1
    assert rows[0]["lang"] == "ko"
    assert rows[0]["wikipedia_url"] == "url-ko"


def test_build_rows_en_falls_through_if_no_ko():
    """ko 없으면 en 사용."""
    fake_rows = [
        ("en", "BMW Dingolfing", "url-en", None, "300", "BMW body",
         {"uniq": "wikipedia_auto::en::plants::BMW_DINGOLFING"}),
    ]
    with mock.patch("autonexusgraph.db.postgres.get_pool") as gp:
        fake_cur = mock.MagicMock()
        fake_cur.fetchall.return_value = fake_rows
        fake_conn = mock.MagicMock()
        fake_conn.cursor.return_value.__enter__.return_value = fake_cur
        gp.return_value.connection.return_value.__enter__.return_value = fake_conn
        rows = L._build_rows()
    assert len(rows) == 1
    assert rows[0]["lang"] == "en"


def test_build_rows_skips_invalid_uniq():
    """malformed uniq → row skip."""
    fake_rows = [
        ("ko", "x", "u", None, "100", "body", {"uniq": "wrong-format"}),
    ]
    with mock.patch("autonexusgraph.db.postgres.get_pool") as gp:
        fake_cur = mock.MagicMock()
        fake_cur.fetchall.return_value = fake_rows
        fake_conn = mock.MagicMock()
        fake_conn.cursor.return_value.__enter__.return_value = fake_cur
        gp.return_value.connection.return_value.__enter__.return_value = fake_conn
        rows = L._build_rows()
    assert rows == []


def test_run_dry_run_skips_neo4j():
    with mock.patch.object(L, "_build_rows", return_value=[
        {"code": "X", "description": "d", "wikipedia_url": "u",
         "wikipedia_title": "t", "lang": "ko", "extract_len": 100}
    ]):
        with mock.patch("autonexusgraph.db.neo4j.get_driver") as gd:
            gd.side_effect = AssertionError("dry_run 시 driver 호출 안 됨")
            out = L.run(dry_run=True)
    assert out["plants_with_wiki"] == 1
    assert out["merged"] == 0


def test_run_empty_chunks_returns_graceful():
    with mock.patch.object(L, "_build_rows", return_value=[]):
        out = L.run(dry_run=False)
    assert out["plants_with_wiki"] == 0
    assert out["merged"] == 0


def test_description_strips_title_prefix():
    """text 가 '제목: X\\n본문' 형식이면 본문만 남음."""
    fake_rows = [
        ("ko", "T", "u", None, "100",
         "제목: 현대자동차\n\n현대자동차는 1967년 설립...",
         {"uniq": "wikipedia_auto::ko::plants::HYU_ULSAN"}),
    ]
    with mock.patch("autonexusgraph.db.postgres.get_pool") as gp:
        fake_cur = mock.MagicMock()
        fake_cur.fetchall.return_value = fake_rows
        fake_conn = mock.MagicMock()
        fake_conn.cursor.return_value.__enter__.return_value = fake_cur
        gp.return_value.connection.return_value.__enter__.return_value = fake_conn
        rows = L._build_rows()
    assert rows[0]["description"].startswith("현대자동차는 1967")


def test_description_truncates_at_300():
    fake_rows = [
        ("ko", "T", "u", None, "100",
         "x" * 1000,
         {"uniq": "wikipedia_auto::ko::plants::HYU_ULSAN"}),
    ]
    with mock.patch("autonexusgraph.db.postgres.get_pool") as gp:
        fake_cur = mock.MagicMock()
        fake_cur.fetchall.return_value = fake_rows
        fake_conn = mock.MagicMock()
        fake_conn.cursor.return_value.__enter__.return_value = fake_cur
        gp.return_value.connection.return_value.__enter__.return_value = fake_conn
        rows = L._build_rows()
    assert len(rows[0]["description"]) <= 300
