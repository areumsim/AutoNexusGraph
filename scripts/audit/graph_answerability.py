"""Graph-answerability audit — 멀티홉 thesis 재판정의 **선결 게이트** (read-only).

`docs/research/thesis_hybrid_routing.md` H1(a)(store-aware hybrid > vector, multi-hop)를
재측정하려면, 먼저 **그래프가 진짜 multi-hop 질문에 답할 수 있는지**(경로가 실재하는지)를
확인해야 한다. 그래야 "hybrid 저조 = thesis 틀림" 과 "hybrid 저조 = Neo4j 희소(data-blocked)"
를 분리할 수 있다 (thesis 문서 §1 원인가설 (b)).

각 후보 multi-hop 패턴의 **연결된 경로 수**(엣지 수가 아니라 chain instantiation)를 세고,
임계(`THRESHOLD`) 이상이면 answerable(gold 생성 가능), 미만이면 data-blocked 로 분류한다.

출력: `data/reports/graph_answerability_<ISO>.json`. 명령: `make audit-graph-answerability`.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

THRESHOLD = 30  # 한 패턴이 이 수 이상 distinct 답변 엔티티를 가지면 gold 생성 가능

# 후보 multi-hop 패턴 — cypher 는 distinct 답변 엔티티 수 `n` 을 반환.
# stratum 별로 thesis 가 주장하는 "graph 가 필요한" 질문 유형.
PATTERNS: list[dict] = [
    {
        "name": "fin_subsidiary_parent_executive",
        "stratum": "finance",
        "desc": "(자회사)-SUBSIDIARY_OF->(모회사)<-EXECUTIVE_OF-(임원) : 자회사 X 의 모회사 임원은?",
        "cypher": "MATCH (sub:Anxg_Company)-[:SUBSIDIARY_OF]->(p:Anxg_Company)"
                  "<-[:EXECUTIVE_OF]-(per:Anxg_Person) RETURN count(DISTINCT sub) AS n",
    },
    {
        "name": "fin_executive_company_shareholder",
        "stratum": "finance",
        "desc": "(임원)-EXECUTIVE_OF->(회사)<-MAJOR_SHAREHOLDER_OF-(대주주) : 임원 X 가 속한 회사의 대주주는?",
        "cypher": "MATCH (per:Anxg_Person)-[:EXECUTIVE_OF]->(co:Anxg_Company)"
                  "<-[:MAJOR_SHAREHOLDER_OF]-(h) RETURN count(DISTINCT co) AS n",
    },
    {
        "name": "auto_manufacturer_model_recall",
        "stratum": "auto",
        "desc": "(제조사)-MANUFACTURES->(차종)-AFFECTED_BY->(리콜) : 제조사 X 가 만든 차종 중 리콜된 것은?",
        "cypher": "MATCH (m:Anxg_Manufacturer)-[:MANUFACTURES]->(v)-[:AFFECTED_BY]->(:Anxg_Recall) "
                  "RETURN count(DISTINCT v) AS n",
    },
    {
        "name": "auto_supplier_module_chain",
        "stratum": "auto",
        "desc": "(모듈)-SUPPLIED_BY->(공급사) : 공급사 체인 (희소 예상)",
        "cypher": "MATCH (mod:Anxg_Module)-[:SUPPLIED_BY]->(:Anxg_Supplier) "
                  "RETURN count(DISTINCT mod) AS n",
    },
]


def _neo4j_counts() -> dict:
    from autonexusgraph.db.neo4j import get_session
    out: dict = {"patterns": [], "edge_density": [], "noise": {}}
    with get_session() as s:
        # 엣지 밀도 + 노이즈 정량 (LLM open-IE 싱글톤)
        rows = [dict(r) for r in s.run(
            "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY c DESC")]
        out["edge_density"] = [{"rel": r["t"], "count": r["c"]} for r in rows[:25]]
        total = len(rows)
        singletons = sum(1 for r in rows if r["c"] == 1)
        out["noise"] = {
            "distinct_rel_types": total, "singletons": singletons,
            "noise_pct": round(100 * singletons / total, 1) if total else 0,
            "total_edges": sum(r["c"] for r in rows),
        }
        # 패턴별 경로 instantiation
        for p in PATTERNS:
            try:
                n = s.run(p["cypher"]).single()["n"]
            except Exception as e:  # noqa: BLE001 — 패턴 쿼리 실패 → n=None(미측정) 기록
                n = None
                p = {**p, "error": str(e)[:120]}
            out["patterns"].append({
                "name": p["name"], "stratum": p["stratum"], "desc": p["desc"],
                "answerable_entities": n,
                "answerable": bool(n is not None and n >= THRESHOLD),
            })
    return out


def _cross_domain_bridge() -> dict:
    """cross-domain(finance↔auto) 교차 질문 가능 수 = bridge 의 manufacturer↔corp_code 링크."""
    from autonexusgraph.db.postgres import get_connection
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM anxg_bridge.corp_entity "
                    "WHERE entity_type='manufacturer' AND corp_code IS NOT NULL AND corp_code <> ''")
        n = cur.fetchone()[0]
    return {
        "name": "cross_manufacturer_corp_bridge", "stratum": "cross_domain",
        "desc": "auto 제조사 ↔ finance 회사 bridge (corp_entity) : 교차도메인 질문 선결",
        "answerable_entities": n, "answerable": bool(n >= THRESHOLD),
    }


def main() -> None:
    result = _neo4j_counts()
    result["patterns"].append(_cross_domain_bridge())
    result["threshold"] = THRESHOLD
    result["generated_at"] = datetime.now(timezone.utc).isoformat()

    # 콘솔 요약
    print(f"[graph-answerability] 엣지 {result['noise']['total_edges']}, "
          f"노이즈 {result['noise']['noise_pct']}% "
          f"({result['noise']['singletons']}/{result['noise']['distinct_rel_types']} 싱글톤)")
    by_stratum: dict[str, list[str]] = {}
    for p in result["patterns"]:
        mark = "✅" if p["answerable"] else "⊘ data-blocked"
        print(f"  {mark}  [{p['stratum']}] {p['name']}: {p['answerable_entities']} (≥{THRESHOLD}?)")
        by_stratum.setdefault(p["stratum"], []).append("answerable" if p["answerable"] else "blocked")
    answerable_strata = [k for k, v in by_stratum.items() if "answerable" in v]
    result["answerable_strata"] = answerable_strata
    print(f"=> gold 생성 가능 stratum: {answerable_strata}")

    out_dir = Path("data/reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = result["generated_at"].replace(":", "").replace("-", "").split(".")[0]
    out = out_dir / f"graph_answerability_{ts}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved → {out}")


if __name__ == "__main__":
    main()
