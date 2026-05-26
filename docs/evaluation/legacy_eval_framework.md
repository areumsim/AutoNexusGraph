# `eval/` — KGQA Agent v1/v2 비교 평가

평가 계획(`plan/eval_plan.md` 또는 사내 평가 SSOT)의 **Phase P1** 을 구현한 디렉토리.
v1 / v2 어댑터를 동일 잣대로 호출하고, EM / F1 / Hits@5 / Faithfulness / Refusal 5 종 deterministic metric 을 산출한다.

---

## 1. 한눈에

```bash
# 1) gold set 준비 (한번만)
PYTHONPATH=. python -m eval.tools.import_v1_regression
PYTHONPATH=. python -m eval.tools.import_v1_scenarios
PYTHONPATH=. python -m eval.tools.append_manual_seed
PYTHONPATH=. python -m eval.tools.lint_gold_set eval/qa_gold/gold_qa_v0.jsonl

# 2) baseline 실행 (50행, 약 50~60분 — 실측 ~55분, subprocess cold start + LLM 대기 포함)
PYTHONPATH=. python -m eval.runners.run_qa_eval \
    --gold eval/qa_gold/gold_qa_v0.jsonl \
    --adapters v1,v2 \
    --top-k 5 \
    --run-id baseline_$(date +%Y%m%d_%H%M%S)

# 3) 빠른 검증 (3행만)
PYTHONPATH=. python -m eval.runners.run_qa_eval \
    --gold eval/qa_gold/gold_qa_v0.jsonl --adapters v1,v2 --limit 3 \
    --run-id smoke_$(date +%H%M%S)

# 4) 임베딩(vector search) on/off 비교 — 한 번 실행으로 3-way 컬럼표
#    v1(임베딩✗) | v2(임베딩✗) | v2(임베딩○) 동일 gold·metric 비교
PYTHONPATH=. python -m eval.runners.run_qa_eval \
    --gold eval/qa_gold/gold_qa_v0.jsonl \
    --adapters v1_noemb,v2_noemb,v2 \
    --run-id compare_emb_$(date +%Y%m%d_%H%M%S)
```

산출물 위치: `eval/reports/{run_id}/summary.md` (질문별 개별 성능은 같은 폴더의 `per_question.csv`).

### 어댑터 변형 (임베딩 토글)

`--adapters` 에 아래 이름을 섞어 한 번에 비교한다 (summary.md 가 adapter 별 컬럼으로 자동 확장).

| adapter | 시스템 / graph | 임베딩 | 토글 방식 |
|---|---|---|---|
| `v1` | v1 / prod | ○ | default |
| `v1_noemb` | v1 / prod | ✗ | 질의-시점 embedding 전 경로 차단 (7종): `AGENT_SEMANTIC_ENABLED=0`, `AGENT_USE_VECTOR_NORMALIZE=0`, `AGENT_USE_VECTOR_HINTS=0`, `AGENT_USE_EVIDENCE_NODES=0`, `AGENT_USE_EDGE_VECTOR=0`, `AGENT_SEMANTIC_AUGMENT=0`, `AGENT_SIMILAR_EVIDENCE_MAX=0` → 순수 fuzzy + graph traversal |
| `v2` | v2 / v2_canary | ○ | default — Neo4j vector (node / edge / evidence) |
| `v2_noemb` | v2 / v2_canary | ✗ | `V2_DISABLE_VECTOR_SEARCH=1` → fulltext + graph traversal 만 |

> **잔차**: v1 의 `_rerank_evidence` 는 evidence ≥ 8 일 때 임베딩으로 *순서만* 바꾼다
> (검색/Hits@5 영향 없음, 별도 토글 없음).
> **주의**: v1(prod ontology)과 v2(v2_canary ontology)는 **다른 graph** + 다른 retrieval
> 아키텍처라 "물리적 동일 조건"은 불가능 — **같은 gold·metric 으로 출력 품질**을 비교한다.

