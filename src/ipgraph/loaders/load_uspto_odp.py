"""USPTO ODP bulk → ip.{patents,assignees,inventors,patent_assignees,patent_inventors,
patent_cpc,citations} PG + Neo4j ``:Patent`` / ``:Assignee`` / ``:Inventor`` +
``:ASSIGNED_TO`` / ``:INVENTED`` / ``:CLASSIFIED_AS`` / ``:CITES`` 적재.

PatentsView (search.patentsview.org) **2026-03-20 종료 (410 Gone)** → data.uspto.gov
ODP bulk dataset 이관. ingestion 단은 ``raw/ip/uspto_odp/*.jsonl`` 무인증 parse,
loader 단은 멱등 upsert + Neo4j MERGE.

PRD §3.5: USPTO ODP = 공공 (US Gov) A 등급 → confidence 0.95.
PRD §6.7: 7-key edge meta 100% (source_type/source_id/confidence_score/
validated_status/snapshot_year/extraction_method/schema_version).

raw 파일 위치 — `data/raw/ip/uspto_odp/`:
    patents.jsonl              필수 — publication_number, application_number, title, ...
    assignees.jsonl            assignee_id, name, country, type, wikidata_qid
    inventors.jsonl            inventor_id, name, country
    patent_assignees.jsonl     pub_no, assignee_id, sequence
    patent_inventors.jsonl     pub_no, inventor_id, sequence
    patent_cpc.jsonl           pub_no, cpc_code, primary_flag
    citations.jsonl            citing_pub_no, cited_pub_no, citation_type

미존재 파일은 graceful skip (0 row + warning). bulk dataset 다운로드 가이드:
https://data.uspto.gov/bulkdata/datasets

CLI:
    python -m ipgraph.loaders.load_uspto_odp
    python -m ipgraph.loaders.load_uspto_odp --skip-neo4j
    python -m ipgraph.loaders.load_uspto_odp --limit 100        # smoke
    python -m ipgraph.loaders.load_uspto_odp --dry-run          # parse 만
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

log = logging.getLogger(__name__)

_SCHEMA_VERSION = "v2.2"
_CONF_A = 0.95
_SNAPSHOT_YEAR = datetime.now(timezone.utc).year
_SOURCE = "uspto_odp"

_EDGE_META = {
    "source_type":       _SOURCE,
    "confidence_score":  _CONF_A,
    "validated_status":  "validated",
    "extraction_method": "deterministic",
    "schema_version":    _SCHEMA_VERSION,
    "snapshot_year":     _SNAPSHOT_YEAR,
}

# Neo4j 인덱스/제약 — 멱등.
_CONSTRAINTS = [
    "CREATE CONSTRAINT patent_pub_no   IF NOT EXISTS FOR (p:Anxg_Patent)   REQUIRE p.pub_no IS UNIQUE",
    "CREATE CONSTRAINT assignee_id     IF NOT EXISTS FOR (a:Anxg_Assignee) REQUIRE a.assignee_id IS UNIQUE",
    "CREATE CONSTRAINT inventor_id     IF NOT EXISTS FOR (i:Anxg_Inventor) REQUIRE i.inventor_id IS UNIQUE",
    "CREATE INDEX patent_jurisdiction IF NOT EXISTS FOR (p:Anxg_Patent) ON (p.jurisdiction)",
    "CREATE INDEX patent_filing_date  IF NOT EXISTS FOR (p:Anxg_Patent) ON (p.filing_date)",
    "CREATE INDEX assignee_country    IF NOT EXISTS FOR (a:Anxg_Assignee) ON (a.country)",
    "CREATE INDEX assignee_qid        IF NOT EXISTS FOR (a:Anxg_Assignee) ON (a.wikidata_qid)",
]


def _load_dotenv() -> None:
    """`.env` 의 POSTGRES_DSN / NEO4J_* 등을 process env 로 흡수 (idempotent)."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
    except ImportError:
        # python-dotenv 없는 환경 — 수동 fallback.
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _dsn_from_env() -> str:
    _load_dotenv()
    if v := os.environ.get("POSTGRES_DSN"):
        return v
    raise RuntimeError("POSTGRES_DSN 미설정")


