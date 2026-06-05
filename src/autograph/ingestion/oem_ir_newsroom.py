"""제조사 IR / 뉴스룸 sitemap 기반 크롤러 — 약관 준수 buffered.

사용자 의제 (2026-05-29 메시지): KG 프로젝트 입장에서 오픈 채널 중 제일 값진
영역. 공장 위치/CAPA/모델 배정 발표를 IR + 뉴스룸 본문에서 추출.

본 모듈의 책임:
    1. ``OEM_NEWSROOM_POLICY`` 라이선스 게이트 강제 (robots.txt + ToS)
    2. sitemap-first 발견 (HTML 스크래핑보다 respectful)
    3. RateLimiter + User-Agent 식별 + Retry-After 인식
    4. raw HTML 디스크 보존 + 메타 jsonl
    5. CheckpointStore 재실행 안전

대상:
    hyundai: www.hyundai.com/worldwide/{ko,en}/company/ir/...    (활성)
    mobis:   www.mobis.com/news/, mobis.co.kr/news/, /ir/         (활성)
    kia:     /kr/discover-kia/news/                               (★ 비활성 ★ robots.txt Disallow)

키 불필요. 정책 정의된 OEM 만 동작. 정책 미정 OEM 은 ``UnknownOEMError``.

CLI:
    python -m autograph.ingestion.oem_ir_newsroom --oem hyundai --limit 50
    python -m autograph.ingestion.oem_ir_newsroom --oem mobis --section ir
    python -m autograph.ingestion.oem_ir_newsroom --list-policies
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from autonexusgraph.config import get_settings
from autonexusgraph.ingestion._common import RateLimiter, save_raw
from autonexusgraph.ingestion._license import (
    OEM_NEWSROOM_POLICY,
    is_url_allowed,
    newsroom_policy,
)

log = logging.getLogger(__name__)


_SOURCE_ROOT = "auto/oem_ir"


class UnknownOEMError(ValueError):
    """OEM 정책 미정 — OEM_NEWSROOM_POLICY 에 등록 필요."""


@dataclass
class CrawlResult:
    oem: str
    urls_discovered: int = 0
    urls_filtered_by_policy: int = 0
    urls_filtered_by_robots: int = 0
    urls_fetched: int = 0
    urls_failed: int = 0
    bytes_saved: int = 0
    policy_active: bool = True
    notes: list[str] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# ── robots.txt 검증 ─────────────────────────────────────────────
def _make_robots_parser(host: str) -> urllib.robotparser.RobotFileParser:
    """robots.txt 파서. 네트워크 실패 시 보수적으로 빈 (모두 허용 X) 반환."""
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"https://{host}/robots.txt")
    try:
        rp.read()
    except Exception as exc:   # noqa: BLE001 — [oem_ir] %s/robots.txt 읽기 실패 흡수 → rp 반환
        log.warning("[oem_ir] %s/robots.txt 읽기 실패: %s", host, exc)
        # 보수적: 모든 경로 disallow 로 설정
        rp.parse(["User-agent: *", "Disallow: /"])
    return rp


_ROBOTS_CACHE: dict[str, urllib.robotparser.RobotFileParser] = {}


def _robots_allowed(url: str, user_agent: str) -> bool:
    """robots.txt 의 User-agent 별 결정. host 별 캐시."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc
    if host not in _ROBOTS_CACHE:
        _ROBOTS_CACHE[host] = _make_robots_parser(host)
    return _ROBOTS_CACHE[host].can_fetch(user_agent, url)


