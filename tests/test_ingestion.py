"""수집 클라이언트 오프라인 테스트 — 외부 HTTP 호출 mock 또는 zip 파싱만."""

from __future__ import annotations

import io
import zipfile
from unittest.mock import patch

import pytest


# ── make_http_client 팩토리 ─────────────────────────────────────────
def test_make_http_client_default_user_agent():
    from autonexusgraph.ingestion._common import (
        DEFAULT_USER_AGENT,
        make_http_client,
    )
    c = make_http_client()
    assert c.headers.get("User-Agent") == DEFAULT_USER_AGENT


def test_make_http_client_custom_user_agent():
    from autonexusgraph.ingestion._common import make_http_client
    c = make_http_client(user_agent="X-Spec/1.0")
    assert c.headers.get("User-Agent") == "X-Spec/1.0"


def test_make_http_client_headers_override_user_agent_arg():
    """headers 의 User-Agent 가 user_agent 인자보다 우선 — SEC 등 엄격 정책 호환."""
    from autonexusgraph.ingestion._common import make_http_client
    c = make_http_client(user_agent="From-Arg",
                          headers={"User-Agent": "From-Headers"})
    assert c.headers.get("User-Agent") == "From-Headers"


def test_make_http_client_timeout_applied():
    from autonexusgraph.ingestion._common import make_http_client
    c = make_http_client(timeout=7.5)
    # httpx 의 Timeout 객체는 float 와 == 비교 가능.
    assert float(c.timeout.read) == 7.5


def test_dart_parse_corp_codes():
    """zip → CorpCode iterator (HTTP 호출 X)."""
    from autonexusgraph.ingestion.dart_client import DartClient

    # 가짜 corpCode.xml 생성
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<result>\n"
        "  <list>\n"
        "    <corp_code>00126380</corp_code>\n"
        "    <corp_name>삼성전자</corp_name>\n"
        "    <stock_code>005930</stock_code>\n"
        "    <modify_date>20240101</modify_date>\n"
        "  </list>\n"
        "  <list>\n"
        "    <corp_code>00123456</corp_code>\n"
        "    <corp_name>비상장사</corp_name>\n"
        "    <stock_code>      </stock_code>\n"
        "    <modify_date>20240101</modify_date>\n"
        "  </list>\n"
        "</result>\n"
    ).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", xml)

    with patch("autonexusgraph.ingestion.dart_client.httpx.Client"):
        client = DartClient(api_key="fake")
        codes = list(client.parse_corp_codes(buf.getvalue()))

    assert len(codes) == 2
    assert codes[0].corp_code == "00126380"
    assert codes[0].corp_name == "삼성전자"
    assert codes[0].stock_code == "005930"
    assert codes[1].stock_code is None      # 공백만 있던 케이스


def test_dart_client_no_key_raises():
    from autonexusgraph.ingestion.dart_client import DartClient

    with pytest.raises(ValueError, match="DART_API_KEY"):
        DartClient(api_key="")


def test_dart_rate_limit_throttle():
    """min_interval 이 _throttle 에 반영되는지."""
    from autonexusgraph.ingestion.dart_client import DartClient

    with patch("autonexusgraph.ingestion.dart_client.httpx.Client"):
        c = DartClient(api_key="fake", rate_limit_per_sec=5)
        assert c._min_interval == pytest.approx(0.2)
        c2 = DartClient(api_key="fake", rate_limit_per_sec=0)
        assert c2._min_interval == 0


def test_ecos_key_stats_keys():
    """사전 정의 지표 목록이 살아 있는지."""
    from autonexusgraph.ingestion.ecos_client import KEY_STATS

    assert "base_rate" in KEY_STATS
    assert "usd_krw" in KEY_STATS
    for _name, meta in KEY_STATS.items():
        assert "stat_code" in meta
        assert "cycle" in meta
        assert meta["cycle"] in {"D", "M", "Q", "A"}


def test_ecos_parse_float_robust():
    from autonexusgraph.ingestion.ecos_client import _parse_float

    assert _parse_float("1234.5") == 1234.5
    assert _parse_float("1,234.5") == 1234.5
    assert _parse_float("") is None
    assert _parse_float(None) is None
    assert _parse_float("not a number") is None


def test_krx_top_n_by_market_cap():
    """FDR 응답을 mock 해서 시가총액 정렬 + Listing 변환 검증."""
    import pandas as pd

    from autonexusgraph.ingestion.krx_client import KrxClient

    fake_df = pd.DataFrame({
        "Code":   ["005930", "000660", "035420"],
        "Name":   ["삼성전자", "SK하이닉스", "NAVER"],
        "Market": ["KOSPI", "KOSPI", "KOSPI"],
        "Marcap": [1_000_000_000, 500_000_000, 200_000_000],
        "ISU_CD": ["KR1", "KR2", "KR3"],
    })
    with patch("FinanceDataReader.StockListing", return_value=fake_df):
        client = KrxClient()
        top2 = client.top_n_by_market_cap("KOSPI", n=2)
        assert len(top2) == 2
        assert top2[0].stock_code == "005930"
        assert top2[0].market_cap == 1_000_000_000
        assert top2[1].stock_code == "000660"


def test_krx_unknown_market():
    from autonexusgraph.ingestion.krx_client import KrxClient

    with patch("FinanceDataReader.StockListing"):
        client = KrxClient()
        with pytest.raises(ValueError, match="unknown market"):
            client.fetch_listed_companies("INVALID")
