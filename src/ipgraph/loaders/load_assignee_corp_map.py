"""ip.assignee_corp_map PG → Neo4j ``(Assignee)-[:MAPPED_TO]->(Company)`` merge.

PG SSOT ``ip.assignee_corp_map`` (19_ipgraph_bridge.sql) 는 assignee_id ↔ corp_code
매핑을 hold. 본 loader 는 그 매핑을 Neo4j 의 cross-domain bridge 엣지로 동기화.

PRD §12.5 / docs/ipgraph.md §4 (M-3): ``bridge.corp_entity`` 직접 변경 회피,
ip 도메인 별도 join 테이블 + Neo4j 엣지로 표현.

ontology/ip/relations.yaml 의 ``MAPPED_TO`` 정의 (Assignee → Company, main_hop,
cross-domain bridge, hybrid provenance, conf 0.80) 와 정합.

CLI:
    python -m ipgraph.loaders.load_assignee_corp_map
    python -m ipgraph.loaders.load_assignee_corp_map --dry-run
    python -m ipgraph.loaders.load_assignee_corp_map --min-confidence 0.7
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

log = logging.getLogger(__name__)

_SCHEMA_VERSION_FALLBACK = "v2.2"


def _fetch_rows(min_confidence: float) -> list[dict]:
    """ip.assignee_corp_map PG 조회 — confidence 임계 이상만."""
    import psycopg
    env = {ln.split("=", 1)[0].strip(): ln.split("=", 1)[1].strip()
           for ln in open(ROOT / ".env")
           if "=" in ln and not ln.strip().startswith("#")}
    dsn = os.environ.get("POSTGRES_DSN") or env.get("POSTGRES_DSN")
    if not dsn:
        log.warning("[load_assignee_corp_map] POSTGRES_DSN 미설정")
        return []
    rows: list[dict] = []
    with psycopg.connect(dsn, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT assignee_id, corp_code, match_type, confidence_score,
                       reviewed_status, schema_version
                  FROM ip.assignee_corp_map
                 WHERE confidence_score >= %s
                   AND reviewed_status <> 'rejected'
                 ORDER BY assignee_id, corp_code
            """, (min_confidence,))
            for aid, ccode, mt, conf, rs, sv in cur.fetchall():
                rows.append({
                    "assignee_id":     aid,
                    "corp_code":       ccode,
                    "source_type":     f"ip_assignee_corp_map_{mt}",
                    "source_id":       f"{aid}|{ccode}",
                    "confidence_score": float(conf),
                    "validated_status": "validated" if rs == "reviewed" else "candidate",
                    "snapshot_year":   None,   # bridge 엣지 — 시점 무관
                    "extraction_method": "hybrid",
                    "schema_version":  sv or _SCHEMA_VERSION_FALLBACK,
                })
    return rows


def _merge_neo4j(rows: list[dict]) -> int:
    """Neo4j ``(a:Assignee {assignee_id})-[:MAPPED_TO]->(c:Company {corp_code})`` merge."""
    from autograph.loaders._neo4j_helpers import edge_meta_cypher, run_batched
    from autonexusgraph.db.neo4j import get_driver

    cypher = f"""
    UNWIND $rows AS r
    MATCH (a:Assignee {{assignee_id: r.assignee_id}})
    MATCH (c:Company {{corp_code: r.corp_code}})
    MERGE (a)-[edge:MAPPED_TO]->(c)
    SET {edge_meta_cypher('edge')}
    """
    driver = get_driver()
    with driver.session() as session:
        return run_batched(session, cypher, rows, batch=500)


def main() -> int:
    p = argparse.ArgumentParser(prog="ipgraph.loaders.load_assignee_corp_map",
                                description=__doc__.split("\n")[0])
    p.add_argument("--min-confidence", type=float, default=0.5,
                   help="이 이상의 confidence_score 만 적재 (default 0.5)")
    p.add_argument("--dry-run", action="store_true",
                   help="Neo4j 적재 skip — PG 조회 결과만 print")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(message)s")

    rows = _fetch_rows(args.min_confidence)
    log.info("[load_assignee_corp_map] PG rows = %d (min_conf=%s)",
             len(rows), args.min_confidence)

    if args.dry_run or not rows:
        if rows:
            for r in rows[:3]:
                print(f"  {r['assignee_id']} → {r['corp_code']} "
                      f"(match_type={r['source_type']}, conf={r['confidence_score']})")
        print(f"[load_assignee_corp_map] dry-run — would merge {len(rows)} edges")
        return 0

    n = _merge_neo4j(rows)
    print(f"[load_assignee_corp_map] merged {n} MAPPED_TO edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
