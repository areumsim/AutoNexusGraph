"""소스별 라이선스 정책 — save_raw() 호출 시 본문 저장 여부 게이트.

원칙:
- public_domain / cc0 / cc_by_*: 본문 저장 OK (출처 표기 의무는 있음)
- kogl_*: 공공누리 — 본문 저장 OK
- copyrighted: 본문 저장 금지 (메타+요약만)
- metadata_only: 약관상 메타만 (빅카인즈 등)

사용:
    from autonexusgraph.ingestion._license import allow_body, LICENSE_POLICY
    if not allow_body("news_yonhap"):
        payload.pop("body", None)
"""

from __future__ import annotations

from typing import Literal


LicenseTier = Literal[
    "public_domain",
    "cc0",
    "cc_by_4_0",
    "cc_by_sa",
    "kogl_type1",
    "kogl_type2",
    "kogl_type3",
    "kogl_type4",
    "public_partial",
    "copyrighted",
    "metadata_only",
    "unknown",
]


LICENSE_POLICY: dict[str, LicenseTier] = {
    # 공개·정부 — 본문 저장 OK
    "dart":            "public_domain",   # 전자공시 (공공)
    "fss_press":       "kogl_type1",      # 금감원 보도자료 — KOGL 1유형
    "fss_disclosure":  "kogl_type1",      # 금감원 제재정보
    "ftc":             "kogl_type1",      # 공정거래위
    "kosis":           "public_domain",   # 통계청
    "ecos":            "public_domain",   # 한국은행
    "law":             "public_domain",   # LAW.go.kr
    "kipris":          "kogl_type1",      # 특허청 — 메타·서지정보
    "sec_edgar":       "public_domain",   # SEC (미국)
    "gleif":           "cc_by_4_0",       # GLEIF LEI
    "krx":             "public_domain",   # KRX 시세 (정보데이터시스템 공개)

    # 위키 계열
    "wikipedia":       "cc_by_sa",        # 본문 OK + 출처표기
    "wikidata":        "cc0",             # 본문 OK, 무조건 자유

    # ESG (KCGS): 등급은 공개, 보고서 본문은 비공개 — 등급만 사용
    "kcgs":            "public_partial",

    # 저작권 — 메타+요약만
    "news_yonhap":     "copyrighted",
    "news_hankyung":   "copyrighted",
    "news_mois":       "kogl_type1",      # 정부 RSS — 본문 OK
    "news_moef":       "kogl_type1",      # 정부 RSS — 본문 OK
    "bigkinds":        "metadata_only",

    # ── 제조사 IR / 뉴스룸 (회사 운영, 공개 IR — 출처표기 의무) ──
    # robots.txt 확인 일자 2026-06-01. 변경 시 본 파일 + ``OEM_NEWSROOM_POLICY``
    # 양쪽 갱신 필요. 정책 결정 근거는 ``OEM_NEWSROOM_POLICY`` 의 notes 참조.
    "hyundai_ir":       "public_partial",  # robots.txt allows; ToS — 본문 저장 가능, 출처 필수
    "mobis_ir":         "public_partial",  # robots.txt Allow: /. 본문 저장 가능, 출처 필수
    "kia_ir":           "metadata_only",   # /kr/discover-kia/news/ Disallow — 본문 저장 금지
}


