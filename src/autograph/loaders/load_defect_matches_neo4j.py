"""PG (anxg_auto.defect_types, anxg_auto.defect_matches, anxg_auto.events_recalls) → Neo4j 미러링.

Bridge: (:Anxg_Recall)-[:DEFECT_MATCHES {cos_sim, conf, match_method}]->(:Anxg_DefectType)

본 모듈이 한 번에 처리하는 것:
  1. :Recall 보충 — anxg_auto.events_recalls 의 KOTSA 941건 + NHTSA 누락분이 Neo4j 에
     없으면 MERGE (id 키 기준).  기존 load_auto_neo4j.py 의 Recall MERGE 와 호환.
  2. :DefectType 노드 (50건) — anxg_auto.defect_types → MERGE (name 키).
  3. DEFECT_MATCHES 엣지 — anxg_auto.defect_matches → MERGE (recall_id, defect_type_id,
     match_method 복합 키).
  4. 모든 신규/기존 노드에 `domain` 속성 (ontology.domain SSOT).

CLI:
    python -m autograph.loaders.load_defect_matches_neo4j
    python -m autograph.loaders.load_defect_matches_neo4j --dry-run
    python -m autograph.loaders.load_defect_matches_neo4j --skip-recall-backfill
"""

from __future__ import annotations

import argparse
import logging

from autonexusgraph.db.neo4j import get_session
from autonexusgraph.db.postgres import get_connection
from autonexusgraph.ontology.domain import domain_for

from ._neo4j_helpers import run_batched

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Cypher
# ──────────────────────────────────────────────────────────────────────

# :Recall MERGE — 기존 load_auto_neo4j.MERGE_RECALL 호환 + domain 속성 추가.
MERGE_RECALL = """
UNWIND $rows AS r
MERGE (rc:Anxg_Recall {id: r.id})
SET   rc.source = r.source,
      rc.source_recall_no = r.source_recall_no,
      rc.report_date = r.report_date,
      rc.country = r.country,
      rc.component_text = r.component_text,
      rc.summary = r.defect_summary,
      rc.consequence = r.consequence,
      rc.remedy = r.remedy_summary,
      rc.affected_units = r.affected_units,
      rc.snapshot_year = r.snapshot_year,
      rc.domain = r.domain,
      rc.updated_at = datetime()
"""

# (VehicleModel)-[:AFFECTED_BY]->(Recall) — variant 매핑 실패 fallback (KOTSA는 variant 매핑 거의 없음)
MERGE_RECALL_EDGE_MODEL = """
UNWIND $rows AS r
MATCH (rc:Anxg_Recall {id: r.id})
WITH rc, r WHERE r.model_id IS NOT NULL
OPTIONAL MATCH (m:Anxg_VehicleModel {id: r.model_id})
WITH rc, r, m WHERE m IS NOT NULL
MERGE (m)-[rel:AFFECTED_BY]->(rc)
SET   rel.source_id = r.source_recall_no,
      rel.source_type = 'pg.anxg_auto.events_recalls',
      rel.extraction_method = 'deterministic',
      rel.confidence_score = r.confidence,
      rel.validated_status = r.validated_status,
      rel.snapshot_year = coalesce(r.snapshot_year, date().year),
      rel.schema_version = coalesce(r.schema_version, 'v2.1')
"""

# :DefectType MERGE (name 키, domain='auto')
MERGE_DEFECT_TYPE = """
UNWIND $rows AS r
MERGE (d:Anxg_DefectType {name: r.name})
SET   d.name_en          = r.name_en,
      d.name_ko          = r.name_ko,
      d.description      = r.description,
      d.category         = r.category,
      d.source           = r.source,
      d.source_type      = r.source_type,
      d.confidence_score = r.confidence_score,
      d.validated_status = r.validated_status,
      d.snapshot_year    = r.snapshot_year,
      d.extraction_method= r.extraction_method,
      d.schema_version   = r.schema_version,
      d.domain           = r.domain,
      d.updated_at       = datetime()
"""

# DEFECT_MATCHES 엣지 — (recall_id, defect_name, match_method) 복합 키
MERGE_DEFECT_MATCH = """
UNWIND $rows AS r
MATCH (rc:Anxg_Recall {id: r.recall_id})
MATCH (d:Anxg_DefectType {name: r.defect_name})
MERGE (rc)-[rel:DEFECT_MATCHES {match_method: r.match_method}]->(d)
SET   rel.cos_sim          = r.cos_sim,
      rel.rank             = r.rank,
      rel.source_id        = r.source_id,
      rel.source_type      = r.source_type,
      rel.extraction_method= r.extraction_method,
      rel.confidence_score = r.confidence_score,
      rel.validated_status = r.validated_status,
      rel.snapshot_year    = coalesce(r.snapshot_year, date().year),
      rel.schema_version   = coalesce(r.schema_version, 'defect_matches_v1')
"""


# ──────────────────────────────────────────────────────────────────────
# PG → row 변환
# ──────────────────────────────────────────────────────────────────────