# ── 1. PG UPSERT ────────────────────────────────────────────

def upsert_pg(*, patents: list[dict], assignees: list[dict], inventors: list[dict],
              patent_assignees: list[dict], patent_inventors: list[dict],
              patent_cpc: list[dict], citations: list[dict]) -> dict[str, dict]:
    """7 테이블 멱등 upsert. PK 충돌 시 selective UPDATE (NULL 보존)."""
    import psycopg2
    conn = psycopg2.connect(_dsn_from_env())
    stats: dict[str, dict] = {}
    try:
        with conn.cursor() as cur:
            stats["patents"]   = _upsert_patents(cur, patents)
            conn.commit()
            stats["assignees"] = _upsert_assignees(cur, assignees)
            conn.commit()
            stats["inventors"] = _upsert_inventors(cur, inventors)
            conn.commit()
            # 다대다 link 는 FK 의존이라 부모 테이블 적재 이후.
            stats["patent_assignees"] = _upsert_link(
                cur, "patent_assignees",
                ("pub_no", "assignee_id"), ("sequence",), patent_assignees,
            )
            stats["patent_inventors"] = _upsert_link(
                cur, "patent_inventors",
                ("pub_no", "inventor_id"), ("sequence",), patent_inventors,
            )
            stats["patent_cpc"] = _upsert_link(
                cur, "patent_cpc",
                ("pub_no", "cpc_code"), ("primary_flag",), patent_cpc,
            )
            conn.commit()
            stats["citations"] = _upsert_citations(cur, citations)
            conn.commit()
    finally:
        conn.close()
    return stats


def _upsert_patents(cur: Any, rows: list[dict]) -> dict[str, int]:
    """RETURNING (xmax = 0) 로 INSERT vs UPDATE 구분 — 실측 inserted/updated 카운트."""
    inserted = updated = skip = 0
    for r in rows:
        if not r.get("pub_no"):
            skip += 1
            continue
        cur.execute("SAVEPOINT sp_pat")
        try:
            cur.execute("""
                INSERT INTO anxg_ip.patents
                  (pub_no, app_no, title, abstract, filing_date, grant_date,
                   kind, jurisdiction, source, snapshot_year, schema_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (pub_no) DO UPDATE SET
                  app_no       = COALESCE(EXCLUDED.app_no, anxg_ip.patents.app_no),
                  title        = COALESCE(EXCLUDED.title, anxg_ip.patents.title),
                  abstract     = COALESCE(EXCLUDED.abstract, anxg_ip.patents.abstract),
                  filing_date  = COALESCE(EXCLUDED.filing_date, anxg_ip.patents.filing_date),
                  grant_date   = COALESCE(EXCLUDED.grant_date, anxg_ip.patents.grant_date),
                  kind         = COALESCE(EXCLUDED.kind, anxg_ip.patents.kind),
                  snapshot_year = EXCLUDED.snapshot_year
                RETURNING (xmax = 0) AS is_new
            """, (r["pub_no"], r.get("app_no"), r.get("title"), r.get("abstract"),
                  r.get("filing_date"), r.get("grant_date"), r.get("kind"),
                  r.get("jurisdiction", "US"), r.get("source", _SOURCE),
                  r.get("snapshot_year", _SNAPSHOT_YEAR),
                  r.get("schema_version", _SCHEMA_VERSION)))
            if bool(cur.fetchone()[0]):
                inserted += 1
            else:
                updated += 1
            cur.execute("RELEASE SAVEPOINT sp_pat")
        except Exception as exc:   # noqa: BLE001 — [uspto:pg:patents] %s fail 흡수 → {"inserted": inserted, "upd... 반환
            cur.execute("ROLLBACK TO SAVEPOINT sp_pat")
            log.warning("[uspto:pg:patents] %s fail: %s", r.get("pub_no"), exc)
            skip += 1
    return {"inserted": inserted, "updated": updated, "skipped": skip}


