"""OEM IR/뉴스룸 크롤러 — 라이선스 게이트 + sitemap 파싱 + 텍스트 추출 테스트.

핵심 회귀 보호:
- Kia 한국 newsroom 은 robots.txt Disallow 라 정책 비활성 — 코드 변경으로
  실수로 허용되면 안 됨.
- Hyundai IR 경로는 명시 allowlist 안에 있어야 허용.
- robots.txt + 정책 dict 양쪽이 일관 — drift 차단.

실제 네트워크 호출 없음. fetcher 는 monkeypatch.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from autograph.ingestion import oem_ir_newsroom as O
from autonexusgraph.ingestion._license import (
    OEM_NEWSROOM_POLICY,
    is_url_allowed,
    newsroom_policy,
)


# ── 라이선스 게이트 (가장 중요) ──────────────────────────────────
def test_kia_kr_newsroom_policy_is_inactive():
    """Kia 한국 — robots.txt Disallow 로 active=False 강제."""
    pol = OEM_NEWSROOM_POLICY["kia"]
    assert pol["active"] is False, "Kia 정책 active=False 유지 — robots.txt Disallow"


def test_kia_kr_news_url_rejected():
    ok, reason = is_url_allowed("kia",
                                  "https://www.kia.com/kr/discover-kia/news/release.html")
    assert ok is False
    assert "비활성" in reason or "active" in reason or "disallow" in reason.lower()


def test_kia_disallowed_prefix_is_explicit():
    """Disallow 경로가 정책에 명시 등록됐는지 (robots.txt SSOT)."""
    pol = OEM_NEWSROOM_POLICY["kia"]
    assert "/kr/discover-kia/news/" in pol["disallowed_path_prefixes"]


def test_hyundai_ir_url_allowed():
    ok, reason = is_url_allowed(
        "hyundai",
        "https://www.hyundai.com/worldwide/ko/company/ir/quarterly-earnings/2024-q1"
    )
    assert ok is True, f"Hyundai IR 허용되어야 — {reason}"


def test_hyundai_login_url_rejected():
    """/kr/ko/login/ — robots.txt 명시 Disallow."""
    ok, reason = is_url_allowed(
        "hyundai", "https://www.hyundai.com/kr/ko/login/")
    assert ok is False
    assert "robots" in reason.lower() or "not in allowed" in reason.lower()


def test_hyundai_non_ir_path_rejected():
    """IR 외 경로는 whitelist 정책에 따라 거부."""
    ok, _ = is_url_allowed(
        "hyundai", "https://www.hyundai.com/worldwide/ko/shop/cars/sonata")
    assert ok is False


def test_mobis_policy_inactive_after_sitemap_check():
    """Mobis sitemap broken + SPA JS routing 으로 v0 비활성. robots.txt 와 별개."""
    pol = OEM_NEWSROOM_POLICY["mobis"]
    assert pol["active"] is False, "Mobis v0 비활성 — sitemap 404 + SPA 구조"


def test_mobis_url_rejected_due_to_inactive_policy():
    """Mobis active=False 라 path 가 allowlist 안에 있어도 거부."""
    ok, reason = is_url_allowed("mobis", "https://www.mobis.co.kr/news/recent.do")
    assert ok is False
    assert "active" in reason.lower() or "비활성" in reason


def test_unknown_oem_rejected():
    ok, reason = is_url_allowed("nonexistent", "https://example.com/x")
    assert ok is False
    assert "unknown" in reason.lower()


def test_invalid_url_rejected():
    ok, _ = is_url_allowed("hyundai", "not-a-url")
    assert ok is False


def test_disallowed_host_for_oem():
    """올바른 host (다른 OEM 의 host) 에 접근 시도해도 거부."""
    ok, _ = is_url_allowed("hyundai",
                             "https://www.mobis.com/ir/anything")
    assert ok is False


def test_newsroom_policy_dict_returns_correct_keys():
    pol = newsroom_policy("hyundai")
    assert pol is not None
    assert "allowed_hosts" in pol
    assert "allowed_path_prefixes" in pol
    assert "disallowed_path_prefixes" in pol


# ── sitemap 파싱 ─────────────────────────────────────────────────
def test_parse_sitemap_extracts_loc_and_lastmod():
    xml = """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/a</loc><lastmod>2024-01-01</lastmod></url>
  <url><loc>https://example.com/b</loc><lastmod>2024-02-15</lastmod></url>
