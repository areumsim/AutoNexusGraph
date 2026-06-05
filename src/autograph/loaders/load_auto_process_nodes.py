"""산단공 합성 공정사전(`anxg_auto.processes`) → Neo4j ``:Process`` 노드 적재 (BoP taxonomy).

ProcessGraph (PRD_process_graph §1 / 로드맵 1단계) — BoP 축의 뼈대.
`anxg_auto.processes` 는 PG SSOT (loader: ``load_sandang_processes.py``). 본 모듈은 그
**정규화 공정명(process_name_norm) 별 1 노드**로 ``:Process`` 를 MERGE 한다.

설계 메모:
- 키 = ``process_name_norm`` (≈410 distinct) — 행 PK ``process_id``(550) 가 아님.
  ontology/auto/entities.yaml 의 ``Process.key`` 와 일치 → neo4j_init UNIQUE 제약과 정합.
- grade C (합성·0.50, validated_status='candidate') — taxonomy 전용, 확정 사실 금지.
- 엣지 없음 (노드만). INSTANTIATES/PRODUCED_BY 등은 후속 단계(3·6).
- 멱등: MERGE by process_name_norm. 키 부재(테이블 비었음) 시 graceful 0 건.

CLI:
    python -m autograph.loaders.load_auto_process_nodes [--batch 500]
"""

from __future__ import annotations

import argparse
import logging

from autonexusgraph.db.neo4j import get_session
from autonexusgraph.db.postgres import get_connection

from ._neo4j_helpers import run_batched


log = logging.getLogger(__name__)


# 정규화 공정명 1 건 = :Process 1 노드. 대표 공정명/공정도명/업종코드는 집계(min).
# grade C governance 속성은 노드에 그대로 — 답변 시 "패턴(합성)" 근거.
MERGE_PROCESS = """
UNWIND $rows AS r
MERGE (p:Anxg_Process {process_name_norm: r.process_name_norm})
SET   p.process_name      = r.process_name,
      p.process_map_name   = r.process_map_name,
      p.industry_code      = r.industry_code,
      p.source             = 'datagokr_15151075',
      p.confidence_score   = 0.50,
      p.validated_status   = 'candidate',
      p.snapshot_year      = r.snapshot_year,
      p.updated_at         = datetime()
"""


def _fetch_processes(cur) -> list[dict]:
    """anxg_auto.processes → process_name_norm 별 1 dict (대표값 집계).

    process_name_norm 이 NULL/빈 문자열인 행은 제외 (노드 키 무결성).
    """
    cur.execute("""
        SELECT process_name_norm,
               min(process_name)      AS process_name,
               min(process_map_name)  AS process_map_name,
               min(industry_code)     AS industry_code,
               max(snapshot_year)     AS snapshot_year
          FROM anxg_auto.processes
         WHERE process_name_norm IS NOT NULL
           AND btrim(process_name_norm) <> ''
         GROUP BY process_name_norm
    """)
    return [{
        "process_name_norm": r[0],
        "process_name": r[1],
        "process_map_name": r[2],
        "industry_code": r[3],
        "snapshot_year": r[4],
    } for r in cur.fetchall()]


def merge_processes(session, rows: list[dict], batch: int = 500) -> int:
    """이미 열린 Neo4j session 에 :Process MERGE — load_auto_neo4j.load_all 재사용용."""
    return run_batched(session, MERGE_PROCESS, rows, batch=batch)


def load_all(batch: int = 500) -> dict:
    """독립 실행 진입점 — 자체 PG/Neo4j 연결로 :Process 적재."""
    pg = get_connection()
    with pg.cursor() as cur:
        rows = _fetch_processes(cur)
    pg.commit()

    if not rows:
        log.warning("[neo4j:process] anxg_auto.processes 비었음 — graceful skip (0 nodes)")
        return {"processes": 0}


    with get_session() as session:
        n = merge_processes(session, rows, batch=batch)
    out = {"processes": n}
    log.info("[neo4j:process] loaded %s (distinct process_name_norm)", out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(prog="autograph.loaders.load_auto_process_nodes")
    ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load_all(batch=args.batch)


if __name__ == "__main__":
    main()
