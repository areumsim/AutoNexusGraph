"""Wikipedia (ko/en) 자동차 본문 ingestion — 키 불필요.

대상:
    auto.master_vehicle_models.name  (예: 'Sonata', 'Grandeur', 'Model Y')
    auto.master_manufacturers.name   (예: 'Hyundai', 'Tesla', 'Genesis')

전략:
    1) Wikidata QID 가 있으면 sitelinks 로 정확 title 획득 (가장 신뢰).
    2) 없으면 name 직접 시도 (Wikipedia 가 redirect 해결).
    3) ko 우선, 실패 시 en fallback.
    4) summary + html + infobox 한 번에 fetch — 본문 청크에 사용.

저장:
    data/raw/auto/wikipedia/{LANG}/models/{model_id}.json
    data/raw/auto/wikipedia/{LANG}/manufacturers/{manufacturer_id}.json

retrieve.py 의 ``AUTO_SOURCES`` 에 등장하는 ``wikipedia_auto`` source 가 본 모듈이
producer. build_chunks_auto.build_from_wikipedia() 가 청크로 변환.

CLI:
    python -m autograph.ingestion.wikipedia_auto --models
    python -m autograph.ingestion.wikipedia_auto --manufacturers
    python -m autograph.ingestion.wikipedia_auto --all
    python -m autograph.ingestion.wikipedia_auto --models --lang en
    python -m autograph.ingestion.wikipedia_auto --models --limit 30
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import re
from typing import Any

from autonexusgraph.db.postgres import get_connection
from autonexusgraph.ingestion._common import (
    CheckpointStore,
    RateLimiter,
    save_raw,
)
from autonexusgraph.ingestion.wikipedia_client import WikipediaClient


log = logging.getLogger(__name__)


_SOURCE = "auto/wikipedia"
# 한국·영문 위키 보수적 1.5 req/sec — 본문까지 받으므로 무거움.
_LIMITER = RateLimiter(per_sec=1.5)


def _title_from_qid(qid: str, lang: str) -> str | None:
    """Wikidata sitelinks 에서 {lang}wiki title 추출. 실패 시 None.

    https://www.wikidata.org/wiki/Special:EntityData/{qid}.json
    """
    import httpx
    url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    try:
        with httpx.Client(timeout=15.0,
                          headers={"User-Agent": "AutoGraph-Research/0.1"}) as c:
            r = c.get(url)
            if r.status_code != 200:
                return None
            data = r.json()
    except Exception:   # noqa: BLE001
        return None
    entity = (data.get("entities") or {}).get(qid)
    if not entity:
        return None
    sitelinks = entity.get("sitelinks") or {}
    sl = sitelinks.get(f"{lang}wiki")
    if isinstance(sl, dict):
        return sl.get("title")
    return None


def _fetch_entity_pages(
    *,
    entity_kind: str,           # 'models' | 'manufacturers'
    rows: list[tuple],          # (id, name, wikidata_qid)
    lang: str,
    with_html: bool,
    with_infobox: bool,
) -> dict[str, int]:
    """rows 각각에 대해 Wikipedia 조회 + raw 저장. dict 통계 반환."""
    ckpt = CheckpointStore(f"{_SOURCE}/{lang}/{entity_kind}")
    stats = {"fetched": 0, "skipped": 0, "missing": 0, "errors": 0}

    with WikipediaClient(lang=lang) as wiki:
        for eid, name, qid in rows:
            key = f"{lang}|{entity_kind}|{eid}"
            if ckpt.is_done(key):
                stats["skipped"] += 1
                ckpt.mark_skipped()
                continue

            # title 결정 — QID 우선, fallback 으로 name.
            title: str | None = None
            if qid:
                _LIMITER.acquire()
                try:
                    title = _title_from_qid(qid, lang)
                except Exception as e:   # noqa: BLE001
                    log.debug("[wiki:%s] qid->title 실패 %s: %s", lang, qid, e)
            if not title:
                title = name
            if not title:
                stats["missing"] += 1
                continue

            _LIMITER.acquire()
            try:
                page = wiki.fetch(title, with_html=with_html,
                                  with_infobox=with_infobox)
            except Exception as e:   # noqa: BLE001
                log.warning("[wiki:%s] fetch %s 실패: %s", lang, title, e)
                stats["errors"] += 1
                ckpt.mark_failed(key, str(e))
                continue

            if not page or not page.extract:
                # 미존재 → search fallback 한 번.
                try:
                    hits = wiki.search(name or title, limit=1)
                    if hits:
                        alt = hits[0].get("title")
                        if alt and alt != title:
                            _LIMITER.acquire()
                            page = wiki.fetch(alt, with_html=with_html,
                                              with_infobox=with_infobox)
                except Exception as e:   # noqa: BLE001
                    log.debug("[wiki:%s] search %s 실패: %s", lang, name, e)

            if not page or not page.extract:
                stats["missing"] += 1
                ckpt.mark_done(key, {"missing": True, "title": title})
                continue

            # 저장 — dataclass 를 dict 으로.
            payload: dict[str, Any] = dataclasses.asdict(page)
            # html 은 대용량 — 길면 본문만 저장. infobox/extract 가 핵심.
            if payload.get("html") and len(payload["html"]) > 200_000:
                payload["html"] = payload["html"][:200_000] + "...<TRUNCATED>"
            payload["__entity"] = {"kind": entity_kind, "id": eid, "name": name,
                                    "qid": qid}
            rel = f"{lang}/{entity_kind}/{eid}.json"
            try:
                save_raw(_SOURCE, rel, payload)
                stats["fetched"] += 1
                ckpt.mark_done(key, {"title": page.title,
                                     "extract_len": len(page.extract or "")})
                log.info("[wiki:%s] %s [%s] %s → %d chars",
                         lang, entity_kind, eid, page.title,
                         len(page.extract or ""))
            except Exception as e:   # noqa: BLE001
                log.warning("[wiki:%s] save %s 실패: %s", lang, key, e)
                stats["errors"] += 1
                ckpt.mark_failed(key, str(e))

    return stats


_PLANT_NAME_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _normalize_plant_name_for_wiki(name: str) -> str:
    """plants.yaml name 의 괄호 부연 strip — Wikipedia fuzzy search 정확도 향상.

    예:
        'Hyundai Motor Group Metaplant America (HMGMA, EV 전용)' →
            'Hyundai Motor Group Metaplant America'
        'Hyundai Motor Türkiye (HMTR, HAOS 별표기)' →
            'Hyundai Motor Türkiye'
        '현대자동차 울산공장' → (변경 없음)

    Wikipedia search 가 'List of Coca-Cola brands' / 'Kia Ceed' 같이 엉뚱한
    페이지로 빠지던 원인 해결.
    """
    if not name:
        return ""
    # 끝에 붙은 (...) 1회 제거. 중간 괄호는 보존 (예: 'Tesla, Inc.').
    while True:
        new = _PLANT_NAME_PAREN_RE.sub("", name).strip()
        if new == name:
            break
        name = new
    return name


_HANGUL_RE = re.compile(r"[가-힣]")


def _has_korean(text: str) -> bool:
    """이름에 한글이 있는가."""
    return bool(_HANGUL_RE.search(text or ""))


def _load_plants_from_yaml(limit: int | None) -> list[tuple]:
    """``ontology/auto/plants.yaml`` 의 plant 목록 → (code, normalized_name, wikidata_qid).

    plants.yaml 의 schema:
        plants:
          - code: HYU_ULSAN
            name: 현대자동차 울산공장
            manufacturer_name: HYUNDAI
            country: KR
            city: Ulsan
            wikidata_qid: Q5928430   # optional

    name 의 괄호 부연 ('(HMGMA, EV 전용)' 등) 은 정규화 후 wiki 검색에 사용.
    """
    from ..ontology import load_plants
    plants = load_plants() or []
    rows: list[tuple] = []
    for p in plants:
        raw_name = p.get("name") or ""
        clean_name = _normalize_plant_name_for_wiki(raw_name)
        rows.append((p.get("code"), clean_name, p.get("wikidata_qid")))
    if limit:
        rows = rows[:limit]
    return rows


def _load_models_from_pg(limit: int | None) -> list[tuple]:
    conn = get_connection()
    with conn.cursor() as cur:
        q = """
            SELECT model_id, name, wikidata_qid
              FROM auto.master_vehicle_models
             ORDER BY model_id
        """
        if limit:
            q += f" LIMIT {int(limit)}"
        cur.execute(q)
        return list(cur.fetchall())


def _load_manufacturers_from_pg(limit: int | None) -> list[tuple]:
    conn = get_connection()
    with conn.cursor() as cur:
        q = """
            SELECT manufacturer_id, name, wikidata_qid
              FROM auto.master_manufacturers
             ORDER BY manufacturer_id
        """
        if limit:
            q += f" LIMIT {int(limit)}"
        cur.execute(q)
        return list(cur.fetchall())


def ingest(
    *,
    targets: tuple[str, ...] = ("models", "manufacturers"),
    lang: str = "ko",
    with_html: bool = True,
    with_infobox: bool = True,
    limit: int | None = None,
    fallback_lang: str | None = "en",
) -> dict[str, dict[str, int]]:
    """전체 또는 일부 entity 의 wikipedia 본문 수집.

    fallback_lang 가 주어지면 1차 lang 에서 미발견인 entity 만 fallback 으로 재시도.
    """
    out: dict[str, dict[str, int]] = {}
    for tgt in targets:
        if tgt == "plants":
            rows = _load_plants_from_yaml(limit)
        elif tgt == "models":
            rows = _load_models_from_pg(limit)
        else:
            rows = _load_manufacturers_from_pg(limit)
        if not rows:
            log.warning("[wiki] %s PG 비어있음 — vpic/wikidata 적재 선행 필요", tgt)
            out[f"{lang}/{tgt}"] = {"fetched": 0, "skipped": 0,
                                     "missing": 0, "errors": 0}
            continue

        # plants 최적화 (2026-06-01): 비한국 plant name (Tesla/BMW/Toyota 등) 은
        # 1차 ko 검색을 skip — 어차피 한국어 wiki 에 없음. en 우선 시도.
        rows_for_primary = rows
        if tgt == "plants" and lang == "ko":
            rows_for_primary = [(c, n, q) for (c, n, q) in rows if _has_korean(n)]
            n_skipped_ko = len(rows) - len(rows_for_primary)
            if n_skipped_ko:
                log.info("[wiki:plants] %d non-Korean names → ko skip, en 직행",
                         n_skipped_ko)

        log.info("[wiki] %s — %d entities (primary lang=%s)",
                 tgt, len(rows_for_primary), lang)
        stats = _fetch_entity_pages(
            entity_kind=tgt, rows=rows_for_primary, lang=lang,
            with_html=with_html, with_infobox=with_infobox,
        )
        out[f"{lang}/{tgt}"] = stats

        # 미발견 entity (+ ko-skipped non-Korean) 모두 fallback_lang 시도.
        fallback_rows = rows if tgt == "plants" else rows
        if (fallback_lang and fallback_lang != lang
                and (stats["missing"] or
                     len(rows_for_primary) < len(rows))):
            log.info("[wiki:%s→%s] %d missing entities 재시도",
                     lang, fallback_lang, stats["missing"])
            stats_fb = _fetch_entity_pages(
                entity_kind=tgt, rows=rows, lang=fallback_lang,
                with_html=with_html, with_infobox=with_infobox,
            )
            out[f"{fallback_lang}/{tgt}"] = stats_fb

    return out


def main() -> None:
    ap = argparse.ArgumentParser(prog="autograph.ingestion.wikipedia_auto")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--models", action="store_true",
                      help="auto.master_vehicle_models 본문 수집")
    grp.add_argument("--manufacturers", action="store_true",
                      help="auto.master_manufacturers 본문 수집")
    grp.add_argument("--plants", action="store_true",
                      help="ontology/auto/plants.yaml 의 plant 본문 수집 (2026-06-01 신규)")
    grp.add_argument("--all", action="store_true",
                      help="models + manufacturers + plants 모두")
    ap.add_argument("--lang", default="ko", choices=["ko", "en"])
    ap.add_argument("--fallback-lang", default="en",
                    help="1차 미발견 시 재시도 언어. 'none' 으로 비활성.")
    ap.add_argument("--no-html", action="store_true",
                    help="HTML 본문 skip (summary + infobox 만)")
    ap.add_argument("--no-infobox", action="store_true")
    ap.add_argument("--limit", type=int, default=None,
                    help="PG 에서 최대 N entity (smoke test)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()

    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.all:
        targets: tuple[str, ...] = ("models", "manufacturers", "plants")
    elif args.models:
        targets = ("models",)
    elif args.manufacturers:
        targets = ("manufacturers",)
    elif args.plants:
        targets = ("plants",)
    else:
        ap.error("--models / --manufacturers / --plants / --all 중 하나 필요")

    fb = None if args.fallback_lang.lower() == "none" else args.fallback_lang
    stats = ingest(
        targets=targets,
        lang=args.lang,
        with_html=not args.no_html,
        with_infobox=not args.no_infobox,
        limit=args.limit,
        fallback_lang=fb,
    )
    log.info("[wiki] done: %s", json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()


__all__ = ["ingest", "_fetch_entity_pages", "_title_from_qid"]
