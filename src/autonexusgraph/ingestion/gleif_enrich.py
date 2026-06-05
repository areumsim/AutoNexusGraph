"""GLEIF KR LEI 보강 — `entity.registeredAs` (사업자번호) 추출 + corp_code 매칭.

기존 `anxg_sec.lei` 2,700 row 는 LEI + legalName 만 보유, `corp_code` 113 row 만 매칭됨.
GLEIF Public API (https://api.gleif.org/api/v1/lei-records) 의 ``filter[entity.jurisdiction]=KR``
페이지네이션으로 2,704 KR LEI 의 ``entity.registeredAs`` (= KR 사업자등록번호) 를 가져와
``anxg_master.entity_map`` 의 business_no SSOT 와 매칭 후 ``anxg_sec.lei.corp_code`` /
``anxg_master.entity_map(id_type='lei')`` / ``anxg_bridge.corp_entity.lei`` 를 멱등 UPSERT.

라이선스: GLEIF Level 1/2 data = CC0. 무인증.
OpenCorporates ID-to-LEI 매핑 파일은 GLEIF 사이트에서 form-gated — 본 모듈은
한국 한정 시나리오라 GLEIF API 의 registeredAs 만으로 충분 (OC 우회).

참고: data.go.kr 등 한국 business_no 는 10자리 또는 (3-2-5) dashed 양식이 혼재.
본 모듈은 ``_normalize_business_no()`` 로 dash 제거 후 비교.

API:
    fetch_kr_leis(*, page_size=200, max_pages=None) -> list[dict]
    enrich() -> dict  (PG UPSERT 통계)

PRD §3.5: GLEIF = A 등급 (공공 LEI 인증), confidence 0.95.
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
from typing import Any

log = logging.getLogger(__name__)

_GLEIF_BASE = "https://api.gleif.org/api/v1/lei-records"
_USER_AGENT = "AutoNexusGraph/1.0 (+contact: ifkbn@kolon.com)"
_THROTTLE_SEC = 0.4   # GLEIF Fair Use 100 req/min → ~0.6s/req 안전.
_SCHEMA_VERSION = "v2.2"


# ── 1. fetch ────────────────────────────────────────────────────

def _http_get_json(url: str, *, retries: int = 3) -> dict:
    last_exc: Exception | None = None
    for i in range(retries):
        req = urllib.request.Request(url, headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/vnd.api+json",
        })
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())
        except Exception as exc:   # noqa: BLE001
            last_exc = exc
            log.warning("[gleif] fetch fail (attempt %d/%d): %s", i + 1, retries, exc)
            time.sleep(1.5 ** i)
    raise RuntimeError(f"GLEIF fetch failed after {retries} retries: {last_exc}")


def fetch_kr_leis(*, page_size: int = 200,
                   max_pages: int | None = None,
                   raw_dir: Path | None = None) -> list[dict]:
    """``filter[entity.jurisdiction]=KR`` 으로 모든 KR LEI 페이지 순회.

    Returns: ``[{lei, legal_name, business_no, jurisdiction, status, registered_at, ...}, ...]``

    raw_dir 가 주어지면 raw JSON page 를 ``gleif_kr_p<n>.json`` 으로 저장 (provenance).
    """
    if raw_dir is not None:
        raw_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    page = 1
    while True:
        params = {
            "filter[entity.jurisdiction]": "KR",
            "page[size]":   str(page_size),
            "page[number]": str(page),
        }
        url = f"{_GLEIF_BASE}?{urllib.parse.urlencode(params, safe='[]')}"
        log.info("[gleif] fetching page %d (size=%d)", page, page_size)
        body = _http_get_json(url)

        if raw_dir is not None:
            (raw_dir / f"gleif_kr_p{page:03d}.json").write_text(
                json.dumps(body, ensure_ascii=False),
                encoding="utf-8",
            )

        meta = body.get("meta", {}).get("pagination", {})
        last_page = int(meta.get("lastPage") or 1)
        for rec in body.get("data") or []:
            attrs = rec.get("attributes") or {}
            ent = attrs.get("entity") or {}
            reg = attrs.get("registration") or {}
            rows.append({
                "lei":            attrs.get("lei") or rec.get("id"),
                "legal_name":    (ent.get("legalName") or {}).get("name"),
                "legal_name_en": _extract_en_name(ent),
                "business_no":   _normalize_business_no(ent.get("registeredAs")),
                "jurir_no":      _normalize_jurir_no(ent.get("registeredAs")),
                "business_no_raw": ent.get("registeredAs"),
                "jurisdiction":  ent.get("jurisdiction"),
                "status":        ent.get("status"),
                "registered_at_id": (ent.get("registeredAt") or {}).get("id"),
                "registration_status": reg.get("status"),
                "issued_at":     (reg.get("initialRegistrationDate") or "")[:10] or None,
                "next_renewal_at": (reg.get("nextRenewalDate") or "")[:10] or None,
            })

        log.info("[gleif] page %d/%d — accumulated %d rows", page, last_page, len(rows))
        if max_pages and page >= max_pages:
            break
        if page >= last_page:
            break
        page += 1
        time.sleep(_THROTTLE_SEC)
    return rows


def _extract_en_name(ent: dict) -> str | None:
    for n in ent.get("otherNames") or []:
        if isinstance(n, dict) and (n.get("language") or "").lower() == "en":
            return n.get("name")
    return None


def _normalize_business_no(raw: str | None) -> str | None:
    """GLEIF registeredAs (KR) → 10-digit business_no.

    KR LEI 의 registeredAs 는 두 형식:
      - '105-81-87072' (10자리 사업자번호)
      - '110111-0671928' (13자리 법인등록번호) → business_no 아님 → None.
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    return digits if len(digits) == 10 else None


