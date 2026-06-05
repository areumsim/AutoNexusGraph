"""factoryon 공장등록(anxg_auto.factoryon_registry) → Neo4j :Plant 승격 + PERFORMED_AT 확대.

PG 의 90 행(현대차/기아/한국지엠/쌍용/르노 + tier-1)을 :Plant 노드(A 등급, 공식
registry)로 승격하고, 회사명 매칭 시 (:Anxg_Manufacturer)-[:OWNS_PLANT]->(:Anxg_Plant) 를
만든다. 추가로 업종명(KSIC)이 공정을 deterministic 하게 시사하는 공장에 대해
회사 귀속 PERFORMED_AT 을 확대한다.

★ 등급 정합 (ontology/auto/relations.yaml PERFORMED_AT notes + PRD §8):
  - :Plant 는 공식 registry = **A 등급** (deterministic).
  - OWNS_PLANT 도 registry 사실 = validated, conf 0.90.
  - 그러나 **"어떤 공정이 도는지"는 업종→공정 추론** 이므로 PERFORMED_AT 엣지는
    `validated_status='candidate'` + conf 0.60 (plant 의 A 등급을 추론 엣지에 전가
    금지). manual_seed(load_performed_at.py, B/validated/0.85) 과 별개 출처.

비제조 업종(창고/임대/수리/정비/도소매/건물)은 :Plant 승격·PERFORMED_AT 모두 skip.

CLI:
    python -m autograph.loaders.load_factoryon_plants
    python -m autograph.loaders.load_factoryon_plants --dry-run
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field

from autonexusgraph.db.neo4j import get_session
from autonexusgraph.db.postgres import get_connection
from autonexusgraph.ingestion._common import normalize_corp_name

from ._neo4j_helpers import edge_meta_cypher, run_batched

log = logging.getLogger(__name__)

_SOURCE_ID = "anxg_auto.factoryon_registry"
_PLANT_CONF = 0.90          # 공식 registry — 공장·소유 사실
_PROC_CONF = 0.60           # 업종→공정 추론 — candidate
_SNAPSHOT_YEAR = 2026

# 비제조(공장 아님) 업종 — 승격·공정 모두 제외.
_SKIP_INDUSTRY = ("창고", "임대", "수리", "정비", "도매", "소매", "건물")


def _processes_for(industry_name: str) -> list[str]:
    """업종명(KSIC) → 캐논 공정 매핑. 비매칭(일반부품/제철/이차전지)은 빈 리스트.

    완성차(승용차 제조업)만 4 대 공정 전체. 부품·소재 업종은 명시 시사분만.
    """
    s = industry_name or ""
    if "승용차" in s or "여객용 자동차" in s or "화물자동차" in s:
        return ["프레스", "차체", "도장", "의장"]
    if "차체용" in s:
        return ["프레스", "차체"]
    if "동력전달" in s or "엔진" in s:
        return ["파워트레인"]
    if "도장" in s or "표면처리" in s:
        return ["도장"]
    return []


def _city_of(address: str | None) -> str:
    return (address or "").strip().split(" ")[0] if address else ""


@dataclass
class LoadStats:
    plants_seen:     int = 0
    plants_promoted: int = 0
    owns_plant:      int = 0
    performed_at:    int = 0
    skipped_nonmfr:  int = 0
    errors: list[str] = field(default_factory=list)


# :Plant 승격 + OWNS_PLANT (회사 매칭 시).
_PLANT_CYPHER = f"""
UNWIND $rows AS r
MERGE (pl:Anxg_Plant {{code: r.code}})
SET   pl.name          = r.name,
      pl.country       = 'KR',
      pl.city          = r.city,
      pl.source        = 'factoryon',
      pl.factory_no    = r.factory_no,
      pl.business_no   = r.business_no,
      pl.industry_name = r.industry_name,
      pl.products      = r.products,
      pl.grade         = 'A',
      pl.updated_at    = datetime()
WITH pl, r
OPTIONAL MATCH (mm:Anxg_Manufacturer) WHERE mm.name_norm = r.company_norm
FOREACH (_ IN CASE WHEN mm IS NULL THEN [] ELSE [1] END |
  MERGE (mm)-[own:OWNS_PLANT]->(pl)
  SET {edge_meta_cypher('own')}
)
"""

# 회사 귀속 :ProcessStep + INSTANTIATES + PERFORMED_AT (candidate, 업종→공정 추론).
_PERFORMED_CYPHER = f"""
UNWIND $rows AS r
MATCH (pl:Anxg_Plant {{code: r.code}})
MERGE (pr:Anxg_Process {{process_name_norm: r.process_name_norm}})
  ON CREATE SET pr.process_name    = r.process_name,
                pr.source           = 'performed_at_seed',
                pr.domain           = 'auto',
                pr.validated_status = 'validated',
                pr.snapshot_year    = r.snapshot_year,
                pr.updated_at        = datetime()
