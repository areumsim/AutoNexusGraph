"""(:Anxg_Part)-[:PRODUCED_BY]->(:Anxg_ProcessStep) — 부품 → 공정 카테고리 추론 적재.

ProcessGraph G-2 / BoP 입력. ontology 가 상정한 deterministic BoP routing
(DART 공정도설명 + 산단공 part_id 매칭)은 **산단공 part_id 부재**로 불가 →
차선으로 :Part 의 NHTSA system / 한글 부품명에서 **공정 카테고리를 추론**한다.

★ 등급 (정직): 카테고리 추론이라 ontology default 0.80(B, DART 매칭)이 아닌
  **candidate / conf 0.50 (C)**. 외주 부품(센서·조명·에어백)은 OEM 공정이 생산하지
  않고 의장(조립)에서 BoP 진입 → 기본값 '의장'. 본체/파워트레인 부품만 제조 공정
  매핑. 진짜 deterministic 매핑(산단공 part_id 또는 DART 공정도)이 들어오면 격상.

구조: (:Anxg_Part)-[:PRODUCED_BY]->(:Anxg_ProcessStep {step_id='proc_<공정>'})-[:INSTANTIATES]->(:Anxg_Process).
대표 ProcessStep(proc_*)은 공정유형별 1개 — 부품 BoP 진입점 표현 (plant 비귀속).

CLI:
    python -m autograph.loaders.process.load_produced_by [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field

from autograph.loaders._neo4j_helpers import edge_meta_cypher, run_batched
from autonexusgraph.db.neo4j import get_session

log = logging.getLogger(__name__)

_SOURCE_ID = "ontology/auto + NHTSA system 추론"
_CONF = 0.50
_SNAPSHOT_YEAR = 2026


def _proc_for(name: str) -> str:
    """부품명(NHTSA system 경로 또는 한글) → 캐논 공정. 기본=의장(조립 BoP 진입)."""
    s = (name or "").upper()
    n = name or ""
    if any(k in s for k in ("STRUCTURE", "BODY", "FRAME")) or "차체" in n:
        return "프레스"
    if any(k in s for k in ("SUSPENSION", "BRAKE", "STEERING", "FUEL")) or "브레이크" in n:
        return "가공"
    if (any(k in s for k in ("ENGINE", "POWER TRAIN", "POWERTRAIN", "TRANSMISSION"))
            or any(k in n for k in ("배터리", "BMS", "점화", "알터네이터", "스타터",
                                     "라디에이터", "워터펌프"))):
        return "파워트레인"
    return "의장"   # AIR BAGS / ELECTRICAL / 센서 / 카메라 / 조명 / 와이퍼 — 외주 조립


@dataclass
class LoadStats:
    parts_seen:    int = 0
    edges_created: int = 0
    errors: list[str] = field(default_factory=list)


# 대표 ProcessStep(proc_*) MERGE + INSTANTIATES + Part PRODUCED_BY.
_MERGE_CYPHER = f"""
UNWIND $rows AS r
MATCH (pt:Anxg_Part {{id: r.part_id}})
MERGE (pr:Anxg_Process {{process_name_norm: r.process_name_norm}})
  ON CREATE SET pr.process_name    = r.process_name,
                pr.source           = 'produced_by_seed',
                pr.domain           = 'auto',
                pr.validated_status = 'validated',
                pr.snapshot_year    = r.snapshot_year,
                pr.updated_at        = datetime()
MERGE (st:Anxg_ProcessStep {{step_id: r.step_id}})
  ON CREATE SET st.process_name_norm = r.process_name_norm,
                st.process_name      = r.process_name,
                st.source            = 'produced_by_seed',
                st.domain            = 'auto',
                st.updated_at        = datetime()
MERGE (st)-[inst:INSTANTIATES]->(pr)
SET {edge_meta_cypher('inst')}
MERGE (pt)-[edge:PRODUCED_BY]->(st)
SET {edge_meta_cypher('edge')}
"""


def _build_rows(parts: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for p in parts:
        pid = p.get("id")
        if pid is None:
            continue
        proc = _proc_for(p.get("name") or "")
        pnorm = proc.lower()
        rows.append({
            "part_id":           pid,
            "process_name":      proc,
            "process_name_norm": pnorm,
            "step_id":           f"proc_{pnorm}",
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

    with get_session() as session:
        parts = session.run("MATCH (p:Anxg_Part) RETURN p.id AS id, p.name AS name").data()
        stats.parts_seen = len(parts)
        rows = _build_rows(parts)

        if dry_run:
            from collections import Counter
            c = Counter(r["process_name"] for r in rows)
            log.info("[produced_by] DRY-RUN — Part %d → PRODUCED_BY %d", len(parts), len(rows))
            for p, n in c.most_common():
                log.info("  • %s: %d", p, n)
            return stats

        if not rows:
            log.warning("[produced_by] :Part 노드 0 — auto neo4j 적재 확인")
            return stats

        run_batched(session, _MERGE_CYPHER, rows, batch=200)
        res = session.run(
            "MATCH (:Anxg_Part)-[e:PRODUCED_BY]->(:Anxg_ProcessStep) RETURN count(e) AS n"
        ).single()
        stats.edges_created = int(res["n"]) if res else 0

    log.info("[produced_by] parts=%d PRODUCED_BY=%d (candidate)",
             stats.parts_seen, stats.edges_created)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(prog="autograph.loaders.process.load_produced_by")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load(dry_run=args.dry_run)


if __name__ == "__main__":
    main()


__all__ = ["load", "LoadStats", "_build_rows", "_proc_for"]
