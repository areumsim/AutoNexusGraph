# API 키 / 계정 발급 대기 목록

이 세션(2026-06-02 ~ 06-04) 중 외부 데이터 적재 진행하면서 발생한 **발급/등록 대기 키 + 계정** 정리. 발급 절차 → 시스템 반영 위치 → 다음 액션 까지.

각 항목 우선순위:
- **P0** = 즉시 필요 (현재 작업 중단)
- **P1** = 다음 세션 진입 시 필요
- **P2** = 옵션, 현재 우회 가능

---

## P0 — 즉시 필요

### 0. LLM provider 키 상태 (2026-06-05 재검증)

**현상**: `.env` 의 세 LLM provider 키 실측 재검증 — Anthropic 활성 확인:
- `ANTHROPIC_API_KEY` (sk-ant-…108자) → ✅ **활성** (claude-haiku-4-5-20251001 호출 PASS, in=12/out=4 tokens, 2026-06-05 06:28 갱신)
- `OPENAI_API_KEY` (sk-proj-…) → ⚠️ **HTTP 429 quota exceeded** (키 자체는 valid, billing 한도 초과)
- `GOOGLE_API_KEY` → ⚠️ **미검증** (`google-generativeai` SDK 미설치, `pip install google-generativeai` 후 재검증 필요)

**영향 (해소)**: Anthropic 단일 키로 `make audit-eval-matrix-full` 의 8 cells 중 Anthropic 셀 즉시 실측 가능. OpenAI/Google 셀은 별도 (billing 충전 / SDK 설치).

**코드측 준비 완료**: rerank ablation 이 `run_agent → search_documents` 까지 실제
전파되도록 수정 완료 (hybrid_rerank0 ≠ hybrid_rerank1 분리) + thesis hits@k fallback 부활.

**다음 액션**:
1. `LLM_PROVIDER=anthropic LLM_MODEL_FAST=claude-haiku-4-5-20251001 make audit-eval-matrix-full` → `eval/reports/<run>/summary.md` 첨부
2. OpenAI billing 갱신 후 `LLM_PROVIDER=openai` 셀 추가 실측
3. Google: `pip install google-generativeai` + 키 검증 → `LLM_PROVIDER=google` 셀 추가

---

### 1. GCP Service Account 키 (Google Patents BigQuery)

**용도**: `patents-public-data.patents.publications` BigQuery 쿼리 → 자동차 OEM(현대/기아/Toyota/Ford/VW/BMW/Mercedes/Tesla 등) 특허 추출 → `ip.patents`/`ip.assignees`/`ip.inventors` 적재.

**진행 상태**: Python `google-cloud-bigquery 3.41.0` 설치 완료. ADC만 부재.

**발급 절차**:
1. https://console.cloud.google.com 로그인 (Google 계정)
2. **프로젝트 생성** (예: `autonexusgraph-ipgraph`) 또는 기존 프로젝트 선택
3. 메뉴 → "APIs & Services" → "Library" → **"BigQuery API" 활성화**
4. 메뉴 → "IAM & Admin" → "Service Accounts" → **"Create Service Account"**
   - 이름: `bq-readonly` (자유)
   - Roles: `BigQuery Job User` + `BigQuery Data Viewer`
5. 만든 SA 클릭 → **Keys** 탭 → "Add Key" → "Create new key" → **JSON**
6. JSON 파일 다운로드

**시스템 반영**:
- 키 파일 위치 권장: `/root/gcp-keys/autonexusgraph-bq.json` (또는 사용자 임의 안전 위치)
- 환경 변수:
  ```bash
  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/autonexusgraph-bq.json
  ```
- 또는 `.env`에 추가 (현재 `.env`는 POSTGRES_DSN만 보유)

**발급 후 진행할 작업**:
1. `patents-public-data.patents.publications` 스키마 점검
2. 자동차 OEM 필터 쿼리 (assignee LIKE + CPC `B60*` 등)
3. `ip.patents` / `ip.assignees` / `ip.inventors` / `ip.patent_assignees` / `ip.patent_inventors` / `ip.patent_cpc` 적재
4. `ip.assignee_corp_map` bridge (Hyundai SA `assignee_name` ↔ `auto.master_manufacturers.HYUNDAI`)
5. Neo4j `:Patent` / `:Assignee` / `:Inventor` MERGE (domain=['ip'])