def _fetch_recalls() -> list[dict]:
    """anxg_auto.events_recalls 전체 → row dict (domain='auto')."""
    domain_val = domain_for("Recall") or ["auto"]
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT recall_id, source, source_recall_no, manufacturer_id, model_id,
                   variant_id, component_text, defect_summary, consequence,
                   remedy_summary, report_date, country, affected_units,
                   confidence, validated_status, snapshot_year
              FROM anxg_auto.events_recalls
        """)
        out = []
        for r in cur.fetchall():
            out.append({
                "id":               r[0],
                "source":           r[1],
                "source_recall_no": r[2],
                "manufacturer_id":  r[3],
                "model_id":         r[4],
                "variant_id":       r[5],
                "component_text":   r[6],
                "defect_summary":   r[7],
                "consequence":      r[8],
                "remedy_summary":   r[9],
                "report_date":      r[10].isoformat() if r[10] else None,
                "country":          r[11],
                "affected_units":   r[12],
                "confidence":       float(r[13]) if r[13] is not None else 1.0,
                "validated_status": r[14],
                "snapshot_year":    r[15],
                "domain":           domain_val,
            })
    return out


def _fetch_defect_types() -> list[dict]:
    domain_val = domain_for("DefectType") or ["auto"]
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT defect_type_id, name, name_en, name_ko, description, category,
                   source, source_type, confidence_score, validated_status,
                   snapshot_year, extraction_method, schema_version
              FROM anxg_auto.defect_types
        """)
        out = []
        for r in cur.fetchall():
            out.append({
                "defect_type_id":    r[0],
                "name":              r[1],
                "name_en":           r[2],
                "name_ko":           r[3],
                "description":       r[4],
                "category":          r[5],
                "source":            r[6],
                "source_type":       r[7],
                "confidence_score":  float(r[8]) if r[8] is not None else 0.700,
                "validated_status":  r[9],
                "snapshot_year":     r[10],
                "extraction_method": r[11],
                "schema_version":    r[12],
                "domain":            domain_val,
            })
    return out


def _fetch_matches() -> list[dict]:
    """anxg_auto.defect_matches → 엣지 row. defect_type_id → defect_name 조인."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT m.recall_id, d.name AS defect_name,
                   m.cos_sim, m.match_method, m.rank,
                   m.source_id, m.source_type, m.confidence_score, m.validated_status,
                   m.snapshot_year, m.extraction_method, m.schema_version
              FROM anxg_auto.defect_matches m
              JOIN anxg_auto.defect_types d ON d.defect_type_id = m.defect_type_id
             -- PRD §6.7: reviewed-rejected 매칭은 그래프에 적재 금지 (rejected_loaded invariant).
             WHERE m.validated_status IS DISTINCT FROM 'rejected'
        """)
        out = []
        for r in cur.fetchall():
            out.append({
                "recall_id":         r[0],
                "defect_name":       r[1],
                "cos_sim":           float(r[2]) if r[2] is not None else None,
                "match_method":      r[3],
                "rank":              r[4],
                "source_id":         r[5],
                "source_type":       r[6],
                "confidence_score":  float(r[7]) if r[7] is not None else 0.700,
                "validated_status":  r[8],
                "snapshot_year":     r[9],
                "extraction_method": r[10],
                "schema_version":    r[11],
            })
    return out


# ──────────────────────────────────────────────────────────────────────
# 적재
# ──────────────────────────────────────────────────────────────────────

def load(*, skip_recall_backfill: bool = False, batch: int = 500) -> dict[str, int]:
    stats = {"recall": 0, "recall_edge_model": 0, "defect_type": 0, "defect_match": 0}


    # 1) Recall 보충
    if not skip_recall_backfill:
        recalls = _fetch_recalls()
        log.info("[neo4j.recall_backfill] %d rows (전체 events_recalls)", len(recalls))
        with get_session() as sess:
            stats["recall"] = run_batched(sess, MERGE_RECALL, recalls, batch=batch)
            stats["recall_edge_model"] = run_batched(sess, MERGE_RECALL_EDGE_MODEL, recalls, batch=batch)

    # 2) DefectType 노드
    defect_types = _fetch_defect_types()
    log.info("[neo4j.defect_types] %d nodes", len(defect_types))
    with get_session() as sess:
        stats["defect_type"] = run_batched(sess, MERGE_DEFECT_TYPE, defect_types, batch=batch)

    # 3) DEFECT_MATCHES 엣지
    matches = _fetch_matches()
    log.info("[neo4j.defect_matches] %d edges", len(matches))
    with get_session() as sess:
        stats["defect_match"] = run_batched(sess, MERGE_DEFECT_MATCH, matches, batch=batch)

    return stats


def main() -> int:
    ap = argparse.ArgumentParser(prog="autograph.loaders.load_defect_matches_neo4j",
                                  description=__doc__.split("\n")[0])
    ap.add_argument("--skip-recall-backfill", action="store_true",
                    help="이미 Recall이 다 들어가있다면 1단계 스킵")
    ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--dry-run", action="store_true",
                    help="PG fetch만 — Neo4j 쓰기 안 함")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.dry_run:
        rec = _fetch_recalls()
        dt = _fetch_defect_types()
        mt = _fetch_matches()
        print(f"[dry-run] recalls={len(rec)} defect_types={len(dt)} matches={len(mt)}")
        if dt:
            t = dt[0]
            print(f"  sample DefectType: name={t['name']!r} domain={t['domain']} category={t['category']}")
        if rec:
            r = rec[0]
            print(f"  sample Recall: id={r['id']} source={r['source']} domain={r['domain']}")
        return 0

    stats = load(skip_recall_backfill=args.skip_recall_backfill, batch=args.batch)
    print(f"[OK] {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
