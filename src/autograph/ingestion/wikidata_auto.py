"""Wikidata SPARQL — 자동차 제조사/모델/부품사 마스터 + Cross-Domain 매핑 키 수집.

목적:
- AutoGraph manufacturer/model 의 정식 명칭·국가·QID 확보.
- finance 도메인 corp_code 와 매핑 가능한 외부 식별자 (LEI, ISIN, P3320 한국사업자번호 등) 동시 적재.

SPARQL 쿼리 (3종):
1) manufacturers : ?mfr wdt:P31 wd:Q786820 (자동차 제조 회사).
   추가: 한국·미국·일본·독일 등 주요국 한정 (P17).
2) models        : ?model wdt:P31/wdt:P279* wd:Q3231690 (자동차 모델).
3) suppliers     : ?supplier wdt:P31/wdt:P279* wd:Q1259897 (자동차 부품 제조사).

저장 (멱등):
    data/raw/auto/wikidata/manufacturers.jsonl
    data/raw/auto/wikidata/models.jsonl
    data/raw/auto/wikidata/suppliers.jsonl

CLI:
    python -m autograph.ingestion.wikidata_auto --kind manufacturers
    python -m autograph.ingestion.wikidata_auto --all
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from typing import Any

import httpx

from autonexusgraph.ingestion._common import (
    CheckpointStore,
    RateLimiter,
    fetch_with_retry,
    raw_dir,
    save_raw,
)
from ..config import get_auto_settings


log = logging.getLogger(__name__)

_LIMITER = RateLimiter(per_sec=1.0)        # SPARQL 보수적
_SOURCE = "auto/wikidata"

# Wikidata SPARQL 의 429 는 종종 ``Retry-After`` 헤더로 60+ 초를 요구한다.
# fetch_with_retry 의 기본 백오프 (base*2^n) 는 너무 빨라 429 가 계속 누적되므로
# 본 ingester 는 별도 retry-after-aware wrapper 사용.
_RATE_LIMIT_MAX_TRIES = 6
_RATE_LIMIT_BASE = 60.0    # 429 미수신 시 fallback 백오프
_RATE_LIMIT_CAP  = 300.0   # 한 retry 가 5분 이상 자게 두지 않음


# ── SPARQL 쿼리 ────────────────────────────────────────────────
SPARQL_MANUFACTURERS = """
SELECT ?mfr ?mfrLabel ?country ?countryLabel ?lei ?biznoKR WHERE {
  ?mfr wdt:P31/wdt:P279* wd:Q786820 .
  OPTIONAL { ?mfr wdt:P17 ?country . }
  OPTIONAL { ?mfr wdt:P1278 ?lei . }
  OPTIONAL { ?mfr wdt:P3320 ?biznoKR . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ko,en". }
}
"""

SPARQL_MODELS = """
SELECT ?model ?modelLabel ?mfr ?mfrLabel ?countryLabel ?inception WHERE {
  ?model wdt:P31/wdt:P279* wd:Q3231690 .
  OPTIONAL { ?model wdt:P176 ?mfr . }
  OPTIONAL { ?model wdt:P495 ?country . }
  OPTIONAL { ?model wdt:P571 ?inception . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ko,en". }
}
LIMIT 8000
"""

SPARQL_SUPPLIERS = """
SELECT ?supplier ?supplierLabel ?countryLabel ?lei ?biznoKR WHERE {
  { ?supplier wdt:P31/wdt:P279* wd:Q1259897 . }
  UNION
  { ?supplier wdt:P452 wd:Q190117 . }     # 자동차 부품 산업
  OPTIONAL { ?supplier wdt:P17 ?country . }
  OPTIONAL { ?supplier wdt:P1278 ?lei . }
  OPTIONAL { ?supplier wdt:P3320 ?biznoKR . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ko,en". }
}
LIMIT 5000
"""

# 자동차 부품 → 공급사 (P176 "manufactured by") 매핑. Wikidata 의 part-supplier
# 트리는 희소하지만 deterministic A/B 출처라 seed 가치가 있다. 결과는 staging_relations
# 에 candidate 로 적재 → P4 cross_validate 가 Neo4j 로 promote.
#
# 단일 쿼리는 종종 429 / timeout — 부품 class 별로 chunk 호출. 한 class 가
# 실패해도 나머지 class 결과는 보존 (체크포인트 단위 = 부품 class QID).
_PART_CLASSES: list[tuple[str, str]] = [
    ("Q1183344",  "vehicle_part"),
    ("Q3454322",  "automobile_part"),
    ("Q44539",    "ic_engine"),
    ("Q189075",   "transmission"),
    ("Q12888",    "battery"),
    ("Q193039",   "tire"),
    ("Q187588",   "brake"),
    ("Q1267283",  "airbag"),
    ("Q191768",   "alternator"),
    ("Q23905",    "spark_plug"),
]


def _sparql_part_supplies_for_class(class_qid: str) -> str:
    """단일 부품 class 의 P176 쿼리 — chunked 호출용."""
    return f"""
SELECT DISTINCT ?part ?partLabel ?supplier ?supplierLabel ?countryLabel WHERE {{
  ?part wdt:P31/wdt:P279* wd:{class_qid} .
  ?part wdt:P176 ?supplier .
  OPTIONAL {{ ?supplier wdt:P17 ?country . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ko,en". }}
}}
LIMIT 1000
"""


# 호환 — 기존 호출자가 본 상수를 import 하는 경우 대비. 실제 ingest 는 chunked.
SPARQL_PART_SUPPLIES = _sparql_part_supplies_for_class("Q1183344")

QUERIES = {
    "manufacturers": SPARQL_MANUFACTURERS,
    "models":        SPARQL_MODELS,
    "suppliers":     SPARQL_SUPPLIERS,
    "part_supplies": SPARQL_PART_SUPPLIES,
}


def _parse_retry_after(resp: "httpx.Response") -> float | None:
    """``Retry-After`` 헤더 파싱 — 초 단위. 무효 시 None."""
    raw = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw.strip())
    except (TypeError, ValueError):
        return None


def _sleep_for_429(attempt: int, retry_after: float | None) -> float:
    """429 시 대기 시간 결정 — Retry-After 우선, 없으면 지수 백오프."""
    if retry_after and retry_after > 0:
        return min(retry_after, _RATE_LIMIT_CAP)
    # 60s → 120s → 240s (cap 300)
    wait = _RATE_LIMIT_BASE * (2 ** max(0, attempt - 1))
    return min(wait, _RATE_LIMIT_CAP)


def _run_sparql(query: str, *, label: str = "") -> list[dict]:
    """SPARQL GET — 429 Retry-After 인식 + 지수 백오프.

    Wikidata 의 endpoint 는 1 req/min 으로 매우 좁다. 429 응답에는 통상
    ``Retry-After`` 헤더가 있으므로 그 값을 우선 사용. 헤더 없으면
    60→120→240 초 지수 백오프 (cap 300).

    다른 (네트워크/5xx) 예외는 ``fetch_with_retry`` (3회 base=3.0) 위임.
    """
    settings = get_auto_settings()
    headers = {
        "User-Agent": settings.wikidata_user_agent,
        "Accept": "application/sparql-results+json",
    }
    params = {"query": query, "format": "json"}

    def _do_once() -> list[dict]:
        with httpx.Client(timeout=120.0, headers=headers) as client:
            r = client.get(settings.wikidata_sparql_url, params=params)
            r.raise_for_status()
            return r.json().get("results", {}).get("bindings", [])

    last_exc: Exception | None = None
    for attempt in range(1, _RATE_LIMIT_MAX_TRIES + 1):
        _LIMITER.acquire()
        try:
            return _do_once()
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code == 429:
                wait = _sleep_for_429(attempt, _parse_retry_after(e.response))
                log.warning(
                    "[wikidata%s] 429 rate-limit — %s wait %.1fs (attempt %d/%d)",
                    f":{label}" if label else "",
                    "Retry-After" if _parse_retry_after(e.response) else "backoff",
                    wait, attempt, _RATE_LIMIT_MAX_TRIES,
                )
                last_exc = e
                if attempt < _RATE_LIMIT_MAX_TRIES:
                    time.sleep(wait)
                continue
            # 비-429 HTTP 에러 → 짧은 fetch_with_retry 위임 (5xx 등)
            log.warning("[wikidata%s] HTTP %s — fetch_with_retry 위임",
                        f":{label}" if label else "",
                        e.response.status_code if e.response else "?")
            return fetch_with_retry(_do_once, max_tries=3, base=3.0)
        except Exception as e:   # noqa: BLE001 — SPARQL 비-HTTP 예외 흡수 → fetch_with_retry 위임 (재시도 boundary)
            log.warning("[wikidata%s] %s — fetch_with_retry 위임",
                        f":{label}" if label else "", type(e).__name__)
            return fetch_with_retry(_do_once, max_tries=3, base=3.0)

    assert last_exc is not None
    raise last_exc


def _binding_to_row(b: dict) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in b.items():
        out[k] = v.get("value")
    # 'http://www.wikidata.org/entity/Q12345' → 'Q12345'
    for k in list(out.keys()):
        if isinstance(out[k], str) and out[k].startswith("http://www.wikidata.org/entity/"):
            out[k + "_qid"] = out[k].rsplit("/", 1)[-1]
    return out


def _ingest_part_supplies_chunked() -> dict:
    """P176 부품→공급사 매핑을 부품 class 별로 chunk 적재.

    한 class 가 429 한도 초과로 끝까지 실패해도 다른 class 결과는 보존.
    체크포인트 단위 = 부품 class — 부분 성공 후 재실행 시 done class 는 skip.
    최종 산출은 모든 jsonl chunk 를 합쳐 ``part_supplies.jsonl`` 로 머지.
    """
    ckpt = CheckpointStore(_SOURCE)
    target_dir = raw_dir(_SOURCE)
    merged_target = target_dir / "part_supplies.jsonl"

    total = 0
    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []
    all_bindings: list[dict] = []

    for class_qid, label in _PART_CLASSES:
        chunk_key = f"part_supplies:{class_qid}"
        chunk_path = target_dir / f"part_supplies_{label}.jsonl"

        if ckpt.is_done(chunk_key) and chunk_path.exists():
            log.info("[wikidata:part_supplies] %s (%s) already done — load cached",
                     class_qid, label)
            with chunk_path.open("r", encoding="utf-8") as f:
                cached = [json.loads(line) for line in f if line.strip()]
            all_bindings.extend(cached)
            total += len(cached)
            succeeded.append(class_qid)
            continue

        try:
            bindings = _run_sparql(
                _sparql_part_supplies_for_class(class_qid),
                label=f"part_supplies:{label}",
            )
            rows = [_binding_to_row(b) for b in bindings]
            with chunk_path.open("w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            ckpt.mark_done(chunk_key, {"rows": len(rows)})
            log.info("[wikidata:part_supplies] %s (%s) -> %d rows",
                     class_qid, label, len(rows))
            all_bindings.extend(rows)
            total += len(rows)
            succeeded.append(class_qid)
        except Exception as e:   # noqa: BLE001 — chunk 단위 실패 흡수 → checkpoint mark_failed + 다음 chunk (부분 성공 보존)
            ckpt.mark_failed(chunk_key, str(e))
            log.warning("[wikidata:part_supplies] %s (%s) 실패 — 보존 후 계속: %s",
                        class_qid, label, e)
            failed.append((class_qid, str(e)))

    # 머지 jsonl — 부분 성공이라도 후속 loader 가 통합 입력으로 쓸 수 있게.
    if all_bindings:
        with merged_target.open("w", encoding="utf-8") as f:
            for row in all_bindings:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        log.info("[wikidata:part_supplies] merged -> %s (%d rows from %d/%d chunks)",
                 merged_target.name, total, len(succeeded), len(_PART_CLASSES))

    # 모든 chunk done 이면 kind 전체 done 마킹 — 재실행 시 skip.
    if len(succeeded) == len(_PART_CLASSES):
        ckpt.mark_done("part_supplies", {"rows": total, "chunks": len(succeeded)})

    return {
        "kind": "part_supplies",
        "rows": total,
        "chunks_succeeded": len(succeeded),
        "chunks_failed": len(failed),
        "failed_classes": [q for q, _ in failed],
    }


def ingest_kind(kind: str) -> dict:
    if kind not in QUERIES:
        raise ValueError(f"unknown kind: {kind!r}")

    # part_supplies 는 chunked 경로 — 429 견딤성을 위해 부품 class 별 적재.
    if kind == "part_supplies":
        return _ingest_part_supplies_chunked()

    ckpt = CheckpointStore(_SOURCE)
    if ckpt.is_done(kind):
        log.info("[wikidata] %s already done (delete state to re-run)", kind)
        return {"skipped": True}

    try:
        bindings = _run_sparql(QUERIES[kind], label=kind)
        # JSONL append (멱등을 위해 일단 trunc 후 write)
        target = raw_dir(_SOURCE) / f"{kind}.jsonl"
        with target.open("w", encoding="utf-8") as f:
            for b in bindings:
                row = _binding_to_row(b)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        # raw 전체도 한 번 더 보존 (감사용)
        save_raw(_SOURCE, f"{kind}.raw.json", bindings)
        log.info("[wikidata] %s -> %d rows", kind, len(bindings))
        ckpt.mark_done(kind, {"rows": len(bindings)})
        return {"kind": kind, "rows": len(bindings)}
    except Exception as e:  # noqa: BLE001 — kind 전체 실패 흡수 → checkpoint mark_failed + error 반환 (다음 kind 진행)
        log.exception("[wikidata] failed %s", kind)
        ckpt.mark_failed(kind, str(e))
        return {"error": str(e)}


def main() -> None:
    ap = argparse.ArgumentParser(prog="autograph.ingestion.wikidata_auto")
    ap.add_argument("--kind", choices=sorted(QUERIES.keys()))
    ap.add_argument("--all", action="store_true", help="3종 전부")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()

    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    kinds = list(QUERIES.keys()) if args.all else ([args.kind] if args.kind else [])
    if not kinds:
        ap.error("--kind 또는 --all 필요")

    for k in kinds:
        ingest_kind(k)


if __name__ == "__main__":
    main()