def _normalize_jurir_no(raw: str | None) -> str | None:
    """GLEIF registeredAs (KR) → 13-digit jurir_no (법인등록번호)."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    return digits if len(digits) == 13 else None


# ── 2. PG UPSERT ────────────────────────────────────────────────

def _build_corp_lookup(cur) -> dict[str, str]:
    """anxg_master.entity_map 에서 (business_no | jurir_no) → corp_code 매핑 dict.

    Key 는 digits-only 정규화 후 길이 10 (business_no) 또는 13 (jurir_no).
    """
    cur.execute("""
        SELECT id_type, id_value, corp_code FROM anxg_master.entity_map
        WHERE id_type IN ('business_no','jurir_no') AND id_value IS NOT NULL
    """)
    out: dict[str, str] = {}
    for _idt, v, corp in cur.fetchall():
        digits = re.sub(r"\D", "", str(v))
        if len(digits) in (10, 13):
            out[digits] = corp
    return out


def _measure_baseline(cur) -> dict[str, int]:
    """before-state 측정 — strong-match 비율 산정용."""
    cur.execute("""
        SELECT
          COUNT(*) FILTER (WHERE id_type='lei') AS em_lei,
          COUNT(*) FILTER (WHERE id_type='business_no') AS em_biz
        FROM anxg_master.entity_map
    """)
    em_lei, em_biz = cur.fetchone()

    cur.execute("SELECT count(*) FROM anxg_sec.lei WHERE corp_code IS NOT NULL AND corp_code <> ''")
    sec_with_corp = cur.fetchone()[0]

    cur.execute("""
        SELECT
          COUNT(*) FILTER (WHERE entity_type='manufacturer' AND match_method IN ('lei','wikidata_qid','business_no','sec_cik')) AS mfr_strong,
          COUNT(*) FILTER (WHERE entity_type='manufacturer') AS mfr_total,
          COUNT(*) FILTER (WHERE entity_type='supplier'     AND match_method IN ('lei','wikidata_qid','business_no','sec_cik')) AS sup_strong,
          COUNT(*) FILTER (WHERE entity_type='supplier') AS sup_total,
          COUNT(*) FILTER (WHERE lei IS NOT NULL AND lei <> '') AS rows_with_lei
        FROM anxg_bridge.corp_entity
    """)
    mfr_s, mfr_t, sup_s, sup_t, rows_lei = cur.fetchone()
    return {
        "entity_map_lei":     em_lei,
        "entity_map_biz":     em_biz,
        "sec_lei_with_corp":  sec_with_corp,
        "bridge_mfr_strong":  mfr_s,
        "bridge_mfr_total":   mfr_t,
        "bridge_sup_strong":  sup_s,
        "bridge_sup_total":   sup_t,
        "bridge_rows_with_lei": rows_lei,
    }


def enrich(*, rows: list[dict] | None = None,
           max_pages: int | None = None,
           raw_dir: Path | None = None,
           dry_run: bool = False) -> dict:
    """KR LEI fetch + PG UPSERT (anxg_sec.lei, anxg_master.entity_map, anxg_bridge.corp_entity)."""
    if raw_dir is None:
        raw_dir = Path("data/raw/gleif/kr")

    if rows is None:
        rows = fetch_kr_leis(max_pages=max_pages, raw_dir=raw_dir)
    log.info("[gleif] fetched %d KR LEIs", len(rows))
    with_biz = sum(1 for r in rows if r.get("business_no"))
    log.info("[gleif] %d/%d rows have valid business_no (10-digit)", with_biz, len(rows))

    if dry_run:
        return {
            "n_rows": len(rows),
            "with_business_no": with_biz,
            "preview": rows[:3],
        }

    import psycopg2
    dsn = os.environ.get("POSTGRES_DSN") or _dsn_from_env()
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            baseline = _measure_baseline(cur)
            log.info("[gleif] baseline: %s", baseline)

            corp_lookup = _build_corp_lookup(cur)
            log.info("[gleif] PG has %d business_no→corp_code mappings", len(corp_lookup))

            stats = {
                "sec_lei_upserted":   0,
                "sec_lei_corp_filled": 0,
                "em_lei_inserted":    0,
                "em_lei_updated":     0,
                "bridge_lei_updated": 0,
                "bridge_match_upgraded": 0,
            }

            for r in rows:
                lei = r["lei"]
                biz = r.get("business_no")
                jur = r.get("jurir_no")
                cc = (corp_lookup.get(biz) if biz else None) or (corp_lookup.get(jur) if jur else None)

                # 2-1. anxg_sec.lei UPSERT — corp_code 동기화.
                cur.execute("SAVEPOINT sp_sec_lei")
                try:
                    cur.execute("""
                        INSERT INTO anxg_sec.lei
                          (lei, corp_code, legal_name, legal_jurisdiction,
                           entity_status, registration_status, issued_at, next_renewal_at, raw)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (lei) DO UPDATE SET
                          corp_code           = COALESCE(EXCLUDED.corp_code, anxg_sec.lei.corp_code),
                          legal_name          = COALESCE(EXCLUDED.legal_name, anxg_sec.lei.legal_name),
                          legal_jurisdiction  = COALESCE(EXCLUDED.legal_jurisdiction, anxg_sec.lei.legal_jurisdiction),
                          entity_status       = COALESCE(EXCLUDED.entity_status, anxg_sec.lei.entity_status),
                          registration_status = COALESCE(EXCLUDED.registration_status, anxg_sec.lei.registration_status),
                          issued_at           = COALESCE(EXCLUDED.issued_at, anxg_sec.lei.issued_at),
                          next_renewal_at     = COALESCE(EXCLUDED.next_renewal_at, anxg_sec.lei.next_renewal_at),
                          raw                 = anxg_sec.lei.raw || EXCLUDED.raw
                        RETURNING (anxg_sec.lei.corp_code IS NOT NULL) AS had_corp
                    """, (
                        lei, cc, r.get("legal_name"), r.get("jurisdiction"),
                        r.get("status"), r.get("registration_status"),
                        r.get("issued_at"), r.get("next_renewal_at"),
                        json.dumps({"gleif_enrich": True,
                                    "business_no_raw": r.get("business_no_raw"),
                                    "legal_name_en":  r.get("legal_name_en")},
                                    ensure_ascii=False),
                    ))
                    had_corp = cur.fetchone()[0]
                    if cc and not had_corp:
                        stats["sec_lei_corp_filled"] += 1
                    stats["sec_lei_upserted"] += 1
                    cur.execute("RELEASE SAVEPOINT sp_sec_lei")
                except Exception as exc:   # noqa: BLE001
                    cur.execute("ROLLBACK TO SAVEPOINT sp_sec_lei")
                    log.warning("[gleif:sec_lei] %s fail: %s", lei, exc)

                # 2-2. anxg_master.entity_map — corp_code 매칭됐을 때만 LEI 등록.
                # PK = (corp_code, id_type, id_value) → 같은 corp 의 기존 LEI 다른 값은
                # DELETE 후 INSERT (1 corp ↔ 1 LEI 정합).
                if cc:
                    cur.execute("SAVEPOINT sp_em")
                    try:
                        cur.execute("""
                            DELETE FROM anxg_master.entity_map
                            WHERE corp_code = %s AND id_type = 'lei' AND id_value <> %s
                        """, (cc, lei))
                        cur.execute("""
                            INSERT INTO anxg_master.entity_map
                              (corp_code, id_type, id_value, source, confidence,
                               resolved_at, resolved_by, notes)
                            VALUES (%s, 'lei', %s, 'gleif_enrich', %s,
                                    now(), 'gleif_kr_enrich', %s)
                            ON CONFLICT (corp_code, id_type, id_value) DO UPDATE SET
                              source      = 'gleif_enrich',
                              confidence  = GREATEST(anxg_master.entity_map.confidence, EXCLUDED.confidence),
                              resolved_at = now(),
                              notes       = EXCLUDED.notes
                            RETURNING (xmax = 0) AS is_new
                        """, (cc, lei, 0.95,
                              f"business_no={biz or '-'}|jurir_no={jur or '-'}|"
                              f"lei={lei}|legal_name={r.get('legal_name')}"))
                        is_new = bool(cur.fetchone()[0])
                        if is_new:
                            stats["em_lei_inserted"] += 1
                        else:
                            stats["em_lei_updated"] += 1
                        cur.execute("RELEASE SAVEPOINT sp_em")
                    except Exception as exc:   # noqa: BLE001
                        cur.execute("ROLLBACK TO SAVEPOINT sp_em")
                        log.warning("[gleif:em] %s/%s fail: %s", cc, lei, exc)

                # 2-3. anxg_bridge.corp_entity 의 LEI 컬럼 보강 — corp_code 매칭됐을 때만.
                # 멤버십 변경 없이 lei + match_method 만 강화.
                if cc:
                    cur.execute("SAVEPOINT sp_bridge")
                    try:
                        cur.execute("""
                            UPDATE anxg_bridge.corp_entity
                            SET lei = %s,
                                match_method = CASE
                                    WHEN match_method IN ('lei','wikidata_qid','sec_cik') THEN match_method
                                    WHEN match_method = 'business_no' THEN 'lei'
                                    WHEN match_method = 'name_exact'  THEN 'lei'
                                    ELSE match_method
                                END,
                                confidence_score = GREATEST(confidence_score, 0.95),
                                reviewed_status = CASE
                                    WHEN match_method IN ('lei','wikidata_qid','sec_cik') THEN reviewed_status
                                    ELSE 'reviewed'
                                END,
                                updated_at = now()
                            WHERE corp_code = %s
                              AND (lei IS NULL OR lei <> %s OR match_method NOT IN ('lei','wikidata_qid','sec_cik'))
                            RETURNING match_method
                        """, (lei, cc, lei))
                        results = cur.fetchall()
                        for (mm,) in results:
                            stats["bridge_lei_updated"] += 1
                            if mm == "lei":
                                stats["bridge_match_upgraded"] += 1
                        cur.execute("RELEASE SAVEPOINT sp_bridge")
                    except Exception as exc:   # noqa: BLE001
                        cur.execute("ROLLBACK TO SAVEPOINT sp_bridge")
                        log.warning("[gleif:bridge] %s/%s fail: %s", cc, lei, exc)

            conn.commit()
            after = _measure_baseline(cur)
            log.info("[gleif] after: %s", after)
    finally:
        conn.close()

    return {
        "n_rows": len(rows),
        "with_business_no": with_biz,
        "corp_lookup_size": len(corp_lookup),
        "baseline": baseline,
        "after":    after,
        "stats":    stats,
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
    ap.add_argument("--max-pages", type=int, default=None,
                    help="페이지 수 제한 (debug). 기본 = 전체 KR LEI")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--raw-dir", type=str, default="data/raw/gleif/kr")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    out = enrich(max_pages=args.max_pages,
                 raw_dir=Path(args.raw_dir),
                 dry_run=args.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["fetch_kr_leis", "enrich", "_normalize_business_no"]
