"""DART 사업보고서 "생산 및 설비" 파서 단위 테스트.

핵심 회귀 보호:
- 섹션 헤더 정규식 (생산능력 / 생산실적 / 가동률) — 변형 헤더 패턴
- ROWSPAN 상속 — 사업부문이 첫 행에만 있고 후속 행에서 plant_code 가 첫 cell
- 숫자 파싱 — 콤마·공백·'-' 처리
- lenient XML — unescaped & 같은 잘못된 토큰 견뎌야 함
- 빈 입력 / 빈 표 — graceful (빈 list)
"""

from __future__ import annotations

import pytest

from autograph.extractors.dart_production_parser import (
    PlantRow,
    parse_business_report,
    parse_section,
    _parse_number,
    _extract_years_from_header,
)


# ── _parse_number ────────────────────────────────────────────────
def test_parse_number_comma_grouped():
    assert _parse_number("1,670,690") == 1670690.0
    assert _parse_number("1,670,690 ") == 1670690.0
    assert _parse_number(" 370,000  ") == 370000.0


def test_parse_number_dash_returns_none():
    assert _parse_number("-") is None
    assert _parse_number("—") is None
    assert _parse_number("") is None


def test_parse_number_invalid_returns_none():
    assert _parse_number("abc") is None


# ── _extract_years_from_header ───────────────────────────────────
def test_extract_years_from_dart_header():
    hdr = ["사업부문", "법인명", "소재지",
           "2023년(제56기)", "2022년(제55기)", "2021년(제54기)"]
    assert _extract_years_from_header(hdr) == [2023, 2022, 2021]


def test_extract_years_from_simple_header():
    """단순 '2024년' / '2023년' 같은 형식."""
    assert _extract_years_from_header(["회계연도", "2024년", "2023년"]) == [2024, 2023]


def test_extract_years_empty_returns_empty():
    assert _extract_years_from_header([]) == []
    assert _extract_years_from_header(["a", "b"]) == []


# ── parse_section — 인공 minimal XML ─────────────────────────────
_MINIMAL_CAPACITY_XML = """<DOCUMENT>
<P><SPAN>(1) 생산능력 (단위: 대)</SPAN></P>
<TABLE>
  <TBODY>
    <TR>
      <TD>사업부문</TD><TD>법인명</TD><TD>소재지</TD>
      <TD>2023년(제56기)</TD><TD>2022년(제55기)</TD><TD>2021년(제54기)</TD>
    </TR>
    <TR>
      <TD>차량부문</TD><TD>HMC</TD><TD>한국</TD>
      <TD>1,670,690</TD><TD>1,633,800</TD><TD>1,612,000</TD>
    </TR>
    <TR>
      <TD>HMMA</TD><TD>북미</TD>
      <TD>356,100</TD><TD>360,000</TD><TD>370,000</TD>
    </TR>
    <TR>
      <TD>HMMR</TD><TD>유럽</TD>
      <TD>-</TD><TD>200,000</TD><TD>200,000</TD>
    </TR>
  </TBODY>
</TABLE>
</DOCUMENT>
"""


def test_parse_capacity_extracts_first_row():
    rows = parse_section(_MINIMAL_CAPACITY_XML, "capacity")
    hmc_rows = [r for r in rows if r.plant_code == "HMC"]
    assert len(hmc_rows) == 3
    by_year = {r.year: r.value for r in hmc_rows}
    assert by_year == {2023: 1670690.0, 2022: 1633800.0, 2021: 1612000.0}
    # division 정확
    assert all(r.business_division == "차량부문" for r in hmc_rows)
    assert all(r.plant_region == "한국" for r in hmc_rows)


def test_parse_capacity_rowspan_inheritance():
    """첫 행에만 division — 후속 HMMA 행도 같은 division 상속해야."""
    rows = parse_section(_MINIMAL_CAPACITY_XML, "capacity")
    hmma_rows = [r for r in rows if r.plant_code == "HMMA"]
    assert len(hmma_rows) == 3
    assert all(r.business_division == "차량부문" for r in hmma_rows)
    assert all(r.plant_region == "북미" for r in hmma_rows)
    by_year = {r.year: r.value for r in hmma_rows}
    assert by_year == {2023: 356100.0, 2022: 360000.0, 2021: 370000.0}