**무료 quota**: BigQuery 매월 1TB query free tier. 자동차 특허 quota 충분.

---

## P1 — 다음 세션 진입 시 필요

### 2. Anthropic API 키 — ✅ 활성 (2026-06-05 재발급 완료)

**용도**: `extract_defect_types_llm.py` 등 LLM 호출. 현재 `.env`의 `ANTHROPIC_API_KEY`(sk-ant-… 108자)는 **2026-06-05 06:28 갱신 후 정상** (claude-haiku-4-5-20251001 1-shot PASS).

**과거 우회 (history)**: Claude Code Agent(`general-purpose`)로 LLM 호출 대체. 이전 세션에서 :DefectType 50건 + :FailureMode 18건 추출 성공 (외부 API 비용 0).

**재발급 절차 (이후 다시 만료될 경우 참고)**:
1. https://console.anthropic.com 로그인
2. **"API Keys"** 탭 → 기존 키 상태 확인 (만료/revoked 여부)
3. 필요하면 **"Create Key"** → 새 키 발급
4. 결제 수단(credit card) + Workspace billing 확인

**시스템 반영**:
- `.env`의 `ANTHROPIC_API_KEY=sk-ant-...` 교체
- `python3 -c "from autonexusgraph.config import get_settings; print(get_settings().anthropic_api_key[:8])"` 로 검증
- `extract_defect_types_llm.py` 직접 호출 가능

**비용 추정** (자동 라벨링 1회 호출 기준): Sonnet 4-6 ~$0.20-0.40 / Haiku 4.5 ~$0.05.

### 3. KIPRIS API 키 (한국 특허청)

**용도**: 한국 OEM(현대/기아/제네시스) 특허 — 한국어 텍스트 정밀. USPTO보다 한국 시장 커버 강함.

**현재 상태**: `kipris_api_key: <None>` (`config.py` 확인). `src/autonexusgraph/ingestion/kipris_client.py` + `src/ipgraph/loaders/load_kipris.py` 코드는 ready (XML → ip.* 적재 패턴 USPTO ODP loader 재사용).

**발급 절차**:
1. http://plus.kipris.or.kr (KIPRIS PLUS) 회원가입
2. 로그인 → **"오픈API"** → **"신청"** → 사용 목적 입력
3. 승인 후 **API 키 발급** (즉시 또는 영업일 내)
4. 키 유효기간 보통 1년, 갱신 필요

**시스템 반영**:
- `.env`에 추가:
  ```
  KIPRIS_API_KEY=<발급키>
  ```
- 실행:
  ```bash
  python -m ipgraph.loaders.load_kipris  # 무인증 시엔 data/raw/ip/kipris/*.xml 미리 필요
  ```

**우선순위**: GCP BigQuery로 Hyundai/Kia USPTO 특허는 커버 가능. KIPRIS는 **한국어 정밀 + 한국 미국 미출원분** 보강.

### 4. KAMP.ai 회원 (선택, 이미 보류 결정)

**용도**: KAMP 본체 데이터셋(다이캐스팅/용접/배터리 등) CSV + 가이드북 PDF.

**현재 상태**: **이번 세션에서 보류 결정** ("본체 받지 마, DEFECT_MATCHES로 점프" 사용자 결정). KAMP 카탈로그(50건)만 `auto.kamp_catalog` 적재 완료.

**보류 이유**: 출처 익명 + 단일 라인 → 일반화 약함. NHTSA+KOTSA 자체 텍스트로 만든 :DefectType 50개가 이미 더 강함.

**향후 변경 시 발급 절차** (참고용):
1. https://www.kamp-ai.kr 회원가입 (이메일 인증, 중기부 운영, 무료)
2. 메뉴 → "AI데이터셋" → 데이터셋 상세 → 다운로드 (로그인 필수)
3. raw 위치: `data/raw/kamp/datasets/<seq>_<name>/`

