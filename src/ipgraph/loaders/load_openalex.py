"""anxg_ip.works / anxg_ip.institution → Neo4j ``:Work`` / ``:Institution`` + ``:AUTHORED_AT``
+ (Institution↔corp_entity) ``IS_ENTITY`` 엣지 적재.

추가로 anxg_ip.works.abstract → anxg_vec.chunks(source='openalex', embedding NULL) 멱등 적재
(BGE-M3 backfill 은 별도 cron 으로 NULL→채움).

PRD §3.5: OpenAlex = A 등급 → confidence 0.95.
PRD §6.7: 7-key edge meta 100%.

CLI:
    python -m ipgraph.loaders.load_openalex --skip-chunks
    python -m ipgraph.loaders.load_openalex            # works → anxg_vec.chunks 도 적재
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SCHEMA_VERSION = "v2.2"
_CONF_A = 0.95

_EDGE_META = {
    "source_type":       "openalex",
    "confidence_score":  _CONF_A,
    "validated_status":  "validated",
    "extraction_method": "deterministic",
    "schema_version":    _SCHEMA_VERSION,
}

_CONSTRAINTS = [
    "CREATE CONSTRAINT work_openalex_id IF NOT EXISTS FOR (w:Anxg_Work) REQUIRE w.openalex_id IS UNIQUE",
    "CREATE CONSTRAINT institution_ror  IF NOT EXISTS FOR (i:Anxg_Institution) REQUIRE i.ror_id IS UNIQUE",
    "CREATE INDEX inst_corp_code IF NOT EXISTS FOR (i:Anxg_Institution) ON (i.corp_code)",
    "CREATE INDEX inst_type      IF NOT EXISTS FOR (i:Anxg_Institution) ON (i.type)",
    "CREATE INDEX work_year      IF NOT EXISTS FOR (w:Anxg_Work) ON (w.publication_year)",
]


def _dsn_from_env() -> str:
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("POSTGRES_DSN="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("POSTGRES_DSN 미설정")


# ── 1. Neo4j 적재 ──────────────────────────────────────────────

def load_neo4j() -> dict:
    """anxg_ip.institution / anxg_ip.works / anxg_ip.work_institution → Neo4j MERGE."""
    logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)
    from neo4j import GraphDatabase
    import psycopg2

    pg = psycopg2.connect(os.environ.get("POSTGRES_DSN") or _dsn_from_env())
    drv = GraphDatabase.driver(os.environ["NEO4J_URI"],
                                auth=(os.environ.get("NEO4J_USER", "neo4j"),
                                      os.environ["NEO4J_PASSWORD"]))
    stats = {
        "institutions_merged": 0,
        "works_merged":        0,
        "authored_at_merged":  0,
        "is_entity_merged":    0,
    }
    try:
        with pg.cursor() as cur, drv.session(database=os.environ.get("NEO4J_DATABASE") or None) as s:
            for q in _CONSTRAINTS:
                s.run(q)

            # 1-1. Institution + IS_ENTITY (institution → :Company corp_entity).
            cur.execute("""
                SELECT i.ror_id, i.openalex_id, i.name, i.country, i.type, i.corp_code
                FROM anxg_ip.institution i
            """)
            for ror, oa, name, country, itype, cc in cur.fetchall():
                s.run("""
                    MERGE (i:Anxg_Institution {ror_id: $ror})
                    SET i.openalex_id = $oa,
                        i.name = $name,
                        i.country = $country,
                        i.type = $type,
                        i.corp_code = $cc,
                        i.updated_at = datetime()
                """, ror=ror, oa=oa, name=name, country=country, type=itype, cc=cc)
                stats["institutions_merged"] += 1
                # IS_ENTITY edge to existing Company (corp_code 매칭).
                if cc:
                    r = s.run("""
                        MATCH (c:Anxg_Company {corp_code: $cc})
                        WITH c
                        MATCH (i:Anxg_Institution {ror_id: $ror})
                        MERGE (i)-[r:IS_ENTITY]->(c)
                        SET r.source_type       = $source_type,
                            r.source_id         = $source_id,
                            r.confidence_score  = $confidence_score,
                            r.validated_status  = $validated_status,
                            r.snapshot_year     = $snapshot_year,
                            r.extraction_method = $extraction_method,
                            r.schema_version    = $schema_version,
                            r.updated_at        = datetime()
                        RETURN count(r) AS n
                    """, ror=ror, cc=cc,
                         source_id=f"openalex:{oa}|corp_code:{cc}",
                         snapshot_year=2024,
                         **_EDGE_META).single()
                    stats["is_entity_merged"] += (r or {}).get("n", 0)

            # 1-2. Works.
            cur.execute("""
                SELECT openalex_id, title, publication_year, cited_by_count, doi, type
                FROM anxg_ip.works
            """)
            for oa, title, year, cited, doi, wtype in cur.fetchall():
                s.run("""
                    MERGE (w:Anxg_Work {openalex_id: $oa})
                    SET w.title = $title,
                        w.publication_year = $year,
                        w.cited_by_count = $cited,
                        w.doi = $doi,
                        w.type = $type,
                        w.updated_at = datetime()
                """, oa=oa, title=title, year=year, cited=cited, doi=doi, type=wtype)
                stats["works_merged"] += 1

            # 1-3. AUTHORED_AT.
            cur.execute("""
                SELECT wi.openalex_id, wi.ror_id, wi.author_position, wi.snapshot_year
                FROM anxg_ip.work_institution wi
            """)
            for oa, ror, pos, sy in cur.fetchall():
                r = s.run("""
                    MATCH (w:Anxg_Work {openalex_id: $oa})
                    WITH w
                    MATCH (i:Anxg_Institution {ror_id: $ror})
                    MERGE (w)-[r:AUTHORED_AT]->(i)
                    SET r.author_position   = $pos,
                        r.source_type       = $source_type,
                        r.source_id         = $source_id,
                        r.confidence_score  = $confidence_score,
                        r.validated_status  = $validated_status,
                        r.snapshot_year     = $snapshot_year,
                        r.extraction_method = $extraction_method,
                        r.schema_version    = $schema_version,
                        r.updated_at        = datetime()
                    RETURN count(r) AS n
                """, oa=oa, ror=ror, pos=pos,
                     source_id=f"openalex:{oa}->{ror}",
                     snapshot_year=sy or 2024,
                     **_EDGE_META).single()
                stats["authored_at_merged"] += (r or {}).get("n", 0)
    finally:
        pg.close()
        drv.close()
    return stats


# ── 2. abstract → anxg_vec.chunks ────────────────────────────────

def load_chunks() -> dict:
    """anxg_ip.works.abstract → anxg_vec.chunks(source='openalex', embedding NULL).

    중복 방지: metadata->>'openalex_id' 로 unique 보장.
    """
    import psycopg2
    pg = psycopg2.connect(os.environ.get("POSTGRES_DSN") or _dsn_from_env())
    pg.autocommit = False
    ins = upd = skip = 0
    try:
        with pg.cursor() as cur:
            cur.execute("""
                SELECT w.openalex_id, w.title, w.abstract, w.publication_year, w.doi,
                       wi.ror_id, i.corp_code
                FROM anxg_ip.works w
                JOIN anxg_ip.work_institution wi USING (openalex_id)
                LEFT JOIN anxg_ip.institution i USING (ror_id)
                WHERE w.abstract IS NOT NULL AND length(w.abstract) > 30
            """)
            seen: set[str] = set()
            for oa, title, abst, year, doi, ror, cc in cur.fetchall():
                # 1 work 가 여러 institution 에 연결될 수 있음 — chunk 는 work 단위 1개로.
                if oa in seen:
                    continue
                seen.add(oa)
                text = (f"{title}\n\n{abst}" if title else abst) or ""
                tok = len(text.split())   # 단순 토큰 추정 (BGE-M3 backfill 시 재계산).
                meta = {
                    "openalex_id":     oa,
                    "doi":             doi,
                    "publication_year": year,
                    "ror_ids":         [ror] if ror else [],
                }
                cur.execute("SAVEPOINT sp_chunk")
                try:
                    # rcept_no 는 anxg_fin.filings FK 라 openalex_id 직접 사용 불가 → NULL.
                    # metadata.openalex_id 로 식별.
                    cur.execute("""
                        INSERT INTO anxg_vec.chunks
                          (corp_code, rcept_no, section, chunk_idx, text, token_count,
                           embedding, metadata, source, fiscal_year)
                        VALUES (%s, NULL, %s, 0, %s, %s,
                                NULL, %s::jsonb, 'openalex', %s)
                        ON CONFLICT DO NOTHING
                        RETURNING id
                    """, (cc, f"openalex_abstract:{oa}"[:64], text[:50000], tok,
                          json.dumps(meta, ensure_ascii=False), year))
                    rid = cur.fetchone()
                    if rid:
                        ins += 1
                    else:
                        skip += 1
                    cur.execute("RELEASE SAVEPOINT sp_chunk")
                except Exception as exc:   # noqa: BLE001 — 예외 흡수 → log + 다음 단계 (silent 아님)
                    cur.execute("ROLLBACK TO SAVEPOINT sp_chunk")
                    log.warning("[load:openalex_chunks] %s fail: %s", oa, exc)
                    skip += 1
            pg.commit()
    finally:
        pg.close()
    return {"inserted": ins, "skipped": skip, "updated": upd}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-chunks", action="store_true",
                    help="abstract→anxg_vec.chunks 적재 생략")
    ap.add_argument("--only-chunks", action="store_true",
                    help="anxg_vec.chunks 만 적재 (Neo4j skip)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    out: dict[str, Any] = {}
    if not args.only_chunks:
        out["neo4j"] = load_neo4j()
        log.info("[load:openalex:neo4j] %s", out["neo4j"])
    if not args.skip_chunks:
        out["vec_chunks"] = load_chunks()
        log.info("[load:openalex:vec_chunks] %s", out["vec_chunks"])
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["load_neo4j", "load_chunks"]