# ── sitemap 다운로드 + URL 추출 ──────────────────────────────────
_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)
_LASTMOD_RE = re.compile(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", re.IGNORECASE)


def _fetch_text(url: str, *, user_agent: str, timeout: float = 20.0
                ) -> str | None:
    """단순 GET. 네트워크/HTTP 에러 시 None."""
    req = urllib.request.Request(url, headers={"User-Agent": user_agent,
                                                  "Accept": "text/html,application/xml"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        log.warning("[oem_ir] %s HTTP %s: %s", url, e.code, e.reason)
        if e.code == 429:
            ra = e.headers.get("Retry-After") if e.headers else None
            try:
                wait = float(ra) if ra else 60.0
            except (TypeError, ValueError):
                wait = 60.0
            log.warning("[oem_ir] 429 — Retry-After %.0fs", wait)
            time.sleep(min(wait, 300.0))
        return None
    except Exception as e:   # noqa: BLE001 — [oem_ir_newsroom] fail-soft 흡수 → None 반환 (log 동반)
        log.warning("[oem_ir] %s 실패: %s", url, e)
        return None


def _parse_sitemap(xml_text: str) -> list[tuple[str, str | None]]:
    """sitemap XML → [(url, lastmod)]. sitemapindex 형식도 loc 만 추출 (재귀 호출 자)."""
    if not xml_text:
        return []
    locs = _LOC_RE.findall(xml_text)
    lastmods = _LASTMOD_RE.findall(xml_text)
    # XML 순서 보존 — zip 으로 페어. lastmod 부족하면 None.
    out: list[tuple[str, str | None]] = []
    for i, loc in enumerate(locs):
        lm = lastmods[i] if i < len(lastmods) else None
        out.append((loc, lm))
    return out


def _is_sitemap_index(xml_text: str) -> bool:
    return "<sitemapindex" in xml_text.lower()


def discover_sitemap_urls(*, oem: str, user_agent: str,
                          rate_limit: RateLimiter,
                          max_sitemaps: int = 50,
                          ) -> list[tuple[str, str | None]]:
    """OEM 의 root sitemap → 하위 sitemap 재귀 → 모든 URL.

    [(url, lastmod_str_or_None), ...] 반환. 정책 비허용 host 는 자동 skip.
    """
    pol = newsroom_policy(oem)
    if pol is None or not pol.get("active"):
        return []
    # 정책에 sitemap_seeds 가 있으면 그것을 직접 사용 (좁은 범위)
    # 없으면 generic /<host>/sitemap.xml.
    seeds: list[str] = list(pol.get("sitemap_seeds") or [])
    if not seeds:
        seeds = [f"https://{h}/sitemap.xml" for h in pol["allowed_hosts"]]

    visited: set[str] = set()
    out: list[tuple[str, str | None]] = []
    queue = list(seeds)
    while queue and len(visited) < max_sitemaps:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        rate_limit.acquire()
        text = _fetch_text(url, user_agent=user_agent)
        if not text:
            continue
        if _is_sitemap_index(text):
            for sub_url, _ in _parse_sitemap(text):
                if sub_url not in visited:
                    queue.append(sub_url)
        else:
            out.extend(_parse_sitemap(text))
    return out


# ── URL 필터링 (policy + robots) ────────────────────────────────
def _slug_from_url(url: str) -> str:
    """파일명 안전 슬러그 — '/' 와 특수문자 제거."""
    parsed = urllib.parse.urlparse(url)
    s = (parsed.path or "/").strip("/").replace("/", "_") or "root"
    s = re.sub(r"[^A-Za-z0-9._\-]", "_", s)
    return s[:120]


def _classify_section(url: str) -> str:
    """URL → section 분류 (라벨)."""
    u = url.lower()
    if "/company/ir/public-disclosure" in u:
        return "ir/public_disclosure"
    if "/company/ir/financial-information/quarterly-earnings" in u:
        return "ir/quarterly_earnings"
    if "/company/ir/ir-resources/sales-results" in u:
        return "ir/sales_results"
    if "/company/ir/ir-events" in u:
        return "ir/events"
    if "/company/ir/" in u:
        return "ir/other"
    if "/news/" in u or "/press/" in u or "newsroom" in u:
        return "news/press"
    if "/ir/" in u:
        return "ir/other"
    return "other"


def _parse_date_from_lastmod(lastmod: str | None) -> _dt.date | None:
    if not lastmod:
        return None
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", lastmod)
    if not m:
        return None
    try:
        return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


# ── 본문 HTML 다운로드 + 텍스트 추출 ─────────────────────────────
_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE
)
_WS_RE = re.compile(r"\s+")
_TITLE_RE = re.compile(r"<title[^>]*>([^<]*)</title>", re.IGNORECASE)


def _extract_text(html: str) -> tuple[str | None, str]:
    """(title, body_text) — 단순 정규식 stripper. bs4/lxml 의존 회피."""
    if not html:
        return None, ""
    title_m = _TITLE_RE.search(html)
    title = (title_m.group(1).strip() if title_m else None) or None
    no_script = _SCRIPT_STYLE_RE.sub(" ", html)
    text = _TAG_RE.sub(" ", no_script)
    text = _WS_RE.sub(" ", text).strip()
    return title, text


@dataclass
class FetchedDocument:
    oem: str
    url: str
    title: str | None
    body_text: str
    body_html_path: str
    section: str
    published_date: _dt.date | None
    fetched_at: _dt.datetime
    source: str   # 'hyundai_ir' 등


def _save_raw_html(*, oem: str, url: str, html: str,
                   published_date: _dt.date | None) -> Path:
    """디스크에 raw HTML 보존. data/raw/auto/oem_ir/<oem>/<YYYY-MM-DD>_<slug>.html"""
    root = get_settings().ingest_raw_dir / _SOURCE_ROOT / oem
    root.mkdir(parents=True, exist_ok=True)
    date_str = (published_date.isoformat()
                if published_date else _dt.date.today().isoformat())
    fname = f"{date_str}_{_slug_from_url(url)}.html"
    p = root / fname
    p.write_text(html, encoding="utf-8", errors="replace")
    return p


def _fetch_and_save(*, oem: str, url: str, lastmod: str | None,
                    user_agent: str, rate_limit: RateLimiter
                    ) -> FetchedDocument | None:
    rate_limit.acquire()
    html = _fetch_text(url, user_agent=user_agent)
    if not html:
        return None
    title, body = _extract_text(html)
    pub = _parse_date_from_lastmod(lastmod)
    saved = _save_raw_html(oem=oem, url=url, html=html, published_date=pub)
    return FetchedDocument(
        oem=oem,
        url=url,
        title=title,
        body_text=body,
        body_html_path=str(saved),
        section=_classify_section(url),
        published_date=pub,
        fetched_at=_dt.datetime.now(_dt.timezone.utc),
        source=f"{oem}_ir",
    )


# ── 공개 API ────────────────────────────────────────────────────
def crawl(*, oem: str, limit: int = 50,
          section_filter: str | None = None,
          fetch_bodies: bool = True) -> CrawlResult:
    """OEM 의 sitemap → 허용 URL 만 fetch + raw 보존 + meta jsonl 누적.

    Args:
        oem: 'hyundai' / 'mobis' / 'kia' (kia 는 정책 비활성)
        limit: fetch 할 최대 URL 수 (rate-limit 보호)
        section_filter: 'ir' / 'news' / 'ir/public_disclosure' 등 prefix 매칭
        fetch_bodies: False 면 URL 목록 보존만 (rate 제어 시)

    Returns:
        ``CrawlResult`` (urls_discovered / fetched / failed / bytes_saved 등).
    """
    pol = newsroom_policy(oem)
    if pol is None:
        raise UnknownOEMError(f"OEM 정책 미정: {oem!r}")

    result = CrawlResult(oem=oem, policy_active=bool(pol.get("active")))
    if not pol.get("active"):
        result.notes = [pol.get("notes", "비활성")]
        log.warning("[oem_ir:%s] 정책 비활성 — skip. %s", oem, pol.get("notes"))
        return result

    user_agent = pol["user_agent"]
    rate = RateLimiter(per_sec=1.0 / max(pol["rate_limit_sec"] or 2.0, 0.1))

    # 1) sitemap discover
    discovered = discover_sitemap_urls(
        oem=oem, user_agent=user_agent, rate_limit=rate)
    result.urls_discovered = len(discovered)

    # 2) 정책·robots 필터
    accepted: list[tuple[str, str | None]] = []
    for url, lm in discovered:
        ok, reason = is_url_allowed(oem, url)
        if not ok:
            result.urls_filtered_by_policy += 1
            continue
        if not _robots_allowed(url, user_agent):
            result.urls_filtered_by_robots += 1
            continue
        if section_filter and not _classify_section(url).startswith(section_filter):
            continue
        accepted.append((url, lm))
        if len(accepted) >= limit:
            break

    log.info("[oem_ir:%s] discovered=%d accepted=%d (limit=%d)",
             oem, result.urls_discovered, len(accepted), limit)

    if not fetch_bodies:
        return result

    # 3) fetch + save
    meta_root = get_settings().ingest_raw_dir / _SOURCE_ROOT / oem
    meta_root.mkdir(parents=True, exist_ok=True)
    meta_path = meta_root / "_meta.jsonl"

    for url, lm in accepted:
        doc = _fetch_and_save(oem=oem, url=url, lastmod=lm,
                                user_agent=user_agent, rate_limit=rate)
        if doc is None:
            result.urls_failed += 1
            continue
        result.urls_fetched += 1
        result.bytes_saved += len(doc.body_text or "")
        # meta jsonl append
        with meta_path.open("a", encoding="utf-8") as f:
            row = {
                "oem": doc.oem,
                "url": doc.url,
                "title": doc.title,
                "section": doc.section,
                "published_date": (doc.published_date.isoformat()
                                    if doc.published_date else None),
                "body_text_len": len(doc.body_text or ""),
                "body_html_path": doc.body_html_path,
                "fetched_at": doc.fetched_at.isoformat(),
                "source": doc.source,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    log.info("[oem_ir:%s] fetched=%d failed=%d bytes=%d",
             oem, result.urls_fetched, result.urls_failed, result.bytes_saved)
    return result


def list_policies() -> list[dict]:
    """현재 적용 중인 OEM 정책 — CLI --list-policies 용."""
    out = []
    for oem, pol in OEM_NEWSROOM_POLICY.items():
        out.append({
            "oem": oem,
            "active": pol.get("active"),
            "hosts": pol["allowed_hosts"],
            "allowed_prefixes": pol["allowed_path_prefixes"],
            "disallowed_prefixes": pol["disallowed_path_prefixes"],
            "rate_limit_sec": pol["rate_limit_sec"],
            "notes": pol["notes"],
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(prog="autograph.ingestion.oem_ir_newsroom")
    ap.add_argument("--oem", choices=sorted(OEM_NEWSROOM_POLICY.keys()),
                    default=None)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--section", default=None,
                    help="섹션 prefix 필터 (예: 'ir', 'ir/quarterly_earnings', 'news')")
    ap.add_argument("--no-bodies", action="store_true",
                    help="URL 목록만 discover (본문 fetch 안 함)")
    ap.add_argument("--list-policies", action="store_true",
                    help="정책 dump")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.list_policies:
        print(json.dumps(list_policies(), ensure_ascii=False, indent=2))
        return 0

    if not args.oem:
        ap.error("--oem 필요 (또는 --list-policies)")

    out = crawl(oem=args.oem, limit=args.limit,
                section_filter=args.section,
                fetch_bodies=not args.no_bodies)
    print(json.dumps(out.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "CrawlResult", "FetchedDocument", "UnknownOEMError",
    "crawl", "discover_sitemap_urls", "list_policies",
    "_classify_section", "_extract_text", "_parse_sitemap",
    "_is_sitemap_index", "_parse_date_from_lastmod",
    "_slug_from_url",
]