# ── OEM IR/뉴스룸 크롤링 정책 ────────────────────────────────────
# robots.txt 의 ``Disallow`` 를 코드 레벨에서 강제. 본 dict 가 SSOT — crawler 가
# 호스트·경로 매칭 후 active=False 면 즉시 skip.
#
# 측정일: 2026-06-01 — `curl https://<host>/robots.txt` 직접 확인 결과.
#
# 호스트별 정책 변경 시 반드시 본 dict 갱신 + 위 ``LICENSE_POLICY`` 의 'oem_ir'
# 항목 동기화.
OEM_NEWSROOM_POLICY: dict[str, dict] = {
    "hyundai": {
        "active": True,
        "allowed_hosts": ["www.hyundai.com"],
        "allowed_path_prefixes": [
            "/worldwide/ko/company/ir/",
            "/worldwide/en/company/ir/",
        ],
        "disallowed_path_prefixes": [
            "/kr/ko/login/", "/kr/ko/member-change/", "/kr/ko/mypage/",
            "/kr/ko/agreements/", "/kr/ko/personal-information/",
            "/kr/ko/copyright.html",
        ],
        "rate_limit_sec": 2.0,
        "user_agent": "AutoGraph-Research/0.1 (research, public-info)",
        "notes": (
            "robots.txt (2026-06-01): IR/newsroom 경로 Disallow 없음. "
            "공식 IR 자료 — 공시·실적·판매 (공개 정보). 본문 저장 가능. "
            "출처 표기 필수."
        ),
    },
    "kia": {
        "active": False,   # ★ robots.txt Disallow 로 v0 비활성 ★
        "allowed_hosts": [],
        "allowed_path_prefixes": [],
        "disallowed_path_prefixes": [
            "/kr/discover-kia/news/",   # robots.txt 명시 Disallow
        ],
        "rate_limit_sec": None,
        "user_agent": None,
        "notes": (
            "robots.txt (2026-06-01): 'Disallow: /kr/discover-kia/news/' 명시. "
            "v0 비활성 — 본 도메인 크롤링 금지. 해외 newsroom (press.kia.com 등) "
            "별도 robots/ToS 검토 후 활성화 가능."
        ),
    },
    "mobis": {
        "active": True,
        "allowed_hosts": ["www.mobis.com", "www.mobis.co.kr"],
        "allowed_path_prefixes": [
            "/news/",
            "/ir/",
        ],
        "disallowed_path_prefixes": [],
        "rate_limit_sec": 2.0,
        "user_agent": "AutoGraph-Research/0.1 (research, public-info)",
        "notes": (
            "robots.txt (2026-06-01): 'Allow: /'. 두 도메인 (mobis.com/mobis.co.kr) "
            "모두 사용. 본문 저장 가능, 출처 표기 필수."
        ),
    },
}


def newsroom_policy(oem: str) -> dict | None:
    """OEM 키 (hyundai/kia/mobis) → 크롤링 정책. 미등록은 None."""
    return OEM_NEWSROOM_POLICY.get(oem.lower())


def is_url_allowed(oem: str, url: str) -> tuple[bool, str]:
    """URL 단일 검증 — (allowed, reason).

    정책 우선순위:
        1. ``active=False`` → 무조건 거부
        2. host 가 ``allowed_hosts`` 에 없으면 거부
        3. path 가 ``disallowed_path_prefixes`` 매칭 → 거부 (robots Disallow)
        4. path 가 ``allowed_path_prefixes`` 매칭 → 허용
        5. 그 외 → 거부 (whitelist 정책)
    """
    pol = newsroom_policy(oem)
    if pol is None:
        return False, f"unknown oem: {oem!r}"
    if not pol.get("active"):
        return False, f"oem {oem!r} 크롤링 비활성 — {pol.get('notes', '')[:80]}"

    from urllib.parse import urlparse
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        return False, f"invalid url: {url!r}"

    host = p.netloc.lower()
    if host not in {h.lower() for h in pol["allowed_hosts"]}:
        return False, f"host {host!r} not in allowed_hosts for {oem!r}"

    path = p.path or "/"
    for bad in pol["disallowed_path_prefixes"]:
        if path.startswith(bad):
            return False, f"path {path!r} robots Disallow ({bad!r})"

    for ok in pol["allowed_path_prefixes"]:
        if path.startswith(ok):
            return True, "ok"

    return False, f"path {path!r} not in allowed_path_prefixes for {oem!r}"


BODY_ALLOWED: set[LicenseTier] = {
    "public_domain", "cc0", "cc_by_4_0", "cc_by_sa",
    "kogl_type1", "kogl_type2",
}


def allow_body(source: str) -> bool:
    """source 키의 본문 저장이 허용되는가."""
    tier = LICENSE_POLICY.get(source, "unknown")
    return tier in BODY_ALLOWED


def require_attribution(source: str) -> bool:
    """출처 표기가 필요한가 (CC BY/SA, KOGL 3·4유형, GLEIF 등)."""
    tier = LICENSE_POLICY.get(source, "unknown")
    return tier in {"cc_by_sa", "cc_by_4_0", "kogl_type3", "kogl_type4"}


def policy(source: str) -> LicenseTier:
    return LICENSE_POLICY.get(source, "unknown")


__all__ = [
    "LicenseTier",
    "LICENSE_POLICY",
    "BODY_ALLOWED",
    "OEM_NEWSROOM_POLICY",
    "allow_body",
    "require_attribution",
    "policy",
    "newsroom_policy",
    "is_url_allowed",
]
