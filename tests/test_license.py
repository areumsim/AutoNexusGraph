"""LICENSE_POLICY 정합성 invariant — 도메인 확장 시 동기화 강제.

목적:
- 모든 도메인 (finance/auto/ip/wiki) 의 raw 저장 source 키가 LICENSE_POLICY 에 등록.
- BODY_ALLOWED 가 LicenseTier Literal 의 부분집합.
- 도메인별 핵심 source 가 본문 허용 tier (혹은 정책에 따라 명시적 거부 tier) 인지.
- 신규 source 추가 시 본 테스트가 강제로 LICENSE_POLICY 동기화를 요구.

본 테스트는 DB 의존 없음 — pure 정책 dict 검증.
"""

from __future__ import annotations

from typing import get_args

from autonexusgraph.ingestion._license import (
    BODY_ALLOWED,
    LICENSE_POLICY,
    OEM_NEWSROOM_POLICY,
    LicenseTier,
    allow_body,
    is_url_allowed,
    newsroom_policy,
    policy,
    require_attribution,
    require_share_alike,
)

REQUIRED_SOURCES_BY_DOMAIN: dict[str, list[str]] = {
    "finance": ["dart", "fss_press", "ftc", "kosis", "ecos", "law",
                "sec_edgar", "gleif", "krx"],
    "auto":    ["hyundai_ir", "kia_worldwide_ir", "mobis_ir"],
    "ip":      ["kipris", "uspto_odp", "cpc_scheme", "openalex"],
    "wiki":    ["wikipedia", "wikidata"],
}


def test_all_required_sources_registered() -> None:
    """도메인별 핵심 source 가 LICENSE_POLICY 에 모두 등록되어 있어야 함.

    신규 ingester 추가 시 REQUIRED_SOURCES_BY_DOMAIN 와 LICENSE_POLICY 양쪽 동기화.
    """
    missing: list[str] = []
    for domain, sources in REQUIRED_SOURCES_BY_DOMAIN.items():
        for src in sources:
            if src not in LICENSE_POLICY:
                missing.append(f"[{domain}] {src!r}")
    assert not missing, f"LICENSE_POLICY 미등록: {missing}"


def test_body_allowed_tiers_in_license_tier() -> None:
    """BODY_ALLOWED 의 모든 tier 가 LicenseTier Literal 에 정의되어 있어야 함."""
    all_tiers = set(get_args(LicenseTier))
    extras = BODY_ALLOWED - all_tiers
    assert not extras, f"BODY_ALLOWED has tiers not in LicenseTier: {extras}"


def test_ip_sources_allow_body() -> None:
    """ip 도메인 4 source 는 모두 본문 저장 허용 (KIPRIS=kogl_type1, 나머지 public_domain/cc0)."""
    for src in REQUIRED_SOURCES_BY_DOMAIN["ip"]:
        assert allow_body(src), (
            f"ip source {src!r} should allow body — tier={policy(src)!r}"
        )


def test_finance_core_sources_allow_body() -> None:
    """finance 의 공개 소스 (DART/FSS/SEC/KOSIS/ECOS/KRX/LAW) 는 본문 저장 허용."""
    for src in ["dart", "fss_press", "sec_edgar", "kosis", "ecos", "krx", "law"]:
        assert allow_body(src), f"finance source {src!r} should allow body"


def test_unknown_source_denies_body() -> None:
    """미등록 source 는 본문 저장 거부 (silent default)."""
    assert not allow_body("nonexistent_source_xyz")
    assert policy("nonexistent_source_xyz") == "unknown"


def test_copyrighted_news_denies_body() -> None:
    """저작권 보호 뉴스 (연합/한경) 는 본문 저장 거부 (metadata only)."""
    assert not allow_body("news_yonhap")
    assert not allow_body("news_hankyung")
    assert not allow_body("bigkinds")
    # 정부 RSS 는 KOGL → 본문 OK
    assert allow_body("news_mois")
    assert allow_body("news_moef")


def test_share_alike_sources() -> None:
    """ODbL/CC BY-SA — downstream 재배포 시 동일 라이선스 강제 (Wikipedia/OpenCorporates)."""
    assert require_share_alike("wikipedia")
    assert require_share_alike("opencorporates")
    assert not require_share_alike("dart")
    assert not require_share_alike("wikidata")  # CC0


def test_attribution_required_sources() -> None:
    """CC BY/SA, KOGL 3·4유형, GLEIF 는 출처 표기 의무."""
    assert require_attribution("gleif")        # CC BY 4.0
    assert require_attribution("gleif_enrich") # CC BY 4.0
    assert require_attribution("wikipedia")    # CC BY-SA
    assert require_attribution("opencorporates")  # CC BY-SA
    assert not require_attribution("dart")     # public_domain


def test_oem_newsroom_policy_consistency() -> None:
    """OEM_NEWSROOM_POLICY 의 키와 LICENSE_POLICY 의 <oem>_ir 키 동기화."""
    missing: list[str] = []
    for oem in OEM_NEWSROOM_POLICY:
        license_key = f"{oem}_ir"
        if license_key not in LICENSE_POLICY:
            missing.append(f"{oem} → LICENSE_POLICY[{license_key!r}]")
    assert not missing, f"OEM newsroom 정책 vs LICENSE_POLICY 불일치: {missing}"


def test_kia_kr_disabled_by_robots() -> None:
    """kia (www.kia.com/kr) 는 robots.txt Disallow 로 비활성. kia_worldwide 와 hyundai 는 활성."""
    pol_kia = newsroom_policy("kia")
    pol_kia_ww = newsroom_policy("kia_worldwide")
    pol_hyundai = newsroom_policy("hyundai")
    assert pol_kia is not None and pol_kia["active"] is False
    assert pol_kia_ww is not None and pol_kia_ww["active"] is True
    assert pol_hyundai is not None and pol_hyundai["active"] is True


def test_is_url_allowed_blocks_disabled_oem() -> None:
    """비활성 OEM 의 URL 은 무조건 거부 (active=False)."""
    ok, reason = is_url_allowed(
        "kia", "https://www.kia.com/kr/discover-kia/news/anything"
    )
    assert not ok
    assert reason  # 거부 사유는 비어있지 않음


def test_is_url_allowed_blocks_unknown_oem() -> None:
    """미등록 OEM 은 즉시 거부."""
    ok, reason = is_url_allowed("nonexistent_oem", "https://example.com/path")
    assert not ok
    assert "unknown" in reason.lower()


def test_is_url_allowed_blocks_wrong_host() -> None:
    """allowed_hosts 외 host 는 거부 — 정책 우회 방지."""
    ok, reason = is_url_allowed(
        "hyundai", "https://evil.example.com/worldwide/ko/company/ir/something.html"
    )
    assert not ok
    assert "host" in reason.lower()


def test_is_url_allowed_passes_legitimate_ir_path() -> None:
    """활성 OEM 의 정상 IR 경로는 통과."""
    ok, reason = is_url_allowed(
        "hyundai", "https://www.hyundai.com/worldwide/ko/company/ir/financials"
    )
    assert ok, f"expected pass — reason={reason}"


def test_kcgs_partial_disallows_body() -> None:
    """KCGS — 등급만 공개, 본문 비공개 (public_partial 는 본문 거부)."""
    assert not allow_body("kcgs")
    assert policy("kcgs") == "public_partial"
