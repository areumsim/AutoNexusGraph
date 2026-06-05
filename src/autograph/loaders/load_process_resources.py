"""(:Anxg_ProcessStep)-[:USES_EQUIPMENT]->(:Anxg_Equipment) + [:CONSUMES_MATERIAL]->(:Anxg_Material).

ProcessGraph G-3. 자동차 공정의 표준 설비·투입소재를 공정유형별로 적재.

- USES_EQUIPMENT: 공정 → 표준 제조설비 (프레스기/용접로봇/도장설비/CNC 등). 모든
  완성차 공장 공통 textbook 사실 → validated, conf 0.50 (ontology default — 특정
  설비 모델은 공장별 상이하므로 type 수준).
- CONSUMES_MATERIAL: 파워트레인(배터리셀) → 기존 L6 배터리소재(NCM/LFP/Graphite).
  셀 제조가 cathode/anode 소재를 소비하는 deterministic 사실 → validated, conf 0.80.

대표 ProcessStep(proc_*)을 통해 연결 (G-2 와 동일 — plant 비귀속 공정유형 노드).
산단공 소재·설비 raw 데이터 부재의 차선 — 표준 공정 지식 기반.

CLI:
    python -m autograph.loaders.load_process_resources [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field

from autonexusgraph.db.neo4j import get_session

from ._neo4j_helpers import edge_meta_cypher, run_batched

log = logging.getLogger(__name__)

_SOURCE_ID = "process_resources_seed (표준 공정 지식)"
_SNAPSHOT_YEAR = 2026

# 공정유형 → 표준 설비. (모든 OEM 완성차 공장 공통.)
_EQUIPMENT = {
    "프레스":   ["프레스기", "프레스금형"],
    "차체":     ["스폿용접로봇", "차체조립지그"],
    "용접":     ["용접로봇"],
    "도장":     ["도장로봇", "전착도장설비"],
    "의장":     ["조립라인", "너트러너"],
    "조립":     ["조립라인", "너트러너"],
    "가공":     ["CNC가공기", "머시닝센터"],
    "사출":     ["사출성형기"],
    "파워트레인": ["CNC가공기", "파워트레인조립설비"],
}
# CONSUMES_MATERIAL — 배터리셀 제조 공정만 기존 L6 소재 소비.
_MATERIAL_PROC = "파워트레인"
_MAT_CONF = 0.80
_EQ_CONF = 0.50


@dataclass
class LoadStats:
    equipment_nodes: int = 0
    uses_equipment:  int = 0
    consumes_material: int = 0
    errors: list[str] = field(default_factory=list)


def _meta(conf: float) -> dict:
    return {
        "source_type":       "manual_seed",
        "source_id":         _SOURCE_ID,
        "confidence_score":  conf,
        "validated_status":  "validated",
        "extraction_method": "deterministic",
        "snapshot_year":     _SNAPSHOT_YEAR,
    }


# proc_* ProcessStep + INSTANTIATES + USES_EQUIPMENT (+ Equipment 노드 MERGE).
_EQ_CYPHER = f"""
UNWIND $rows AS r
MERGE (pr:Anxg_Process {{process_name_norm: r.process_name_norm}})
  ON CREATE SET pr.process_name = r.process_name, pr.source='process_resources_seed',
                pr.domain='auto', pr.validated_status='validated',
                pr.snapshot_year=r.snapshot_year, pr.updated_at=datetime()
MERGE (st:Anxg_ProcessStep {{step_id: r.step_id}})
  ON CREATE SET st.process_name_norm=r.process_name_norm, st.process_name=r.process_name,
                st.source='process_resources_seed', st.domain='auto', st.updated_at=datetime()
MERGE (st)-[inst:INSTANTIATES]->(pr)
SET {edge_meta_cypher('inst')}
MERGE (eq:Anxg_Equipment {{name: r.equipment}})
  ON CREATE SET eq.domain='auto', eq.source='process_resources_seed', eq.updated_at=datetime()
MERGE (st)-[edge:USES_EQUIPMENT]->(eq)
SET {edge_meta_cypher('edge')}
"""

# 파워트레인 proc step → 기존 :Material (배터리소재) CONSUMES_MATERIAL.
_MAT_CYPHER = f"""
UNWIND $rows AS r
MATCH (st:Anxg_ProcessStep {{step_id: r.step_id}})
MATCH (m:Anxg_Material {{code: r.material_code}})
MERGE (st)-[edge:CONSUMES_MATERIAL]->(m)
SET {edge_meta_cypher('edge')}
"""


def _build_equipment_rows() -> list[dict]:
    rows: list[dict] = []
    for proc, equips in _EQUIPMENT.items():
        norm = proc.lower()
        for eq in equips:
            rows.append({
                "process_name": proc, "process_name_norm": norm,
                "step_id": f"proc_{norm}", "equipment": eq,
                **_meta(_EQ_CONF),
            })
    return rows


def load(*, dry_run: bool = False) -> LoadStats:
    stats = LoadStats()
    eq_rows = _build_equipment_rows()

    with get_session() as session:
        mats = session.run("MATCH (m:Anxg_Material) RETURN m.code AS code").value()
        norm = _MATERIAL_PROC.lower()
        mat_rows = [{
            "step_id": f"proc_{norm}", "material_code": code, **_meta(_MAT_CONF)
        } for code in mats if code]

        if dry_run:
            log.info("[process_resources] DRY-RUN — USES_EQUIPMENT %d (설비 %d) / CONSUMES_MATERIAL %d",
                     len(eq_rows), len({r["equipment"] for r in eq_rows}), len(mat_rows))
            return stats

        run_batched(session, _EQ_CYPHER, eq_rows, batch=200)
        if mat_rows:
            run_batched(session, _MAT_CYPHER, mat_rows, batch=200)

        stats.equipment_nodes = session.run(
            "MATCH (e:Anxg_Equipment {source:'process_resources_seed'}) RETURN count(e) AS n").single()["n"]
        stats.uses_equipment = session.run(
            "MATCH (:Anxg_ProcessStep)-[r:USES_EQUIPMENT]->(:Anxg_Equipment) RETURN count(r) AS n").single()["n"]
        stats.consumes_material = session.run(
            "MATCH (:Anxg_ProcessStep)-[r:CONSUMES_MATERIAL]->(:Anxg_Material) RETURN count(r) AS n").single()["n"]

    log.info("[process_resources] Equipment=%d USES_EQUIPMENT=%d CONSUMES_MATERIAL=%d",
             stats.equipment_nodes, stats.uses_equipment, stats.consumes_material)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(prog="autograph.loaders.load_process_resources")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load(dry_run=args.dry_run)


if __name__ == "__main__":
    main()


__all__ = ["load", "LoadStats", "_build_equipment_rows", "_EQUIPMENT"]
