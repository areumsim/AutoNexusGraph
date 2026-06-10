"""anxg_auto.components Part(L5) 적재 — NHTSA depth≥3 재분류 + manual seed (PR-P2-A 옵션 AC).

ProcessGraph 격상 #2 — BoM L5 격상. 현재 :Part 0 → ~46 (NHTSA 31 자동 + manual seed 15).

옵션 AC (사용자 결정 2026-06-02):
1. **NHTSA depth≥3 자동 재분류** (31 row): anxg_auto.components.canonical_name 의 콜론 깊이
   ≥3 인 level=4 row 를 level=5 로 UPDATE + parent_component_id = parent prefix 매핑.
   예 ``AIR BAGS:FRONTAL:DRIVER SIDE:INFLATOR MODULE`` (depth=3) → level=5,
   parent_component_id = ``AIR BAGS:FRONTAL:DRIVER SIDE`` (depth=2) 의 component_id.
   UNIQUE (canonical_name, system_code) 제약 무영향 (level 만 변경).
2. **Manual seed 한국어 Part 적재** (~15): ``ontology/auto/part_seed.yaml`` →
   level=5 신규 INSERT (다른 canonical_name 사용 → NHTSA L4 와 UNIQUE 충돌 없음).
   parent_module_canonical_name lookup 으로 parent_component_id 채움 (실패 시 NULL).
3. **Neo4j 라벨 swap**: NHTSA depth≥3 노드의 ``:Module`` → ``:Part`` (REMOVE + SET).
   기존 RECALL_OF 엣지는 라벨 무관 (cypher 가 ``Module|Part`` union 으로 매칭).
4. **Neo4j 신규 :Part 노드** (manual seed) MERGE.
5. **CONTAINED_IN 엣지** (Part → Module) — parent_component_id NOT NULL 인 것만.

등급: NHTSA(A 0.95, 재분류만), manual seed(B 0.80, 사전 출처).
멱등: PG UPSERT (canonical_name+system_code UNIQUE), Neo4j MERGE.

CLI:
    python -m autograph.loaders.master.load_parts_l5
    python -m autograph.loaders.master.load_parts_l5 --dry-run
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

from autograph.loaders._neo4j_helpers import edge_meta_cypher, run_batched
from autonexusgraph.db.neo4j import get_session
from autonexusgraph.db.postgres import get_connection

log = logging.getLogger(__name__)


_PART_SEED_YAML = Path(__file__).resolve().parents[4] / "ontology/auto/part_seed.yaml"


# ── PG 트랜잭션 ───────────────────────────────────────────────

_SQL_PROMOTE_DEPTH3 = """
WITH candidates AS (
  SELECT component_id, canonical_name, system_code,
         regexp_replace(canonical_name, ':[^:]+$', '') AS parent_name
    FROM anxg_auto.components
   WHERE level = 4
     AND (length(canonical_name) - length(replace(canonical_name, ':', ''))) >= 3
),
matched AS (
  SELECT c.component_id, p.component_id AS parent_id
    FROM candidates c
    LEFT JOIN anxg_auto.components p
      ON p.canonical_name = c.parent_name
     AND p.system_code   = c.system_code
)
UPDATE anxg_auto.components ac
   SET level = 5,
       parent_component_id = m.parent_id
  FROM matched m
 WHERE ac.component_id = m.component_id
   AND ac.level = 4
RETURNING ac.component_id, ac.canonical_name, ac.parent_component_id
"""


_SQL_FIND_PARENT = """
SELECT component_id
  FROM anxg_auto.components
 WHERE canonical_name = %s
   AND level = 4
 LIMIT 1
