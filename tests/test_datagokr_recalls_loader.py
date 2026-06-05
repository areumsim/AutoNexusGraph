"""data.go.kr 15089863 한국 리콜 loader — 회사명 해석 단위 테스트.

실제 PG 없이 ``_ko_alias_lookup`` + ``_resolve_manufacturer_id`` 의 로직만 검증.
DB 호출은 mock cursor 로 흉내냄. API 키 없이도 로직 회귀 방지 가능.
"""

from __future__ import annotations

from unittest import mock

from autograph.loaders.recall import load_datagokr_recalls as L
from autonexusgraph.ingestion._common import normalize_corp_name


# ── 한국어 alias dict 직접 lookup ────────────────────────────────
def test_ko_alias_hyundai_legal_suffix_stripped():
    """'현대자동차주식회사' → normalize 후 '현대자동차' → HYUNDAI."""
    raw = "현대자동차주식회사"
    norm = normalize_corp_name(raw)
    assert L._ko_alias_lookup(raw, norm) == "HYUNDAI"


def test_ko_alias_kia():
    raw = "기아"
    assert L._ko_alias_lookup(raw, normalize_corp_name(raw)) == "KIA"


def test_ko_alias_ssangyong_and_kgm_both_map():
    """쌍용 / KG모빌리티 별칭 — KGM 으로 통합 (FY 2023 사명 변경 반영)."""
    assert L._ko_alias_lookup("쌍용자동차", normalize_corp_name("쌍용자동차")) == "SSANGYONG"
    assert L._ko_alias_lookup("KG모빌리티", normalize_corp_name("KG모빌리티")) == "KGM"


def test_ko_alias_partial_match_handles_company_form():
    """'(주)현대자동차' → 부분 매칭으로 HYUNDAI."""
    raw = "(주)현대자동차"
    norm = normalize_corp_name(raw)
    assert L._ko_alias_lookup(raw, norm) == "HYUNDAI"


def test_ko_alias_unknown_returns_none():
    raw = "알수없는모터스"
    assert L._ko_alias_lookup(raw, normalize_corp_name(raw)) is None


def test_ko_alias_empty_input():
    assert L._ko_alias_lookup("", "") is None


def test_ko_alias_global_brands():
    """글로벌 브랜드의 한국 표기도 매핑."""
    cases = [
        ("토요타",             "TOYOTA"),
        ("도요타",             "TOYOTA"),
        ("벤츠",               "MERCEDES-BENZ"),
        ("메르세데스-벤츠",    "MERCEDES-BENZ"),
        ("BMW코리아",          "BMW"),
        ("포드코리아",         "FORD"),
        ("랜드로버",           "LAND ROVER"),
        ("쉐보레",             "CHEVROLET"),
        ("폭스바겐",           "VOLKSWAGEN"),
    ]
    for raw, expected in cases:
        norm = normalize_corp_name(raw)
        assert L._ko_alias_lookup(raw, norm) == expected, \
            f"{raw!r} (norm={norm!r}) → {L._ko_alias_lookup(raw, norm)!r}, expected {expected!r}"


# ── _resolve_manufacturer_id — DB mock 로 SQL fan-out 검증 ──────
def _make_cur(rows_by_query: list):
    """fetchone 응답을 순서대로 돌려주는 가짜 cursor."""
    cur = mock.MagicMock()
    cur.fetchone.side_effect = rows_by_query
    return cur


def test_resolve_returns_name_norm_match_first():
    """1단계 (name_norm exact) 에서 매칭되면 alias dict 까지 안 감."""
    cur = _make_cur([(441,)])   # 첫 SELECT 에서 hit
    out = L._resolve_manufacturer_id(cur, "현대자동차")
    assert out == 441
    # 한 번만 호출 — 후속 단계 SQL 없음
    assert cur.execute.call_count == 1


def test_resolve_falls_through_to_aliases_array():
    """1단계 miss → 2단계 aliases array 매칭."""
    cur = _make_cur([
        None,        # 1단계 name_norm miss
        (442,),      # 2단계 aliases @> hit
    ])
    out = L._resolve_manufacturer_id(cur, "현대자동차")
    assert out == 442
    assert cur.execute.call_count == 2


def test_resolve_falls_through_to_ko_alias_dict():
    """1단계 + 2단계 miss → 3단계 한국어 alias dict → 영문 정규형 재조회."""
    cur = _make_cur([
        None,          # 1단계 miss
        None,          # 2단계 aliases miss
        (443,),        # 3단계 hit (HYUNDAI 영문으로 재조회)
    ])
    out = L._resolve_manufacturer_id(cur, "현대자동차주식회사")
    assert out == 443
    assert cur.execute.call_count == 3
    # 3번째 호출의 args 가 영문 정규형이어야 함
    args_3 = cur.execute.call_args_list[2][0][1]
    assert "HYUNDAI" in args_3 or "hyundai" in args_3


def test_resolve_none_when_unknown_company():
    """모든 단계 miss + dict 에도 없음 → None."""
    cur = _make_cur([
        None,   # 1단계
        None,   # 2단계
        # 3단계는 alias 가 없어서 SQL 호출 자체가 안 됨
    ])
    out = L._resolve_manufacturer_id(cur, "알수없는모터스")
    assert out is None
    # 3단계 SQL 은 alias dict 가 None 반환해서 skip — 총 2번 호출
    assert cur.execute.call_count == 2


def test_resolve_empty_name_returns_none():
    cur = _make_cur([])
    assert L._resolve_manufacturer_id(cur, "") is None
    assert L._resolve_manufacturer_id(cur, None) is None
    # 빈 입력엔 SQL 호출 자체가 없어야
    assert cur.execute.call_count == 0
