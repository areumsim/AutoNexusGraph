#!/usr/bin/env python3
"""다등급(A/B/C) confidence calibration 용 gold 생성 — graph traverse 결정적 정답.

Q-2 full A/B/C reliability 곡선의 선결(2): 답이 **서로 다른 confidence 등급 엣지**를
traverse 하면서 **EM-scorable**(결정적 graph 정답) 인 gold. auto spec gold(EM 0/56,
데이터 부재)와 달리 graph 에 존재하는 관계만 질문 → 에이전트가 답 가능.

등급별 엣지(Neo4j 실측 confidence_score):
  1.0  MANUFACTURES+AFFECTED_BY (제조사→리콜차종)   — GMR 패턴(검증됨)
  0.95 SUBSIDIARY_OF / EXECUTIVE_OF (자회사/임원회사) — GMH/GMI 패턴(검증됨)
  0.9  HAS_CEO (대표이사)
  0.65 RECALL_OF (리콜→결함 모듈)
  0.5  INSTANTIATES (공정→공정단계)

각 질문은 gold_cypher 로 결정적 정답(gold_answer_entities) 산출. EM-contains 채점.
출력: eval/qa_gold/gold_qa_multigrade_calib_v0.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from autonexusgraph.db.neo4j import get_session  # noqa: E402

# (grade, domain, 인스턴스 탐색 cypher → {q_entity, ans[]}, 질문 템플릿, gold_cypher 템플릿, n)
SPECS = [
    ("1.0", "auto",
     """MATCH (m:Anxg_Manufacturer)-[:MANUFACTURES]->(v:Anxg_VehicleModel)-[:AFFECTED_BY]->(:Anxg_Recall)
        WITH m, collect(DISTINCT v.name) AS ans WHERE size(ans) >= 3 AND size(ans) <= 18
        RETURN m.name AS q, ans LIMIT 5""",
     "{q}가 제조한 차종 중 리콜 대상이 된 모델명을 모두 답하라.", 5),
    ("0.95", "finance",
     """MATCH (p:Anxg_Company)<-[:SUBSIDIARY_OF]-(c:Anxg_Company)
        WITH p, collect(DISTINCT c.name) AS ans WHERE size(ans) >= 2 AND size(ans) <= 12
        RETURN p.name AS q, ans LIMIT 10""",
     "{q}의 자회사(계열사)를 모두 답하라.", 10),
    ("0.95b", "finance",
     """MATCH (per:Anxg_Person)-[:EXECUTIVE_OF]->(c:Anxg_Company)
        WITH per, collect(DISTINCT c.name) AS ans WHERE size(ans) >= 2 AND size(ans) <= 8
        RETURN per.name AS q, ans LIMIT 8""",
     "{q}이(가) 임원으로 재직하는 회사를 모두 답하라.", 8),
    ("0.9", "finance",
     """MATCH (c:Anxg_Company)-[:HAS_CEO]->(p:Anxg_Person)
        WITH c, collect(DISTINCT p.name) AS ans WHERE size(ans) >= 1 AND size(ans) <= 4
        RETURN c.name AS q, ans LIMIT 10""",
     "{q}의 대표이사(CEO)는 누구인가? 모두 답하라.", 10),
    ("0.65", "auto",
     """MATCH (rc:Anxg_Recall)-[:RECALL_OF]->(mod:Anxg_Module)
        WITH rc, collect(DISTINCT mod.name) AS ans WHERE size(ans) >= 1 AND size(ans) <= 5
              AND rc.source_recall_no IS NOT NULL
        RETURN rc.source_recall_no AS q, ans LIMIT 10""",
     "리콜 {q}이(가) 지목한 결함 부위(모듈)는 무엇인가? 모두 답하라.", 10),
    ("0.5", "auto",
     """MATCH (st:Anxg_ProcessStep)-[:INSTANTIATES]->(pr:Anxg_Process)
        WITH pr, collect(DISTINCT st.step_id) AS ans WHERE size(ans) >= 2 AND size(ans) <= 8
        RETURN pr.process_name_norm AS q, ans LIMIT 10""",
     "{q} 공정을 구성하는 공정 단계(step)는 무엇인가? 모두 답하라.", 8),
]


def main() -> int:
    out_path = ROOT / "eval" / "qa_gold" / "gold_qa_multigrade_calib_v0.jsonl"
    rows: list[dict] = []
    with get_session() as s:
        for grade, domain, find_cy, q_tmpl, _n in SPECS:
            conf = float(grade.rstrip("ab"))
            tag = grade.replace(".", "")
            for i, rec in enumerate(s.run(find_cy)):
                q_ent = rec["q"]
                ans = [str(a) for a in (rec["ans"] or []) if a]
                if not q_ent or len(ans) < 1:
                    continue
                rows.append({
                    "qid": f"CAL-{tag}-{i+1:02d}",
                    "question": q_tmpl.format(q=q_ent),
                    "question_type": "relation",
                    "complexity": "medium",
                    "requires_multi_hop": True,
                    "hop_count": 2 if grade == "1.0" else 1,
                    "domain": domain,
                    "tags": ["calibration", f"grade_{tag}", "graph_traverse"],
                    "gold_answer_entities": ans,
                    "gold_answer_text": ans,
                    "required_stores": ["AutoNexusGraph.Graph"] if domain == "finance"
                                       else ["AutoGraph.Graph"],
                    "required_confidence_min": conf,
                    "is_answerable": True,
                })
    out_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                        encoding="utf-8")
    import collections
    dist = collections.Counter(r["required_confidence_min"] for r in rows)
    print(f"[gen] {len(rows)} questions → {out_path.relative_to(ROOT)}")
    print("[gen] grade 분포:", dict(sorted(dist.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