---

## P2 — 옵션 (현재 우회 가능 / 미사용)

### 5. USPTO ODP API 키

**용도**: USPTO Open Data Portal REST API. PatentsView(2026-03-20 종료) 후속.

**현재 상태**: 무인증으로 일부 접근 가능, **2026-06-18 이후 mandatory** (현재 2026-06-04, 14일 남음). GCP BigQuery로 자동차 OEM USPTO 특허 커버 시 불필요.

**발급 절차** (필요 시):
1. https://account.uspto.gov 가입 (ID.me 연동 필요)
2. https://data.uspto.gov/apis/getting-started 따라 API 키 생성
3. HTTP 헤더 `X-API-KEY: <키>` 또는 `api_key` query param

**시스템 반영** (필요 시):
- `.env`에 `USPTO_API_KEY=` 추가 (현재 config.py에 필드 없음, 추가 필요)
- `src/ipgraph/loaders/load_uspto_odp.py` 는 raw JSONL 파일 기반이라 API 키 안 쓰고 동작 가능

### 6. EPO OPS API 키 (유럽 특허청)

**용도**: 유럽 OEM(VW Group/Stellantis/BMW/Mercedes/Renault) EU 특허. EU Safety Gate 리콜과 cross-link 가능.

**현재 상태**: 미설정 / 미사용. GCP BigQuery `patents-public-data`가 EPO 특허도 포함하므로 우선순위 낮음.

**발급 절차** (필요 시):
1. https://developers.epo.org 가입
2. "My Apps" → "Add a new app" → API key + secret 발급
3. Free tier: 일일 4GB / OAuth2 토큰 갱신 필요

---

## 기타: 키 불필요 / 이미 완료된 데이터 출처

이번 세션에서 적재한 출처 중 키/등록이 **불필요**한 것들 (참고):

| 출처 | 상태 |
|---|---|
| data.go.kr 15089213 (KAMP 카탈로그) | 무인증 파일 다운 — **50건 적재 완료** |
| data.go.kr 3048950 (KOTSA 자동차 리콜 CSV) | 무인증 (이전 세션 적재) — 941건 |
| NHTSA Recalls | 이전 세션 적재 — 493건 |
| NASA PCoE (Bearing/Battery/IGBT/C-MAPSS/Milling) | 무인증 S3 — **3 zip 1.4GB 다운 + 18 :FailureMode 적재 완료** |
| EU Safety Gate weekly XML | 무인증 — **972 자동차 알림 적재 완료** |
| TEI BGE-M3 (자체 호스팅) | 로컬 (localhost:8080) — 동작 중 |

## 기타: 보류/검토 게이트

| 출처 | 게이트 |
|---|---|
| data.go.kr 15089863 (구 KOTSA 리콜 OpenAPI) | **폐기** — 3048950 CSV로 대체됨 |
| data.go.kr 15155857 (수리검사) | 미검증 — 15057736(종합정보 검사, 키 자동발급)로 대체 검토 |
| car.go.kr (자동차리콜센터 직접) | **사전협의 게이트** — 사실상 보류, NHTSA + KOTSA로 대체 |
| MaintNet (RIT, arXiv 2005.12443) | **보류 결정** — GitHub 없음, 200건 sample 라벨이 결함 아닌 조치 분류 |
| AI Hub 71567 (한국 용접 데이터) | 검토 안 함 — 다음 세션 후보 |

---

## 다음 세션 진입 체크리스트

1. [ ] GCP Service Account JSON 키 발급 (P0)
2. [ ] `GOOGLE_APPLICATION_CREDENTIALS` 환경 변수 설정
3. [ ] `patents-public-data.patents.publications` BigQuery 스키마 점검
4. [ ] (선택) Anthropic API 키 재발급 — Agent 우회 가능하므로 미발급 OK
5. [ ] (선택) KIPRIS PLUS API 키 발급 — 한국 특허 정밀 보강

---

## LLM 키 발급 즉시 실행 — One-Shot Runbook (2026-06-04 정리)

