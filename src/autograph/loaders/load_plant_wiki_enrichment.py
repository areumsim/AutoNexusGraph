"""Wikipedia plant 청크 → Neo4j :Plant 노드 속성 보강.

기존: ontology/auto/plants.yaml + load_seed_standards_plants 가 code/name/country/
city/wikidata_qid 만 채움. Wikipedia 본문 (extract + infobox) 에서 추가로:

    description (extract 첫 200 chars), wikipedia_url, wikipedia_title,
    extract_len (본문 길이 — RAG 검색 가치 지표)

anxg_vec.chunks (source='wikipedia_auto', kind='plants') 에서 metadata 추출 후
:Plant.code 매칭하여 MERGE.

2026-06-01 신규.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

log = logging.getLogger(__name__)


_MERGE_CYPHER = """
UNWIND $rows AS r
MATCH (p:Anxg_Plant {code: r.code})
SET p.description    = coalesce(p.description, r.description),
    p.wikipedia_url  = coalesce(p.wikipedia_url, r.wikipedia_url),
    p.wikipedia_title = coalesce(p.wikipedia_title, r.wikipedia_title),
    p.wiki_extract_len = r.extract_len,
    p.wiki_lang      = r.lang
WITH p
RETURN count(p) AS n
"""


def _build_rows() -> list[dict]:
    """anxg_vec.chunks 의 wiki plant 청크 → (code, description, url, title, lang) row.

    한 plant 가 ko + en 양쪽 청크 가지면 ko 우선 (한국어 사용자 친화).
    """
    from autonexusgraph.db.postgres import get_pool

    rows_by_code: dict[str, dict] = {}
    with get_pool().connection() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT metadata->>'lang', metadata->>'title', metadata->>'fullurl',
                   metadata->>'qid', metadata->>'extract_len',
                   text, metadata
              FROM anxg_vec.chunks
             WHERE source='wikipedia_auto' AND metadata->>'kind'='plants'
        """)
        for lang, title, fullurl, qid, ext_len, text, meta in cur.fetchall():
            # plant code 는 metadata->>'uniq' 의 끝부분
            # uniq = 'wikipedia_auto::ko::plants::HYU_ULSAN'
            uniq = (meta or {}).get("uniq", "")
            parts = uniq.split("::")
            code = parts[-1] if len(parts) >= 4 else None
            if not code:
                continue

            # ko 우선 — 이미 ko 가 들어있으면 en 으로 덮어쓰지 않음.
            existing = rows_by_code.get(code)
            if existing and existing["lang"] == "ko" and lang == "en":
                continue

            # description: text 앞부분 (이미 "제목: ..." 포함) 의 첫 200 chars
            desc = (text or "").strip()
            # "제목: X" prefix 제거
            if desc.startswith("제목:"):
                lines = desc.split("\n", 2)
                if len(lines) > 1:
                    desc = "\n".join(lines[1:]).strip()
            desc = desc[:300].rstrip()

            try:
                ext_len_int = int(ext_len) if ext_len else None
            except (TypeError, ValueError):
                ext_len_int = None

            rows_by_code[code] = {
                "code": code,
                "description": desc,
                "wikipedia_url": fullurl or "",
                "wikipedia_title": title or "",
                "lang": lang or "",
                "extract_len": ext_len_int,
            }
    return list(rows_by_code.values())


def run(*, dry_run: bool = False) -> dict:
    rows = _build_rows()
    if not rows:
        log.warning("[plant_wiki] anxg_vec.chunks 에 wikipedia plant 청크 없음 — "
                    "build_chunks_auto --source wikipedia 실행 선행 필요")
        return {"plants_with_wiki": 0, "merged": 0}

    if dry_run:
        return {
            "plants_with_wiki": len(rows),
            "by_lang": {
                lg: sum(1 for r in rows if r["lang"] == lg)
                for lg in {r["lang"] for r in rows}
            },
            "merged": 0,
        }

    from autonexusgraph.db.neo4j import get_session

    merged = 0
    with get_session() as session:
        r = session.run(_MERGE_CYPHER, rows=rows).single()
        merged = r["n"] if r else 0
    log.info("[plant_wiki] wiki chunks=%d, plants merged=%d", len(rows), merged)
    return {"plants_with_wiki": len(rows), "merged": merged}


def main() -> int:
    ap = argparse.ArgumentParser(prog="autograph.loaders.load_plant_wiki_enrichment")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    out = run(dry_run=args.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["run"]
