"""산단공 자동차 부품 제조업 공정 합성데이터 (15151075) loader 단위 테스트.

DB 없이 CSV 파싱 / 정규화 / 인코딩 자동 감지만 검증. 실제 PG 적재는
integration 테스트 영역.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autograph.loaders.load_sandang_processes import (
    _find_csv,
    _normalize_process_name,
    _open_csv,
    run,
)


# ── _normalize_process_name ──────────────────────────────────────
def test_normalize_strips_whitespace():
    assert _normalize_process_name("  전처리  ") == "전처리"


def test_normalize_collapses_internal_whitespace():
    assert _normalize_process_name("스프레이  도장") == "스프레이 도장"


def test_normalize_lowercases():
    assert _normalize_process_name("CNC 가공") == "cnc 가공"


def test_normalize_empty():
    assert _normalize_process_name("") == ""
    assert _normalize_process_name(None) == ""   # type: ignore[arg-type]


# ── _find_csv ────────────────────────────────────────────────────
def test_find_csv_explicit_path_priority(tmp_path):
    p = tmp_path / "explicit.csv"
    p.write_text("dummy")
    assert _find_csv(str(p)) == p


def test_find_csv_explicit_path_missing_returns_none(tmp_path):
    p = tmp_path / "nope.csv"
    assert _find_csv(str(p)) is None


# ── _open_csv — 인코딩 자동 감지 ─────────────────────────────────
_CSV_HEADER = "공장관리번호,업종차수,업종코드,공정도명,공정도설명,공정순서,공정명,공정설명\n"
_CSV_BODY = "12345,11,30399,자동차 내장 부품,설명,1,전처리,원재료 전처리\n"


def test_open_csv_utf8(tmp_path):
    p = tmp_path / "utf8.csv"
    p.write_text(_CSV_HEADER + _CSV_BODY, encoding="utf-8")
    rows = _open_csv(p)
    assert len(rows) == 1
    assert rows[0]["공정명"] == "전처리"
    assert rows[0]["공장관리번호"] == "12345"


def test_open_csv_euc_kr(tmp_path):
    p = tmp_path / "euckr.csv"
    p.write_text(_CSV_HEADER + _CSV_BODY, encoding="euc-kr")
    rows = _open_csv(p)
    assert len(rows) == 1
    assert rows[0]["공정명"] == "전처리"


def test_open_csv_utf8_bom(tmp_path):
    p = tmp_path / "bom.csv"
    p.write_text(_CSV_HEADER + _CSV_BODY, encoding="utf-8-sig")
    rows = _open_csv(p)
    assert len(rows) == 1
    # utf-8-sig 디코드 시 BOM 제거되어 첫 컬럼명 정확
    assert "공정명" in rows[0]


# ── run() dry-run 통계 ───────────────────────────────────────────
def test_run_dry_run_with_explicit_csv(tmp_path):
    """dry_run=True 면 PG 호출 없이 통계만 — DB 미가용 환경에서도 안전."""
    csv = tmp_path / "test.csv"
    body = (_CSV_HEADER
            + "12345,11,30399,자동차 내장 부품,설명,1,전처리,원재료 전처리\n"
            + "12345,11,30399,자동차 내장 부품,설명,2,스프레이도장,도장 작업\n"
            + "67890,11,30399,자동차 섀시 부품,설명,1,전처리,섀시 전처리\n")
    csv.write_text(body, encoding="utf-8")

    result = run(csv_path=str(csv), dry_run=True)
    assert result["n_rows"] == 3
    assert result["distinct_process_names"] == 2   # 전처리, 스프레이도장
    assert result["distinct_industries"] == 1
    assert result["inserted"] == 0
    assert result["updated"] == 0


def test_run_missing_csv_returns_graceful(tmp_path, monkeypatch):
    """CSV 없으면 0 returns + warning 만 — exit 1 안 함."""
    from autonexusgraph.config import get_settings
    # csv_path None + datagokr 디렉토리 비어있음 → 빈 결과
    result = run(csv_path=str(tmp_path / "nonexistent.csv"), dry_run=True)
    assert result["inserted"] == 0
    assert result["updated"] == 0
    assert result["skipped"] == 0
    assert result["csv"] is None


def test_normalize_real_data_examples():
    """실제 CSV row 의 공정명 정규화 예시."""
    # 데이터 inspection 결과 — 다양한 표기.
    examples = [
        ("전처리", "전처리"),
        ("스프레이도장", "스프레이도장"),
        ("CSP렙 제거", "csp렙 제거"),
        ("  CNC 가공  ", "cnc 가공"),
    ]
    for raw, expected in examples:
        assert _normalize_process_name(raw) == expected, \
            f"{raw!r} → {_normalize_process_name(raw)!r}, expected {expected!r}"