MERGE (st:Anxg_ProcessStep {{step_id: r.step_id}})
  SET st.process_name_norm = r.process_name_norm,
      st.process_name      = r.process_name,
      st.source            = 'factoryon',
      st.manufacturer      = r.company_name,
      st.plant_code        = r.code,
      st.domain            = 'auto',
      st.confidence_score  = r.confidence_score,
      st.validated_status  = 'candidate',
      st.snapshot_year     = r.snapshot_year,
      st.updated_at        = datetime()
MERGE (st)-[inst:INSTANTIATES]->(pr)
SET {edge_meta_cypher('inst')}
MERGE (st)-[edge:PERFORMED_AT]->(pl)
SET {edge_meta_cypher('edge')}
"""


def _fetch_registry() -> list[dict]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT factory_no, company_name, business_no, address,
                   industry_name, products
              FROM anxg_auto.factoryon_registry
        """)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _edge_meta(method: str, conf: float) -> dict:
    return {
        "source_type":       "factoryon",
        "source_id":         _SOURCE_ID,
        "confidence_score":  conf,
        "validated_status":  "validated" if method == "registry" else "candidate",
        "extraction_method": "deterministic",
        "snapshot_year":     _SNAPSHOT_YEAR,
    }


def _build(rows_db: list[dict]) -> tuple[list[dict], list[dict], int]:
    """registry → (plant_rows, performed_rows, skipped_nonmfr)."""
    plant_rows: list[dict] = []
    perf_rows: list[dict] = []
    skipped = 0
    for d in rows_db:
        fno = (d.get("factory_no") or "").strip()
        company = (d.get("company_name") or "").strip()
        industry = d.get("industry_name") or ""
        if not fno or not company:
            continue
        if any(tok in industry for tok in _SKIP_INDUSTRY):
            skipped += 1
            continue
        code = f"FCTRY_{fno}"
        plant_rows.append({
            "code":          code,
            "name":          company,
            "factory_no":    fno,
            "business_no":   d.get("business_no"),
            "city":          _city_of(d.get("address")),
            "industry_name": industry,
            "products":      d.get("products"),
            "company_norm":  normalize_corp_name(company),
            **_edge_meta("registry", _PLANT_CONF),     # OWNS_PLANT 메타
        })
        for proc in _processes_for(industry):
            pnorm = proc.strip().lower()
            perf_rows.append({
                "code":              code,
                "company_name":      company,
                "process_name":      proc,
                "process_name_norm": pnorm,
                "step_id":           f"fctry_{fno}_{pnorm}",
                "confidence_score":  _PROC_CONF,
                **_edge_meta("inferred", _PROC_CONF),  # PERFORMED_AT/INSTANTIATES 메타
            })
    return plant_rows, perf_rows, skipped


def load(*, dry_run: bool = False) -> LoadStats:
    stats = LoadStats()
    rows_db = _fetch_registry()
    plant_rows, perf_rows, skipped = _build(rows_db)
    stats.plants_seen = len(rows_db)
    stats.skipped_nonmfr = skipped

    if dry_run:
        log.info("[factoryon_plants] DRY-RUN — :Plant=%d PERFORMED_AT=%d skip(비제조)=%d",
                 len(plant_rows), len(perf_rows), skipped)
        for r in perf_rows[:8]:
            log.info("  • %s @ %s (candidate)", r["process_name"], r["company_name"][:24])
        return stats

    if not plant_rows:
        log.warning("[factoryon_plants] registry 비어있음 — make load-factoryon 먼저")
        return stats


    with get_session() as session:
        run_batched(session, _PLANT_CYPHER, plant_rows, batch=200)
        stats.plants_promoted = session.run(
            "MATCH (p:Anxg_Plant {source:'factoryon'}) RETURN count(p) AS n").single()["n"]
        stats.owns_plant = session.run(
            "MATCH (:Anxg_Manufacturer)-[r:OWNS_PLANT]->(:Anxg_Plant {source:'factoryon'}) "
            "RETURN count(r) AS n").single()["n"]
        if perf_rows:
            run_batched(session, _PERFORMED_CYPHER, perf_rows, batch=200)
        stats.performed_at = session.run(
            "MATCH (:Anxg_ProcessStep {source:'factoryon'})-[e:PERFORMED_AT]->(:Anxg_Plant) "
            "RETURN count(e) AS n").single()["n"]

    log.info("[factoryon_plants] :Plant=%d OWNS_PLANT=%d PERFORMED_AT(factoryon)=%d skip=%d",
             stats.plants_promoted, stats.owns_plant, stats.performed_at, stats.skipped_nonmfr)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(prog="autograph.loaders.load_factoryon_plants")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load(dry_run=args.dry_run)


if __name__ == "__main__":
    main()


__all__ = ["load", "LoadStats", "_processes_for", "_build"]
