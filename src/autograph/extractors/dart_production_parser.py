"""DART 사업보고서 "III. 사업의 내용 → 생산 및 설비" 섹션 파서.

목적: 한국 상장 자동차 OEM 의 공장(법인)별 **생산능력 / 생산실적 / 가동률** 데이터를
사업보고서 XML 에서 추출 → ``anxg_auto.plant_capacity`` / ``anxg_auto.plant_production`` /
``anxg_auto.plant_utilization`` 으로 정형화.

원천: ``data/raw/dart_bulk/corp/<corp_code>/documents/<rcept_no>.zip`` 에 들어있는
DART XML (``dart4.xsd``). 본 파서는 zip 자체는 다루지 않고 추출된 XML 문자열을
입력으로 받는다 (loader 가 zip 핸들링).

추출 전략 — Deterministic XML table parser (LLM 0):
    1. ``<SPAN>`` 본문에서 섹션 헤더 ("(1) 생산능력", "(2) 생산실적", "(3) 가동률") 검출
    2. 각 헤더 이후의 첫 ``<TABLE>`` 위치 파악
    3. ``<TR>`` 행 단위 ``<TD>`` 추출 — 첫 행 = 헤더 (연도 추출), 이후 = 데이터
    4. 컬럼 패턴 (법인명 / 소재지 / Year1 / Year2 / Year3) 검증 후 dict 화

법인 약어(plant_code) — 본 모듈은 raw XML 값을 그대로 보존. 한국·해외 매핑은
loader 가 ``ontology/auto/plants.yaml`` 과 대조 (별도 책임).

PRD §3.5: DART 공식 공시 = B 등급 → confidence 0.80 / validated_status='validated'.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable
from xml.etree import ElementTree as ET

# DART XML 은 종종 unescaped ``&`` ('S&P(미국)') 같은 잘못된 토큰을 포함한다.
# 표준 xml.etree 는 strict parser 라 첫 violation 에서 전체 파싱 실패.
# lxml.html (또는 bs4 의 html.parser) 의 lenient 모드로 우회.
try:
    from lxml import html as _lxml_html, etree as _lxml_etree
    _HAS_LXML = True
except ImportError:
    _HAS_LXML = False

log = logging.getLogger(__name__)


# ── 섹션 헤더 패턴 ─────────────────────────────────────────────────
# DART 사업보고서는 "가/나/다/라" + "(1)/(2)/(3)" 의 nested 번호 체계를 쓴다.
# "(1) 생산능력" 또는 "다. 생산능력" 또는 "생산능력 및 생산능력의 산출근거" 등 변형 모두 매칭.
_HDR_CAPACITY = re.compile(
    r"(?:\(\s*\d+\s*\)|[가-힣]\.)\s*생산\s*능력"
    r"|생산\s*능력\s*및\s*생산\s*능력의\s*산출",
    re.UNICODE,
)
_HDR_PRODUCTION = re.compile(
    r"(?:\(\s*\d+\s*\)|[가-힣]\.)\s*생산\s*실적",
    re.UNICODE,
)
_HDR_UTILIZATION = re.compile(
    r"(?:\(\s*\d+\s*\)|[가-힣]\.)\s*가동\s*률",
    re.UNICODE,
)

# 회계연도 (제 N 기) 또는 4자리 연도 추출.
# Year 추출 — 다음 변형 모두 인식:
#   '2023년(제56기)' / '2023년' / '2024년' — Hyundai
#   '제80기('23.1.1~12.31)'                — Kia (2자리 연도 → 20XX)
_YEAR_RE = re.compile(
    r"(20\d{2})\s*년"                       # 2023년
    r"|(\d{4})\s*년\s*\(제"                  # 2023년(제
    r"|제\s*\d+\s*기\s*\(\s*'?(\d{2})\."     # 제80기('23.  → year 23
)


@dataclass
class PlantRow:
    """한 공장(법인)의 한 연도 측정값."""

    business_division: str | None = None
    plant_code: str = ""
    plant_region: str | None = None
    year: int = 0
    value: float | None = None       # 생산능력/생산실적 = 대 수, 가동률 = %
    extra: dict = field(default_factory=dict)


@dataclass
class ProductionExtract:
    """단일 사업보고서에서 뽑은 3 종 데이터."""

    capacity: list[PlantRow] = field(default_factory=list)
    production: list[PlantRow] = field(default_factory=list)
    utilization: list[PlantRow] = field(default_factory=list)
    source_rcept_no: str | None = None


# ── 텍스트 가공 헬퍼 ──────────────────────────────────────────────
def _tag(elem) -> str:
    """tag 이름 (대문자 정규형). lxml.html (소문자) / etree (혼합) 양쪽 대응."""
    t = getattr(elem, "tag", "") or ""
    if not isinstance(t, str):
        return ""
    return t.upper()


def _iter_by_tag(root, *names: str):
    """tag 이름 case-insensitive 매칭 iterator."""
    target = {n.upper() for n in names}
    for e in root.iter():
        if _tag(e) in target:
            yield e


def _text(elem) -> str:
    """엘리먼트의 모든 텍스트 (descendant 포함) 를 공백 join."""
    parts: list[str] = []
    if getattr(elem, "text", None):
        parts.append(elem.text)
    for child in elem:
        parts.append(_text(child))
        if getattr(child, "tail", None):
            parts.append(child.tail)
    return " ".join(p.strip() for p in parts if p and p.strip())


def _parse_number(s: str) -> float | None:
    """'1,670,690 ' / '-' / '1,670,690 ' → float 또는 None."""
    if not s:
        return None
    s = s.strip().replace(",", "")
    if s in ("-", "—", "–", ""):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _extract_years_from_header(header_cells: list[str]) -> list[int]:
    """헤더 cell 들에서 연도 추출. 잡힌 순서 유지.

    DART 형식 예:
        Hyundai: ['사업부문', '법인명', '소재지', '2023년(제56기)', '2022년(제55기)', '2021년(제54기)']
            → [2023, 2022, 2021]
        Kia: ['사업부문', '품목', '소재지', "제80기('23.1.1~12.31)", "제79기('22.1.1~12.31)", "제78기('21.1.1~12.31)"]
            → [2023, 2022, 2021]
    """
    out: list[int] = []
    for c in header_cells:
        m = _YEAR_RE.search(c)
        if m:
            # group(1)='2023년' 4자리 / group(2)=4자리 / group(3)='23' 2자리
            y = m.group(1) or m.group(2) or m.group(3)
            try:
                yi = int(y)
                # 2자리 연도 → 2000+
                if yi < 100:
                    yi += 2000
                out.append(yi)
                continue   # 중복 캡쳐 회피
            except (TypeError, ValueError):
                continue
    return out


# ── 핵심: XML 안에서 섹션별 테이블 찾기 ──────────────────────────
def _iter_spans_with_text(root) -> Iterable[tuple[object, str]]:
    """SPAN/P/TD 의 (elem, normalized_text) 페어 — 헤더 매칭용."""
    for elem in _iter_by_tag(root, "SPAN", "P", "TD"):
        txt = _text(elem)
        if txt:
            yield elem, txt


def _find_next_table_after(root, anchor, *, min_rows: int = 2,
                            min_cols: int = 3):
    """anchor 엘리먼트 이후 document order 의 의미있는 첫 <TABLE>.

    min_rows / min_cols 미만 표는 skip — Kia 사업보고서의 `(단위:대)` 1-cell
    안내 표 같은 경우를 건너뛰기 위함.
    """
    flat = list(root.iter())
    try:
        idx = flat.index(anchor)
    except ValueError:
        return None
    for e in flat[idx + 1:]:
        if _tag(e) != "TABLE":
            continue
        # 행/컬럼 최소 size 검사
        trs = list(_iter_by_tag(e, "TR"))
        if len(trs) < min_rows:
            continue
        max_cols = max(
            (len(list(_iter_by_tag(tr, "TD", "TH"))) for tr in trs),
            default=0,
        )
        if max_cols < min_cols:
            continue
        return e
    return None


def _parse_table_rows(table) -> tuple[list[str], list[list[str]]]:
    """첫 행 = 헤더 cell 텍스트, 나머지 = 데이터 cell 텍스트 list."""
    rows: list[list[str]] = []
    for tr in _iter_by_tag(table, "TR"):
        # TD + TH 양쪽 — Kia/일부 사업보고서는 헤더에 <TH> 사용
        cells = [_text(td) for td in _iter_by_tag(tr, "TD", "TH")]
        if cells:
            rows.append(cells)
    if not rows:
        return [], []
    return rows[0], rows[1:]


def _row_to_plant_rows(data_cells: list[str], years: list[int],
                       running_division: str | None,
                       expected_full_count: int,
                       *,
                       plant_col: int = 0,
                       region_col: int = 1,
                       ) -> tuple[list[PlantRow], str | None]:
    """한 데이터 행 → PlantRow list (연도 수만큼).

    DART 테이블은 ``ROWSPAN`` 으로 사업부문이 첫 행에만 나타나고 후속 행은
    그 cell 이 생략된다. 행의 cell 개수로 분기:

    - len(cells) == expected_full_count        → 첫 cell 이 division (새 그룹 시작)
    - len(cells) == expected_full_count - 1    → division 은 ROWSPAN 상속
    - 그 외                                    → 무관 행 (skip)

    expected_full_count 는 header cell 수 = 3 + len(years) (division+plant_code+
    region+year*N).

    반환: (rows, updated_running_division)
    """
    if not data_cells:
        return [], running_division

    n = len(data_cells)
    n_short = expected_full_count - 1

    if n == expected_full_count:
        # division cell 포함 — 새 그룹 시작
        division = data_cells[0].strip() or running_division
        running_division = division
        body_cells = data_cells[1:]
    elif n == n_short:
        # division ROWSPAN 상속
        division = running_division
        body_cells = data_cells
    else:
        # 모양이 다른 행 — skip (헤더 변형, 주석 행 등)
        return [], running_division

    if len(body_cells) < 2 + len(years):
        return [], running_division

    # 컬럼 매핑 — plant_col/region_col 은 body_cells (division 제외) 기준 index.
    # Hyundai (5-col body): [plant_code=0, region=1, y1, y2, y3]
    # Kia    (5-col body): [품목=0, 소재지=1, y1, y2, y3] → plant_col=1, region_col=None
    plant_code = body_cells[plant_col].strip()
    plant_region = (body_cells[region_col].strip() or None
                    if region_col is not None and region_col < len(body_cells)
                    else None)
    value_cells = body_cells[-len(years):]

    rows: list[PlantRow] = []
    for year, vcell in zip(years, value_cells):
        val = _parse_number(vcell)
        if val is None and plant_code in ("", "-"):
            continue
        rows.append(PlantRow(
            business_division=division,
            plant_code=plant_code,
            plant_region=plant_region,
            year=year,
            value=val,
        ))
    return rows, running_division


# ── XML lenient parsing ─────────────────────────────────────────
def _parse_dart_xml(xml_text: str):
    """DART XML 의 unescaped ``&`` 등 비표준 토큰을 견디는 lenient 파서.

    1차: lxml 의 HTML 모드 (가장 견고) — 항상 root 반환
    2차: 표준 ``xml.etree`` (lxml 없거나 실패 시) — strict
    3차: pre-process 후 표준 etree — ``&`` 를 ``&amp;`` 로 sanitize
    모두 실패 시 None.
    """
    # 1차: lxml HTML 모드 — 견고한 lenient 파서.
    # 두 가지 함정:
    #   (a) ``lxml.html.fromstring(bytes)`` 는 charset 선언 없으면 Latin-1 가정
    #       → 한글 mojibake.
    #   (b) ``lxml.html.fromstring(str)`` 는 ``<?xml ...?>`` 선언이 있으면 거부.
    # 해결: ``<?xml ...?>`` 선언이 있으면 stripped str 사용, 없으면 그대로.
    if _HAS_LXML:
        try:
            # XML 선언 제거 — lxml.html 은 str 입력에 XML 선언 거부
            text = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", xml_text)
            return _lxml_html.fromstring(text)
        except Exception as exc:   # noqa: BLE001
            log.debug("[dart_production] lxml.html 실패: %s", exc)

    # 2차: 표준 etree
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.debug("[dart_production] strict etree 실패: %s", exc)

    # 3차: ``&`` sanitize 후 재시도
    sanitized = re.sub(r"&(?![a-zA-Z#][a-zA-Z0-9]*;)", "&amp;", xml_text)
    try:
        return ET.fromstring(sanitized)
    except ET.ParseError as exc:
        log.warning("[dart_production] 모든 파서 실패: %s", exc)
        return None


# ── utilization 표 전용 파서 (2026-06-01 신규) ────────────────────
def _parse_pct(s: str) -> float | None:
    """'116.6%' / '116.6 %' / '-' → float (없으면 None)."""
    if not s:
        return None
    s = s.strip().replace(",", "").rstrip("%").strip()
    if s in ("", "-", "—", "–"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_utilization_table(data_rows: list[list[str]],
                              years: list[int]) -> list[PlantRow]:
    """Hyundai 사업보고서 "(3) 가동률" 표 — 다른 컬럼 schema 처리.

    Table layout (Hyundai 표 기준):
        Header row 0: 사업부문 / 법인명 / 소재지 / 2023년(제56기) [COLSPAN=3]
        Subheader row 1: 생산능력 / 생산실적 / 가동률(%)
        Data rows (cells=6): [사업부문(ROWSPAN), 법인명, 소재지, capa, actual, util%]
        Inherited rows (cells=5): [법인명, 소재지, capa, actual, util%]

    Args:
        data_rows: ``_parse_table_rows`` 의 ``data_rows`` (header 1 행 제거 후).
            첫 행이 subheader '생산능력/생산실적/가동률(%)' 면 자동 skip.
        years: 헤더에서 추출한 년도 list (보통 1 개).

    Returns:
        Plant 마다 1 행 — ``value=utilization_pct``, ``extra`` 에 capa/actual.
    """
    if not data_rows or not years:
        return []
    out: list[PlantRow] = []
    year = years[0]

    # subheader row skip
    rows_iter = list(data_rows)
    if rows_iter and any("생산능력" in c or "가동률" in c
                          for c in rows_iter[0]):
        rows_iter = rows_iter[1:]

    running_division: str | None = None
    for cells in rows_iter:
        n = len(cells)
        if n == 6:
            division = cells[0].strip() or running_division
            running_division = division
            plant_code = cells[1].strip()
            region = cells[2].strip() or None
            capa = _parse_number(cells[3])
            actual = _parse_number(cells[4])
            util = _parse_pct(cells[5])
        elif n == 5:
            division = running_division
            plant_code = cells[0].strip()
            region = cells[1].strip() or None
            capa = _parse_number(cells[2])
            actual = _parse_number(cells[3])
            util = _parse_pct(cells[4])
        else:
            continue
        if not plant_code or plant_code in ("-", "—"):
            continue
        out.append(PlantRow(
            business_division=division,
            plant_code=plant_code,
            plant_region=region,
            year=year,
            value=util,
            extra={"capacity_units": capa, "actual_units": actual},
        ))
    return out


# ── 공개 API ──────────────────────────────────────────────────────
def parse_section(xml_text: str, section: str) -> list[PlantRow]:
    """단일 섹션 파싱. section ∈ {'capacity', 'production', 'utilization'}.

    매칭 헤더 패턴:
        capacity   → _HDR_CAPACITY
        production → _HDR_PRODUCTION
        utilization → _HDR_UTILIZATION
    """
    pattern = {
        "capacity":    _HDR_CAPACITY,
        "production":  _HDR_PRODUCTION,
        "utilization": _HDR_UTILIZATION,
    }.get(section)
    if pattern is None:
        raise ValueError(f"unknown section: {section!r}")

    root = _parse_dart_xml(xml_text)
    if root is None:
        return []

    out: list[PlantRow] = []
    for elem, txt in _iter_spans_with_text(root):
        if not pattern.search(txt):
            continue
        table = _find_next_table_after(root, elem)
        if table is None:
            continue
        header, data_rows = _parse_table_rows(table)
        if not header or not data_rows:
            continue
        years = _extract_years_from_header(header)
        if not years:
            continue

        # ── utilization 전용 branch (2026-06-01 신규) ────────────
        # Hyundai 사업보고서 "(3) 가동률" 표 구조:
        #   header: 사업부문 / 법인명 / 소재지 / 2023년(제56기) [COLSPAN=3]
        #   subheader 행: 생산능력 / 생산실적 / 가동률(%)
        #   data row (cells=6): 사업부문 [ROWSPAN] / 법인명 / 소재지 / capa / actual / util%
        # 즉 header len=4 (year cell 1) 이지만 data row 는 6 cells.
        if section == "utilization":
            util_rows = _parse_utilization_table(data_rows, years)
            out.extend(util_rows)
            break

        # header cell 수 = 사업부문 + 법인명 + 소재지 + year * N (capacity / production)
        expected_full = len(header)

        # 컬럼 매핑 자동 검출 — Kia 사업보고서는 header[1]='품목' 이라
        # plant 식별자가 header[2]='소재지' 에 들어있음.
        # Hyundai: header[1]='법인명' (plant_code), header[2]='소재지' (region)
        plant_col, region_col = 0, 1     # default Hyundai
        h1 = re.sub(r"\s+", "", (header[1] if len(header) > 1 else ""))
        if "품목" in h1:
            # Kia 스타일 — body[0]='품목', body[1]='소재지' (plant 식별자)
            plant_col, region_col = 1, None
            log.info("[dart_production] Kia-style header detected (품목/소재지) — "
                     "plant_col=1")

        running: str | None = None
        for cells in data_rows:
            rows, running = _row_to_plant_rows(
                cells, years, running, expected_full,
                plant_col=plant_col, region_col=region_col,
            )
            out.extend(rows)
        # 첫 매칭 표만 채용 — 동일 섹션이 본문에 여러 번 등장하면 중복 위험
        break
    return out


def parse_business_report(xml_text: str, *,
                          rcept_no: str | None = None) -> ProductionExtract:
    """단일 사업보고서 XML → 3 섹션 모두 추출."""
    return ProductionExtract(
        capacity=parse_section(xml_text, "capacity"),
        production=parse_section(xml_text, "production"),
        utilization=parse_section(xml_text, "utilization"),
        source_rcept_no=rcept_no,
    )


__all__ = [
    "PlantRow",
    "ProductionExtract",
    "parse_section",
    "parse_business_report",
]