</urlset>"""
    out = O._parse_sitemap(xml)
    assert out == [
        ("https://example.com/a", "2024-01-01"),
        ("https://example.com/b", "2024-02-15"),
    ]


def test_parse_sitemap_handles_missing_lastmod():
    xml = """<urlset><url><loc>https://a/x</loc></url></urlset>"""
    out = O._parse_sitemap(xml)
    assert out == [("https://a/x", None)]


def test_is_sitemap_index_detects_sitemapindex():
    assert O._is_sitemap_index("<sitemapindex><sitemap>...</sitemap></sitemapindex>")
    assert not O._is_sitemap_index("<urlset><url>...</url></urlset>")


def test_parse_date_from_lastmod():
    assert O._parse_date_from_lastmod("2024-03-15") is not None
    assert O._parse_date_from_lastmod("2024-03-15T10:00:00") is not None
    assert O._parse_date_from_lastmod(None) is None
    assert O._parse_date_from_lastmod("not-a-date") is None


# ── classify_section ─────────────────────────────────────────────
def test_classify_ir_subsections():
    assert O._classify_section(
        "https://www.hyundai.com/worldwide/ko/company/ir/public-disclosure-and-notices/public-disclosure"
    ) == "ir/public_disclosure"
    assert O._classify_section(
        "https://www.hyundai.com/worldwide/ko/company/ir/financial-information/quarterly-earnings"
    ) == "ir/quarterly_earnings"
    assert O._classify_section(
        "https://www.hyundai.com/worldwide/ko/company/ir/ir-resources/sales-results"
    ) == "ir/sales_results"
    assert O._classify_section(
        "https://www.hyundai.com/worldwide/ko/company/ir/ir-events"
    ) == "ir/events"


def test_classify_news_section():
    assert O._classify_section("https://www.mobis.co.kr/news/recent.do") == "news/press"


def test_classify_other_returns_other():
    assert O._classify_section("https://example.com/about") == "other"


# ── slug ─────────────────────────────────────────────────────────
def test_slug_safe_filename():
    s = O._slug_from_url("https://www.hyundai.com/worldwide/ko/company/ir/x")
    assert "/" not in s
    assert all(c.isalnum() or c in "._-" for c in s)
    assert "worldwide_ko_company_ir_x" in s


def test_slug_truncates_long_path():
    long_url = "https://x/" + ("a" * 300)
    s = O._slug_from_url(long_url)
    assert len(s) <= 120


# ── HTML 텍스트 추출 ─────────────────────────────────────────────
def test_extract_text_strips_scripts_and_tags():
    html = """<html><head><title>Hyundai 2024 1Q</title>
    <script>alert(1)</script></head>
    <body><p>매출 35조원, 영업이익 3.6조원</p>
    <style>body{color:red}</style></body></html>"""
    title, body = O._extract_text(html)
    assert title == "Hyundai 2024 1Q"
    assert "alert" not in body
    assert "color:red" not in body
    assert "매출 35조원" in body


def test_extract_text_empty_input():
    title, body = O._extract_text("")
    assert title is None
    assert body == ""


def test_extract_text_no_title_tag():
    title, body = O._extract_text("<html><body>hello</body></html>")
    assert title is None
    assert "hello" in body


# ── discover_sitemap_urls — fetcher 차단 ─────────────────────────
def test_discover_returns_empty_when_inactive(monkeypatch):
    """Kia 같이 active=False 면 sitemap 호출 자체 안 함."""
    monkeypatch.setattr(O, "_fetch_text",
                        lambda *args, **kwargs: pytest.fail("호출되면 안 됨"))
    rate = O.RateLimiter(per_sec=10.0)
    out = O.discover_sitemap_urls(oem="kia", user_agent="test", rate_limit=rate)
    assert out == []