다음 주 LLM 키 발급 직후 즉시 실행 가능한 명령 sequence. 키 발급 → 검증 → 평가 매트릭스 실측 → 결과 정리까지.

### Step 0 — 키 검증 (1 분, 비용 0)

`.env` 의 LLM 키 교체 후 즉시 검증. 셋 중 1개만 통과해도 OK.

```bash
# 키 검증 — model + 실 chat() 1-shot (provider 속성은 LLMClient 에 없음 → model 로 확인).
PYTHONPATH=src python3 -c "
from autonexusgraph.llm.base import get_llm_client
c = get_llm_client(role='synthesizer')
print('model:', c.model)
print(c.chat([{'role':'user','content':'say OK'}], max_tokens=5).content)
"
# 기대: 'OK' 또는 'OK.' (HTTP 200)
```

실패 시: 401/400 응답 메시지를 `data/reports/llm_key_check_<ts>.log` 로 보존 후 다른 provider 시도.

### Step 1 — 평가 매트릭스 full 실측 (15-30 분, $5-20)

S-4 P0+ 게이트의 핵심. 4 어댑터 × FAST tier 1종 × rerank{on/off} = 8 cells.

```bash
# 1-a. 사전 dry-run (LLM 호출 0, 시뮬레이션만)
make audit-eval-matrix     # simulation = 8 cells enumerate

# 1-b. full 실측 (LLM 호출 발생, 비용 추정 $5-20)
make audit-eval-matrix-full
# → eval/reports/<run>/summary.md 생성
# → eval/reports/<run>/per_cell_metrics.json 생성
```

**예산 가드**: `LLM_SESSION_HARD_LIMIT_USD=5.00` (코드 기본) — 한 세션 누적 $5 초과 시 자동 중단. 더 큰 예산 필요 시 `export LLM_SESSION_HARD_LIMIT_USD=20.00`.

**중단 시 재개**: cost_log.jsonl 기반 누적이라 재실행 시 이전 cells 결과 + 신규 cells 만 추가 실행.

### Step 2 — Confidence Calibration (5 분, LLM 호출 0)

Step 1 의 predictions.jsonl 기반 Platt scaling. Q-2 P1 항목.

```bash
make audit-calibrate
# → data/reports/calibration_<run>_<adapter>_em.{json,png}
```

**EM 데이터 부족 시** (gold answer 비어있음 등): F1 metric 우회.
```bash
make audit-calibrate ARGS="--adapter hybrid --metric f1 --em-threshold 0.5"
```

**해석**: `a ≥ 0.9~1.1` = well-calibrated, `a < 0.9` = overconfident (README §4.0 등급 0.95 → 0.88 하향 검토), `a > 1.1` = underconfident.

### Step 3 — Langfuse cloud export (선택, LANGFUSE 키 발급 시)

S-2 P0+ 게이트의 cloud export. PG 적재는 이미 ✅ — Langfuse cloud 만 미실행.

```bash
# .env 에 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST 추가
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=https://cloud.langfuse.com   # 또는 self-host

make audit-trace-full
# → 실 agent run + Langfuse dashboard 에 turn별 token/cost/replan 송신 검증
# (키 없이 PG 적재만 PASS 확인하려면: make audit-trace)
```

### Step 4 — DoD 20항 트래픽라이트 재측정 (5 분)

```bash
make audit-dod
# → eval/reports/dod_v3.0.md 갱신
# 변경 사항:
#   §10.7 Hybrid > Vector multi-hop  : ⊘ → 실측값
#   §10.8 CD-L1~L4 정답률            : ⊘ → 실측값
#   §10.9 EM 95%+                    : ⊘ → 실측값
#   §10.10 Ragas Faithfulness 90%+   : ⊘ → 실측값
#   §10.17 (d) 평가 매트릭스         : (wired, partial) → (wired) 또는 ✅
```

### Step 5 — 결과 정리 + PR

