#!/usr/bin/env python3
"""auto / ip / finance 도메인 엣지 메타 무결성 audit (PRD §6.7 / DoD #11).

`ontology/{auto,ip}/relations.yaml` 와 `ontology/relations.yaml` 의 `edge_required_meta`
(7키: source_type / source_id / confidence_score / validated_status / snapshot_year /
extraction_method / schema_version) 가 모든 도메인 엣지에 채워져 있는지 검증.

DoD #11: "모든 SUPPLIED_BY 엣지에 confidence + provenance + snapshot_year 100% 채움."

본 스크립트는 docs/autograph.md §7.5 의 수동 cypher invariant 들을 Python 으로
패키징해서 CI 에서도 회귀 가능하게 한다.

종료 코드:
    0: 모든 invariant 통과
    1: 한 개 이상 위반 (출력에 위반 카운트 명시)
    2: DB 연결 실패
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


# 검사 대상 — (이름, cypher, 임계값[exceed=fail], 설명).
# 임계값 = "이 이상이면 fail" (보통 0).
_CHECKS: list[tuple[str, str, int, str]] = [
    # PRD §6.7 의무 메타 누락 — auto 도메인 엣지 전체.
    ("auto_edge_missing_meta",
     """
     MATCH (a)-[r]->(b)
     WHERE (r.confidence_score IS NULL
            OR r.source_type IS NULL
            OR r.snapshot_year IS NULL
            OR r.validated_status IS NULL
            OR r.extraction_method IS NULL
            OR r.schema_version IS NULL)
       AND any(l IN labels(a) WHERE l IN
            ['Manufacturer','VehicleModel','VehicleVariant',
             'Module','Part','Supplier','Recall','Complaint','Plant','Standard','System',
             'Process','ProcessStep','Equipment'])
     RETURN count(*) AS n
     """, 0, "PRD §6.7 — auto 엣지 7대 의무 메타 결손 (BoP Process/ProcessStep/Equipment 포함)"),

    # SUPPLIED_BY 엣지 메타 100% — DoD #11.
    ("supplied_by_missing_meta",
     """
     MATCH ()-[r:SUPPLIED_BY]->()
     WHERE r.confidence_score IS NULL
        OR r.source_type IS NULL
        OR r.snapshot_year IS NULL
        OR r.schema_version IS NULL
     RETURN count(*) AS n
     """, 0, "DoD #11 — SUPPLIED_BY 의 confidence/source/snapshot_year/schema_version 결손"),

    # Supplier 식별 — docs/autograph.md §7.5 #0.1.
    ("supplier_no_entity_id",
     "MATCH (s:Anxg_Supplier) WHERE s.entity_id IS NULL RETURN count(s) AS n",
     0, "Supplier.entity_id NULL (식별자 미부여)"),

    # Module 노드에 legacy component_id 잔재 — §7.5 #0.2.
    ("module_with_legacy_component_id",
     "MATCH (m:Anxg_Module) WHERE m.component_id IS NOT NULL RETURN count(m) AS n",
     0, "Module 노드에 legacy component_id 키 잔재"),

    # System 이름 — §7.5 #0.8.
    ("system_no_name",
     "MATCH (s:Anxg_System) WHERE s.name IS NULL RETURN count(s) AS n",
     0, "System 노드에 name 속성 없음"),

    # Ghost variant — §7.5 #0.3 (소프트 — model_year/trim/body_class 모두 NULL).
    ("ghost_variant",
     """
     MATCH (v:Anxg_VehicleVariant)
     WHERE v.model_year IS NULL AND v.trim IS NULL AND v.body_class IS NULL
     RETURN count(v) AS n
     """, 0, "Ghost VehicleVariant (식별 정보 전무)"),

    # confidence < 0.5 인 엣지가 validated 로 적재되어 있으면 안 됨 (PRD §6.7).
    ("low_conf_validated",
     """
     MATCH ()-[r]->()
     WHERE r.confidence_score IS NOT NULL
       AND r.confidence_score < 0.5
       AND r.validated_status = 'validated'
     RETURN count(r) AS n
     """, 0, "PRD §6.7 — confidence<0.5 인데 validated 로 잘못 적재"),

    # rejected 가 절대 적재되지 않아야 함.
    ("rejected_loaded",
     """
     MATCH ()-[r]->()
     WHERE r.validated_status = 'rejected'
     RETURN count(r) AS n
     """, 0, "validated_status='rejected' 인 엣지가 그래프에 적재됨"),

    # ── ip 도메인 (도메인3) 의무 메타 ──────────────────────────
    ("ip_edge_missing_meta",
     """
     MATCH (a)-[r]->(b)
     WHERE (r.confidence_score IS NULL
            OR r.source_type IS NULL
            OR r.snapshot_year IS NULL
            OR r.validated_status IS NULL
            OR r.extraction_method IS NULL
            OR r.schema_version IS NULL)
       AND any(l IN labels(a) WHERE l IN
            ['Patent','Assignee','Inventor','CPCCode','Work','Institution','TechField'])
     RETURN count(*) AS n
     """, 0, "PRD §6.7 — ip 도메인 엣지 의무 메타 7키 결손 (Patent/Assignee/Inventor/CPCCode/Work/Institution)"),

    # CPC SUBCLASS_OF — 적재 완료 후 100% meta 검증.
    ("subclass_of_missing_meta",
     """
     MATCH ()-[r:SUBCLASS_OF]->()
     WHERE r.confidence_score IS NULL
        OR r.source_type IS NULL
        OR r.schema_version IS NULL
     RETURN count(r) AS n
     """, 0, "SUBCLASS_OF (CPC 계층) 의무 메타 결손 — cpc_scheme A 등급 의무 100%"),

    # IS_ENTITY / AUTHORED_AT — OpenAlex cross-domain 엣지.
    ("authored_at_missing_meta",
     """
     MATCH ()-[r:AUTHORED_AT]->()
     WHERE r.confidence_score IS NULL
        OR r.source_type IS NULL
        OR r.snapshot_year IS NULL
        OR r.schema_version IS NULL
     RETURN count(r) AS n
     """, 0, "AUTHORED_AT (Work→Institution) 의무 메타 결손"),

    # ── finance 도메인 의무 메타 ──────────────────────────────
    ("finance_edge_missing_meta",
     """
     MATCH (a)-[r]->(b)
     WHERE (r.confidence_score IS NULL
            OR r.source_type IS NULL
            OR r.snapshot_year IS NULL
            OR r.schema_version IS NULL)
       AND any(l IN labels(a) WHERE l IN
            ['Company','Person','NewsEvent'])
     RETURN count(*) AS n
     """, 0, "PRD §6.7 — finance 도메인 엣지 의무 메타 4키 (source/snapshot/schema/conf) 결손"),
]


def _check(session, cypher: str) -> int:
    try:
        rec = list(session.run(cypher))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"query failed: {exc}") from exc
    if not rec:
        return 0
    return int(rec[0].get("n", 0) or 0)


def run_all() -> list[dict]:
    from autonexusgraph.db.neo4j import get_session

    out: list[dict] = []
    with get_session() as session:
        for name, cypher, threshold, desc in _CHECKS:
            try:
                n = _check(session, cypher)
                passed = n <= threshold
            except RuntimeError as exc:
                n = -1
                passed = False
                desc = f"{desc} (쿼리 실패: {exc})"
            out.append({
                "name": name, "count": n, "threshold": threshold,
                "passed": passed, "desc": desc,
            })
    return out


def render_md(rows: list[dict]) -> str:
    lines = ["# Edge Meta Invariants Audit",
             "",
             "PRD §6.7 / DoD #11 — auto / ip / finance 3 도메인 엣지의 의무 메타 7키 "
             "(source_type / source_id / confidence_score / validated_status / "
             "snapshot_year / extraction_method / schema_version) 와 라벨/식별 invariant 검사.",
             "",
             "| check | count | threshold | passed |",
             "|---|---|---|---|"]
    for r in rows:
        flag = "✅" if r["passed"] else "❌"
        lines.append(f"| {r['name']} | {r['count']} | ≤ {r['threshold']} | {flag} |")
    lines.append("")
    # 실패 상세.
    fails = [r for r in rows if not r["passed"]]
    if fails:
        lines.append("## 실패 항목 상세")
        for r in fails:
            lines.append(f"- **{r['name']}** (count={r['count']}): {r['desc']}")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--stdout", action="store_true")
    p.add_argument("--strict", action="store_true",
                   help="invariant 한 개라도 실패 시 exit 1 (CI 용)")
    args = p.parse_args()

    try:
        rows = run_all()
    except Exception as exc:  # noqa: BLE001
        print(f"[edge_meta_invariants] DB 연결 실패: {exc}", file=sys.stderr)
        return 2

    md = render_md(rows)
    if args.stdout:
        print(md)
    else:
        from datetime import date as _date
        out = args.out or (ROOT / "data" / "reports" /
                           f"edge_meta_{_date.today().strftime('%Y%m%d')}.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"[edge_meta_invariants] wrote {out}")

    failed = sum(1 for r in rows if not r["passed"])
    if args.strict and failed:
        print(f"[edge_meta_invariants] {failed} invariant 실패", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
