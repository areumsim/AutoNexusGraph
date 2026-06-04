"""(:Module)-[:USES_PROCESS]->(:Process) — 모듈 → 제조 공정유형 추론 적재.

ProcessGraph G-6. :Module(BoM L4) 의 system_code 를 캐논 공정 카테고리로 매핑.
PRODUCED_BY(Part→ProcessStep)의 모듈 수준 대응 — "이 모듈이 어떤 공정으로
만들어지나".

★ 등급: system_code→공정 카테고리 추론이라 **candidate / conf 0.50**. 산단공
  part_id 같은 deterministic 출처 들어오면 격상. 외주 전장/센서 모듈은 의장(조립).

CLI:
    python -m autograph.loaders.load_uses_process [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field

from autonexusgraph.db.neo4j import get_driver

from ._neo4j_helpers import edge_meta_cypher, run_batched


log = logging.getLogger(__name__)

_SOURCE_ID = "Module.system_code → 공정 추론"
_CONF = 0.50
_SNAPSHOT_YEAR = 2026

# Module system_code → 캐논 공정. 미매핑(전장/센서/조명/안전)은 의장(조립).
_SYS_PROC = {
    "BODY": "프레스", "CHASSIS": "프레스",
    "POWERTRAIN": "파워트레인", "BATTERY": "파워트레인",
    "SUSPENSION": "가공", "BRAKE": "가공", "STEERING": "가공",
    "TIRES_WHEELS": "사출",
}
_DEFAULT_PROC = "의장"   # LIGHTING/ELECTRICAL/ADAS/INFOTAINMENT/SAFETY/HVAC/FUEL/UNKNOWN


def _proc_for(system_code: str) -> str:
    return _SYS_PROC.get((system_code or "").upper(), _DEFAULT_PROC)


@dataclass
class LoadStats:
    modules_seen:  int = 0
    edges_created: int = 0
    errors: list[str] = field(default_factory=list)


_MERGE_CYPHER = f"""
UNWIND $rows AS r
MATCH (m:Module {{id: r.module_id}})
MERGE (pr:Process {{process_name_norm: r.process_name_norm}})
  ON CREATE SET pr.process_name = r.process_name, pr.source='uses_process_seed',
                pr.domain='auto', pr.validated_status='validated',
                pr.snapshot_year=r.snapshot_year, pr.updated_at=datetime()
MERGE (m)-[edge:USES_PROCESS]->(pr)
SET {edge_meta_cypher('edge')}
"""


def _build_rows(modules: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for m in modules:
        mid = m.get("id")
        if mid is None:
            continue
        proc = _proc_for(m.get("system_code") or "")
        rows.append({
            "module_id":         mid,
            "process_name":      proc,
            "process_name_norm": proc.lower(),
            "source_type":       "manual_seed",
            "source_id":         _SOURCE_ID,
            "confidence_score":  _CONF,
            "validated_status":  "candidate",
            "extraction_method": "deterministic",
            "snapshot_year":     _SNAPSHOT_YEAR,
        })
    return rows


def load(*, dry_run: bool = False) -> LoadStats:
    stats = LoadStats()
    driver = get_driver()
    with driver.session() as session:
        modules = session.run(
            "MATCH (m:Module) RETURN m.id AS id, m.system_code AS system_code").data()
        stats.modules_seen = len(modules)
        rows = _build_rows(modules)

        if dry_run:
            from collections import Counter
            c = Counter(r["process_name"] for r in rows)
            log.info("[uses_process] DRY-RUN — Module %d → USES_PROCESS %d", len(modules), len(rows))
            for p, n in c.most_common():
                log.info("  • %s: %d", p, n)
            return stats

        if not rows:
            log.warning("[uses_process] :Module 노드 0 — auto neo4j 적재 확인")
            return stats

        run_batched(session, _MERGE_CYPHER, rows, batch=200)
        res = session.run(
            "MATCH (:Module)-[e:USES_PROCESS]->(:Process) RETURN count(e) AS n").single()
        stats.edges_created = int(res["n"]) if res else 0

    log.info("[uses_process] modules=%d USES_PROCESS=%d (candidate)",
             stats.modules_seen, stats.edges_created)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(prog="autograph.loaders.load_uses_process")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load(dry_run=args.dry_run)


if __name__ == "__main__":
    main()


__all__ = ["load", "LoadStats", "_build_rows", "_proc_for", "_SYS_PROC"]
