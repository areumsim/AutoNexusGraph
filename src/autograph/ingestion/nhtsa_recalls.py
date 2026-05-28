"""NHTSA Recalls API — 차종별 리콜 캠페인 수집.

엔드포인트 (키 불필요):
    GET https://api.nhtsa.gov/recalls/recallsByVehicle
        ?make=HYUNDAI&model=SONATA&modelYear=2024

응답 형식 (대략):
    {
      "count": N,
      "results": [
        {
          "Manufacturer": "...", "NHTSACampaignNumber": "23V-xxx",
          "ReportReceivedDate": "01/15/2023",
          "Component": "...", "Summary": "...", "Consequence": "...",
          "Remedy": "...", "Notes": "...",
          "ModelYear": "2024", "Make": "HYUNDAI", "Model": "SONATA",
          "PotentialNumberofUnitsAffected": "..."
        }, ...
      ]
    }

저장:
    data/raw/auto/nhtsa_recalls/{MAKE}/{MODEL}/{YEAR}.json

models 목록은 nhtsa_vpic 적재 결과(`data/raw/auto/nhtsa_vpic/{make}/{year}/variants.jsonl`)에서
가져온다. vpic 적재가 선행돼야 효율적 (없으면 --models 인자로 직접 받음).

CLI:
    python -m autograph.ingestion.nhtsa_recalls --make HYUNDAI --year 2024
    python -m autograph.ingestion.nhtsa_recalls --make HYUNDAI --year 2024 --models SONATA,TUCSON
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import httpx

from fingraph.config import get_settings
from fingraph.ingestion._common import (
    CheckpointStore,
    RateLimiter,
    fetch_with_retry,
    save_raw,
)
from ..config import get_auto_settings


log = logging.getLogger(__name__)

_LIMITER = RateLimiter(per_sec=4.0)
_SOURCE = "auto/nhtsa_recalls"


def _http_get(url: str, params: dict) -> dict:
    settings = get_auto_settings()
    headers = {"User-Agent": settings.wikidata_user_agent}

    def _do() -> dict:
        with httpx.Client(timeout=30.0, headers=headers) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            return r.json()

    _LIMITER.acquire()
    return fetch_with_retry(_do, max_tries=5)


def _models_from_vpic(make: str, year: int) -> list[str]:
    """vpic 캐시에서 모델명 목록. 없으면 빈 리스트."""
    fg = get_settings()
    p = fg.ingest_raw_dir / "auto" / "nhtsa_vpic" / make / str(year) / "variants.jsonl"
    if not p.exists():
        return []
    out: list[str] = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                m = row.get("model_name")
                if m:
                    out.append(m)
            except json.JSONDecodeError:
                continue
    return sorted(set(out))


def fetch_recalls(make: str, model: str, year: int) -> dict:
    settings = get_auto_settings()
    url = f"{settings.nhtsa_api_base_url}/recalls/recallsByVehicle"
    data = _http_get(url, {"make": make, "model": model, "modelYear": year})
    rel = f"{make}/{model}/{year}.json"
    save_raw(_SOURCE, rel, data)
    n = len(data.get("results") or [])
    log.info("[recalls] %s %s %s -> %d", make, model, year, n)
    return data


def ingest_make_year(make: str, year: int, *,
                     models: list[str] | None = None) -> dict:
    if not models:
        models = _models_from_vpic(make, year)
    if not models:
        log.warning("[recalls] %s %s: models 비어있음 — vpic 먼저 실행 또는 --models 지정", make, year)
        return {"models": 0}

    ckpt = CheckpointStore(_SOURCE)
    n_done = 0
    n_recalls = 0
    for model in models:
        key = f"{make}|{model}|{year}"
        if ckpt.is_done(key):
            ckpt.mark_skipped()
            continue
        try:
            data = fetch_recalls(make, model, year)
            n_done += 1
            n_recalls += len(data.get("results") or [])
            ckpt.mark_done(key, {"recalls": len(data.get("results") or [])})
        except Exception as e:  # noqa: BLE001
            log.exception("[recalls] failed %s", key)
            ckpt.mark_failed(key, str(e))

    return {"models_fetched": n_done, "recalls_total": n_recalls}


def main() -> None:
    ap = argparse.ArgumentParser(prog="autograph.ingestion.nhtsa_recalls")
    ap.add_argument("--make", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--models", help="콤마 구분. 없으면 vpic 캐시에서 가져옴.")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()

    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    models = None
    if args.models:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
    out = ingest_make_year(args.make.upper(), args.year, models=models)
    log.info("[recalls] done %s", out)


if __name__ == "__main__":
    main()