> **문서 역할**: 지표 정의(§5.3)·해석(§6)·실행(§1)은 **본 README 가 단일 출처**.
> `eval/comparison_history.md` 는 **누적 실험 결과(수치 추세)만** 기록한다.

---

## 2. 디렉토리 구조

```
eval/
├── README.md                      ← 본 문서 (정의·해석·실행의 단일 출처)
├── comparison_history.md          누적 실험 결과 로그 (수치만)
├── embedding_effect_analysis.md   임베딩 효과 원인 분석 (정량)
├── adapters/
│   ├── base.py                    AgentAdapter ABC + AgentResponse + Evidence (frozen)
│   ├── _subprocess.py             subprocess 격리 helper (v1/v2 모듈 충돌 회피)
│   ├── v1_adapter.py              v1 어댑터 (PIPELINE NEO4J_NAMESPACE=prod)
│   └── v2_adapter.py              v2 어댑터 (V2_QA_NEO4J_NAMESPACE=v2_canary)
├── metrics/
│   ├── _text_norm.py              NFKC 정규화 + 한글 char-bigram 토큰화
│   ├── em_f1.py                   Exact Match / Token-F1
│   ├── hits_at_k.py               Hits@k / Recall@k (정확일치 / 부분문자열 len≥3 / difflib 0.85)
│   ├── faithfulness.py            answer ∩ evidence 토큰 overlap
│   ├── refusal.py                 refusal confusion matrix
│   ├── execution_accuracy.py      Cypher result-set 동등 비교 (실구현, P1 = 대부분 NA)
│   └── llm_judge.py               P1 = None stub (P2 활성화 예정)
├── qa_gold/
│   ├── gold_qa_v0.jsonl           N=50 seed (auto 33 + manual 17)
│   └── gold_qa_v0.backup.jsonl    (auto-fill 이전 백업)
├── tools/
│   ├── import_v1_regression.py    v1/scripts/agent_test_questions.yaml → gold
│   ├── import_v1_scenarios.py     v1/src/schema.py SCENARIOS.example → gold
│   ├── append_manual_seed.py      수기 negative 8 + 다양화 9 (= 17) append
│   ├── lint_gold_set.py           스키마 / qid 유일성 / 필수키 검증
│   └── auto_fill_gold_from_baseline.py
│                                  v1 baseline 답을 reference 로 gold 자동 채움 (P1 한정, self-bias 주의)
├── runners/
│   └── run_qa_eval.py             Layer 1 entrypoint (resume / meta.yaml / summary.md 자동 생성)
├── reports/{run_id}/              run 별 산출물 (덮어쓰기 X)
│   ├── meta.yaml                  config + git commit + LLM provider/model + sha256
│   ├── raw/{v1,v2}_responses.jsonl
│   ├── predictions.jsonl
│   ├── per_question.csv           qid × adapter × 메트릭 행
│   └── summary.md                 표 + refusal confusion + top regression
└── tests/
    ├── test_adapters_smoke.py     refusal 정규화 / 매핑 27 케이스 (mock raw)
    └── test_metrics.py            metric 산식 + 정규화 25 케이스
```

---

## 3. 사전 조건

### 3.1 Neo4j

- **prod namespace** — v1 이 추출한 entity + 51 relation 그래프 (v1 평가 시 read)
- **v2_canary namespace** — v2 가 추출한 entity + statement + 6 operational relation 그래프 (v2 평가 시 read)

확인:

```cypher
MATCH (n {namespace:'prod'})       RETURN count(n);   // 수천 단위 기대
MATCH (n {namespace:'v2_canary'})  RETURN count(n);   // 수만 단위 기대 (현재 ~83K)
```

v2_canary 가 비어있다면 → v2 추출 파이프라인을 먼저 실행해야 함.

### 3.2 LLM (Azure OpenAI)

v1 / v2 모두 Azure OpenAI 를 사용 (v2 도 내부적으로 `anthropic_client` thin shim → `client.py` 의 `AzureOpenAI` 호출).