def _upsert_assignees(cur: Any, rows: list[dict]) -> dict[str, int]:
    """RETURNING (xmax = 0) 로 INSERT vs UPDATE 구분 — patents 와 동일 shape."""
    inserted = updated = skip = 0
    for r in rows:
        if not r.get("assignee_id"):
            skip += 1
            continue
        cur.execute("SAVEPOINT sp_asn")
        try:
            cur.execute("""
                INSERT INTO anxg_ip.assignees
                  (assignee_id, name, name_norm, country, type, wikidata_qid,
                   snapshot_year, schema_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (assignee_id) DO UPDATE SET
                  name         = COALESCE(EXCLUDED.name, anxg_ip.assignees.name),
                  name_norm    = COALESCE(EXCLUDED.name_norm, anxg_ip.assignees.name_norm),
                  country      = COALESCE(EXCLUDED.country, anxg_ip.assignees.country),
                  type         = COALESCE(EXCLUDED.type, anxg_ip.assignees.type),
                  wikidata_qid = COALESCE(EXCLUDED.wikidata_qid, anxg_ip.assignees.wikidata_qid),
                  snapshot_year = EXCLUDED.snapshot_year
                RETURNING (xmax = 0) AS is_new
            """, (r["assignee_id"], r.get("name"), r.get("name_norm"),
                  r.get("country"), r.get("type", "company"), r.get("wikidata_qid"),
                  r.get("snapshot_year", _SNAPSHOT_YEAR),
                  r.get("schema_version", _SCHEMA_VERSION)))
            if bool(cur.fetchone()[0]):
                inserted += 1
            else:
                updated += 1
            cur.execute("RELEASE SAVEPOINT sp_asn")
        except Exception as exc:   # noqa: BLE001 — [uspto:pg:assignees] %s fail 흡수 → {"inserted": inserted, "upd... 반환
            cur.execute("ROLLBACK TO SAVEPOINT sp_asn")
            log.warning("[uspto:pg:assignees] %s fail: %s", r.get("assignee_id"), exc)
            skip += 1
    return {"inserted": inserted, "updated": updated, "skipped": skip}


def _upsert_inventors(cur: Any, rows: list[dict]) -> dict[str, int]:
    """RETURNING (xmax = 0) 로 INSERT vs UPDATE 구분 — patents 와 동일 shape."""
    inserted = updated = skip = 0
    for r in rows:
        if not r.get("inventor_id"):
            skip += 1
            continue
        cur.execute("SAVEPOINT sp_inv")
        try:
            cur.execute("""
                INSERT INTO anxg_ip.inventors
                  (inventor_id, name, name_norm, country, schema_version)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (inventor_id) DO UPDATE SET
                  name      = COALESCE(EXCLUDED.name, anxg_ip.inventors.name),
                  name_norm = COALESCE(EXCLUDED.name_norm, anxg_ip.inventors.name_norm),
                  country   = COALESCE(EXCLUDED.country, anxg_ip.inventors.country)
                RETURNING (xmax = 0) AS is_new
            """, (r["inventor_id"], r.get("name"), r.get("name_norm"),
                  r.get("country"), r.get("schema_version", _SCHEMA_VERSION)))
            if bool(cur.fetchone()[0]):
                inserted += 1
            else:
                updated += 1
            cur.execute("RELEASE SAVEPOINT sp_inv")
        except Exception as exc:   # noqa: BLE001 — [uspto:pg:inventors] %s fail 흡수 → {"inserted": inserted, "upd... 반환
            cur.execute("ROLLBACK TO SAVEPOINT sp_inv")
            log.warning("[uspto:pg:inventors] %s fail: %s", r.get("inventor_id"), exc)
            skip += 1
    return {"inserted": inserted, "updated": updated, "skipped": skip}


def _upsert_link(cur: Any, table: str, pk: tuple[str, ...],
                  extra: tuple[str, ...], rows: list[dict]) -> dict[str, int]:
    """patent_{assignees,inventors,cpc} 등 link 테이블 멱등 upsert. PK 일치 시 NO-OP."""
    skip = 0
    for r in rows:
        if any(not r.get(k) for k in pk):
            skip += 1
            continue
        cur.execute("SAVEPOINT sp_link")
        try:
            cols = (*pk, *extra)
            placeholders = ",".join(["%s"] * len(cols))
            cur.execute(
                f"INSERT INTO anxg_ip.{table} ({','.join(cols)}) "
                f"VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                tuple(r.get(c) for c in cols),
            )
            cur.execute("RELEASE SAVEPOINT sp_link")
        except Exception as exc:   # noqa: BLE001 — [uspto:pg:%s] %s fail 흡수 → {"inserted_or_updated": len... 반환
            cur.execute("ROLLBACK TO SAVEPOINT sp_link")
            log.warning("[uspto:pg:%s] %s fail: %s", table, {k: r.get(k) for k in pk}, exc)
            skip += 1
    return {"inserted_or_updated": len(rows) - skip, "skipped": skip}