def test_discover_calls_sitemap_seeds_for_active_oem(monkeypatch):
    """policy 에 sitemap_seeds 가 있으면 그것을 직접 호출."""
    called: list[str] = []

    def fake_fetch(url, **kwargs):
        called.append(url)
        return "<urlset></urlset>"

    monkeypatch.setattr(O, "_fetch_text", fake_fetch)
    rate = O.RateLimiter(per_sec=100.0)
    O.discover_sitemap_urls(oem="hyundai", user_agent="test", rate_limit=rate)
    # Hyundai 정책의 sitemap_seeds (worldwide-ko/en) 가 호출됨
    assert any("worldwide/ko/sitemap.xml" in u for u in called)


def test_discover_recurses_into_sitemap_index(monkeypatch):
    """sitemapindex → 하위 sitemap fetch 까지 재귀."""
    pages = {
        "https://www.hyundai.com/worldwide/ko/sitemap.xml": (
            "<sitemapindex><sitemap><loc>"
            "https://www.hyundai.com/sub.xml"
            "</loc></sitemap></sitemapindex>"
        ),
        "https://www.hyundai.com/worldwide/en/sitemap.xml": "",
        "https://www.hyundai.com/sub.xml": (
            "<urlset><url><loc>https://www.hyundai.com/x</loc></url></urlset>"
        ),
    }

    def fake_fetch(url, **kwargs):
        return pages.get(url, "")

    monkeypatch.setattr(O, "_fetch_text", fake_fetch)
    rate = O.RateLimiter(per_sec=100.0)
    out = O.discover_sitemap_urls(oem="hyundai", user_agent="test", rate_limit=rate)
    assert any(u == "https://www.hyundai.com/x" for u, _ in out)


# ── crawl() 정책 비활성 short-circuit ───────────────────────────
def test_crawl_kia_returns_inactive_result():
    """Kia crawl() 호출해도 fetch 0건 + policy_active=False."""
    out = O.crawl(oem="kia", limit=10, fetch_bodies=False)
    assert out.policy_active is False
    assert out.urls_fetched == 0


def test_crawl_unknown_oem_raises():
    with pytest.raises(O.UnknownOEMError):
        O.crawl(oem="unknownco", limit=1, fetch_bodies=False)


def test_crawl_filters_disallowed_urls(monkeypatch, tmp_path):
    """sitemap 에서 발견된 URL 중 정책 disallow / robots Disallow 인 것 필터."""
    discovered = [
        ("https://www.hyundai.com/worldwide/ko/company/ir/quarterly-earnings", None),
        ("https://www.hyundai.com/kr/ko/login/", None),   # 정책 disallow
        ("https://www.hyundai.com/shop/cars", None),       # 정책 외
    ]
    monkeypatch.setattr(O, "discover_sitemap_urls",
                        lambda **kw: discovered)
    monkeypatch.setattr(O, "_robots_allowed", lambda u, ua: True)
    monkeypatch.setattr(O, "_fetch_and_save", lambda **kw: pytest.fail("호출되면 안 됨"))

    out = O.crawl(oem="hyundai", limit=5, fetch_bodies=False)
    assert out.urls_discovered == 3
    assert out.urls_filtered_by_policy == 2   # login + shop


def test_crawl_robots_check_blocks_url(monkeypatch):
    """정책은 통과해도 robots.txt 가 거부하면 fetch 안 함."""
    discovered = [
        ("https://www.hyundai.com/worldwide/ko/company/ir/quarterly-earnings", None),
    ]
    monkeypatch.setattr(O, "discover_sitemap_urls", lambda **kw: discovered)
    monkeypatch.setattr(O, "_robots_allowed", lambda u, ua: False)   # robots 거부
    monkeypatch.setattr(O, "_fetch_and_save", lambda **kw: pytest.fail("호출 안 됨"))

    out = O.crawl(oem="hyundai", limit=5, fetch_bodies=False)
    assert out.urls_filtered_by_robots == 1
    assert out.urls_fetched == 0


