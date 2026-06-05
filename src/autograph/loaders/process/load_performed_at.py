"""(:Anxg_ProcessStep)-[:PERFORMED_AT]->(:Anxg_Plant) 회사 귀속 공정 시드 적재.

source: ``ontology/auto/performed_at_seed.yaml`` — 한국 OEM 완성차/파워트레인
공장의 4 대 핵심공정(프레스/차체/도장/의장) + 파워트레인 매핑. 공개 자료 기반
PRD §3.5 **B 등급** (deterministic) → confidence 0.85 + validated.

ProcessGraph DoD #19 (회사 귀속 인스턴스 ≥ 30) 의 **source allowlist hard-check**
실현. 산단공(synthetic·익명) :ProcessStep 550 은 회사 귀속 금지 — 본 로더는 별도의
회사 귀속 :ProcessStep (step_id prefix ``seed_``) 을 새로 생성하므로 익명 스텝을
오염시키지 않는다.

생성:
    (:Anxg_Process {process_name_norm})              캐논 공정유형 (synthetic 사전과 분리)
    (:Anxg_ProcessStep {step_id='seed_<plant>_<proc>'})  회사 귀속 인스턴스
    (:Anxg_ProcessStep)-[:INSTANTIATES]->(:Anxg_Process)
    (:Anxg_ProcessStep)-[:PERFORMED_AT]->(:Anxg_Plant {code})  ★ 회사 귀속 (7키 메타)

선행 조건:
    ``make load-auto-seed-standards-plants`` — :Plant 노드(code) 적재.

CLI:
    python -m autograph.loaders.process.load_performed_at
    python -m autograph.loaders.process.load_performed_at --dry-run

종료 코드:
    0: 정상 (seed 미적재 / Plant 부재 시 graceful 0 건).
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field

from autograph.loaders._neo4j_helpers import edge_meta_cypher, run_batched
from autograph.ontology import load_performed_at_seed
from autonexusgraph.db.neo4j import get_session

log = logging.getLogger(__name__)

_DEFAULT_CONFIDENCE = 0.85
_SOURCE_ID = "ontology/auto/performed_at_seed.yaml"
_SNAPSHOT_YEAR = 2026


def _norm(name: str) -> str:
    """공정명 → process_name_norm (synthetic 사전과 동일 규약: strip + lower)."""
    return (name or "").strip().lower()


@dataclass
class LoadStats:
    rows_seen:      int = 0
    edges_created:  int = 0
    plants_missing: int = 0
    errors: list[str] = field(default_factory=list)


# 캐논 :Process MERGE + 회사 귀속 :ProcessStep + INSTANTIATES + PERFORMED_AT.
# Plant 부재 시 MATCH 실패 → 해당 row 전체 skip (orphan step 미생성).
_MERGE_CYPHER = f"""
UNWIND $rows AS r
MATCH (pl:Anxg_Plant {{code: r.plant_code}})
MERGE (pr:Anxg_Process {{process_name_norm: r.process_name_norm}})
  ON CREATE SET pr.process_name     = r.process_name,
                pr.process_desc      = r.process_desc,
                pr.source            = 'performed_at_seed',
                pr.domain            = 'auto',
                pr.validated_status  = 'validated',
                pr.confidence_score  = r.confidence_score,
                pr.snapshot_year     = r.snapshot_year,
                pr.updated_at        = datetime()
MERGE (st:Anxg_ProcessStep {{step_id: r.step_id}})
  SET st.process_name_norm = r.process_name_norm,
      st.process_name      = r.process_name,
      st.source            = 'performed_at_seed',
      st.manufacturer      = r.manufacturer,
      st.plant_code        = r.plant_code,
      st.domain            = 'auto',
      st.confidence_score  = r.confidence_score,
      st.validated_status  = 'validated',
      st.snapshot_year     = r.snapshot_year,
      st.updated_at        = datetime()
MERGE (st)-[inst:INSTANTIATES]->(pr)
SET {edge_meta_cypher('inst')}
MERGE (st)-[edge:PERFORMED_AT]->(pl)
SET {edge_meta_cypher('edge')}
"""


def _build_rows(seed: dict) -> list[dict]:
    """seed → PERFORMED_AT row 1개 = (plant_code, process) 페어."""
    desc = {(_norm(p.get("name"))): (p.get("desc") or "")
            for p in (seed.get("processes") or [])}
    rows: list[dict] = []
    for m in seed.get("mappings") or []:
        plant = (m.get("plant_code") or "").strip()
        mfr = (m.get("manufacturer") or "").strip()
        if not plant:
            continue
        for proc in m.get("processes") or []:
            pname = (proc or "").strip()
            if not pname:
                continue
            pnorm = _norm(pname)
            rows.append({
                "plant_code":        plant,
                "manufacturer":      mfr,
                "process_name":      pname,
                "process_name_norm": pnorm,
                "process_desc":      desc.get(pnorm, ""),
                "step_id":           f"seed_{plant}_{pnorm}",
                # 7키 메타 (snapshot/schema 는 helper default 보강)
                "source_type":       "manual_seed",
                "source_id":         _SOURCE_ID,
                "confidence_score":  _DEFAULT_CONFIDENCE,
                "validated_status":  "validated",
                "extraction_method": "manual",
                "snapshot_year":     _SNAPSHOT_YEAR,
            })
    return rows


def load(*, dry_run: bool = False) -> LoadStats:
    stats = LoadStats()
    seed = load_performed_at_seed()
    rows = _build_rows(seed)
    stats.rows_seen = len(rows)

    if not rows:
        log.warning("[performed_at] seed 비어있음 — %s 확인", _SOURCE_ID)
        return stats

    if dry_run:
        log.info("[performed_at] DRY-RUN — would emit %d PERFORMED_AT edges", len(rows))
        for r in rows[:8]:
            log.info("  • %s @ %s (%s)", r["process_name"], r["plant_code"], r["manufacturer"])
        return stats


    with get_session() as session:
        # Plant 부재 진단 (code 매칭).
        missing = set()
        for r in rows:
            chk = session.run(
                "MATCH (p:Anxg_Plant {code:$c}) RETURN count(p) AS n", c=r["plant_code"]
            ).single()
            if not chk or int(chk["n"]) == 0:
                missing.add(r["plant_code"])
        stats.plants_missing = len(missing)

        run_batched(session, _MERGE_CYPHER, rows, batch=200)
        # 실제 적재된 PERFORMED_AT 엣지 수 (멱등 재실행 정합).
        res = session.run(
            "MATCH (:Anxg_ProcessStep)-[e:PERFORMED_AT]->(:Anxg_Plant) "
            "WHERE e.source_id = $sid RETURN count(e) AS n", sid=_SOURCE_ID
        ).single()
        stats.edges_created = int(res["n"]) if res else 0

    log.info("[performed_at] seen=%d PERFORMED_AT(seed)=%d plants_missing=%d",
             stats.rows_seen, stats.edges_created, stats.plants_missing)
    if missing:
        log.warning("[performed_at] Plant code 부재로 skip: %s — plants.yaml 적재 확인",
                    sorted(missing))
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(prog="autograph.loaders.process.load_performed_at")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load(dry_run=args.dry_run)


if __name__ == "__main__":
    main()


__all__ = ["load", "LoadStats"]