def _upsert_citations(cur: Any, rows: list[dict]) -> dict[str, int]:
    """RETURNING (xmax = 0) 로 INSERT vs UPDATE 구분 — patents 와 동일 shape."""
    inserted = updated = skip = 0
    for r in rows:
        if not (r.get("citing_pub_no") and r.get("cited_pub_no")):
            skip += 1
            continue
        cur.execute("SAVEPOINT sp_cit")
        try:
            cur.execute("""
                INSERT INTO anxg_ip.citations
                  (citing_pub_no, cited_pub_no, citation_type, snapshot_year, schema_version)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (citing_pub_no, cited_pub_no) DO UPDATE SET
                  citation_type = COALESCE(EXCLUDED.citation_type, anxg_ip.citations.citation_type),
                  snapshot_year = EXCLUDED.snapshot_year
                RETURNING (xmax = 0) AS is_new
            """, (r["citing_pub_no"], r["cited_pub_no"], r.get("citation_type"),
                  r.get("snapshot_year", _SNAPSHOT_YEAR),
                  r.get("schema_version", _SCHEMA_VERSION)))
            if bool(cur.fetchone()[0]):
                inserted += 1
            else:
                updated += 1
            cur.execute("RELEASE SAVEPOINT sp_cit")
        except Exception as exc:   # noqa: BLE001 — [uspto:pg:citations] %s→%s fail 흡수 → {"inserted": inserted, "upd... 반환
            cur.execute("ROLLBACK TO SAVEPOINT sp_cit")
            log.warning("[uspto:pg:citations] %s→%s fail: %s",
                        r.get("citing_pub_no"), r.get("cited_pub_no"), exc)
            skip += 1
    return {"inserted": inserted, "updated": updated, "skipped": skip}


# ── 2. Neo4j MERGE ──────────────────────────────────────────

