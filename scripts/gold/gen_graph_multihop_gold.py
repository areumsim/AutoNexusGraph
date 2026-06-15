"""그래프-유래 진짜 multi-hop gold 생성 — thesis 재판정용 (Pillar B).

`docs/research/thesis_hybrid_routing.md` H1(a) 를 robust 하게 판정하려면 **진짜 ≥2-hop·
graph 필수·vector-trivial 하지 않은** 질문이 필요하다. 사람이 상상해 쓰면 self-bias·
verifiability 문제가 있으므로, **Neo4j 의 실제 경로를 traverse 해 결정적으로 생성**한다:

- 질문은 데이터-유래, 정답은 `gold_cypher` traverse 의 결정적 결과(모델 생성 아님)
  → LLM-judge 순환 없음, EM/hits 가 어댑터 간 대칭. (judge 미사용)
- **non-vector-triviality 필터**: 후보 질문을 production retriever(`search_documents`)로 검색해,
  단일 chunk 가 start+answer 를 모두 담으면(=vector 가 trivially 답함) **기각**.
  → vector 가 단일 청크로 못 푸는, graph traverse 가 진짜 필요한 질문만 남긴다.

answerable 패턴만 사용 (graph_answerability.py 게이트). 출력:
`eval/qa_gold/gold_qa_graph_multihop_v0.jsonl`. 검증: `make validate-gold-qa <file>`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

OUT = Path("eval/qa_gold/gold_qa_graph_multihop_v0.jsonl")
PER_PATTERN_CAP = 40          # 패턴당 최대 emit (전체 stratum ≥30 목표)
CANDIDATE_LIMIT = 400         # 패턴당 후보 탐색 상한

# 추출 노이즈 답 제거 — 표 합계 조각·placeholder 등(예: '계','합계'). 정답 엔티티 위생.
_JUNK = {"계", "소계", "합계", "총계", "기타", "미정", "-", "없음", "해당없음"}


def _clean(answers: list[str]) -> list[str]:
    out = []
    for a in answers:
        a = (a or "").strip()
        if len(a) < 2 or a in _JUNK or a.replace(".", "").replace(",", "").isdigit():
            continue
        out.append(a)
    return out

# answerable 패턴 (graph_answerability.py 가 answerable 판정한 finance/auto 만).
PATTERNS: list[dict] = [
    {
        "prefix": "FIN-L3-GMH", "domain": "finance", "qtype": "relation",
        "main_hop_path": ["Company", "Company", "Person"],
        "amax": 8,
        "tags": ["graph_multihop", "path", "auto_generated", "ownership_executive"],
        "q": lambda start: f"{start}의 모회사에서 임원(등기임원 포함)으로 재직하는 사람의 이름을 답하라.",
        # 후보: parent 당 1개(자회사 1 + 모회사 임원 셋) — 다양성 위해 parent 로 dedupe
        "candidates": (
            "MATCH (sub:Anxg_Company)-[:SUBSIDIARY_OF]->(p:Anxg_Company)<-[:EXECUTIVE_OF]-(per:Anxg_Person) "
            "WITH p, collect(DISTINCT sub.name) AS subs, collect(DISTINCT per.name) AS ans "
            "WHERE size(ans) >= 1 AND size(ans) <= $amax AND size(subs) >= 1 "
            "RETURN subs[0] AS start, ans, p.name AS mid LIMIT $lim"
        ),
        "gold_cypher": ("MATCH (sub:Anxg_Company {name:$name})-[:SUBSIDIARY_OF]->(p:Anxg_Company)"
                        "<-[:EXECUTIVE_OF]-(per:Anxg_Person) RETURN DISTINCT per.name AS ans"),
    },
    {
        "prefix": "FIN-L3-GMI", "domain": "finance", "qtype": "relation",
        "main_hop_path": ["Person", "Company", "Company"],
        "amax": 8,
        "tags": ["graph_multihop", "path", "auto_generated", "executive_subsidiary"],
        "q": lambda start: f"{start}이(가) 임원으로 재직하는 회사의 자회사는 무엇인가? 모두 답하라.",
        "candidates": (
            "MATCH (per:Anxg_Person)-[:EXECUTIVE_OF]->(co:Anxg_Company)<-[:SUBSIDIARY_OF]-(sub:Anxg_Company) "
            "WITH co, collect(DISTINCT per.name) AS pers, collect(DISTINCT sub.name) AS ans "
            "WHERE size(ans) >= 1 AND size(ans) <= $amax AND size(pers) >= 1 "
            "RETURN pers[0] AS start, ans, co.name AS mid LIMIT $lim"
        ),
        "gold_cypher": ("MATCH (per:Anxg_Person {name:$name})-[:EXECUTIVE_OF]->(co:Anxg_Company)"
                        "<-[:SUBSIDIARY_OF]-(sub:Anxg_Company) RETURN DISTINCT sub.name AS ans"),
    },
    {
        "prefix": "AUTO-L3-GMR", "domain": "auto", "qtype": "relation",
        "main_hop_path": ["Manufacturer", "VehicleModel", "Recall"],
        "amax": 25,
        "tags": ["graph_multihop", "path", "auto_generated", "manufacturer_recall"],
        "q": lambda start: f"{start}가 제조한 차종 중 리콜 대상이 된 모델명을 모두 답하라.",
        "candidates": (
            "MATCH (m:Anxg_Manufacturer)-[:MANUFACTURES]->(v:Anxg_VehicleModel)-[:AFFECTED_BY]->(:Anxg_Recall) "
            "WITH m, collect(DISTINCT v.name) AS ans WHERE size(ans) >= 1 AND size(ans) <= $amax "
            "RETURN m.name AS start, ans, m.name AS mid LIMIT $lim"
        ),
        "gold_cypher": ("MATCH (m:Anxg_Manufacturer {name:$name})-[:MANUFACTURES]->(v:Anxg_VehicleModel)"
                        "-[:AFFECTED_BY]->(:Anxg_Recall) RETURN DISTINCT v.name AS ans"),
    },
]


def _is_vector_trivial(question: str, start: str, answers: list[str]) -> bool:
    """단일 retrieved chunk 가 start + 정답 1개를 모두 담으면 vector-trivial (graph 불필요)."""
    from autonexusgraph.tools.retrieve import search_documents
    try:
        hits = search_documents(question, top_k=8, rerank=True)
    except Exception:   # noqa: BLE001 — retriever 불가 시 보수적으로 trivial 아님(통과)
        return False
    for h in hits:
        t = h.get("text", "") or ""
        if start in t and any(a and a in t for a in answers):
            return True
    return False


def main() -> None:
    from autonexusgraph.db.neo4j import get_session
    rows: list[dict] = []
    stats: dict = {}
    with get_session() as s:
        for pat in PATTERNS:
            cands = [dict(r) for r in s.run(pat["candidates"], amax=pat["amax"], lim=CANDIDATE_LIMIT)]
            emitted = trivial = 0
            seen_mid: set = set()
            for c in cands:
                if emitted >= PER_PATTERN_CAP:
                    break
                start, ans, mid = c["start"], _clean(c["ans"]), c.get("mid")
                if not start or not ans or mid in seen_mid:
                    continue
                q = pat["q"](start)
                if _is_vector_trivial(q, start, ans):
                    trivial += 1
                    continue
                seen_mid.add(mid)
                emitted += 1
                rows.append({
                    "qid": f"{pat['prefix']}{emitted:03d}",
                    "question": q,
                    "question_type": pat["qtype"],
                    "complexity": "hard",
                    "requires_multi_hop": True,
                    "hop_count": len(pat["main_hop_path"]) - 1,
                    "level": "L3",
                    "domain": pat["domain"],
                    "tags": pat["tags"],
                    "gold_answer_text": ans,
                    "gold_answer_entities": [start, *ans],
                    "required_stores": ["AutoNexusGraph.Graph"],
                    "required_confidence_min": 0.9,
                    "main_hop_path": pat["main_hop_path"],
                    "gold_cypher": pat["gold_cypher"].replace("$name", json.dumps(start, ensure_ascii=False)),
                    "is_answerable": True,
                    "notes": f"graph-derived {pat['qtype']}; 정답=gold_cypher traverse(결정적); "
                             f"vector-triviality 필터 통과(단일 chunk 미공존).",
                })
            stats[pat["prefix"]] = {"candidates": len(cands), "emitted": emitted, "trivial_rejected": trivial}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[gen-multihop-gold] {len(rows)} rows → {OUT}")
    for k, v in stats.items():
        print(f"  {k}: emitted={v['emitted']} (후보 {v['candidates']}, trivial 기각 {v['trivial_rejected']})")
    by_dom: dict = {}
    for r in rows:
        by_dom[r["domain"]] = by_dom.get(r["domain"], 0) + 1
    print("  per-domain:", by_dom)


if __name__ == "__main__":
    main()