필요 env (`.env` 또는 export):

```bash
LLM_API_URL=https://<region>.openai.azure.com/
LLM_API_KEY=<azure-key>
LLM_MODEL=<default-deployment>
LLM_MODEL_QA=<gpt-4o-deployment-or-similar>
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

### 3.3 v2 보조

- **PostgreSQL**: 불필요 (`V2_ENABLE_POSTGRES=false` 가 어댑터 기본값)
- **Redis**: 불필요 (v2 코드가 import 안 함)

---

## 4. Gold set 작성 가이드

`eval/qa_gold/gold_qa_v0.jsonl` 의 한 행 = 한 평가 케이스. 스키마:

| key | type | 설명 |
|---|---|---|
| `qid` | str | `Q0001` 형식 유일 ID |
| `source` | str | `v1_regression_single` / `v1_scenarios_example` / `manual_negative` / `manual_positive` / `auto_filled_from_v1` |
| `question` | str | 자연어 질문 |
| `question_type` | str | `single_entity` / `list` / `comparison` / `aggregation` / `refusal` |
| `complexity` | str | `easy` / `medium` / `hard` |
| `requires_multi_hop` | bool | 2-hop 이상 추론 필요 여부 |
| `scenario_id` | str | v1 SCENARIOS 의 S1~S40 또는 `compound` / `refusal` |
| `gold_answer_entities` | list[str] | Hits@5 reference (정답 entity 이름 1~N개) |
| `gold_answer_text` | str | EM/F1 reference (paraphrase 1개) |
| `gold_cypher_v1` | str / null | v1 의 정답 Cypher (P2 채움) |
| `gold_cypher_v2` | str / null | v2 는 cypher 노출 안 함 → 항상 null |
| `evidence_doc_ids` | list[str] | 정답 근거 문서 ID (v1: `{폴더}_{파일명}` 소문자) |
| `is_answerable` | bool | 백서 범위에서 답 가능 여부 (refusal 평가용) |
| `min_records` | int | 기대 결과 행 수 (참고) |
| `notes` | str | 자유 메모 |

### gold 채우기 우선순위

1. **수기 negative 8개** (필수) — `append_manual_seed.py` 의 `_NEGATIVE` 리스트 그대로 사용 가능
2. **수기 positive 시나리오 다양화 ≥ 9개** (필수) — `append_manual_seed.py` 의 `_POSITIVE` 리스트
3. **answerable 행의 `gold_answer_entities`** ≥ 25개 (권장) — Hits@5 산정 가능
4. **동일 25개의 `gold_answer_text`** (권장) — EM/F1 산정 가능
5. **`gold_cypher_v1`** (P2) — v1 의 execution_accuracy 실측 가능

답이 빈 행은 자동으로 EM/F1/Hits@5 산정에서 제외되고 `n_evaluated_*` 분모에서 빠진다.

### 자동 채우기 (P1 임시)

도메인 전문가가 채우기 전까지의 임시 옵션. `eval/tools/auto_fill_gold_from_baseline.py` 가 v1 의 high-confidence 답변(`answer_confidence ≥ 0.75`)을 reference 로 채워준다.

```bash
# v1 baseline 의 raw 응답을 reference 로 사용
PYTHONPATH=. python -m eval.tools.auto_fill_gold_from_baseline \
    --source eval/reports/<v1_baseline_run>/raw/v1_responses.jsonl \
    --gold   eval/qa_gold/gold_qa_v0.jsonl
```

⚠️ **self-bias 주의**: 이렇게 채우면 v1 EM/F1/Hits@5 는 자연스럽게 매우 높게 나옴 (자기 답이 reference 가 되므로). v2 평가는 외부 reference 와의 비교이므로 유효. summary.md 의 v1 vs v2 격차를 절대 점수로 받아들이지 말고, P2 에서 도메인 전문가 교정 필수.

---

## 5. Adapter / Metric / Runner 의 책임

### 5.1 `AgentAdapter` 계약 (`adapters/base.py`)

```python
class AgentAdapter(ABC):
    name: str         # "v1" | "v2"
    version: str
    def query(self, question: str) -> AgentResponse: ...