def test_parse_capacity_dash_value_becomes_none():
    """'-' 값은 PlantRow.value = None 으로 보존 (drop 안 함)."""
    rows = parse_section(_MINIMAL_CAPACITY_XML, "capacity")
    hmmr_2023 = [r for r in rows if r.plant_code == "HMMR" and r.year == 2023]
    assert len(hmmr_2023) == 1
    assert hmmr_2023[0].value is None


def test_parse_section_unknown_raises():
    with pytest.raises(ValueError):
        parse_section("<X/>", "unknown_section")


# ── lenient XML — unescaped & 등 ────────────────────────────────
_MALFORMED_XML = """<DOCUMENT>
<P><SPAN>비정상 토큰: S&P(미국)</SPAN></P>
<P><SPAN>(1) 생산능력</SPAN></P>
<TABLE>
  <TBODY>
    <TR><TD>사업부문</TD><TD>법인명</TD><TD>소재지</TD>
        <TD>2024년</TD></TR>
    <TR><TD>차량부문</TD><TD>HMC</TD><TD>한국</TD>
        <TD>1,000,000</TD></TR>
  </TBODY>
</TABLE>
</DOCUMENT>
"""


def test_lenient_parser_handles_unescaped_ampersand():
    rows = parse_section(_MALFORMED_XML, "capacity")
    # XML 정상 파싱되어 HMC 행 추출되어야
    assert len(rows) == 1
    assert rows[0].plant_code == "HMC"
    assert rows[0].value == 1000000.0
    assert rows[0].year == 2024


# ── parse_business_report 통합 ──────────────────────────────────
_FULL_XML = _MINIMAL_CAPACITY_XML.replace(
    "(1) 생산능력 (단위: 대)",
    "(1) 생산능력 (단위: 대)",
).replace(
    "</DOCUMENT>",
    """<P><SPAN>(2) 생산실적 (단위: 대)</SPAN></P>
<TABLE>
  <TBODY>
    <TR><TD>사업부문</TD><TD>법인명</TD><TD>소재지</TD>
        <TD>2023년</TD><TD>2022년</TD><TD>2021년</TD></TR>
    <TR><TD>차량부문</TD><TD>HMC</TD><TD>한국</TD>
        <TD>1,947,351</TD><TD>1,732,639</TD><TD>1,620,231</TD></TR>
  </TBODY>
</TABLE>
</DOCUMENT>
""",
)


def test_parse_business_report_extracts_both_sections():
    out = parse_business_report(_FULL_XML, rcept_no="TEST_001")
    assert out.source_rcept_no == "TEST_001"
    assert len(out.capacity) >= 3   # 3 plants × 3 years × 일부 (HMC만 보장)
    assert len(out.production) == 3
    # production 의 HMC 2023 정확
    hmc_2023_prod = [r for r in out.production
                     if r.plant_code == "HMC" and r.year == 2023]
    assert len(hmc_2023_prod) == 1
    assert hmc_2023_prod[0].value == 1947351.0


def test_parse_empty_xml_returns_empty():
    assert parse_section("", "capacity") == []
    assert parse_business_report("").capacity == []


def test_parse_garbage_returns_empty():
    out = parse_section("not even XML at all >>><<<", "capacity")
    assert out == []


def test_parse_section_without_header_returns_empty():
    """헤더 SPAN 없이 표만 있으면 빈 list (oversearch 방지)."""
    no_header_xml = """<DOCUMENT>
<TABLE><TBODY>
  <TR><TD>법인</TD><TD>한국</TD><TD>2023년</TD></TR>
  <TR><TD>HMC</TD><TD>한국</TD><TD>1,000,000</TD></TR>
</TBODY></TABLE>
</DOCUMENT>"""
    assert parse_section(no_header_xml, "capacity") == []
