#!/usr/bin/env python3
"""B7 우회 routine — Wikidata P176(manufactured by) **배치** SPARQL → part_supplies.jsonl.

기존 per-entity 쿼리는 Wikidata SPARQL rate-limit(1 req/min, 429)에 걸려 staging_relations
P176 행이 0이었다(B7). 본 routine 은 **우리 supplier QID 집합을 VALUES 로 묶어 단일 배치
쿼리** 1회만 보내, rate-limit 을 사실상 회피한다.

산출: data/raw/auto/wikidata/part_supplies.jsonl (loader 가 기대하는 스키마):
    {"part_qid","partLabel","supplier_qid","supplierLabel"}
후속: python -m autograph.loaders.load_wikidata_part_supplies  → anxg_auto.staging_relations.

사용:
    python scripts/ingest/ingest_wikidata_part_supplies.py [--limit 3000] [--max-suppliers 60]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from autonexusgraph.db.postgres import get_connection  # noqa: E402

ENDPOINT = "https://query.wikidata.org/sparql"
UA = "AutoNexusGraph/1.0 (research; contact: ops@autonexusgraph) python-urllib"


def _supplier_qids(max_suppliers: int) -> list[str]:
    """master_suppliers 의 wikidata_qid — 주요(자주 등장) supplier 우선."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT s.wikidata_qid
              FROM anxg_auto.master_suppliers s
             WHERE s.wikidata_qid ~ '^Q[0-9]+$'
             ORDER BY (SELECT count(*) FROM anxg_auto.staging_relations r
                        WHERE r.tail_text_norm = s.name_norm) DESC NULLS LAST,
                      length(s.name)
             LIMIT %s
        """, (max_suppliers,))
        return [r[0] for r in cur.fetchall()]


def _sparql(query: str, *, retries: int = 3) -> dict:
    url = ENDPOINT + "?" + urllib.parse.urlencode({"format": "json", "query": query})
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            wait = int(e.headers.get("Retry-After", "60")) if e.code == 429 else 5
            print(f"  HTTP {e.code} — {wait}s 대기 후 재시도 ({attempt+1}/{retries})")
            time.sleep(wait)
    raise RuntimeError("SPARQL 재시도 초과")


def ingest(*, limit: int = 3000, max_suppliers: int = 60) -> int:
    qids = _supplier_qids(max_suppliers)
    if not qids:
        print("supplier QID 없음")
        return 0
    values = " ".join(f"wd:{q}" for q in qids)
    query = f"""
    SELECT ?part ?partLabel ?supplier ?supplierLabel WHERE {{
      VALUES ?supplier {{ {values} }}
      ?part wdt:P176 ?supplier .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,ko,de,ja". }}
    }} LIMIT {limit}
    """
    print(f"배치 SPARQL — supplier {len(qids)}개 VALUES, limit {limit} … (1 request)")
    data = _sparql(query)
    out_dir = ROOT / "data" / "raw" / "auto" / "wikidata"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "part_supplies.jsonl"
    n = 0
    with out.open("w", encoding="utf-8") as f:
        for b in data.get("results", {}).get("bindings", []):
            part_qid = b["part"]["value"].rsplit("/", 1)[-1]
            sup_qid = b["supplier"]["value"].rsplit("/", 1)[-1]
            rec = {
                "part_qid": part_qid,
                "partLabel": b.get("partLabel", {}).get("value", ""),
                "supplier_qid": sup_qid,
                "supplierLabel": b.get("supplierLabel", {}).get("value", ""),
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"wrote {n} P176 rows → {out}")
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=3000)
    ap.add_argument("--max-suppliers", type=int, default=60)
    a = ap.parse_args()
    ingest(limit=a.limit, max_suppliers=a.max_suppliers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