```bash
# 5-a. 측정 결과 본문 갱신 (수동 - 보고서 인용)
# README §6 "현재 측정 결과" 표 + §10 DoD 20항 표 + BACKLOG.md S-4 행

# 5-b. PR 생성
git checkout -b feat/llm-eval-matrix-measured
git add eval/reports/<run>/summary.md eval/reports/dod_v3.0.md \
        README.md BACKLOG.md data/reports/calibration_*.json
git commit -m "feat(eval): S-4 평가 매트릭스 full 실측 + Platt calibration

- 8 cells full 실측 (4 어댑터 × FAST tier × rerank{on/off})
- DoD §10.7~§10.10 / §10.17(d) ⊘ → 실측 갱신
- Platt scaling calibration: a=<>, b=<> (overconfident/calibrated 판정)
"
gh pr create --base main --title "feat(eval): S-4 P0+ 평가 매트릭스 full 실측 + Platt calibration"
```

---

## DoD unblock 매트릭스 (각 키 → unblock DoD 항)

| 키 | 즉시 unblock DoD | BACKLOG |
|---|---|---|
| **LLM 키 1개** (OpenAI / Anthropic / Google 중) | §10.7 (Hybrid +30%p), §10.8 (CD 정답률), §10.9 (EM 95%+), §10.10 (Faithfulness 90%+), §10.13 (메인 홉 효율), §10.17 (d) 평가 매트릭스 | E-1, E-2, S-4, Q-2 |
| **LANGFUSE 키** | §10.17 (b) Langfuse cloud export | S-2 (PG 경로는 이미 PASS) |
| **GCP Service Account** (BigQuery) | §10.15~10.17 — IPGraph 데이터 적재 → cross-domain CD-L4-IP | D-2 우회 (USPTO BigQuery), IP-1~6 |
| **KIPRIS_API_KEY** | (한국 특허 추가) — IP 보조축 데이터 보강 | D-2, IP-1, IP-2, IP-4, IP-5, IP-6 |
| **USPTO ODP API 키** (2026-06-18 이후 mandatory) | D-3 BigQuery 대체 시 backup 경로 | D-3 |
| **KOSIS_API_KEY** (선택) | §10 외 — 매크로 통계 보강 | D-8 |

---

## Bulk 데이터 (키 불필요 — 즉시 다운로드 가능)

`make audit-eval-matrix-full` 와 병렬 진행 가능.

```bash
# USPTO ODP bulk dataset (14일 후 API mandatory 전 대비)
# data.uspto.gov/bulkdata/datasets — wget/curl 로 7 jsonl 다운
# raw 위치: data/raw/ip/uspto_odp/*.jsonl
make load-uspto-odp   # PG ip.* 7 테이블 + Neo4j :Patent/:Assignee/:Inventor + ASSIGNED_TO/INVENTED/CLASSIFIED_AS/CITES 적재

# CPC scheme subgroup 250K bulk
# USPTO CPCSubgroupList202605.zip 또는 EPO bulk
make load-cpc -- --include-subgroups   # KIPRIS IPC subgroup 매칭 FK 통과 위해 선행 필요

# KAMP 데이터셋 CSV (data.go.kr 15089213)
# 회원가입 후 CSV 다운 → data/raw/kamp/<dataset_id>/*.csv
# (make load-kamp-process-metrics — 또는 직접 모듈 호출)
PYTHONPATH=src python3 -m autograph.loaders.process.load_kamp_process_metrics   # auto.process_metrics (corp_code 부재 = 익명, 회사 귀속 hard-check 차단)
```

---

## 본 runbook 자체의 검증 (`make` 타겟 살아있는지)

```bash
# 본 runbook 인용 타겟 grep — 0 missing 기대
make -n audit-eval-matrix audit-eval-matrix-full audit-calibrate audit-trace audit-dod \
       load-uspto-odp load-cpc 2>&1 | grep -E "^make.*Error|No rule" || echo "✓ all targets exist"
```

(위 타겟 모두 Makefile 정의됨 — `make load-kamp-process-metrics` 포함 (Makefile:719). 또는 `python3 -m autograph.loaders.process.load_kamp_process_metrics` 직접 호출.)
