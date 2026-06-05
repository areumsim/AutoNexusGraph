"""(:Anxg_Recall)-[:CAUSED_BY_PROCESS]->(:Anxg_Process) — 한글 리콜 결함 → 공정 추론 적재.

ProcessGraph G-4 / DoD §10.20 cross. KOTSA 한글 리콜(anxg_auto.events_recalls,
source='datagokr_kotsa', 941행) 의 결함 요약에서 **공정 키워드 + 결함 지시어**
동시출현을 deterministic 매칭 → CAUSED_BY_PROCESS 후보 엣지.

★ 등급 (ontology CAUSED_BY_PROCESS: confidence_default 0.50, "C — 후보, 단독 근거
금지"):
  - 결함 텍스트가 공정을 명시해도 "그 공정이 원인"은 **인과 추론** → 모든 엣지
    `validated_status='candidate'` + conf 0.50.
  - 한글-한글 매칭(US 영문 리콜 ↔ 한글 공정 환각위험 회피). LLM 미사용 —
    deterministic 키워드라 P3 LLM 보다 보수적. LLM P3 cross-validate 는 후속.

노이즈 차단: '단조'(첨단조향장치 부분매칭), '압연'/'납땜'(극소·불안정) 제외.
'조립/체결' → 조립, '성형' → 프레스, '코팅' → 도장 으로 정규화.

CLI:
    python -m autograph.loaders.load_recall_process_map
    python -m autograph.loaders.load_recall_process_map --dry-run
"""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass, field

from autonexusgraph.db.neo4j import get_session
from autonexusgraph.db.postgres import get_connection

from ._neo4j_helpers import edge_meta_cypher, run_batched

log = logging.getLogger(__name__)

_SOURCE_ID = "anxg_auto.events_recalls(datagokr_kotsa)"
_CONF = 0.50            # ontology C default — 후보
_SNAPSHOT_YEAR = 2026

# 공정 키워드 → 캐논 공정명. 단조/압연/납땜 제외(노이즈/극소).
_PROC = {
    "용접": "용접", "조립": "조립", "체결": "조립",
    "가공": "가공", "사출": "사출",
    "프레스": "프레스", "성형": "프레스",
    "도장": "도장", "코팅": "도장",
}
# 인과 정밀도 — 공정 키워드 + 결함 지시어 동시출현 시에만 후보.
_DEFECT = re.compile("불량|오류|누락|결함|균열|문제|미흡|손상|이탈|파손")


@dataclass
class LoadStats:
    recalls_scanned: int = 0
    recalls_matched: int = 0
    edges_created:   int = 0
    errors: list[str] = field(default_factory=list)


_MERGE_CYPHER = f"""
UNWIND $rows AS r
MATCH (rc:Anxg_Recall {{id: r.recall_id}})
MERGE (pr:Anxg_Process {{process_name_norm: r.process_name_norm}})
  ON CREATE SET pr.process_name    = r.process_name,
                pr.source           = 'recall_process_map',
                pr.domain           = 'auto',
                pr.validated_status = 'validated',
                pr.snapshot_year    = r.snapshot_year,
                pr.updated_at        = datetime()
MERGE (rc)-[edge:CAUSED_BY_PROCESS]->(pr)
SET {edge_meta_cypher('edge')}
"""


def _build_rows(db_rows: list[tuple]) -> tuple[list[dict], int]:
    """(recall_id, defect_summary) → CAUSED_BY_PROCESS row. 결함지시어 필수."""
    rows: list[dict] = []
    matched: set = set()
    for recall_id, defect in db_rows:
        text = defect or ""
        if not _DEFECT.search(text):
            continue
        procs = {proc for kw, proc in _PROC.items() if kw in text}
        if not procs:
            continue
        matched.add(recall_id)
        for proc in sorted(procs):
            rows.append({
                "recall_id":         recall_id,
                "process_name":      proc,
                "process_name_norm": proc.lower(),
                "source_type":       "datagokr_recall",
                "source_id":         _SOURCE_ID,
                "confidence_score":  _CONF,
                "validated_status":  "candidate",
                "extraction_method": "deterministic",
                "snapshot_year":     _SNAPSHOT_YEAR,
            })
    return rows, len(matched)


def _fetch() -> list[tuple]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT recall_id, defect_summary
              FROM anxg_auto.events_recalls
             WHERE source = 'datagokr_kotsa' AND defect_summary IS NOT NULL
        """)
        return cur.fetchall()


def load(*, dry_run: bool = False) -> LoadStats:
    stats = LoadStats()
    db_rows = _fetch()
    stats.recalls_scanned = len(db_rows)
    rows, n_matched = _build_rows(db_rows)
    stats.recalls_matched = n_matched

    if dry_run:
        log.info("[recall_process_map] DRY-RUN — recall 매칭 %d / 스캔 %d → 엣지 %d",
                 n_matched, len(db_rows), len(rows))
        from collections import Counter
        c = Counter(r["process_name"] for r in rows)
        for p, n in c.most_common():
            log.info("  • %s: %d", p, n)
        return stats

    if not rows:
        log.warning("[recall_process_map] 매칭 0 — datagokr_kotsa 리콜 적재 확인")
        return stats


    with get_session() as session:
        run_batched(session, _MERGE_CYPHER, rows, batch=300)
        res = session.run(
            "MATCH (:Anxg_Recall)-[e:CAUSED_BY_PROCESS]->(:Anxg_Process) "
            "WHERE e.source_type = 'datagokr_recall' RETURN count(e) AS n"
        ).single()
        stats.edges_created = int(res["n"]) if res else 0

    log.info("[recall_process_map] scanned=%d matched=%d CAUSED_BY_PROCESS=%d (candidate)",
             stats.recalls_scanned, stats.recalls_matched, stats.edges_created)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(prog="autograph.loaders.load_recall_process_map")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load(dry_run=args.dry_run)


if __name__ == "__main__":
    main()


__all__ = ["load", "LoadStats", "_build_rows", "_PROC"]
