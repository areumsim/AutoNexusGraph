# Gold QA 운영 가이드 — 큐레이션·추가·수정·시스템 흡수 SSOT

> **본 문서의 위치**: gold QA 의 **운영·정책·사용자 큐레이터 워크플로** SSOT.
> 스키마·필드 정책 SSOT 는 [eval/qa_gold/README.md](../eval/qa_gold/README.md) 가 SSOT.
> 평가 매트릭스·DoD 측정은 [README §6](../README.md) + [README §10 DoD 20항](../README.md#10-dod-definition-of-done--20-항) 참조.
>
> **핵심 원칙**: gold QA 는 **LLM-as-judge 의 ground truth**. 우리가 만든 정답을 LLM 이 채점한다 — 즉 **gold QA 품질이 평가 전체의 상한선**. 추가·수정은 정책에 따라 신중히.

---

## 1. 현재 gold QA 일람 (실측 2026-06-02)

| 파일 | 도메인 | seed | 목표 | 적재 상태 | 답변 가능 여부 |
|---|---|---:|---:|---|---|
| `eval/qa_gold/gold_qa_v0.jsonl` | finance | 30 | 100 (L1 30 / L2 40 / L3 30) | ✅ DB 적재 완료 | ✅ 모든 row 답변 가능 |
| `eval/qa_gold/gold_qa_auto_v0.jsonl` | auto | 46 | 100 (L1 30 / L2 40 / L3 30) | ✅ DB 적재 완료 | ✅ 대부분 답변 가능 (`:Part` 0 노드 라 L3 일부 sparse) |
| `eval/qa_gold/gold_qa_cross_v0.jsonl` | cross_domain | 44 (CD-L1 10 / CD-L2 8 / CD-L3 12 / CD-L4 8 + 6 row는 IP 결합 변형으로 level 필드 미설정 — qid prefix 는 CD-L3-/L4- 사용) | 50+ | ✅ Bridge 적재 완료 | ⚠️ 일부 (CD-L4 시점 의존) 측정 미실시 |
| `eval/qa_gold/gold_qa_ip_v0.jsonl` | ip | 30 | 100 (IP-L1/L2/L3 30 / 40 / 30) | ⚠️ **gold_answer_text 비어있음** — KIPRIS/USPTO 적재 후 채움 | ❌ 답변 측정 불가 (정답 미정) |
| `eval/qa_gold/gold_qa_allganize_v0.example.jsonl` | finance (외부 벤치) | 1 (stub) | TBD | ❌ 미적재 | ❌ **외부 큐레이터 30% 정책 슬롯** — Allganize RAG-Evaluation-Dataset-KO 흡수 대기 |
| `eval/qa_gold/gold_qa_v0.example.jsonl` | finance (테스트 픽스처) | 3 | — | 픽스처 | 패키지 동작 검증용, 데이터 의미 없음 |

**총 적재 가능 row = 30 + 46 + 44 = 120 (finance + auto + cross)**. ip 30 은 wire-up 완료, 측정 대기.

---

## 2. 정책 — 왜 이런 운영 규칙이 있는가

### 2.1 핵심 원칙 5개

1. **DB 에서 정답 추출** — `psql` / `cypher-shell` 로 직접 조회 후 적음. **LLM 으로 정답 생성 금지** (self-bias 차단).
2. **paraphrase 3개 이상** — `gold_answer_text` 는 한국어 수기 작성 paraphrase 3개+. EM/F1 의 max 매칭.
3. **출처 명시** — `evidence_corp_codes` / `evidence_doc_ids` 가 정답을 직접 뒷받침하는 ID. 추적 가능해야 함.
4. **`is_answerable=false` 10% 포함** — DB 에 없는 사실 의도적 작성 → **refusal precision** 측정 (시스템이 모를 때 "정보 부족" 답하는가). **현재 실측 (2026-06-02)**: finance 3.3% (1/30) / auto 4.3% (2/46) / cross 9.1% (4/44) / ip 0% (0/30) — **평균 5.3%, 정책 10% 미달**. P0 보강 후보.
5. **외부 큐레이터 30%** — 시스템 작성자가 아닌 외부인 (또는 별도 팀) 이 만든 row 30% 이상 — **자기충족 위험 완화** (mental_model §5.7). **현재 비율 = 0%** — Allganize 외부 벤치 흡수 P0 권장.

### 2.2 자기충족성 위험 — 왜 외부 큐레이터가 필요한가

**문제**: 시스템 작성자가 gold QA 를 직접 만들면 "이 시스템이 잘 푸는 질문" 만 무의식적으로 선별. → 평가 점수가 시스템 실력이 아니라 **작성자의 편향**.

학술 출처: Zheng et al, "Judging LLM-as-a-Judge with MT-Bench" (arXiv:2306.05685) — judge LLM 과 candidate LLM 이 같은 family 면 자기 편향 발생. gold QA 작성자와 시스템 개발자가 같은 사람이면 더 큰 편향.

**완화 정책 (`README §11.6` + `mental_model §5.7`)**:
- 외부 큐레이터 30% (별도 팀 또는 외부 컨설팅)
- **Allganize RAG-Evaluation-Dataset-KO** 같은 공개 외부 벤치 흡수 (`gold_qa_allganize_v0.example.jsonl` 슬롯)
- LLM-as-judge 의 candidate LLM 과 judge LLM 을 **다른 family** 로 (예: Anthropic candidate vs OpenAI judge)

**현재 상태 (정직 표기)**: 외부 큐레이터 30% **미실행**. 모든 seed (120 row) 가 시스템 작성자 작성. 평가 점수는 sanity check 수준이며, 정량 증거로 활용할 때 본 한계 명시 필수.

### 2.3 정답 무결성 — 시간이 지나면 답이 바뀐다

| 정답 유형 | 안정성 | 갱신 정책 |
|---|---|---|
| **재무 수치** (매출/영업이익) | 회계연도 확정 후 안정 (보통 익년 3월) | `gold_answer_text` 에 `fiscal_year` 명시. `valid_until` 없이 영구. |
| **리콜 캠페인** | 캠페인 종결 후 안정 (NHTSA campaign_id 영구) | `nhtsa_campaign_id` 명시. |
| **자회사·임원** | 변동 잦음 (snapshot_year 필수) | `snapshot_year` 명시. "2024년 기준" 같은 timeframe 한정. |
| **특허** | publication 후 안정 (`pub_no` 영구) | `pub_no` 명시. |
| **ESG 등급** | 연 1회 갱신 | `snapshot_year` 필수. |
| **공급 관계 (`SUPPLIED_BY`)** | 변동 (계약 기간) | `valid_from/to` 명시 권장. |

→ **시간 의존 정답은 `snapshot_year` 또는 `valid_until` 필드로 timeframe 잠금**. 그렇지 않으면 1년 뒤 정답이 outdated 가 됨.

---

## 3. 사용자 큐레이터 워크플로 — 새 gold QA 추가

### 3.1 5분 빠른 시작 — 1 row 추가

```bash
# 1. 정답을 DB 에서 직접 조회
psql -h localhost -p 31011 -U autonexusgraph -d autonexusgraph -c "
  SELECT corp_code, fiscal_year, value_won
    FROM fin.financials
   WHERE corp_code='00164742' AND fiscal_year=2024
     AND item_name LIKE '%매출%';
"
# 결과: 162,664,123,456,789  (예시)

# 2. eval/qa_gold/gold_qa_v0.jsonl 에 한 줄 추가 (jsonl — 한 줄 = 한 row)
cat >> eval/qa_gold/gold_qa_v0.jsonl <<'EOF'
{"qid":"FIN-L1-031","question":"현대자동차 2024년 매출은?","question_type":"single_entity","complexity":"easy","requires_multi_hop":false,"hop_count":1,"domain":"finance","level":"L1","gold_answer_text":["162조 6,641억원","약 162조 6천억원","162,664,123,456,789원"],"gold_answer_entities":["현대자동차","매출"],"evidence_corp_codes":["00164742"],"required_stores":["AutoNexusGraph.SQL"],"required_confidence_min":0.95,"main_hop_path":["Company"],"side_hops":[],"is_answerable":true,"notes":"DART XBRL 직접 조회 (psql 2026-06-02)"}
EOF

# 3. lint 통과 검증 — 7키 + qid prefix + evidence_corp_code 실재
make validate-gold-qa
# 또는 단일 파일만
python scripts/audit/validate_gold_qa.py eval/qa_gold/gold_qa_v0.jsonl

# 4. (선택) 평가 실행 — 새 row 가 답변 가능한지
make eval-smoke   # 3 row + 새 row 빠른 검증
```

### 3.2 새 파일 추가 — 외부 큐레이터 작업 흡수

외부 큐레이터가 50 row 를 별도로 만들었을 때 시스템 흡수 절차:

```bash
# 1. 외부 파일을 staging 위치에 배치
mkdir -p eval/qa_gold/staging/
cp /tmp/external_curator_finance_50.jsonl eval/qa_gold/staging/

# 2. 스키마 lint
python scripts/audit/validate_gold_qa.py eval/qa_gold/staging/external_curator_finance_50.jsonl --no-db
# --no-db: DB 검증 건너뛰기 (외부 큐레이터가 우리 DB 접근 못한 경우)

# 3. DB 검증 — corp_code / pub_no 등이 우리 DB 에 실재하는지
python scripts/audit/validate_gold_qa.py eval/qa_gold/staging/external_curator_finance_50.jsonl
# 실재 안 하는 row 는 staging/rejected/ 로 이동 + 사유 로그

# 4. 통과한 row 만 메인 파일에 머지
# qid 충돌 검사 (FIN-L1-XXX prefix 가 기존과 안 겹치는지)
# ⚠️ 표준 routine 미구현 — 수동 jq 머지 권장:
#   jq -s 'add' eval/qa_gold/gold_qa_v0.jsonl eval/qa_gold/staging/external_curator_finance_50.jsonl > /tmp/merged.jsonl
#   # qid 충돌 검사
#   jq -r '.qid' /tmp/merged.jsonl | sort | uniq -d
#   # 없으면 교체
#   mv /tmp/merged.jsonl eval/qa_gold/gold_qa_v0.jsonl
# 향후 `scripts/audit/merge_gold_qa.py` 표준화 후보 — `docs/system_review.md` P2 백로그

# 5. 외부 비율 추적 — notes 에 "external_curator" 태그
jq -r '.[] | select(.notes | contains("external_curator")) | .qid' eval/qa_gold/gold_qa_v0.jsonl | wc -l
# → 외부 큐레이터 row 수 / 전체 row 수 비율이 30% 이상인지 확인 (PRD §11.6)

# 6. (필수) regression 평가 — 머지 후 점수 변화 확인
make eval-full
# eval/reports/finance_<ts>/summary.md 의 점수가 머지 전후 비교
# 점수 급변 (±10%p 이상) 시 외부 row 의 난이도 분포 검토
```

### 3.3 시나리오별 추가 패턴

#### A. Finance — DART XBRL 기반 수치 답변

```json
{
  "qid": "FIN-L1-032",
  "question": "삼성전자 2023년 영업이익은?",
  "question_type": "single_entity",
  "complexity": "easy",
  "domain": "finance", "level": "L1",
  "gold_answer_text": ["6조 5,670억원", "약 6.5조원"],
  "gold_answer_entities": ["삼성전자", "영업이익"],
  "evidence_corp_codes": ["00126380"],
  "required_stores": ["AutoNexusGraph.SQL"],
  "required_confidence_min": 0.95,
  "main_hop_path": ["Company"],
  "is_answerable": true,
  "notes": "DART XBRL — IFRS 별도 기준"
}
```

**검증 방법**: `psql ... SELECT value_won FROM fin.financials WHERE corp_code='00126380' AND fiscal_year=2023 AND item_name='영업이익';`

#### B. Auto — NHTSA 리콜 (campaign_id 영구)

```json
{
  "qid": "AUTO-L2-047",
  "question": "Hyundai Sonata 2024 ABS 관련 리콜 사례는?",
  "question_type": "relation",
  "complexity": "medium",
  "requires_multi_hop": true,
  "hop_count": 2,
  "domain": "auto", "level": "L2",
  "gold_answer_text": ["24V-XXX 캠페인 (ABS 모듈 결함)", "..."],
  "gold_answer_entities": ["Sonata", "2024", "ABS", "24V-XXX"],
  "required_stores": ["AutoGraph.Graph", "AutoGraph.SQL"],
  "main_hop_path": ["VehicleVariant", "Recall"],
  "side_hops": ["Component"],
  "is_answerable": true,
  "notes": "NHTSA Recalls API campaign_id=24V-XXX (replace with actual)"
}
```

#### C. Cross-Domain — Bridge 경유

```json
{
  "qid": "CD-L1-011",
  "question": "현대차가 제조한 모델의 리콜 건수와 현대차 영업이익을 같이 보여줘",
  "question_type": "aggregation",
  "complexity": "medium",
  "requires_multi_hop": true,
  "hop_count": 3,
  "domain": "cross_domain", "level": "CD-L1",
  "gold_answer_text": ["리콜 N건, 영업이익 Y억원", "..."],
  "gold_answer_entities": ["현대자동차", "리콜", "영업이익"],
  "evidence_corp_codes": ["00164742"],
  "required_stores": ["AutoGraph.Graph", "Bridge", "AutoNexusGraph.SQL"],
  "main_hop_path": ["Manufacturer", "VehicleModel", "Recall", "Company", "Financials"],
  "is_answerable": true,
  "notes": "Bridge: corp_code 00164742 ↔ manufacturer_id N (bridge.corp_entity reviewed)"
}
```

#### D. IP — 특허 적재 후 작성 (현재 gold_answer 비어있음)

```json
{
  "qid": "IP-L1-031",
  "question": "삼성전자 2023년 출원 특허 수는?",
  "question_type": "aggregation",
  "complexity": "easy",
  "domain": "ip", "level": "IP-L1",
  "gold_answer_text": [],   // KIPRIS/USPTO 적재 후 채움
  "evidence_corp_codes": ["00126380"],
  "required_stores": ["IPGraph.SQL"],
  "main_hop_path": ["Assignee", "Patent"],
  "is_answerable": true,
  "notes": "WAITING: KIPRIS_API_KEY 발급 후 ip.patents 적재 → count_patents_by_field 실측 후 gold_answer_text 채움"
}
```

**현재 모든 IP-L1~L3 30 row 가 이 상태** — wire-up 완료, 답 채움 대기.

#### E. Refusal — 답할 수 없는 질문 (10%)

```json
{
  "qid": "FIN-L1-033",
  "question": "삼성전자 2050년 매출은?",
  "question_type": "single_entity",
  "complexity": "easy",
  "domain": "finance", "level": "L1",
  "gold_answer_text": ["미래 시점 데이터 없음", "정보 부족"],
  "evidence_corp_codes": ["00126380"],
  "is_answerable": false,   // refusal 평가 대상
  "notes": "refusal precision 측정용 — 시스템이 '정보 부족' 답해야 정답"
}
```

→ 시스템이 환각으로 답하면 fail. "정보 부족" 으로 답하면 pass.

---

## 4. 기존 row 수정 — 정합·regression·version 관리

### 4.1 수정 가능한 경우

| 사유 | 수정 방법 | regression 영향 |
|---|---|---|
| **오타·표기 정정** | 직접 수정 | 없음 (의미 보존) |
| **paraphrase 추가** | `gold_answer_text` 에 append | 점수 ↑ (관대해짐) |
| **DB 갱신 후 정답 변경** | `gold_answer_text` 교체 + `notes` 에 변경 일자 | 점수 변동 가능 |
| **시간 의존 → snapshot_year 추가** | 필드 추가 + `valid_until` | 점수 변동 가능 |

### 4.2 수정 금지

| 사유 | 왜 금지 |
|---|---|
| **점수 올리려고 정답 풀이** ("부분 정답도 인정") | 자기충족 강화 — 평가 무의미 |
| **시스템이 못 풀어서 질문 자체 삭제** | survivorship bias — 어려운 질문이 사라짐 |
| **`is_answerable=true ↔ false` 토글** | refusal precision 의미 손상 |
| **`qid` 변경** (renumber) | 시계열 평가 추적 불가 |

### 4.3 version 관리

현재 모든 파일이 `_v0.jsonl` (seed). breaking change (스키마 변경, 대규모 답안 교체) 시:

```bash
# v0 → v1 마이그레이션
cp eval/qa_gold/gold_qa_v0.jsonl eval/qa_gold/gold_qa_v1.jsonl
# v1 에서 변경 수행
# v0 는 archive 로 이동
mkdir -p eval/qa_gold/_archive/v0/
mv eval/qa_gold/gold_qa_v0.jsonl eval/qa_gold/_archive/v0/
# runner / Makefile 의 파일 경로 갱신
```

**`v0 → v1` 마이그레이션은 모든 비교 평가 baseline 을 invalidate** — 직전 평가 결과 (`eval/reports/`) 를 v1 baseline 으로 재실행 필요.

### 4.4 regression 평가 — 수정 전후 비교

```bash
# 수정 전 백업
cp eval/qa_gold/gold_qa_v0.jsonl /tmp/gold_v0_before.jsonl

# 수정 후 평가
make eval-full
# eval/reports/finance_<ts>/summary.md 점수 기록

# 백업 복원 후 동일 LLM/adapter 로 재평가
cp /tmp/gold_v0_before.jsonl eval/qa_gold/gold_qa_v0.jsonl
make eval-full
# 두 summary.md 의 점수 diff 가 수정 영향
```

**점수 변동 ±5%p 이내** 가 healthy. ±10%p 이상이면 수정의 의도 vs 결과 검토.

---

## 5. 시스템 흡수 — gold QA 가 어디서 어떻게 적용되나

### 5.1 데이터 흐름 (gold → eval → DoD)

```
eval/qa_gold/*.jsonl  ─┬─→  scripts/audit/validate_gold_qa.py  ─→  lint OK?
                       │
                       ├─→  eval/runners/run_qa_eval.py  ─→
                       │     ├─ 각 row 의 question 을 run_agent() 호출
                       │     ├─ predictions.jsonl 생성 (LLM 답변)
                       │     ├─ manifest.json (cost / latency / replan)
                       │     └─ eval/metrics/* 적용 (em_f1 / hits_at_k / llm_judge / faithfulness)
                       │           ↓
                       │     eval/reports/<run-id>/summary.md
                       │           ↓
                       └─→  make audit-dod
                              ├─ summary.md 의 점수 → DoD #7 (Hybrid vs Vector +30%p)
                              ├─ DoD #8 (CD-L1 80%+ / L2 70%+ / L3 50%+ / L4 40%+)
                              ├─ DoD #9 (Exact Match 95%+)
                              ├─ DoD #10 (Faithfulness 90%+)
                              └─ eval/reports/dod_v2.2.md 트래픽라이트
```

### 5.2 어떤 메트릭이 어느 필드 사용

| gold QA 필드 | 사용 메트릭 | 어디서 |
|---|---|---|
| `gold_answer_text` (paraphrase list) | EM / F1 (max 매칭) | `eval/metrics/em_f1.py` |
| `gold_answer_entities` | Hits@k / Recall@k | `eval/metrics/hits_at_k.py:32, 42` |
| `gold_cypher` (있을 때) | execution_accuracy | `eval/metrics/execution_accuracy.py` |
| `evidence_doc_ids` (있을 때) | retrieval recall | runner 내부 |
| 전체 question + gold | LLM-as-judge | `eval/metrics/llm_judge.py` |
| `is_answerable=false` | Refusal precision | `eval/metrics/refusal.py` |
| `required_confidence_min` | Confidence-Weighted Accuracy | `eval/metrics/confidence_weighted.py` |
| `requires_multi_hop=true OR hop_count>=2` | Multi-hop subset | runner `--multi-hop-only` |

### 5.3 어댑터 매트릭스에 어떻게 들어가나

`eval/adapters/` 의 4 어댑터 (`vector_adapter` / `graph_adapter` / `hybrid_adapter` / `sql_vec_adapter`) 각각이 동일 gold QA 를 처리:

```
gold_qa_v0.jsonl (finance 30)
   ├─→ vector_adapter      → predictions_vector.jsonl     → 점수 V
   ├─→ graph_adapter       → predictions_graph.jsonl      → 점수 G
   ├─→ hybrid_adapter      → predictions_hybrid.jsonl     → 점수 H
   └─→ sql_vec_adapter     → predictions_sql_vec.jsonl    → 점수 S

PRD §10.7 = "Hybrid > Vector +30%p (multi-hop subset)" 가 thesis headline
```

축소 매트릭스 (DoD #17 (d)): 4 어댑터 × FAST tier 1종 × rerank{on/off} = **8 cells**. `make audit-eval-matrix simulation` 으로 cell wire-up 확인, `--full` 로 LLM 실측 (비용 발생).

### 5.4 gold QA 갱신 = DoD 재측정

| 변경 | DoD 영향 |
|---|---|
| 새 row 1~10 추가 | 점수 약간 변동 — `make audit-dod` 재실행 권장 |
| 새 row 30+ 추가 (큰 batch) | baseline 변동 가능 — 직전 평가 invalidate |
| 정답 수정 | EM/F1 직접 영향 — regression 평가 필수 (§4.4) |
| 새 도메인 추가 (예: pharma) | gold_qa_pharma_v0.jsonl 신설 + runner 등록 + DoD 신항목 |

→ **gold QA 변경은 시스템 평가의 baseline 변경**. PR 단위로 변경 + reviewer 가 regression 점수 확인.

---

## 6. 외부 큐레이터 30% 정책 — 실행 가이드

### 6.1 왜 30% 이상이 필요한가

- **자기충족 회피**: 시스템 작성자가 만든 row 만으로 평가하면 점수가 작성자 능력에 종속
- **다양성**: 외부인은 다른 관점·다른 질문 패턴 도입
- **재현성**: 외부 평가자가 만든 row 는 본 시스템 outside 의 ground truth

### 6.2 외부 큐레이터 후보

| 후보 | 비용 | 장점 | 단점 |
|---|---|---|---|
| **Allganize RAG-Evaluation-Dataset-KO** | 0 (공개) | finance 도메인 한국어 / 학술 표준 | 본 시스템 DB 와 정답 매핑 작업 필요 |
| **사내 별도 팀** | 인건비 | 우리 DB 직접 접근 가능 | 같은 회사 = 약한 외부성 |
| **학술 컨소시엄** (학교·연구소) | 협업 | 강한 외부성 + 출판 가능 | 일정·요구사항 협의 |
| **데이터 라벨링 회사** (예: Scale AI 한국 파트너) | 견적 | 대량 빠름 | 도메인 전문성 약함 |

### 6.3 Allganize 외부 벤치 흡수 워크플로 (wired, 2026-06-02)

```bash
# 1. Allganize 데이터셋 다운로드 (라이선스 확인 후)
git clone https://github.com/allganize/RAG-Evaluation-Dataset-KO \
  data/external/allganize-rag-kor

# 2. 우리 스키마로 변환 — ✅ 표준 변환 스크립트 (scripts/audit/convert_allganize_gold.py)
#    jsonl/json/csv 자동 감지 + difficulty→level 매핑 + external_curator/allganize_external 태그 + qid prefix ALG-FIN-NNN
make convert-allganize ARGS="\
  --src data/external/allganize-rag-kor/finance \
  --domain finance \
  --out eval/qa_gold/staging/gold_qa_allganize_v0.jsonl"

# 3. 정답이 우리 DB 에서 답변 가능한지 검증 (--no-db: 외부 row 는 corp_code 매칭 불가)
python scripts/audit/validate_gold_qa.py \
  eval/qa_gold/staging/gold_qa_allganize_v0.jsonl --no-db

# 4. 답변 가능한 row 만 흡수
mv eval/qa_gold/staging/gold_qa_allganize_v0.jsonl eval/qa_gold/

# 5. 비율 측정 — 30%+ 달성 검증 (P1-7 KPI)
make audit-external-ratio

# 6. 평가 매트릭스에 추가 — DoD #17 (d) Allganize 외부 벤치 측정
make audit-eval-matrix-full   # Allganize cell 포함
```

### 6.4 비율 측정 (audit) — 정규 KPI routine

```bash
# 한 줄 실행 — tags / notes / qid 검출 + 도메인별 breakdown.
make audit-external-ratio

# CI 게이트 (30% 미달 시 exit 1)
make audit-external-ratio ARGS="--strict --target 0.30"
```

판정 기준 (스크립트 SoT):
- `tags` 에 `external_curator` / `allganize_external` / `academic_external`
- `notes` 정규식 매칭 (`external_curator|allganize|academic`)
- `qid` prefix `ALG-` / `EXT-` / `ACA-`

산출: `data/reports/external_curator_ratio.json` + stdout 도메인별 표.

**현재 비율 (2026-06-02 실측)**: **0 / 150 = 0.0%** (모든 seed 가 시스템 작성자 작성). 도메인별 breakdown 까지 동일하게 0%. → 우선순위 작업 (`make convert-allganize` 로 Allganize 흡수 시 9~30% 로 단번에 상승).

---

## 7. 자주 막히는 지점 (FAQ — Gold QA 한정)

### Q1. 새 row 의 evidence_corp_codes 가 DB 에 없다고 lint fail

→ `master.companies` 에 해당 corp_code 가 적재 안 됨. (a) 본 시스템 범위 (코스피200+코스닥100) 밖일 가능성, (b) corp_code 8자리 leading-0 형식 오류 (예: `"126380"` 대신 `"00126380"`). 확인:

```sql
SELECT * FROM master.companies WHERE corp_code = '00126380';
```

### Q2. ip 도메인 gold_answer_text 가 비어있는데 평가 어떻게?

→ 현재 모든 ip 30 row 가 wire-up 완료 / 답 채움 대기. KIPRIS/USPTO 적재 후:

```bash
# ip 적재 완료 가정
psql ... -c "SELECT COUNT(*) FROM ip.patents WHERE jurisdiction='KR' AND filing_year=2023 AND assignee_id IN (SELECT assignee_id FROM ip.assignees WHERE name LIKE '삼성%');"
# 결과를 IP-L1-001 의 gold_answer_text 에 채움
```

→ 자동화 routine (`scripts/audit/fill_ip_gold.py` 등) 미구현. 현재는 KIPRIS/USPTO 적재 후 각 row 의 query 를 수동 실행해서 채움.

### Q3. paraphrase 가 적은데 점수가 낮음

→ `gold_answer_text` 가 1개 paraphrase 면 EM/F1 가 엄격해짐. 한국어 표기 변형 (`162조 6,641억원` / `162조 6천억원` / `162,664,123,456,789원` / `162.6조원`) 을 모두 추가. **3개+ 권장**.

### Q4. cross-domain row 의 main_hop_path 가 길어 grader 가 헷갈림

→ `main_hop_path` 는 시스템이 풀어야 할 그래프 traversal 의 핵심 노드만. side_hops (Standard / Plant 등) 는 별도. 예: CD-L4 시연 row 는 `["Assignee", "Patent", "CPCCode", "Company", "Financials", "Manufacturer", "Recall"]` 까지 길어질 수 있음 — main_hop_path 는 핵심 4~5개만 권장.

### Q5. 같은 질문이 시간 지나면 답이 바뀜 (예: 자회사 추가)

→ `snapshot_year` 명시 필수 (`§2.3 정답 무결성`). question 에도 "2024년 기준" 명시 권장.

### Q6. LLM-as-judge 점수가 EM/F1 보다 후함

→ LLM judge 는 의미 유사도 기준 — 표기 다른 paraphrase 도 인정. EM 은 정확 일치. 두 메트릭 모두 보고하고 (`summary.md` 에 둘 다), gap 이 크면 paraphrase 보강 신호.

### Q7. 외부 큐레이터 row 가 우리 DB 와 안 맞음

→ 외부 큐레이터의 회사·연도가 우리 적재 범위 (코스피200+코스닥100, NHTSA 5 OEM × 2020-2024) 밖. (a) skip + 사유 로그, (b) DB 적재 확장 (KOSDAQ 추가 등), (c) 외부 큐레이터에게 범위 가이드 사전 제공.

---

## 8. 운영 체크리스트 — 분기별 검토

```
□ gold QA seed → 목표 row 진행률 (finance 30/100, auto 46/100, cross 44/50+, ip 30/100)
□ 외부 큐레이터 비율 ≥ 30% (현재 0%)
□ Allganize 외부 벤치 흡수 완료 여부
□ ip 도메인 gold_answer 채움 (KIPRIS/USPTO 적재 후)
□ refusal row 비율 ≥ 10% (`is_answerable=false`)
□ paraphrase 평균 ≥ 3개 — **현재 실측 (2026-06-02): finance 0.23 / auto 0.41 / cross 0.00 — 정책 3.0 미달**. 즉 EM/F1 매우 엄격. P0 보강 후보
□ snapshot_year 필드 없는 시간 의존 row 식별
□ 직전 분기 대비 점수 추이 (eval/reports/ 비교)
□ 자기충족 위험 review — 어려운 질문이 빠진 건 없는지
```

---

## 9. 더 깊이

- 스키마·필드 정책 SSOT: [eval/qa_gold/README.md](../eval/qa_gold/README.md)
- 평가 매트릭스 + DoD: [README §6](../README.md) + [README §10 DoD 20항](../README.md#10-dod-definition-of-done--20-항)
- 메트릭 코드: `eval/metrics/{em_f1, hits_at_k, llm_judge, faithfulness, confidence_weighted, refusal}.py`
- 자기충족 위험 분석: [docs/mental_model.md §5.7](mental_model.md) + [docs/learning_guide.md §8.2.1](learning_guide.md)
- 외부 벤치 학술 출처: Zheng et al, "Judging LLM-as-a-Judge with MT-Bench" (arXiv:2306.05685)
