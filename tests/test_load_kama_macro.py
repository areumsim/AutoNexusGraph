"""KAMA 매크로 통계 (15051116 yearly / 15051118 monthly) loader 단위 테스트.

DB 없이 CSV 파싱 / encoding 자동 감지 / row 정규화만 검증. 실제 PG 적재는
integration 영역.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from autograph.loaders.load_kama_macro import (
    _coerce_int,
    _find_csvs,
    _open_csv,
    _parse_monthly_row,
    _parse_yearly_row,
    run,
)


# ── _coerce_int ──────────────────────────────────────────────────
def test_coerce_int_comma_grouped():
    assert _coerce_int("1,234,567") == 1234567


def test_coerce_int_negative_signals():
    assert _coerce_int("-") is None
    assert _coerce_int("") is None
    assert _coerce_int(None) is None
    assert _coerce_int("  ") is None


def test_coerce_int_float_string():
    assert _coerce_int("3699.0") == 3699


# ── _parse_yearly_row ────────────────────────────────────────────
def test_parse_yearly_row_basic():
    row = {"연도": "2024",
           "국내생산(1000대)": "4128",
           "세계생산(1000대)": "90662"}
    assert _parse_yearly_row(row) == (2024, 4128, 90662)


def test_parse_yearly_row_missing_year_returns_none():
    assert _parse_yearly_row({"연도": "",
                              "국내생산(1000대)": "100",
                              "세계생산(1000대)": "200"}) is None


def test_parse_yearly_row_partial_values():
    row = {"연도": "2010",
           "국내생산(1000대)": "4272",
           "세계생산(1000대)": ""}
    out = _parse_yearly_row(row)
    assert out == (2010, 4272, None)


# ── _parse_monthly_row ───────────────────────────────────────────
def test_parse_monthly_row_basic():
    row = {"기간": "2024-12",
           "내수판매(국산차)": "130000",
           "수출량": "220000",
           "수출금액(천달러)": "3500000"}
    assert _parse_monthly_row(row) == (2024, 12, 130000, 220000, 3500000)


def test_parse_monthly_row_zero_padded_month():
    row = {"기간": "2009-01",
           "내수판매(국산차)": "73874",
           "수출량": "122946",
           "수출금액(천달러)": "1376094"}
    assert _parse_monthly_row(row) == (2009, 1, 73874, 122946, 1376094)


def test_parse_monthly_row_invalid_period_returns_none():
    assert _parse_monthly_row({"기간": "2024", "내수판매(국산차)": "1"}) is None
    assert _parse_monthly_row({"기간": "abc", "내수판매(국산차)": "1"}) is None


def test_parse_monthly_row_invalid_month_returns_none():
    assert _parse_monthly_row({"기간": "2024-13", "내수판매(국산차)": "1"}) is None
    assert _parse_monthly_row({"기간": "2024-00", "내수판매(국산차)": "1"}) is None


# ── _open_csv — encoding 자동 감지 ──────────────────────────────
def _write_csv(p: Path, *, content: str, encoding: str) -> None:
    p.write_text(content, encoding=encoding)


def test_open_csv_utf8_yearly(tmp_path):
    p = tmp_path / "yr.csv"
    _write_csv(p, content="연도,국내생산(1000대),세계생산(1000대)\n2024,4128,90662\n",
               encoding="utf-8")
    rows = _open_csv(p, expected_header_token="연도")
    assert rows == [{"연도": "2024", "국내생산(1000대)": "4128", "세계생산(1000대)": "90662"}]


def test_open_csv_cp949_monthly(tmp_path):
    p = tmp_path / "mo.csv"
    _write_csv(p,
               content="기간,내수판매(국산차),수출량,수출금액(천달러)\n2024-12,130000,220000,3500000\n",
               encoding="cp949")
    rows = _open_csv(p, expected_header_token="기간")
    assert len(rows) == 1
    assert rows[0]["기간"] == "2024-12"


def test_open_csv_no_header_token_returns_empty(tmp_path):
    p = tmp_path / "bad.csv"
    _write_csv(p, content="a,b,c\n1,2,3\n", encoding="utf-8")
    rows = _open_csv(p, expected_header_token="연도")
    assert rows == []


# ── _find_csvs — 디렉토리 glob ──────────────────────────────────
def test_find_csvs_both_present(tmp_path):
    (tmp_path / "산업통상부_국내 및 세계 자동차 생산량(한국자동차산업협회)_20251231.csv").write_text("")
    (tmp_path / "산업통상부_전체 자동차 산업 현황_20251231.csv").write_text("")
    yearly, monthly = _find_csvs(root=tmp_path)
    assert yearly is not None and "국내 및 세계" in yearly.name
    assert monthly is not None and "전체 자동차 산업" in monthly.name


def test_find_csvs_missing_dir_returns_none(tmp_path):
    yearly, monthly = _find_csvs(root=tmp_path / "nope")
    assert yearly is None and monthly is None


def test_find_csvs_partial(tmp_path):
    """yearly 만 있고 monthly 는 없는 경우."""
    (tmp_path / "산업통상부_국내 및 세계 자동차 생산량_2024.csv").write_text("")
    yearly, monthly = _find_csvs(root=tmp_path)
    assert yearly is not None
    assert monthly is None


def test_find_csvs_picks_latest_when_multiple(tmp_path):
    """동일 패턴 여러 파일이면 sort 후 마지막 (가장 최근 YYYYMMDD)."""
    (tmp_path / "산업통상부_국내 및 세계 자동차 생산량_20231231.csv").write_text("")
    (tmp_path / "산업통상부_국내 및 세계 자동차 생산량_20251231.csv").write_text("")
    yearly, _ = _find_csvs(root=tmp_path)
    assert "20251231" in yearly.name


# ── run() dry_run ────────────────────────────────────────────────
def test_run_dry_run_with_both_csvs(tmp_path):
    yearly = tmp_path / "산업통상부_국내 및 세계 자동차 생산량_2025.csv"
    yearly.write_text(
        "연도,국내생산(1000대),세계생산(1000대)\n"
        "2023,4244,91021\n2024,4128,90662\n",
        encoding="utf-8")
    monthly = tmp_path / "산업통상부_전체 자동차 산업 현황_2025.csv"
    monthly.write_text(
        "기간,내수판매(국산차),수출량,수출금액(천달러)\n"
        "2024-01,100000,200000,3000000\n"
        "2024-02,110000,210000,3100000\n"
        "bad-row,X,Y,Z\n",
        encoding="utf-8")

    out = run(root=tmp_path, dry_run=True)
    assert out["yearly"]["n_rows"] == 2
    assert out["yearly"]["valid_rows"] == 2
    assert out["yearly"]["inserted"] == 0   # dry_run
    assert out["monthly"]["n_rows"] == 3
    assert out["monthly"]["valid_rows"] == 2   # 'bad-row' 는 skip


def test_run_missing_csvs_returns_graceful(tmp_path):
    out = run(root=tmp_path / "nope", dry_run=True)
    assert out["yearly"]["csv"] is None
    assert out["monthly"]["csv"] is None
    assert out["yearly"]["inserted"] == 0
    assert out["monthly"]["inserted"] == 0


def test_run_does_not_call_get_connection_in_dry_run(tmp_path):
    """dry_run=True 면 PG 미접속 — 인프라 없는 환경 안전 확인."""
    (tmp_path / "산업통상부_국내 및 세계 자동차 생산량_2025.csv").write_text(
        "연도,국내생산(1000대),세계생산(1000대)\n2024,4128,90662\n",
        encoding="utf-8")

    with mock.patch("autonexusgraph.db.postgres.get_connection") as gc:
        run(root=tmp_path, dry_run=True)
        assert gc.call_count == 0
