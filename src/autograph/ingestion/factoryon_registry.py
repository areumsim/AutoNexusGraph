"""data.go.kr 15087611 — 한국산업단지공단 공장등록생산정보조회서비스 (팩토리온).

base URL: ``https://apis.data.go.kr/B550624/fctryRegistInfo``

3 종 endpoint (사용자 명시):
    GET /getFctryListInIrsttService_v2   — 산업단지명 기반 (단지별 등록 공장 목록)
    GET /getFctryByFctryManageNoService_v2 — 공장관리번호 기반 (단일 공장 상세)
    GET /getFctryPrdctnService_v2         — 회사명 기반 (회사 → 공장·생산품)

목적: PRD §4.4 MANUFACTURED_AT 보강 — Manufacturer ↔ Plant + 생산품.
응답 라이선스: data.go.kr — 이용허락범위 제한 없음.

키 미설정 시 graceful skip — exit 0 + 로그. ``DATA_GO_KR_API_KEY`` 가 키 SSOT.

저장:
    data/raw/auto/factoryon/by_company/<company>_page_NN.{json|xml}
    data/raw/auto/factoryon/by_industrial_complex/<name>_page_NN.{json|xml}
    data/raw/auto/factoryon/by_factory_no/<factory_no>.{json|xml}
    data/raw/auto/factoryon/_checkpoint.json

CLI:
    python -m autograph.ingestion.factoryon_registry --by-company 현대자동차
    python -m autograph.ingestion.factoryon_registry --by-factory-no 123456
    python -m autograph.ingestion.factoryon_registry --by-industrial-complex 울산미포
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.parse
import urllib.request

from autonexusgraph.ingestion._common import (
    CheckpointStore,
    RateLimiter,
    save_raw,
)

from ..config import get_auto_settings


log = logging.getLogger(__name__)


_SOURCE = "auto/factoryon"
_LIMITER = RateLimiter(per_sec=2.0)
_BASE = "https://apis.data.go.kr/B550624/fctryRegistInfo"

# 3 endpoint 키. _v2 suffix 는 사용자 제공 정보 그대로.
ENDPOINTS = {
    "by_industrial_complex": "/getFctryListInIrsttService_v2",
    "by_factory_no":         "/getFctryByFctryManageNoService_v2",
    "by_company":            "/getFctryPrdctnService_v2",
}


def _fetch(endpoint: str, params: dict, *, return_xml: bool = False) -> bytes | dict:
    """단일 GET. 키 미설정 시 빈 dict."""
    s = get_auto_settings()
    if not s.data_go_kr_api_key:
        return {}
    full = dict(params)
    full["serviceKey"] = s.data_go_kr_api_key
    full.setdefault("type", "xml" if return_xml else "json")
    qs = urllib.parse.urlencode(full, quote_via=urllib.parse.quote)
    url = f"{_BASE}{endpoint}?{qs}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/xml" if return_xml else "application/json",
        "User-Agent": "AutoGraph-Research/0.1",
    })
    _LIMITER.acquire()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if return_xml:
                return raw
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        log.error("[factoryon] %s HTTP %s: %s", endpoint, e.code, e.reason)
        return b"" if return_xml else {}
    except Exception as e:   # noqa: BLE001
        log.error("[factoryon] %s 실패: %s", endpoint, e)
        return b"" if return_xml else {}


def _normalize_label(s: str) -> str:
    """파일명 안전 정규화 — 공백·슬래시 등 치환."""
    return (s or "").strip().replace("/", "_").replace(" ", "_") or "_"


def by_company(company_name: str, *, max_pages: int = 10,
               per_page: int = 100) -> int:
    """회사명 → 공장 + 생산품. /getFctryPrdctnService_v2."""
    s = get_auto_settings()
    if not s.data_go_kr_api_key:
        log.warning("[factoryon:by_company] DATA_GO_KR_API_KEY 미설정 — graceful skip")
        return 0

    ckpt = CheckpointStore(_SOURCE)
    total = 0
    label = _normalize_label(company_name)
    for page in range(1, max_pages + 1):
        key = f"by_company:{label}:p{page}"
        if ckpt.is_done(key):
            continue
        payload = _fetch(ENDPOINTS["by_company"],
                         {"page": page, "perPage": per_page,
                          "cmpnyNm": company_name})
        if not payload:
            break
        items = (payload.get("data") or payload.get("items")
                 or payload.get("response", {}).get("body", {}).get("items") or [])
        if not items:
            break
        save_raw(_SOURCE, f"by_company/{label}_page_{page:03d}.json", payload)
        ckpt.mark_done(key)
        total += len(items)
        if len(items) < per_page:
            break
    log.info("[factoryon:by_company] %s 누적 %d items", company_name, total)
    return total


def by_factory_no(factory_no: str) -> int:
    """공장관리번호 단일 조회."""
    s = get_auto_settings()
    if not s.data_go_kr_api_key:
        log.warning("[factoryon:by_factory_no] DATA_GO_KR_API_KEY 미설정 — graceful skip")
        return 0

    ckpt = CheckpointStore(_SOURCE)
    key = f"by_factory_no:{factory_no}"
    if ckpt.is_done(key):
        return 0
    payload = _fetch(ENDPOINTS["by_factory_no"],
                     {"fctryManageNo": factory_no})
    if not payload:
        return 0
    save_raw(_SOURCE, f"by_factory_no/{_normalize_label(factory_no)}.json", payload)
    ckpt.mark_done(key)
    return 1


def by_industrial_complex(complex_name: str, *,
                           max_pages: int = 50, per_page: int = 100) -> int:
    """산업단지명 → 단지 내 등록 공장 목록."""
    s = get_auto_settings()
    if not s.data_go_kr_api_key:
        log.warning("[factoryon:by_industrial_complex] DATA_GO_KR_API_KEY 미설정 — graceful skip")
        return 0

    ckpt = CheckpointStore(_SOURCE)
    total = 0
    label = _normalize_label(complex_name)
    for page in range(1, max_pages + 1):
        key = f"by_industrial_complex:{label}:p{page}"
        if ckpt.is_done(key):
            continue
        payload = _fetch(ENDPOINTS["by_industrial_complex"],
                         {"page": page, "perPage": per_page,
                          "irsttNm": complex_name})
        if not payload:
            break
        items = (payload.get("data") or payload.get("items")
                 or payload.get("response", {}).get("body", {}).get("items") or [])
        if not items:
            break
        save_raw(_SOURCE,
                 f"by_industrial_complex/{label}_page_{page:03d}.json", payload)
        ckpt.mark_done(key)
        total += len(items)
        if len(items) < per_page:
            break
    log.info("[factoryon:by_industrial_complex] %s 누적 %d items",
             complex_name, total)
    return total


def main() -> int:
    ap = argparse.ArgumentParser(prog="autograph.ingestion.factoryon_registry")
    ap.add_argument("--by-company", default=None,
                    help="회사명 검색 — getFctryPrdctnService_v2")
    ap.add_argument("--by-factory-no", default=None,
                    help="공장관리번호 단일 조회 — getFctryByFctryManageNoService_v2")
    ap.add_argument("--by-industrial-complex", default=None,
                    help="산업단지명 검색 — getFctryListInIrsttService_v2")
    ap.add_argument("--max-pages", type=int, default=10)
    ap.add_argument("--per-page", type=int, default=100)
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    actions = sum(1 for x in (args.by_company, args.by_factory_no,
                              args.by_industrial_complex) if x)
    if actions != 1:
        ap.error("--by-company | --by-factory-no | --by-industrial-complex 중 정확히 하나")

    if args.by_company:
        n = by_company(args.by_company, max_pages=args.max_pages,
                       per_page=args.per_page)
    elif args.by_factory_no:
        n = by_factory_no(args.by_factory_no)
    else:
        n = by_industrial_complex(args.by_industrial_complex,
                                   max_pages=args.max_pages,
                                   per_page=args.per_page)
    print(json.dumps({"items": n}))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "by_company",
    "by_factory_no",
    "by_industrial_complex",
    "ENDPOINTS",
]