def load_neo4j(*, patents: list[dict], assignees: list[dict], inventors: list[dict],
               patent_assignees: list[dict], patent_inventors: list[dict],
               patent_cpc: list[dict], citations: list[dict],
               edge_meta: dict | None = None) -> dict[str, int]:
    """:Patent/:Assignee/:Inventor + 4 엣지 타입 멱등 적재. 7-key edge meta 100%.

    ``edge_meta`` 미지정 시 USPTO ODP 기본 ({source_type=uspto_odp, conf=0.95}).
    KIPRIS 등 다른 source 는 호출자가 override — source_type/source_id_prefix 만 다름.
    """
    edge_meta = edge_meta or _EDGE_META
    # source_prefix — cypher 의 $source_prefix 파라미터로 source_id 접두사 주입.
    # edge_meta 에 명시되면 우선, 아니면 source_type 재사용.
    edge_meta = {**edge_meta,
                  "source_prefix": edge_meta.get("source_prefix") or edge_meta["source_type"]}
    logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)
    _load_dotenv()
    from neo4j import GraphDatabase
    drv = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"]),
    )
    stats = {
        "patents_merged":       0,
        "assignees_merged":     0,
        "inventors_merged":     0,
        "assigned_to_merged":   0,
        "invented_merged":      0,
        "classified_as_merged": 0,
        "cites_merged":         0,
    }
    batch = 1000
    try:
        with drv.session(database=os.environ.get("NEO4J_DATABASE") or None) as s:
            for q in _CONSTRAINTS:
                s.run(q)

            # 노드 — Patent.
            for i in range(0, len(patents), batch):
                chunk = patents[i:i + batch]
                s.run("""
                    UNWIND $rows AS r
                    MERGE (p:Anxg_Patent {pub_no: r.pub_no})
                    SET p.app_no       = r.app_no,
                        p.title        = r.title,
                        p.abstract     = r.abstract,
                        p.filing_date  = r.filing_date,
                        p.grant_date   = r.grant_date,
                        p.kind         = r.kind,
                        p.jurisdiction = r.jurisdiction,
                        p.source       = r.source,
                        p.updated_at   = datetime()
                """, rows=chunk)
                stats["patents_merged"] += len(chunk)

            # 노드 — Assignee.
            for i in range(0, len(assignees), batch):
                chunk = assignees[i:i + batch]
                s.run("""
                    UNWIND $rows AS r
                    MERGE (a:Anxg_Assignee {assignee_id: r.assignee_id})
                    SET a.name         = r.name,
                        a.name_norm    = r.name_norm,
                        a.country      = r.country,
                        a.type         = r.type,
                        a.wikidata_qid = r.wikidata_qid,
                        a.updated_at   = datetime()
                """, rows=chunk)
                stats["assignees_merged"] += len(chunk)

            # 노드 — Inventor.
            for i in range(0, len(inventors), batch):
                chunk = inventors[i:i + batch]
                s.run("""
                    UNWIND $rows AS r
                    MERGE (i:Anxg_Inventor {inventor_id: r.inventor_id})
                    SET i.name       = r.name,
                        i.name_norm  = r.name_norm,
                        i.country    = r.country,
                        i.updated_at = datetime()
                """, rows=chunk)
                stats["inventors_merged"] += len(chunk)

            # 엣지 — ASSIGNED_TO (Patent → Assignee).
            for i in range(0, len(patent_assignees), batch):
                chunk = patent_assignees[i:i + batch]
                s.run("""
                    UNWIND $rows AS r
                    MATCH (p:Anxg_Patent {pub_no: r.pub_no})
                    WITH p, r
                    MATCH (a:Anxg_Assignee {assignee_id: r.assignee_id})
                    MERGE (p)-[e:ASSIGNED_TO]->(a)
                    SET e.sequence         = r.sequence,
                        e.source_type      = $source_type,
                        e.source_id        = $source_prefix + ':' + r.pub_no + '->' + r.assignee_id,
                        e.confidence_score = $confidence_score,
                        e.validated_status = $validated_status,
                        e.snapshot_year    = $snapshot_year,
                        e.extraction_method = $extraction_method,
                        e.schema_version   = $schema_version,
                        e.updated_at       = datetime()
                """, rows=chunk, **edge_meta)
                stats["assigned_to_merged"] += len(chunk)

            # 엣지 — INVENTED (Inventor → Patent).
            for i in range(0, len(patent_inventors), batch):
                chunk = patent_inventors[i:i + batch]
                s.run("""
                    UNWIND $rows AS r
                    MATCH (p:Anxg_Patent {pub_no: r.pub_no})
                    WITH p, r
                    MATCH (i:Anxg_Inventor {inventor_id: r.inventor_id})
                    MERGE (i)-[e:INVENTED]->(p)
                    SET e.sequence         = r.sequence,
                        e.source_type      = $source_type,
                        e.source_id        = $source_prefix + ':' + r.inventor_id + '->' + r.pub_no,
                        e.confidence_score = $confidence_score,
                        e.validated_status = $validated_status,
                        e.snapshot_year    = $snapshot_year,
                        e.extraction_method = $extraction_method,
                        e.schema_version   = $schema_version,
                        e.updated_at       = datetime()
                """, rows=chunk, **edge_meta)
                stats["invented_merged"] += len(chunk)

            # 엣지 — CLASSIFIED_AS (Patent → CPCCode). 본 loader 는 CPCCode 노드
            # 적재 안 함 (load_cpc.py SoT). 매칭 안 되면 skip.
            for i in range(0, len(patent_cpc), batch):
                chunk = patent_cpc[i:i + batch]
                s.run("""
                    UNWIND $rows AS r
                    MATCH (p:Anxg_Patent {pub_no: r.pub_no})
                    WITH p, r
                    MATCH (c:Anxg_CPCCode {code: r.cpc_code})
                    MERGE (p)-[e:CLASSIFIED_AS]->(c)
                    SET e.primary_flag     = r.primary_flag,
                        e.source_type      = $source_type,
                        e.source_id        = $source_prefix + ':' + r.pub_no + '->' + r.cpc_code,
                        e.confidence_score = $confidence_score,
                        e.validated_status = $validated_status,
                        e.snapshot_year    = $snapshot_year,
                        e.extraction_method = $extraction_method,
                        e.schema_version   = $schema_version,
                        e.updated_at       = datetime()
                """, rows=chunk, **edge_meta)
                stats["classified_as_merged"] += len(chunk)

            # 엣지 — CITES (Patent → Patent). cited 가 우리 graph 에 없으면 skip.
            for i in range(0, len(citations), batch):
                chunk = citations[i:i + batch]
                s.run("""
                    UNWIND $rows AS r
                    MATCH (citing:Anxg_Patent {pub_no: r.citing_pub_no})
                    WITH citing, r
                    MATCH (cited:Anxg_Patent  {pub_no: r.cited_pub_no})
                    MERGE (citing)-[e:CITES]->(cited)
                    SET e.citation_type    = r.citation_type,
                        e.source_type      = $source_type,
                        e.source_id        = $source_prefix + ':' + r.citing_pub_no + '->' + r.cited_pub_no,
                        e.confidence_score = $confidence_score,
                        e.validated_status = $validated_status,
                        e.snapshot_year    = $snapshot_year,
                        e.extraction_method = $extraction_method,
                        e.schema_version   = $schema_version,
                        e.updated_at       = datetime()
                """, rows=chunk, **edge_meta)
                stats["cites_merged"] += len(chunk)
    finally:
        drv.close()
    return stats