@dataclass(frozen=True)
class AgentResponse:
    answer: str
    refused: bool                 # 핵심 정규화 필드
    refusal_reason: str
    answer_entities: list[str]    # Hits@k 용 (entity 이름 list)
    evidence: list[Evidence]
    cypher: str | None            # v1: cypher_used. v2: 항상 None (D0-3)
    scenario_id: str
    answer_confidence: float | None
    data_completeness: str
    latency_sec: float
    tokens_used: int              # v1=0, v2=input+output
    raw: dict                     # predictions.jsonl 용 보존
```

새 adapter 추가 (예: v3, pure RAG baseline) 는 `AgentAdapter` 상속 + 정규화 함수 작성만 하면 runner 가 자동 인식한다.

### 5.2 Refusal 정규화 규칙

| 시스템 | refused=True 조건 |
|---|---|
| v1 | `warnings` 에 `db_connection_error` / `no_match` / `compound_no_records` / `grounding:*` |
| v1 | `resolution_state in {none, error}` |
| v1 | `resolution_state == similarity` 이고 `evidence == []` |
| v2 | `answer_posture == "no_answer"` |
| v2 | `answer_generation_mode in {deterministic_no_grounding, deterministic_llm_ungrounded, deterministic_llm_rejected_grounding, deterministic_llm_empty, deterministic_llm_unavailable}` |
| v2 | `answer_posture == "restricted"` 이고 `similar_evidence == []` |

**refused = False (답변 있음)** 케이스:
- v1: `pivot` (ungrounded → pivot_search 성공), `compound_partial:*`, `answer_coverage_*`
- v2: `restricted` + similar_evidence 있음, `llm_grounded`, `llm_restricted`, 정상 `deterministic`

### 5.3 Metric

| Metric | 정의 | gold 가 없을 때 |
|---|---|---|
| **EM** | NFKC + 공백/구두점 제거 + 소문자 후 **전체 문자열** 정확 일치 | NA (분모에서 제외, summary 에 `NA` 표기) |
| **Token-F1** | 공백 split + 한글 **3글자+** char-bigram 토큰 overlap | NA |
| **Hits@5** | pred 상위 5 중 gold 와 매칭 1건 이상. 매칭 = 정확일치 OR 부분문자열(짧은 쪽 길이 ≥3) OR difflib ratio ≥ 0.85 | NA |
| **Recall@5** | gold entity 중 pred 상위 5 에 매칭된 *비율* (Hits@5 의 graded 버전, 같은 매칭 규칙) | NA |
| **Faithfulness** | answer 토큰 ∩ evidence 토큰 / answer 토큰 | 0.0 (gold 무관) |
| **Refusal Precision** | refused ∧ unanswerable / refused | — |
| **Refusal Recall** | refused ∧ unanswerable / unanswerable | — |
| **False Refusal Rate** | refused ∧ answerable / answerable (over-refusal) | — |
| **Latency mean / p50 / p95** | adapter `query()` 전후 monotonic 시간 (cold start·timeout 포함) | — (전 행) |
| **Execution Accuracy** | pred/gold Cypher 의 result set 동등 | NA (runner 미주입 / gold 부재) |
| **LLM Judge** | (P2) 평가용 LLM 으로 의미적 정답 판정 | None (P1 stub) |

> 각 지표의 **의미·해석·함정**(EM≈0 의 의미, NA vs 0.000, Faithfulness 분모 효과,
> Hits@5 의 관대함, latency 와 refusal 의 결합)은 → **§6 결과 해석 가이드**.
> 진단 컬럼(`failure_mode`, `v1_resolution_state`, `n_vector_only_top5`,
> `emb_changed_entities`)은 per_question.csv 에 함께 기록된다.

### 5.4 Runner 동작

1. gold jsonl 로드 (`--limit` 로 smoke 가능)
2. 각 adapter 순회 → `adapter.query(question)` → 정규화된 AgentResponse
3. **raw/{adapter}_responses.jsonl 에 즉시 append** — 같은 qid 가 이미 있으면 **resume**으로 재호출하지 않음
4. metric 계산 (per_question + 집계)
5. 산출물:
   - `meta.yaml` — run_id, gold sha256, adapter 설정, env, git commit, LLM provider/model
   - `predictions.jsonl` — qid × adapter × 정규화된 응답 (raw 제외)
   - `per_question.csv` — qid 별 메트릭 행 (`llm_judge` 컬럼 포함, P1=빈값)
   - `summary.md` — 비교 표 (`Latency mean/p50/p95` 포함). gold 없는 EM/F1/Hits@5 는 `NA`

> **재현성 caveat**: `meta.yaml` 의 `env` 는 `os.environ ∪ 후보 .env(.env, v1/.env,
> v2/.env)` 의 키 존재 기준으로 기록한다 (`config_source` 필드 참조). v1/v2 가
> child subprocess 에서 자기 `.env` 를 로드하므로 부모 env 만으로는 불완전하기
> 때문. **secret(키/토큰/비밀번호)은 meta 에 절대 기록하지 않는다** (host/model/
> version 만). 또 repo 에 커밋이 없으면 `git.commit` 은 빈 값이라 SHA 재현은 불가 —
> 커밋 후 실행해야 git 추적이 남는다.

**raw 재사용 기법**: 어댑터 호출은 매우 비싸다 (50 행 × 2 adapter ≒ 50분). gold 만 바꾸고 재측정 하려면, 새 `run_id` 디렉토리 만들고 raw 만 복사 → runner 실행하면 즉시 metric 만 재계산.

```bash
NEW=baseline_rescore_$(date +%H%M%S)
mkdir -p eval/reports/$NEW/raw
cp eval/reports/<원본>/raw/*_responses.jsonl eval/reports/$NEW/raw/
PYTHONPATH=. python -m eval.runners.run_qa_eval \
    --gold eval/qa_gold/gold_qa_v0.jsonl --adapters v1,v2 --run-id $NEW
```

---

## 6. 결과 해석 가이드

### 6.0 지표 읽는 법 / 함정 (먼저 읽기)

지표는 독립적이지 않다. **검색(Hits@5) → 답 텍스트(EM/F1) → 근거(Faithfulness)**
순으로 영향이 전파되고, 거부(refusal) 여부가 여러 지표를 동시에 흔든다.

- **EM 이 0.000 이어도 "다 틀림"이 아니다.** EM 은 공백·구두점 제거 후 *전체
  문자열* 완전 일치라, 문장형 자연어 답변에서는 사실상 도달 불가능하다. 정답성은
  **Token-F1 / Hits@5** 로 판단하고, EM 은 "표면형이 거의 동일한가"의 보조 신호로만
  본다. (의미적 정답 판정은 P2 LLM Judge 예정.)
- **NA vs 0.000 구분.** gold 가 빈 행은 EM/F1/Hits@5 에서 제외되며, 그 adapter 의
  `n_evaluated_*` 가 0 이면 summary 표에 **`NA`** (0.000 아님). 분모를 항상 함께 보라.
- **Faithfulness 는 분모 효과에 취약.** evidence 없으면 0 이라 **거부가 많은 adapter
  는 자동으로 낮아진다** (답 품질이 아니라 답을 안 한 것). refused 비율과 함께 읽는다.
- **Hits@5 는 의도적으로 관대.** 부분문자열 매칭(짧은 쪽 길이 ≥3)을 허용하므로
  "베니트" ⊂ "코오롱베니트" 같은 부분 이름도 정답 처리된다. 절대값보다 **adapter 간
  상대 비교**로 읽는 게 안전. Recall@5 는 graded(부분 정답률) 보조 지표.
- **Latency 는 품질이 아니라 거동** (상세 §6.4): timeout·빠른 거부에 오염되므로
  False Refusal / refused / Timeouts 와 함께 본다.
- **인과 요약**: Hits@5↓ → F1/EM↓, evidence 회수 실패 → Faithfulness 영향,
  refused↑ → Faithfulness↓·latency↓ 동시 발생.

### 6.1 v1 vs v2 의 비교 차원

> 아래는 일반적 *경향* 이며, 실제 수치는 `comparison_history.md` 최신 엔트리를 본다.
> (예: 최신 `compare_4way` 에선 v2 Faithfulness 가 오히려 v1 보다 높았다 — 경향은
> 데이터마다 달라질 수 있으니 절대 단정 금지.)

| 차원 | 읽는 법 |
|---|---|
| **Hits@5 / Recall@5** | retrieval(정답 entity 회수) 품질. 가장 핵심. |
| **Faithfulness** | 답이 evidence 에 근거하는 정도. 단 거부 많으면 분모효과로 낮아짐(§6.0). |
| **Refusal Recall** | 답 없는 질문을 올바로 거부하는가 (negative 인식). |
| **False Refusal Rate** | 답 가능한데 거부 (over-refusal). **↓ 좋음**, 핵심 실패 지표. |
| **Latency mean/p95** | 거동 지표. 빠름=좋음 아님 — 거부/timeout 과 함께 읽기(§6.4). |

v2 의 over-refusal 이 높게 나오면 `deterministic_llm_empty` (LLM 호출했는데 빈 답
→ fallback) 가 자주 발생한다는 뜻일 수 있다. 설계상 의도된 보수성일 수도, prompt
튜닝 부족일 수도 있어 P2 진단 대상.

### 6.2 self-bias 의 식별

`source` 가 `auto_filled_from_v1` 인 행은 v1 답을 reference 로 채워졌으므로 v1 점수가 자동으로 부풀려진다. summary.md 에서 EM 격차가 비현실적으로 클 때 (v1 0.7+ vs v2 0.0) 거의 확실히 self-bias.

신뢰할 수 있는 비교는:
- 수기로 작성한 `source=manual_*` 행만
- 또는 P2 에서 도메인 전문가 교정 후

### 6.3 EM ≥ 0.5 변화 케이스

summary.md 의 마지막 섹션은 v1 → v2 의 EM 변화가 큰 행을 보여준다. 두 시스템의 답변 스타일 차이를 빠르게 비교할 수 있는 진단 도구.

### 6.4 Latency 읽는 법 (품질 아님, 거동)

`Latency mean / p50 / p95` 는 빠르다고 무조건 좋은 게 아니다.

- **timeout 오염**: 한 질의가 timeout 되면 그 latency 는 timeout 값(v1=120s,
  v2=300s)으로 기록되어 **p95·mean 을 끌어올린다**. p95 가 timeout 값에 가까우면
  "느린 게 아니라 일부가 죽은 것"일 수 있다.
- **빠른 거부**: refused 질의는 LLM 생성을 건너뛰어 매우 빠르다. 따라서 **latency 가
  낮은 adapter 는 답을 잘 만든 게 아니라 거부를 많이 한 것**일 수 있다 — 반드시
  `False Refusal Rate` / `refused` 비율과 함께 본다.
- **mean vs p50 vs p95**: mean 은 전반 비용 감각, p50 은 전형적 질의 속도, p95 는
  꼬리(느린 질의·timeout) 진단. mean ≫ p50 이면 소수의 느린 질의가 평균을 끈다는 뜻.

### 6.5 표 한 줄 읽기 예시 (worked example)

`compare_4way` (2026-05-20, 신 메트릭) 의 **v2 (임베딩○)** 컬럼을 문장으로 풀면:

> Hits@5 **0.222** — 정답 entity 가 채워진 27개 질문 중 약 22%에서 v2 가 상위 5
> 회수 안에 정답 entity 를 넣었다 (v1 0.556 의 절반 이하). Token-F1 **0.174** 는
> 답 텍스트 중첩도 낮음을 뜻하지만, EM **0.000** 은 "다 틀림"이 아니라 문장형 답에
> 완전일치 EM 이 부적합하다는 신호다(§6.0). Faithfulness **0.403** 으로
> 4 adapter 중 가장 높아, v2 가 내놓는 답은 evidence 근거 비율이 상대적으로 높다.
> refused **3/50**, False Refusal **0.071** — 답 가능한 42개 중 3개만 잘못 거부.
> Latency mean **15.66s** / p95 **39.71s** — p95 가 mean 의 2.5배라 소수의 느린
> 질의가 꼬리를 만든다. tokens 평균 **7548** 로 비용은 4 중 가장 크다.

같은 표에서 **v2_noemb** 와 나란히 보면(Hits@5 0.148, Faithfulness 0.343,
False Refusal 0.119, tokens 6015) **임베딩을 켰을 때 검색·근거·과소거부가 모두
개선되고 토큰 비용이 +25%** 라는 trade-off 가 한 줄로 읽힌다.

---

## 7. 알려진 한계

### Hard limits (해결 불가)

1. **v2 cypher 미노출**: v2 는 vector + 고정 cypher 템플릿 방식이라 응답에 cypher 가 없다 (D0-3 검증). → `execution_accuracy` 의 v2 측은 영구 NA. v2 코드에 cypher 노출 추가 안 하는 한.
2. **v1/v2 동일 모듈 충돌**: 둘 다 `src.agent.service` 경로 사용 → subprocess 격리 필수. cold start ~400-500ms 비용.
3. **데이터 직접 검토 금지**: CLAUDE.md 정책상 백서 원문/추출 결과 직접 read 불가. → gold_answer 수기 채우기는 사용자/도메인 전문가가 진행해야 정확.
4. **v2 Neo4j-only retrieval 적재 + vector search 통합** (2026-05-19~20): v2_canary namespace 의 embedding + retrieval **코드/인프라 상태** (성능 수치는 → `eval/comparison_history.md`):
   - Entity 노드 **100% embedding** + `entity_node_vector_index` + entity-type별 `vec_*` 9종 ONLINE — `search_graph_nodes`.
   - Relation 14,919건 **100% embedding** + **per-type vector index 23종 ONLINE** (`vec_rel_<type>_embedding`, `eval/tools/ensure_relation_vector_indexes`). Neo4j 5.18 이 untyped relationship vector index 미지원이라 type 별 생성. `search_graph_edges` 1차 path 가 23 index UNION.
   - **namespace 격리 fix**: vector index 는 schema 수준 namespace 분리 불가 → prod/v2_canary relation 이 같은 index 에 인덱싱됨. `search_graph_edges` UNION 각 branch 에 `WHERE relationship.namespace=$namespace` + `type_limit = max(limit*5, 30)` oversampling 으로 격리·recall 보장. 추가로 `v2/src/config.py:_resolve_v2_qa_namespace` fallback default 를 `"prod"` → `"v2_canary"` 로 변경 (env 누락 시 prod read trap 차단).
   - Evidence 65,426건 **100% embedding** + `evidence_vector_index` ONLINE. `search_evidence_by_vector` 가 `graph_guidance.py` main flow 에서 evidence vector hit 을 `span_scores` 에 통합. `V2_DISABLE_VECTOR_SEARCH=1` 로 위 vector 회수 전체를 끌 수 있다 (임베딩 off 비교용).
   - 미완: prod 측 v1 retrieval 가 Neo4j vector 활용하도록 코드 변경 (별도 작업, paradigm 변경 큼).

### Soft limits (P2 에서 개선 가능)

4. **gold set 빈약**: N=50 + answerable 42 중 gold 채움 비율 < 100%. → 도메인 전문가 검수 후 200~400 으로 확대.
5. **EM/F1 의 한글 형태소 미적용**: P1 은 char-bigram 만. P2 에서 mecab/kkma 도입 가능.
6. **LLM Judge 비활성**: P1 stub. P2 에서 시스템과 다른 provider (e.g., GPT-4o ↔ Claude) 로 의미적 정답 판정.
7. **subprocess 비용**: N=200+ 확장 시 worker pool 도입.

---

## 8. 트러블슈팅

| 증상 | 원인 | 대처 |
|---|---|---|
| `ModuleNotFoundError: No module named 'eval'` | PYTHONPATH 미설정 | `PYTHONPATH=. python -m eval.runners.run_qa_eval` |
| 모든 v2 응답이 `refused=True / no_answer` | v2_canary 비어있음 **또는** vector index 누락으로 IndexNotFound 가 catch 안 되어 build_guidance 전체 실패 | (1) D0-1 cypher 로 노드 수 확인 (수만 단위 기대). (2) 노드 OK 면 `SHOW INDEXES YIELD name, type, state` 로 `entity_node_vector_index` 존재 확인 — 누락 시 graph_writer 재실행. (3) `vec_rel_*_embedding` 23 종 미생성은 graceful fallback (cosine full-scan 작동) — 가속용이라면 `python -m eval.tools.ensure_relation_vector_indexes --namespace <ns>` 실행. (4) v2 의 graceful fallback (`v2/src/retrieval/neo4j_vector_search.py:_is_vector_index_missing`) 이 적용됐는지 git log 확인 |
| 모든 v2 응답이 `deterministic_llm_unavailable` | Azure LLM 키/URL 미설정 | `.env` 확인 (LLM_API_URL, LLM_API_KEY, LLM_MODEL_QA) |
| subprocess timeout | LLM 응답 지연 | adapter 의 `timeout=` 늘리거나 (v1=120, v2=180), 질문 단순화 |
| `JSONDecodeError` in stderr | v1/v2 가 비정상 stderr 출력을 stdout 으로 보냄 | `eval/reports/{run}/raw/*.jsonl` 의 `_subprocess_stderr` 확인 |
| EM/F1 모두 0.000 | gold_answer_text 가 모두 빔 | `n_evaluated_em` 셀 확인 → 0 이면 gold 채우기 필요 |
| 같은 run 재실행 시 변화 없음 | resume 동작 (raw 재사용) | 새 `--run-id` 사용 또는 `raw/*.jsonl` 삭제 |

---

## 9. 다음 단계 (P2 권장 순서)

0. **임베딩 가치 검증 (intrinsic 별칭→엔티티 recall)** — 임베딩 효과 조사 결론(`embedding_effect_analysis.md`)의 1순위 후속. 그래프 실제 별칭(`node.aliases`, 어휘적으로 먼 것)으로 vector vs fulltext recall 비교. 합성 패러프레이즈(stage4_lexgap)는 슬라이스 무효로 불가 판정. RRF(`V2_ENTITY_FUSION=rrf`)는 base gold 에서 과소거부↓ 확인 → 이 검증 후 채택 판단.
1. **gold_answer 도메인 전문가 채우기** (N=50 → 모든 answerable 행) — self-bias 제거
2. **v2 over-refusal 원인 분석** — `deterministic_llm_*` 8가지 mode 의 분류 기준 재검토
3. **LLM Judge 활성화** — 시스템과 다른 provider 모델 선정 + prompt calibration + human alignment 측정
4. **gold set 확대** N=50 → 200~400 + 도메인 전문가 검수
5. **Layer 2 (KG construction quality)** — entity / relation extraction 의 precision/recall (별도 어노테이션 워크아이템)
6. **Layer 3 diagnostic 대시보드** — both correct / v1 only / v2 only / v1 hallucinated / both wrong 6 카테고리 분류
7. **CI 통합** — `eval/qa_gold/splits/ci.jsonl` (N=50) 로 매 PR 회귀