"""


_SQL_INSERT_SEED = """
INSERT INTO anxg_auto.components (
  canonical_name, name_norm, system_code, aliases, wikidata_qid,
  source, confidence, validated_status, level, parent_component_id, snapshot_year
) VALUES (
  %(canonical_name)s, %(name_norm)s, %(system_code)s, %(aliases)s, %(wikidata_qid)s,
  'manual_part_seed', 0.800, 'validated', 5, %(parent_component_id)s, 2026
)
ON CONFLICT (canonical_name, system_code) DO UPDATE SET
  name_norm           = EXCLUDED.name_norm,
  aliases             = EXCLUDED.aliases,
  wikidata_qid        = EXCLUDED.wikidata_qid,
  level               = 5,
  parent_component_id = EXCLUDED.parent_component_id
RETURNING component_id, canonical_name, parent_component_id, (xmax = 0) AS inserted
"""


def _promote_depth3(cur, dry_run: bool) -> list[tuple[int, str, int | None]]:
    """NHTSA depth≥3 row → level=5 + parent_component_id UPDATE. 결과 list 반환."""
    cur.execute(_SQL_PROMOTE_DEPTH3)
    rows = cur.fetchall()
    log.info("[parts_l5] depth>=3 promoted: %d (dry_run=%s)", len(rows), dry_run)
    return [(int(r[0]), str(r[1]), int(r[2]) if r[2] is not None else None) for r in rows]


def _load_seed_yaml() -> list[dict]:
    if not _PART_SEED_YAML.exists():
        log.warning("[parts_l5] part_seed.yaml 없음 — manual seed skip")
        return []
    with _PART_SEED_YAML.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return list(data.get("parts") or [])


def _insert_seed(cur, seed: list[dict], dry_run: bool
                  ) -> list[tuple[int, str, int | None, bool]]:
    """manual seed → level=5 INSERT/UPSERT. parent_component_canonical 로 lookup."""
    out: list[tuple[int, str, int | None, bool]] = []
    for s in seed:
        parent_name = s.get("parent_module_canonical_name")
        parent_id: int | None = None
        if parent_name:
            cur.execute(_SQL_FIND_PARENT, (parent_name,))
            r = cur.fetchone()
            if r is None:
                log.warning("[parts_l5] seed '%s' parent_module='%s' lookup 실패 → NULL",
                            s.get("canonical_name"), parent_name)
            else:
                parent_id = int(r[0])
        cur.execute(_SQL_INSERT_SEED, {
            "canonical_name":      s["canonical_name"],
            "name_norm":           s["name_norm"],
            "system_code":         s["system_code"],
            "aliases":             list(s.get("aliases") or []),
            "wikidata_qid":        s.get("wikidata_qid"),
            "parent_component_id": parent_id,
        })
        r = cur.fetchone()
        out.append((int(r[0]), str(r[1]), int(r[2]) if r[2] is not None else None, bool(r[3])))
    log.info("[parts_l5] manual seed processed: %d (dry_run=%s)", len(out), dry_run)
    return out


# ── Neo4j 라벨 swap + 신규 적재 ───────────────────────────────

_CY_SWAP_LABEL = """
UNWIND $ids AS id
MATCH (n:Anxg_Module {id: id})
REMOVE n:Anxg_Module
SET   n:Anxg_Part,
      n.level = 5
"""

_CY_MERGE_PART = """
UNWIND $rows AS r
MERGE (n:Anxg_Part {id: r.id})
SET   n.name           = r.name,
      n.name_norm      = r.name_norm,
      n.system_code    = r.system_code,
      n.aliases        = r.aliases,
      n.wikidata_qid   = r.wikidata_qid,
      n.level          = 5,
      n.source         = 'manual_part_seed',
      n.confidence     = 0.80,
      n.validated_status = 'validated',
      n.snapshot_year  = 2026,
      n.updated_at     = datetime()
