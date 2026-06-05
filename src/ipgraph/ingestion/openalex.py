"""OpenAlex 승격 — Institution / Work / AUTHORED_AT 적재.

전략 (한국 기업 R&D ↔ 특허 ↔ 재무 3중 cross 진입점):
    1. ``anxg_bridge.corp_entity`` + ``anxg_master.entity_map`` 의 wikidata_qid 풀로
       OpenAlex institutions 매칭 (filter=ids.wikidata:<QID>).
    2. 매칭된 institution 마다 상위 N 개 Work fetch
       (sort=cited_by_count:desc, type=article, last 5y).
    3. PG: anxg_ip.works + anxg_ip.institution + anxg_ip.work_institution 멱등 UPSERT.
    4. anxg_ip.institution.corp_code 는 매칭된 corp_entity 의 corp_code.

OpenAlex API 인증:
    ``OPENALEX_API_KEY`` (premium/authenticated plus tier) 또는 ``mailto`` 폴리트 풀.
    환경변수 없으면 무인증 (rate limit 낮음 — graceful 진행 가능하나 throttling 권장).

라이선스: OpenAlex = CC0. 본문 (abstract 등) 저장 OK.

PRD §3.5: OpenAlex 공식 통계 = A 등급 → confidence 0.95.

CLI:
    python -m ipgraph.ingestion.openalex --max-institutions 60 --works-per-inst 25
    python -m ipgraph.ingestion.openalex --dry-run --qids Q20718,Q59243,Q497534
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger(__name__)

_OA_BASE = "https://api.openalex.org"
_USER_AGENT = "AutoNexusGraph/1.0 (+contact: ifkbn@kolon.com)"
_THROTTLE_SEC = 0.15   # premium pool — 100 req/sec 안전 마진.


# ── 1. HTTP ────────────────────────────────────────────────────

def _http_get(url: str, *, params: dict | None = None, retries: int = 3) -> dict:
    key = os.environ.get("OPENALEX_API_KEY") or ""
    p = dict(params or {})
    if key:
        p["api_key"] = key
    else:
        # 폴리트 풀 fallback.
        p["mailto"] = os.environ.get("OPENALEX_MAILTO", "ifkbn@kolon.com")
    full_url = url + ("?" + urllib.parse.urlencode(p, safe=":,") if p else "")
    last: Exception | None = None
    for i in range(retries):
        req = urllib.request.Request(full_url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())
        except Exception as exc:   # noqa: BLE001 — boundary → RuntimeError 변환 (raise, silent 아님)
            last = exc
            log.warning("[openalex] fetch fail %d/%d: %s", i + 1, retries, exc)
            time.sleep(1.5 ** i)
    raise RuntimeError(f"openalex fetch failed: {last}")


# ── 2. QID 풀 ─────────────────────────────────────────────────

def _gather_qid_pool(cur, *, limit: int | None = None) -> list[dict]:
    """`anxg_bridge.corp_entity` + `anxg_master.entity_map(wikidata_qid)` 에서 unique QID 풀.

    return: [{qid, corp_code|None, name, source}, ...]
    """
    cur.execute("""
        WITH brides AS (
          -- bridge 는 corp_code 매칭됐거나 reviewed/manufacturer 인 것만 (정합 신뢰).
          SELECT wikidata_qid AS qid, corp_code, name, 'bridge' AS source
          FROM anxg_bridge.corp_entity
          WHERE wikidata_qid IS NOT NULL AND wikidata_qid <> ''
            AND (corp_code IS NOT NULL OR entity_type = 'manufacturer'
                 OR reviewed_status IN ('reviewed','validated'))
        ),
        em AS (
          -- anxg_master.entity_map(qid) 는 모든 295 상장사 매핑 — 신뢰 100%.
          SELECT em.id_value AS qid, em.corp_code, c.corp_name AS name, 'entity_map' AS source
          FROM anxg_master.entity_map em
          LEFT JOIN anxg_master.companies c USING (corp_code)
          WHERE em.id_type = 'wikidata_qid' AND em.id_value IS NOT NULL AND em.id_value <> ''
        ),
        all_rows AS (
          SELECT * FROM brides
          UNION ALL
          SELECT * FROM em
        )
        SELECT DISTINCT ON (qid) qid, corp_code, name, source
        FROM all_rows
        ORDER BY qid, CASE WHEN corp_code IS NOT NULL THEN 0 ELSE 1 END, source
    """)
    rows = [dict(qid=r[0], corp_code=r[1], name=r[2], source=r[3]) for r in cur.fetchall()]
    if limit:
        rows = rows[:limit]
    log.info("[openalex] QID pool=%d (limit=%s)", len(rows), limit)
    return rows


# ── 3. Institution lookup by QID ────────────────────────────

def lookup_institution_by_qid(qid: str, *,
                                hint_name: str | None = None) -> dict | None:
    """OpenAlex institution lookup by Wikidata QID.

    OpenAlex API 가 ``filter=ids.wikidata`` 를 지원하지 않으므로 우회 경로:
      1. hint_name 이 있으면 search 후 ids.wikidata 매칭 검증.
      2. 없으면 Wikidata Special:EntityData 에서 ROR (P6782) 추출 → ``ror:`` filter.
    """
    qid_norm = qid.split("/")[-1].strip()
    # 1. search-then-verify.
    if hint_name:
        body = _http_get(f"{_OA_BASE}/institutions",
                         params={"search": hint_name, "per-page": "5"})
        for rec in body.get("results") or []:
            wd = (rec.get("ids") or {}).get("wikidata") or ""
            if wd.rsplit("/", 1)[-1] == qid_norm:
                return rec
    # 2. Wikidata fallback (P6782 ROR ID).
    ror = _wikidata_qid_to_ror(qid_norm)
    if ror:
        try:
            body = _http_get(f"{_OA_BASE}/institutions/ror:{ror}", params={})
            if body and body.get("id"):
                return body
        except Exception as exc:   # noqa: BLE001 — fail-soft 흡수 → None 반환 (log 동반)
            log.debug("[openalex] ror:%s lookup failed: %s", ror, exc)
    return None


def _wikidata_qid_to_ror(qid: str) -> str | None:
    """Wikidata Q-id → ROR ID (P6782 property) via Special:EntityData."""
    url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as exc:   # noqa: BLE001 — fail-soft 흡수 → None 반환 (log 동반)
        log.debug("[openalex] wikidata fetch %s failed: %s", qid, exc)
        return None
    ent = (data.get("entities") or {}).get(qid) or {}
    claims = (ent.get("claims") or {}).get("P6782") or []   # ROR ID property
    for c in claims:
        try:
            return c["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue
    return None


def _normalize_institution(rec: dict) -> dict:
    """OpenAlex institution rec → anxg_ip.institution row dict."""
    ids = rec.get("ids") or {}
    ror = (rec.get("ror") or ids.get("ror") or "").rsplit("/", 1)[-1] or None
    qid = (ids.get("wikidata") or "").rsplit("/", 1)[-1] or None
    oa_id = (rec.get("id") or "").rsplit("/", 1)[-1] or None
    return {
        "ror_id":      ror,
        "openalex_id": oa_id,
        "name":        rec.get("display_name"),
        "country":     rec.get("country_code"),
        "type":        rec.get("type"),
        "wikidata_qid": qid,
        "works_count": rec.get("works_count"),
        "cited_by_count": rec.get("cited_by_count"),
    }


# ── 4. Works fetch ──────────────────────────────────────────

def fetch_works_for_institution(oa_inst_id: str, *,
                                  per_page: int = 25,
                                  max_pages: int = 1,
                                  type_filter: str = "article",
                                  from_year: int | None = None) -> list[dict]:
    """institution 의 상위 cited Work 목록 (가장 최근 → cite desc)."""
    filt = f"institutions.id:{oa_inst_id},type:{type_filter}"
    if from_year:
        filt += f",from_publication_date:{from_year}-01-01"
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        body = _http_get(f"{_OA_BASE}/works", params={
            "filter": filt,
            "per-page": str(per_page),
            "page": str(page),
            "sort": "cited_by_count:desc",
        })
        results = body.get("results") or []
        out.extend(results)
        if len(results) < per_page:
            break
        time.sleep(_THROTTLE_SEC)
    return out


def _normalize_work(rec: dict) -> dict:
    """OpenAlex work rec → anxg_ip.works row dict."""
    oa_id = (rec.get("id") or "").rsplit("/", 1)[-1] or None
    doi   = (rec.get("doi") or "").replace("https://doi.org/", "") or None
    abstract = _reconstruct_abstract(rec.get("abstract_inverted_index"))
    return {
        "openalex_id":     oa_id,
        "title":           rec.get("title"),
        "publication_year": rec.get("publication_year"),
        "cited_by_count":  rec.get("cited_by_count"),
        "doi":             doi,
        "type":            rec.get("type"),
        "abstract":        abstract,
    }


def _reconstruct_abstract(inverted: dict | None) -> str | None:
    """OpenAlex abstract_inverted_index → 원본 abstract 텍스트.

    OpenAlex 는 저작권 우회 위해 inverted-index 형태 (term → [positions]) 로 배포.
    위치 기준 재조립.
    """
    if not inverted:
        return None
    try:
        max_pos = max((p for positions in inverted.values() for p in positions), default=-1)
        if max_pos < 0:
            return None
        tokens = [""] * (max_pos + 1)
        for term, positions in inverted.items():
            for p in positions:
                if 0 <= p < len(tokens):
                    tokens[p] = term
        return " ".join(t for t in tokens if t)
    except Exception:   # noqa: BLE001 — fail-soft 흡수 → None 반환
        return None


def _extract_institution_ids_from_work(work: dict) -> list[str]:
    """work.authorships[].institutions[].id → 짧은 OpenAlex ID 리스트."""
    out: list[str] = []
    for a in work.get("authorships") or []:
        for inst in a.get("institutions") or []:
            iid = (inst.get("id") or "").rsplit("/", 1)[-1]
            if iid:
                out.append(iid)
    return list(dict.fromkeys(out))   # dedup, 순서 보존.


def _first_author_pos(work: dict, inst_id: str) -> str | None:
    for a in work.get("authorships") or []:
        for inst in a.get("institutions") or []:
            if (inst.get("id") or "").endswith(inst_id):
                return a.get("author_position")
    return None


# ── 5. PG UPSERT ─────────────────────────────────────────────

def _upsert_institution(cur, inst: dict, corp_code: str | None) -> bool:
    cur.execute("""
        INSERT INTO anxg_ip.institution
          (ror_id, openalex_id, name, country, type, corp_code)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (ror_id) DO UPDATE SET
          openalex_id = COALESCE(EXCLUDED.openalex_id, anxg_ip.institution.openalex_id),
          name        = COALESCE(EXCLUDED.name, anxg_ip.institution.name),
          country     = COALESCE(EXCLUDED.country, anxg_ip.institution.country),
          type        = COALESCE(EXCLUDED.type, anxg_ip.institution.type),
          corp_code   = COALESCE(EXCLUDED.corp_code, anxg_ip.institution.corp_code),
          updated_at  = now()
        RETURNING (xmax = 0) AS is_new
    """, (inst.get("ror_id"), inst.get("openalex_id"), inst.get("name"),
          inst.get("country"), inst.get("type"), corp_code))
    return bool(cur.fetchone()[0])


def _upsert_work(cur, w: dict) -> bool:
    cur.execute("""
        INSERT INTO anxg_ip.works
          (openalex_id, title, publication_year, cited_by_count, doi, type, abstract)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (openalex_id) DO UPDATE SET
          title             = COALESCE(EXCLUDED.title, anxg_ip.works.title),
          publication_year  = COALESCE(EXCLUDED.publication_year, anxg_ip.works.publication_year),
          cited_by_count    = GREATEST(COALESCE(anxg_ip.works.cited_by_count, 0), COALESCE(EXCLUDED.cited_by_count, 0)),
          doi               = COALESCE(EXCLUDED.doi, anxg_ip.works.doi),
          type              = COALESCE(EXCLUDED.type, anxg_ip.works.type),
          abstract          = COALESCE(EXCLUDED.abstract, anxg_ip.works.abstract),
          updated_at        = now()
        RETURNING (xmax = 0) AS is_new
    """, (w.get("openalex_id"), w.get("title"), w.get("publication_year"),
          w.get("cited_by_count"), w.get("doi"), w.get("type"), w.get("abstract")))
    return bool(cur.fetchone()[0])


def _upsert_work_institution(cur, openalex_work_id: str, ror_id: str,
                              author_position: str | None,
                              snapshot_year: int | None) -> None:
    cur.execute("""
        INSERT INTO anxg_ip.work_institution
          (openalex_id, ror_id, author_position, snapshot_year)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (openalex_id, ror_id) DO UPDATE SET
          author_position = COALESCE(EXCLUDED.author_position, anxg_ip.work_institution.author_position),
          snapshot_year   = COALESCE(EXCLUDED.snapshot_year,   anxg_ip.work_institution.snapshot_year)
    """, (openalex_work_id, ror_id, author_position, snapshot_year))


# ── 6. 메인 ────────────────────────────────────────────────

def run(*, max_institutions: int | None = None,
        works_per_inst: int = 25,
        qids: list[str] | None = None,
        from_year: int | None = 2020,
        dry_run: bool = False,
        raw_dir: Path | None = None) -> dict:
    if raw_dir is None:
        raw_dir = Path("data/raw/openalex")
    raw_dir.mkdir(parents=True, exist_ok=True)

    import psycopg2
    dsn = os.environ.get("POSTGRES_DSN") or _dsn_from_env()

    # 1. QID 풀 결정.
    if qids:
        pool = [{"qid": q, "corp_code": None, "name": None, "source": "cli"} for q in qids]
    else:
        conn = psycopg2.connect(dsn)
        try:
            with conn.cursor() as cur:
                pool = _gather_qid_pool(cur, limit=max_institutions)
        finally:
            conn.close()

    stats = {
        "qids_searched":         0,
        "institutions_matched":  0,
        "institutions_inserted": 0,
        "institutions_updated":  0,
        "works_inserted":        0,
        "works_updated":         0,
        "work_inst_edges":       0,
    }
    samples: list[dict] = []

    conn = psycopg2.connect(dsn) if not dry_run else None
    try:
        for entry in pool:
            qid = entry["qid"]
            stats["qids_searched"] += 1
            try:
                rec = lookup_institution_by_qid(qid, hint_name=entry.get("name"))
            except Exception as exc:   # noqa: BLE001 — 1 unit 실패 흡수 → log + continue (부분 성공 보존)
                log.warning("[openalex] inst lookup fail %s: %s", qid, exc)
                rec = None
            if not rec:
                continue
            inst = _normalize_institution(rec)
            if not inst.get("ror_id"):
                # ROR 없으면 PG PK 가 없어 skip.
                continue
            stats["institutions_matched"] += 1
            samples.append({
                "qid": qid, "corp_code": entry.get("corp_code"),
                "ror": inst["ror_id"], "openalex": inst["openalex_id"],
                "name": inst["name"], "type": inst["type"],
                "works_count": inst.get("works_count"),
            })
            # raw 보존.
            (raw_dir / f"institution_{inst['openalex_id']}.json").write_text(
                json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            time.sleep(_THROTTLE_SEC)

            if dry_run:
                continue

            with conn.cursor() as cur:
                cur.execute("SAVEPOINT sp_inst")
                try:
                    is_new = _upsert_institution(cur, inst, entry.get("corp_code"))
                    cur.execute("RELEASE SAVEPOINT sp_inst")
                    if is_new:
                        stats["institutions_inserted"] += 1
                    else:
                        stats["institutions_updated"] += 1
                except Exception as exc:   # noqa: BLE001 — 1 unit 실패 흡수 → log + continue (부분 성공 보존)
                    cur.execute("ROLLBACK TO SAVEPOINT sp_inst")
                    log.warning("[openalex:inst] %s fail: %s", inst.get("ror_id"), exc)
                    continue
            conn.commit()

            # Works fetch.
            try:
                works = fetch_works_for_institution(
                    inst["openalex_id"], per_page=works_per_inst,
                    max_pages=1, from_year=from_year)
            except Exception as exc:   # noqa: BLE001 — [openalex] works fetch 실패 흡수 → 빈 list + 다음 institution
                log.warning("[openalex] works fetch fail %s: %s", inst["openalex_id"], exc)
                works = []

            if works:
                (raw_dir / f"works_{inst['openalex_id']}.json").write_text(
                    json.dumps(works[:5], ensure_ascii=False), encoding="utf-8")

            with conn.cursor() as cur:
                for w in works:
                    nw = _normalize_work(w)
                    if not nw.get("openalex_id"):
                        continue
                    cur.execute("SAVEPOINT sp_w")
                    try:
                        is_new = _upsert_work(cur, nw)
                        cur.execute("RELEASE SAVEPOINT sp_w")
                        if is_new:
                            stats["works_inserted"] += 1
                        else:
                            stats["works_updated"] += 1
                    except Exception as exc:   # noqa: BLE001 — 1 unit 실패 흡수 → log + continue (부분 성공 보존)
                        cur.execute("ROLLBACK TO SAVEPOINT sp_w")
                        log.warning("[openalex:work] %s fail: %s", nw.get("openalex_id"), exc)
                        continue
                    # Work ↔ Institution edge.
                    cur.execute("SAVEPOINT sp_wi")
                    try:
                        pos = _first_author_pos(w, inst["openalex_id"])
                        _upsert_work_institution(cur, nw["openalex_id"], inst["ror_id"],
                                                  pos, nw.get("publication_year"))
                        stats["work_inst_edges"] += 1
                        cur.execute("RELEASE SAVEPOINT sp_wi")
                    except Exception as exc:   # noqa: BLE001 — [openalex:wi] work_institution edge 실패 흡수 → SAVEPOINT rollback + 다음 work
                        cur.execute("ROLLBACK TO SAVEPOINT sp_wi")
                        log.warning("[openalex:wi] %s/%s fail: %s",
                                    nw["openalex_id"], inst["ror_id"], exc)
            conn.commit()
            time.sleep(_THROTTLE_SEC)
    finally:
        if conn is not None:
            conn.close()

    return {
        "stats":   stats,
        "samples": samples[:8],
    }


def _dsn_from_env() -> str:
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("POSTGRES_DSN="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("POSTGRES_DSN 미설정")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-institutions", type=int, default=None,
                    help="QID 풀에서 처리할 최대 institution 수 (cost cap)")
    ap.add_argument("--works-per-inst", type=int, default=25)
    ap.add_argument("--qids", type=str, default=None,
                    help="콤마 분리 QID 직접 지정 (예 Q20718,Q59243)")
    ap.add_argument("--from-year", type=int, default=2020)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    qids = [q.strip() for q in args.qids.split(",")] if args.qids else None
    out = run(max_institutions=args.max_institutions,
              works_per_inst=args.works_per_inst,
              qids=qids,
              from_year=args.from_year,
              dry_run=args.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["run", "lookup_institution_by_qid", "fetch_works_for_institution"]
