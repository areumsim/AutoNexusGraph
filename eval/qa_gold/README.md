# qa_gold — 평가용 정답 데이터셋

[README v3.0 §6 평가 전략 / Cross-Domain QA 4단계 층화](../../README.md#6-평가-전략) 의 도메인 내 100문항 + Cross-Domain 30~50문항 + IP 30 + 외부 벤치 (Allganize) 평가셋 큐레이션 가이드. (구 README §6 — README v3.0 흡수.)

> **운영 가이드 (사용자가 새로 추가/수정·시스템 흡수 절차) 는** [docs/gold_qa_guide.md](../../docs/gold_qa_guide.md). 본 파일은 **스키마·큐레이션 빠른 가이드** SSOT.

## 파일 일람 (실측 2026-06-02)

| 파일 | 도메인 | 목표 row | 현재 row | 비고 |
|---|---|---:|---:|---|
| `gold_qa_v0.jsonl` | finance | 100 (L1 30 / L2 40 / L3 30) | **seed 30** | 코스피200+코스닥100 기반 |
| `gold_qa_auto_v0.jsonl` | auto | 100 (L1 30 / L2 40 / L3 30) | **seed 46** | NHTSA + Wikidata + DART 사업보고서 기반 |
| `gold_qa_cross_v0.jsonl` | cross_domain | 50+ (CD-L1~L4 + IP cross) | **seed 44** — level 기준 CD-L1=10 / CD-L2=8 / CD-L3=12 / CD-L4=8 + 6 row 는 IP 결합 변형 (qid prefix `CD-L3-IP`/`CD-L4-IP`, level 필드 미설정) | Bridge 한국 OEM/부품사 + ip 결합 시연 |
| `gold_qa_ip_v0.jsonl` | ip | 100 (IP-L1 30 / L2 40 / L3 30) | **seed 30** (IP-L1/L2/L3 각 10) | gold_answer 채우기는 KIPRIS/USPTO 적재 후 |
| `gold_qa_allganize_v0.example.jsonl` | finance (외부 벤치) | (stub) | 1 (예시) | **외부 큐레이터 30% 정책** — Allganize RAG-Evaluation-Dataset-KO 흡수 슬롯. 자기충족성 완화 신호 (PRD §11.6) |
| `gold_qa_v0.example.jsonl` | finance | (테스트 픽스처) | 3 | 패키지 동작 검증용 — 데이터 의미 없음 |

> 본 디렉토리의 jsonl 은 **실제 DB 조회로 검증 가능한 정답만 포함**한다. 예측·추정 정답
> 또는 모델 자가생성 정답은 큐레이션 정책 위반. `notes` 에 데이터 가정·전제 명시.

---

## 1. 스키마 (README §6 확장)

```json
{
  "qid":                   "Q0001",
  "question":              "현대모비스 2023년 매출은?",
  "question_type":         "single_entity",
                              // single_entity | multi_entity | relation
                              // | aggregation | ranking | comparison
  "complexity":            "easy",            // easy | medium | hard
  "requires_multi_hop":    false,             // README §6 (multi-hop 75%+ 목표) multi-hop 75%+ 측정
  "hop_count":             1,                 // 그래프 hop 수 (정량)
  "domain":                "finance",         // finance | auto | cross_domain
  "level":                 "L1",              // L1 | L2 | L3 (도메인 내) — 또는
                                              // CD-L1 | CD-L2 | CD-L3 | CD-L4 (cross)

  "gold_answer_text":      ["7조 1,261억원", "약 7조 1천억원"],
                                              // paraphrase 허용. EM/F1 의 max
  "gold_answer_entities":  ["현대모비스", "매출"],

  "evidence_doc_ids":      ["rcept_no_or_chunk_ids"],   // 옵션 (Recall@k)
  "evidence_corp_codes":   ["00164788"],

  "gold_cypher":           null,              // 옵션 (execution_accuracy)
  "scenario_id":           null,              // 옵션 — 시나리오 집계 키
  "tags":                  ["sql_only", "revenue"],

  // README §6 추가 메타.
  "required_stores":         ["AutoNexusGraph.SQL"],
                              // 어느 저장소가 풀이에 필요한가
                              // AutoNexusGraph.SQL / AutoNexusGraph.Graph
                              // AutoGraph.SQL / AutoGraph.Graph / AutoGraph.Vector
                              // Bridge
  "required_confidence_min": 0.7,             // 답변 근거 엣지 confidence 최소
  "main_hop_path":           ["Company"],     // 메인 홉 경로 (README §11.2 / §10.13)
  "side_hops":               [],              // 보조 홉 (Standard / Plant / Supplier ...)
  "source_citations":        [],              // 정답을 직접 뒷받침하는 chunk_id / row_id

  "is_answerable":         true,              // false 면 refusal 평가
  "notes":                 ""
}
```

### 필드 정책

- `qid` 는 prefix 로 도메인·레벨 식별: `FIN-L1-001`, `AUTO-L2-001`, `CD-L1-001`.
- `gold_answer_text` 는 paraphrase 3개 이상 권장 — `em`/`f1` 의 max 매칭.
- `gold_answer_entities` 는 Hits@k 매칭 — 정확한 표기 + alias.
- `evidence_doc_ids` 가 있으면 `recall@k` 평가 가능.
- `gold_cypher` 가 있으면 `execution_accuracy` 평가 가능 — `MATCH ... RETURN ...` 만.
- `is_answerable=false` 행은 refusal precision 측정용 — DB 에 없는 사실로 의도적으로 작성.

---

## 2. 큐레이션·운영 가이드 → [docs/gold_qa_guide.md 로 이관 (2026-06-02)]

다음 항목은 모두 [docs/gold_qa_guide.md](../../docs/gold_qa_guide.md) 가 SSOT (운영 위치):

- **레벨별 분포 권장** (L1 30% / L2 40% / L3 30%) → [gold_qa_guide.md §3](../../docs/gold_qa_guide.md) "시나리오별 추가 패턴"
- **Cross-Domain 4단계 층화** (CD-L1 80%+ / L2 70%+ / L3 50%+ / L4 40%+) → [gold_qa_guide.md §3.3 cross_domain 예시](../../docs/gold_qa_guide.md) + [README §6 Cross-Domain QA 4단계 층화](../../README.md#cross-domain-qa--4단계-층화-난이도별-목표-정답률)
- **5 큐레이션 단계** (DB 조회 → paraphrase 3개 → entity normalize → required_stores 채움 → refusal 10%) → [gold_qa_guide.md §3.1 5분 빠른 시작](../../docs/gold_qa_guide.md)
- **lint 항목 + `make validate-gold-qa`** → [gold_qa_guide.md §3.1](../../docs/gold_qa_guide.md) (`scripts/audit/validate_gold_qa.py`)
- **자동 생성 / paraphrase self-bias 주의** → [gold_qa_guide.md §2.2 자기충족성 위험](../../docs/gold_qa_guide.md)
- **파일 → 정답 추출 위치 매핑** → [gold_qa_guide.md §3.3 시나리오 A~E](../../docs/gold_qa_guide.md) (코드 예시 포함)
- **평가 실행 (`make eval-full / eval-auto / eval-cross`)** → [gold_qa_guide.md §5 시스템 흡수](../../docs/gold_qa_guide.md)
- **외부 큐레이터 30% 정책** → [gold_qa_guide.md §6](../../docs/gold_qa_guide.md) (Allganize 흡수 워크플로 포함)
- **실측 vs 정책 gap** (refusal 5.3% vs 10% / paraphrase 0.2~0.4 vs 3+) → [gold_qa_guide.md §2.1](../../docs/gold_qa_guide.md) + [system_review.md §3.6](../../docs/system_review.md)

본 README 는 **스키마 정의** (§1) + **파일 일람** 만 SSOT 로 유지. 큐레이션·운영 흐름은 docs/gold_qa_guide.md 가 단일 진입점.
