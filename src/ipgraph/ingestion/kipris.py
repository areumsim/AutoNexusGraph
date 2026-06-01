"""KIPRIS Open API — 한국 특허 검색·서지 수집. docs/ipgraph.md §5.

라이선스: KIPRIS Open API (공공데이터포털) — 검색·서지 무료, 본문/대량은 KIPRISPLUS
회원·일부 비공개. ``LICENSE_POLICY['kipris'] = 'kogl_type1'`` (메타 저장 OK).

우선 출원인: 현대차 / 기아 / 삼성SDI / LG에너지솔루션 / 현대모비스 (docs/ipgraph.md §5).

API 인증:
    ``KIPRIS_API_KEY`` env 필요. 미설정 시 graceful skip + 0 row.

CLI:
    python -m ipgraph.ingestion.kipris
    python -m ipgraph.ingestion.kipris --applicants 한국조폐공사,삼성SDI --year 2024
    python -m ipgraph.ingestion.kipris --dry-run

본 단계는 wire-up — 실제 API 호출은 KIPRIS_API_KEY 가 있을 때만.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "raw" / "ip" / "kipris"

log = logging.getLogger(__name__)


# KIPRIS Open API endpoint — 공공데이터포털.
# https://www.data.go.kr/data/15077221/openapi.do
KIPRIS_SEARCH_URL = (
    "http://plus.kipris.or.kr/openapi/rest/patUtiModInfoSearchSevice/"
    "advancedSearch"
)

# 우선 출원인 (docs/ipgraph.md §5).
PRIORITY_APPLICANTS = (
    "현대자동차", "기아", "삼성SDI", "LG에너지솔루션", "현대모비스",
)


def _api_key() -> str | None:
    """KIPRIS_API_KEY env — 미설정 시 None (graceful skip)."""
    key = os.getenv("KIPRIS_API_KEY", "").strip()
    return key or None


def _ensure_raw_dir() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    return RAW_DIR


def _fetch_one_applicant(applicant: str, *, year: int | None,
                         api_key: str, max_pages: int = 5) -> list[dict]:
    """단일 출원인 advanced search — 페이지네이션. fail-soft."""
    rows: list[dict] = []
    for page in range(1, max_pages + 1):
        params = {
            "ServiceKey":  api_key,
            "applicant":   applicant,
            "numOfRows":   "100",
            "pageNo":      str(page),
            "patent":      "true",
        }
        if year:
            params["applicationDate"] = f"{year}0101~{year}1231"
        url = f"{KIPRIS_SEARCH_URL}?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "AutoNexusGraph/IPG"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = resp.read().decode("utf-8")
        except Exception as e:   # noqa: BLE001
            log.warning("[kipris] fetch 실패 (%s page=%d): %s",
                        applicant, page, e)
            break
        # KIPRIS 응답이 XML 일 수 있음 — wire-up 단계는 raw 저장만.
        raw_path = RAW_DIR / f"{applicant}_y{year or 'all'}_p{page}.txt"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(payload, encoding="utf-8")
        # 본 단계는 parse 미구현 (XML schema 인증 후) — rows 빈 list 반환.
        # 후속 PR 에서 lxml 파싱 추가.
        if "<item>" not in payload and "<patentInfo>" not in payload:
            break
    return rows


def collect(*, applicants: list[str] | None = None,
            year: int | None = None,
            dry_run: bool = False) -> dict[str, Any]:
    """KIPRIS 수집 진입점.

    ``KIPRIS_API_KEY`` 미설정 시 graceful skip + 0 row.
    """
    raw_dir = _ensure_raw_dir()
    apps = applicants or list(PRIORITY_APPLICANTS)

    key = _api_key()
    if not key:
        log.warning("[kipris] KIPRIS_API_KEY 미설정 — graceful skip. 가이드: data.go.kr 15077221")
        return {
            "n_rows":   0,
            "raw_dir":  str(raw_dir),
            "skipped":  True,
            "reason":   "KIPRIS_API_KEY 미설정",
        }

    snapshot_year = datetime.now(timezone.utc).year
    total = 0
    for applicant in apps:
        if dry_run:
            log.info("[kipris] dry-run %s year=%s", applicant, year)
            continue
        rows = _fetch_one_applicant(applicant, year=year, api_key=key)
        total += len(rows)

    return {
        "n_rows":         total,
        "applicants":     apps,
        "year":           year,
        "snapshot_year":  snapshot_year,
        "raw_dir":        str(raw_dir),
    }


def main() -> int:
    p = argparse.ArgumentParser(prog="ipgraph.ingestion.kipris",
                                 description=__doc__.split("\n")[0])
    p.add_argument("--applicants", default=None,
                   help="csv — 미지정 시 priority 5사")
    p.add_argument("--year", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(message)s")

    apps: list[str] | None = None
    if args.applicants:
        apps = [a.strip() for a in args.applicants.split(",") if a.strip()]
    result = collect(applicants=apps, year=args.year, dry_run=args.dry_run)
    print(f"[kipris] {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