# ── _meta.jsonl 저장 + loader 통합 ─────────────────────────────
def test_crawl_writes_meta_jsonl(monkeypatch, tmp_path):
    """fetch 성공 시 _meta.jsonl 에 row append 검증."""
    from autograph.ingestion.oem_ir_newsroom import FetchedDocument
    import datetime as _dt

    fake_doc = FetchedDocument(
        oem="hyundai",
        url="https://www.hyundai.com/worldwide/ko/company/ir/quarterly-earnings",
        title="2024 1Q",
        body_text="매출 35조원",
        body_html_path=str(tmp_path / "fake.html"),
        section="ir/quarterly_earnings",
        published_date=_dt.date(2024, 4, 25),
        fetched_at=_dt.datetime(2024, 4, 25, 12, 0, tzinfo=_dt.timezone.utc),
        source="hyundai_ir",
    )

    monkeypatch.setattr(O, "discover_sitemap_urls",
                        lambda **kw: [(fake_doc.url, "2024-04-25")])
    monkeypatch.setattr(O, "_robots_allowed", lambda u, ua: True)
    monkeypatch.setattr(O, "_fetch_and_save", lambda **kw: fake_doc)

    class FakeSettings:
        ingest_raw_dir = tmp_path
    monkeypatch.setattr(O, "get_settings", lambda: FakeSettings())

    out = O.crawl(oem="hyundai", limit=5, fetch_bodies=True)
    assert out.urls_fetched == 1
    meta_path = tmp_path / "auto/oem_ir/hyundai/_meta.jsonl"
    assert meta_path.exists()
    rows = [json.loads(line) for line in meta_path.read_text().splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["url"] == fake_doc.url
    assert rows[0]["section"] == "ir/quarterly_earnings"


# ── list_policies ───────────────────────────────────────────────
def test_list_policies_returns_all():
    out = O.list_policies()
    assert {p["oem"] for p in out} >= {"hyundai", "kia", "mobis"}
    # Kia 가 비활성으로 표시
    kia = next(p for p in out if p["oem"] == "kia")
    assert kia["active"] is False


# ── loader 라이선스 게이트 ──────────────────────────────────────
def test_loader_skips_when_meta_missing(monkeypatch, tmp_path):
    """raw _meta.jsonl 없으면 graceful skip."""
    from autograph.loaders import load_oem_ir_news as LD

    class FakeSettings:
        ingest_raw_dir = tmp_path
    monkeypatch.setattr(LD, "get_settings", lambda: FakeSettings())

    out = LD.run_oem("hyundai", dry_run=True)
    assert out["inserted"] == 0


def test_loader_dry_run_reports_tier(monkeypatch, tmp_path):
    """dry_run=True 시 tier 정보 노출."""
    from autograph.loaders import load_oem_ir_news as LD

    oem_dir = tmp_path / "auto" / "oem_ir" / "hyundai"
    oem_dir.mkdir(parents=True)
    (oem_dir / "_meta.jsonl").write_text(
        json.dumps({"url": "https://x/", "title": "t", "section": "ir/other"})
        + "\n", encoding="utf-8")

    class FakeSettings:
        ingest_raw_dir = tmp_path
    monkeypatch.setattr(LD, "get_settings", lambda: FakeSettings())

    out = LD.run_oem("hyundai", dry_run=True)
    assert out["n_rows"] == 1
    assert "tier" in out


def test_loader_kia_skips_due_to_metadata_only():
    """Kia 라이선스 'metadata_only' 라 body_text 미저장."""
    from autonexusgraph.ingestion._license import LICENSE_POLICY, allow_body
    assert LICENSE_POLICY["kia_ir"] == "metadata_only"
    # metadata_only 는 BODY_ALLOWED 에 없음
    assert allow_body("kia_ir") is False