"""

_CY_CONTAINED_IN = f"""
UNWIND $rows AS r
MATCH (p:Anxg_Part   {{id: r.part_id}})
MATCH (m:Anxg_Module {{id: r.module_id}})
MERGE (p)-[rel:CONTAINED_IN]->(m)
SET {edge_meta_cypher('rel')}
"""


def _neo4j_apply(session, promoted: list[tuple[int, str, int | None]],
                  seed_rows: list[tuple[int, str, int | None, bool]],
                  seed_yaml: list[dict], batch: int) -> dict:
    """Neo4j 라벨 swap + 신규 노드 + CONTAINED_IN."""
    stats = {"swapped": 0, "seed_merged": 0, "contained_in": 0}

    # 1) NHTSA depth≥3: :Module → :Part 라벨 swap
    if promoted:
        ids = [pid for pid, _, _ in promoted]
        for i in range(0, len(ids), batch):
            res = session.run(_CY_SWAP_LABEL, ids=ids[i:i + batch])
            res.consume()
        stats["swapped"] = len(ids)

    # 2) Manual seed: 신규 :Part MERGE (seed_yaml 의 메타 + DB INSERT 의 component_id 합침)
    seed_by_name = {s["canonical_name"]: s for s in seed_yaml}
    merge_rows: list[dict] = []
    for cid, cname, _parent, _inserted in seed_rows:
        s = seed_by_name.get(cname, {})
        merge_rows.append({
            "id":           cid,
            "name":         cname,
            "name_norm":    s.get("name_norm"),
            "system_code":  s.get("system_code"),
            "aliases":      list(s.get("aliases") or []),
            "wikidata_qid": s.get("wikidata_qid"),
        })
    if merge_rows:
        stats["seed_merged"] = run_batched(session, _CY_MERGE_PART, merge_rows, batch=batch)

    # 3) CONTAINED_IN (Part → Module) — parent_component_id NOT NULL 인 것만
    contained_rows: list[dict] = []
    for pid, _, parent_id in promoted:
        if parent_id is not None:
            contained_rows.append(_meta_row(pid, parent_id, "nhtsa_depth_promote"))
    for cid, _, parent_id, _ in seed_rows:
        if parent_id is not None:
            contained_rows.append(_meta_row(cid, parent_id, "manual_part_seed"))
    if contained_rows:
        stats["contained_in"] = run_batched(session, _CY_CONTAINED_IN, contained_rows, batch=batch)

    return stats


def _meta_row(part_id: int, module_id: int, source: str) -> dict:
    """CONTAINED_IN 엣지 7키 메타 row (snapshot/schema_version 은 helper default)."""
    return {
        "part_id":           part_id,
        "module_id":         module_id,
        "source_type":       source,
        "source_id":         source,
        "confidence_score":  0.95 if source == "nhtsa_depth_promote" else 0.80,
        "validated_status":  "validated",
        "extraction_method": "deterministic",
    }


# ── 메인 진입 ─────────────────────────────────────────────────

def run(*, dry_run: bool = False, batch: int = 200) -> dict:
    pg = get_connection()
    with pg.cursor() as cur:
        promoted = _promote_depth3(cur, dry_run)
        seed_yaml = _load_seed_yaml()
        seed_rows = _insert_seed(cur, seed_yaml, dry_run)

    if dry_run:
        pg.rollback()
        log.info("[parts_l5] DRY-RUN — PG rollback. promoted=%d, seed_processed=%d",
                 len(promoted), len(seed_rows))
        return {"promoted": len(promoted), "seed": len(seed_rows),
                "swapped": 0, "seed_merged": 0, "contained_in": 0, "dry_run": True}
    pg.commit()


    with get_session() as session:
        neo = _neo4j_apply(session, promoted, seed_rows, seed_yaml, batch=batch)

    result = {
        "promoted":     len(promoted),
        "seed":         len(seed_rows),
        **neo,
    }
    log.info("[parts_l5] result=%s", result)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(prog="autograph.loaders.master.load_parts_l5")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--batch", type=int, default=200)
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    print(run(dry_run=args.dry_run, batch=args.batch))


if __name__ == "__main__":
    main()


__all__ = ["run"]
