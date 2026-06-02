"""산단공 공정사전 → Neo4j BoP routing 적재 — :ProcessStep + INSTANTIATES + PRECEDES.

ProcessGraph (PRD_process_graph 로드맵 3단계 — 공정 경로/BoP routing).
``auto.processes`` 의 행 1개 = ``:ProcessStep`` 1개 (step_id='sd_<process_id>').

엣지 (전부 grade C — 산단공 합성, **회사 비귀속**):
- ``(:ProcessStep)-[:INSTANTIATES]->(:Process)``  단계 → 공정유형(사전, process_name_norm).
- ``(:ProcessStep)-[:PRECEDES]->(:ProcessStep)``  같은 (factory_manage_no, process_map_name)
  그룹 내 process_order 인접 단계. **선형 체인**(분기 없음) → 적재 폭발 없음.
  조회 depth cap 은 ``auto_proc_route`` 템플릿의 ``PRECEDES*0..10`` 으로 질의에서 제한.

비목표(정직): ``PRODUCED_BY (Part→ProcessStep)`` 는 산단공에 part_id 가 없어(공정도명=
시스템 카테고리뿐) 결정적 출처 부재 → 본 단계 미생성(relations.yaml enabled:false).

선행: :Process 노드 적재 완료 (``load_auto_process_nodes``). INSTANTIATES 가 MATCH 의존.

CLI:
    python -m autograph.loaders.load_auto_process_routes [--batch 500]
"""

from __future__ import annotations

import argparse
import logging

from autonexusgraph.db.neo4j import get_driver
from autonexusgraph.db.postgres import get_connection

from ._neo4j_helpers import edge_meta_cypher, run_batched


log = logging.getLogger(__name__)

_SOURCE = "datagokr_15151075"   # 산단공 합성 — grade C
_CONF_C = 0.50

# :ProcessStep MERGE + INSTANTIATES → :Process (process_name_norm 으로 매칭).
MERGE_STEP_INSTANTIATES = f"""
UNWIND $rows AS r
MERGE (st:ProcessStep {{step_id: r.step_id}})
SET   st.seq               = r.seq,
      st.process_name_norm  = r.process_name_norm,
      st.source             = '{_SOURCE}',
      st.confidence_score   = {_CONF_C},
      st.validated_status   = 'candidate',
      st.snapshot_year      = r.snapshot_year,
      st.updated_at         = datetime()
WITH st, r
MATCH (p:Process {{process_name_norm: r.process_name_norm}})
MERGE (st)-[rel:INSTANTIATES]->(p)
SET {edge_meta_cypher('rel')}
"""

# PRECEDES — 두 ProcessStep 모두 존재해야 하므로 별도 패스.
MERGE_PRECEDES = f"""
UNWIND $rows AS r
MATCH (a:ProcessStep {{step_id: r.from_step}})
MATCH (b:ProcessStep {{step_id: r.to_step}})
MERGE (a)-[rel:PRECEDES]->(b)
SET {edge_meta_cypher('rel')}
"""


def _meta(extra: dict) -> dict:
    """7키 메타 중 row 가 직접 보유해야 하는 5키 (snapshot/schema 는 helper default)."""
    base = {
        "source_type": _SOURCE,
        "source_id": _SOURCE,
        "confidence_score": _CONF_C,
        "validated_status": "candidate",
        "extraction_method": "deterministic",
    }
    base.update(extra)
    return base


def _fetch_steps(cur) -> list[dict]:
    """auto.processes → ProcessStep row (factory/map 는 PRECEDES 그룹핑용, 노드 미저장)."""
    cur.execute("""
        SELECT process_id, factory_manage_no, process_map_name,
               process_order, process_name_norm, snapshot_year
          FROM auto.processes
         WHERE process_name_norm IS NOT NULL
           AND btrim(process_name_norm) <> ''
         ORDER BY factory_manage_no, process_map_name, process_order, process_id
    """)
    out = []
    for pid, fac, mp, order, norm, yr in cur.fetchall():
        out.append(_meta({
            "step_id": f"sd_{pid}",
            "seq": order,
            "process_name_norm": norm,
            "snapshot_year": yr,
            "_factory": fac, "_map": mp,   # grouping only (밑줄 = 노드 미저장)
        }))
    return out


def _build_precedes(steps: list[dict]) -> list[dict]:
    """같은 (factory, map) 그룹 내 인접 step → PRECEDES pair (선형)."""
    pairs: list[dict] = []
    prev = None
    for r in steps:
        key = (r["_factory"], r["_map"])
        if prev is not None and prev[0] == key:
            pairs.append(_meta({"from_step": prev[1], "to_step": r["step_id"]}))
        prev = (key, r["step_id"])
    return pairs


def load_all(batch: int = 500) -> dict:
    pg = get_connection()
    with pg.cursor() as cur:
        steps = _fetch_steps(cur)
    pg.commit()

    if not steps:
        log.warning("[neo4j:proc_route] auto.processes 비었음 — graceful skip")
        return {"steps": 0, "instantiates": 0, "precedes": 0}

    precedes = _build_precedes(steps)
    driver = get_driver()
    with driver.session() as session:
        n_step = run_batched(session, MERGE_STEP_INSTANTIATES, steps, batch=batch)
        n_prec = run_batched(session, MERGE_PRECEDES, precedes, batch=batch)
    out = {"steps": n_step, "instantiates": n_step, "precedes": n_prec}
    log.info("[neo4j:proc_route] loaded %s", out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(prog="autograph.loaders.load_auto_process_routes")
    ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load_all(batch=args.batch)


if __name__ == "__main__":
    main()