# ── 3. CLI ──────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ipgraph.loaders.load_uspto_odp",
                                  description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="parse 만 — PG/Neo4j 적재 안 함")
    ap.add_argument("--skip-pg", action="store_true")
    ap.add_argument("--skip-neo4j", action="store_true")
    ap.add_argument("--limit", type=int, default=None,
                    help="각 파일별 첫 N row (smoke test)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    from ipgraph.ingestion import uspto_odp as ing

    patents = ing.collect_patents(limit=args.limit)
    assignees = ing.collect_assignees(limit=args.limit)
    inventors = ing.collect_inventors(limit=args.limit)
    patent_assignees = ing.collect_patent_assignees(limit=args.limit)
    patent_inventors = ing.collect_patent_inventors(limit=args.limit)
    patent_cpc = ing.collect_patent_cpc(limit=args.limit)
    citations = ing.collect_citations(limit=args.limit)

    counts = {
        "patents":          len(patents),
        "assignees":        len(assignees),
        "inventors":        len(inventors),
        "patent_assignees": len(patent_assignees),
        "patent_inventors": len(patent_inventors),
        "patent_cpc":       len(patent_cpc),
        "citations":        len(citations),
    }
    log.info("[uspto] parsed: %s", counts)

    if not any(counts.values()):
        log.warning("[uspto] no raw data — bulk dataset 다운로드 필요 "
                     "(https://data.uspto.gov/bulkdata/datasets → data/raw/ip/uspto_odp/*.jsonl)")
        print(json.dumps({"parsed": counts, "status": "no_data"},
                         ensure_ascii=False, indent=2))
        return 0

    out: dict[str, Any] = {"parsed": counts}
    if args.dry_run:
        out["status"] = "dry_run"
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0

    if not args.skip_pg:
        out["pg"] = upsert_pg(
            patents=patents, assignees=assignees, inventors=inventors,
            patent_assignees=patent_assignees, patent_inventors=patent_inventors,
            patent_cpc=patent_cpc, citations=citations,
        )
        log.info("[uspto:pg] %s", out["pg"])

    if not args.skip_neo4j:
        out["neo4j"] = load_neo4j(
            patents=patents, assignees=assignees, inventors=inventors,
            patent_assignees=patent_assignees, patent_inventors=patent_inventors,
            patent_cpc=patent_cpc, citations=citations,
        )
        log.info("[uspto:neo4j] %s", out["neo4j"])

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["upsert_pg", "load_neo4j"]
