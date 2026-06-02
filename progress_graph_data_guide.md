# 공정 데이터 다운로드·활용 가이드 (AutoNexusGraph ProcessGraph 축)

> **목적** — "공정 ↔ 고장유형 ↔ 결함" 회사 무관 지식층을 채우고, 회사귀속 케이스(리콜·결함신고)에 **의미 유사도로 다리**를 놓기 위한 데이터의 (1) 적합성 판정, (2) 실제 다운로드 절차, (3) 그래프 적재·활용 방법, (4) 기존 데이터와 합치는 법(요약)을 정리한다.
>
> **전제** — 이 시스템은 **GraphRAG**(Neo4j 관계 / PostgreSQL 수치·메타 / pgvector 텍스트)다. **이미지로 CV 모델을 학습하는 파이프라인이 아니다.** 따라서 "자동차 제조 데이터인가"가 아니라 **"세 저장소에 적재 가능한가 + A/B/C 등급 정책과 PERFORMED_AT 회사귀속 hard-check를 통과하는가"** 가 적합성 기준이다.

> ⚠️ **링크 검증 주의 (2026-06 기준)** — data.go.kr 데이터셋은 **폐기·이관·사전협의 게이트**가 잦다. 본문 ID는 적재 전에 **반드시 해당 페이지를 직접 열어 상태(파일다운 / OpenAPI 자동발급 / 사전협의 / 폐기)를 확인**할 것. 본 문서에서 확인한 상태:
> - **KAMP 15089213** — ✅ 라이브, 파일데이터 로그인 없이 다운 가능.
> - **자동차 리콜 15089863** — ⚠️ 데이터셋은 존재하나 OpenAPI가 **car.go.kr 사전협의 게이트**를 전제 → 사전협의가 막혀 있으면 **사실상 사용 불가**. Layer 2 리콜은 **NHTSA 우선** + car.go.kr 웹 열람(ToS 확인)으로 대체.
> - **수리검사 15155857** — ❓ **본 문서에서 재검증 못 함**(README 출처 ID). KOTSA 검사 데이터는 **다른 ID**로 다수 존재(예: 15057736 자동차 종합정보 검사정보 OpenAPI, 인증키 자동발급). 사용 전 포털에서 ID 확인.
> - **NASA PCoE / CWRU / MaintNet / SECOM(UCI 179) / AI4I(UCI 601)** — 실 검색 결과 라이브 URL 확인됨(한국 ID보다 신뢰도 높음). 그래도 클릭 검증 권장.

---

## 0. 적합성 판정 (기존 리스트 + 신규) — "이거 의미 있나" 검토

판정 기호: **◎ 핵심** / **○ 유효** / **△ 제한적(taxonomy 시드 정도)** / **✗ 부적합(이 시스템엔 안 맞음)**

### 0.1 이전에 정리했던 리스트 재검토

| 데이터 | 형태 | 회사귀속 | 그래프 적재 경로 | 판정 | 이유 |
|---|---|---|---|:--:|---|
| **Bosch Production Line Performance** | 익명 표(센서) | ✗ (라인/스테이션 익명) | 없음(굳이 ProcessStep 통계 패턴 검증) | △ | 보쉬지만 완전 익명화 → 회사귀속 불가, 그래프 노드/엣지로 안 떨어짐. CV도 아님 |
| **Welding Defect Object Detection/Segmentation** | 이미지 | ✗ | 없음 | ✗ | CV 학습용. 결함 클래스명만 `:DefectType` 시드로 미미하게 |
| **Severstal Steel Defect** | 이미지 | ✗ | 없음 | ✗ | 동일. 강판 결함 클래스명 정도 |
| **NEU / GC10-DET** | 이미지 | ✗ | 없음 | ✗ | 동일 |
| **Robotic Operations Performance** | 익명 합성 표 | ✗ | 없음 | △ | 익명·합성 → 그래프 기여 거의 없음 |
| **Predicting Manufacturing Defects** | 합성 표 | ✗ | 없음 | △ | 합성. 패턴 검증용 |
| **AI4I 2020 (UCI/Kaggle)** | 합성 표 | ✗ | `:Equipment` 고장모드 5종 시드 | ○ | 고장유형 taxonomy(공구마모·방열·전력·과부하·랜덤)가 `:FailureMode` 시드로 소소하게 유효. CC BY 4.0 |
| **AI Hub 부품 품질 검사(자동차) 578** | 이미지 | ✗(원천) | **이미 component taxonomy 22개로 사용 중** | ○ | 이미지 자체는 안 쓰되 부품 분류 시드로 이미 시스템에 반영됨 |
| **AI Hub 차량 외관 영상 554** | 이미지 | ✗ | 14개 파트명 매핑 정도 | △ | 외관 검출용 CV. 파트 taxonomy 보조 |
| **AI Hub 이송장치 열화 예지보전 71567** | 센서+열화상 멀티모달 | ✗(비귀속) | ProcessStep/Equipment 통계 + vec.chunks | ○ | PdM. README에 grade B(익명)로 이미 명시. Layer 1에 적합 |
| **AI Hub 스마트 제조 안전 감시 71679** | CCTV/열화상 | ✗ | 없음 | ✗ | 사고·침입·화재 감시 → 공정/고장과 무관 |
| **AI Hub 선박 도장 품질 71447** | 이미지 | ✗ | 도장 `:DefectType` 시드 | △ | 도장 결함 분류명 참고. 이미지라 적재 X |
| **AI Hub 부품 품질 검사(선박) 579** | 이미지 | ✗ | 용접 `:DefectType` 시드 | △ | 용접 결함 분류명 참고 |
| **data.go.kr 15135578 (AI허브 목록)** | 메타 CSV | — | 탐색 카탈로그 | ○ | 데이터 탐색용 보조 |
| **MVTec AD** | 이미지 | ✗ | 없음 | ✗ | CV 이상탐지 + **CC BY-NC-SA(상업 불가)** → 이중으로 부적합 |
| **Intel 용접 audio/video 논문** | 오디오/영상 | ✗ | 용접 결함 taxonomy 참고 | △ | CV/오디오. 그래프 직접 적재 X |
| **Bosch Kaggle 논문(1701.00705)** | 논문 | — | — | △ | 데이터 아님. 참고문헌 |

**핵심 결론** — 이전 리스트에서 **그래프에 실제로 의미 있는 건 소수**다.
- 이미지·CV 벤치마크(Welding/Severstal/NEU/MVTec/차량외관/안전감시/Intel)는 **이 GraphRAG에 직접 안 맞는다.** 굳이 쓰면 "결함 클래스명"을 `:DefectType` taxonomy 시드로 긁는 정도이고, 이미지 픽셀 자체는 들어갈 자리가 없다.
- 익명 표/합성(Bosch/AI4I/Robotic/Predicting)은 **회사귀속 불가**하고 그래프 기여가 작다. AI4I만 고장모드 5종 시드로 ○.
- **이미 시스템에 반영된 것**: AI Hub 578(component taxonomy 22), 이송장치 71567(grade B).

→ 이미지 셋들은 과감히 빼고, **아래 §0.2의 회사 무관 "고장/공정 지식" 텍스트·구조 데이터**로 무게를 옮기는 게 맞다.

### 0.2 신규 추천 (이번에 추가로 찾은 것) — Layer별

| 데이터 | 층 | 형태 | 라이선스 | 판정 |
|---|---|---|---|:--:|
| **KAMP 제조AI 데이터셋 (15089213)** | L1 | 공정별 표+가이드북 | 공공 | ◎ |
| **MaintNet** | L1 | 정비 로그북 텍스트 | CC BY 4.0 | ◎ |
| **NASA PCoE (C-MAPSS·bearing·battery)** | L1 | run-to-failure 시계열 | 공공(US Gov) | ○ |
| **CWRU / Paderborn 베어링** | L1 | 진동 시계열 | 오픈 | ○ |
| **SECOM (UCI)** | L1 | 공정 센서 표(yield) | CC BY 4.0 | ○ |
| **AI Hub 용접 AI 학습 데이터(창원)** | L1 | 용접 데이터 | 공공(승인) | △~○ |
| **한국 자동차 리콜 (15089863)** | L2 | 회사귀속 리콜 표 | 공공 | ⚠️ | 데이터셋 존재하나 OpenAPI가 car.go.kr **사전협의 게이트** → 사실상 보류. NHTSA로 대체 |
| **KOTSA 검사 데이터 (15057736 계열)** | L2 | 검사 표(OpenAPI/CSV) | 공공 | ○ | 15155857(수리검사)은 미검증. 15057736(종합정보 검사, 키 자동발급) + EV 배터리셀 전압 CSV 등으로 대체 검토 |
| **EU Safety Gate (RAPEX)** | L2 | 회사귀속 리콜 | 공공(EU) | ○ |

---

## 1. 3층 그래프 설계 (요약)

기존 온톨로지(`:Process`/`:ProcessStep`/`:Equipment`/`:Material` + `CAUSED_BY_PROCESS`)에 노드 2종·엣지 3종만 추가한다. 코어 변경 ≈ 0(§10.12 유지).

```
[Layer 1 · 회사무관 지식, grade C/B]
(:ProcessStep)-[:CAN_CAUSE]->(:FailureMode)-[:MANIFESTS_AS]->(:DefectType)
(:Equipment)-[:SUBJECT_TO]->(:FailureMode)

[Layer 2 · 회사귀속 실제 케이스, grade A] (이미 보유 + 보강)
(:Manufacturer)-[:RECALL_OF]->(:Recall {component_text})
(:VehicleModel)-[:REPORTED_IN]->(:Complaint)

[Bridge · 계산된 유사도 엣지] (BGE-M3 코사인)
(:Recall)-[:DEFECT_MATCHES {cos_sim, confidence}]->(:DefectType)
(:Recall)-[:SIMILAR_CASE_OF {cos_sim}]->(:Recall)
```

이렇게 하면 "프레스 공정 크랙 결함이 어떻게 나타나나?" → 회사무관 인과 사슬 + "유사 실제 케이스: NHTSA 25V-xxx(Ford, sim 0.83), 한국 리콜 xxx" 를 함께 반환한다. **"X사가 이 공정을 수행한다"는 주장이 아니라** "이 공정은 이런 고장을 유발할 수 있다(C/B 후보) + 그 고장과 의미가 가까운 실제 회사 케이스는 이것(측정된 유사도)"이라서 PERFORMED_AT hard-check와 충돌하지 않는다.

---

## 2. 데이터별 상세 — 다운로드 / 활용 / 합치기

> 각 항목 공통: **다운로드(아주 상세) → 활용(아주 상세) → 기존 데이터와 합치기(요약)**.
> 적재 위치 약어: **PG** = PostgreSQL, **N4J** = Neo4j, **VEC** = vec.chunks(pgvector).

---

### 2.1 ◎ KAMP 제조AI 데이터셋 — Layer 1 핵심

공정별 정상/불량 데이터 + 가이드북. `:ProcessStep` 고장통계 + `:FailureMode` 시드 + VEC.

#### 다운로드 (두 경로, 무인증 우선)

**경로 A — 공공데이터포털 파일 다운(로그인 불필요, 가장 간단)**
1. 접속: `https://www.data.go.kr/data/15089213/fileData.do`
2. 상단 "파일데이터" 탭 → "다운로드" 버튼. 회원가입·키 없이 즉시 받아진다(이 목록은 KAMP 개방 24종 데이터셋의 **메타·링크 카탈로그**).
3. 받은 CSV에서 각 데이터셋의 KAMP URL을 추출 → 실제 데이터는 경로 B에서 받는다.

**경로 B — KAMP 포털 본체(데이터셋 실파일)**
1. 가입: `https://www.kamp-ai.kr/` → 회원가입(이메일 인증). 중소벤처기업부 운영, 무료.
2. 메뉴: `제조AI데이터셋` → 공정/설비별 목록(예: CNC 가공, 사출성형, 용해, 프레스, 용접, 생산계획 최적화 등).
3. 각 데이터셋 상세에서 **데이터 CSV + 가이드북(PDF)** 다운. 데이터셋마다 정상/불량 라벨·센서 컬럼 구성이 다르므로 가이드북을 반드시 같이 받는다.

```bash
# 작업 폴더 예시
mkdir -p data/raw/kamp/{cnc,injection,press,welding,melting}
# data.go.kr 카탈로그(메타) 먼저
curl -L -o data/raw/kamp/_catalog_15089213.csv \
  "https://www.data.go.kr/download/15089213/fileData.do"   # 실제 다운 링크는 페이지 버튼에서 확인
# 실데이터는 KAMP 포털 로그인 후 브라우저 다운(직접 링크는 세션 필요)
```

- **형식**: 데이터셋별 CSV(센서/품질 라벨), 가이드북 PDF
- **라이선스**: 공공(중기부/KAMP). 파일데이터 자체는 로그인 없이 이용 가능
- **등급**: **B (익명)** — 회사귀속 불가. 정적 등급표 SOURCE_TO_GRADE에 `kamp_manufacturing = B(0.80)` 추가

#### 활용 (아주 상세)

1. **`:FailureMode` / `:DefectType` 노드 시드 (N4J)**
   - 각 KAMP 공정 데이터셋의 불량 라벨(예: 사출 "미성형/플래시/버", 용해 "탕도막힘", 프레스 "크랙/주름")을 추출해 노드화.
   - `:FailureMode {name, name_en, process_hint, source_type:'kamp_manufacturing', grade:'B'}`
2. **`(:ProcessStep)-[:CAN_CAUSE]->(:FailureMode)` 엣지 (N4J)**
   - 산단공 공정사전(`:Process`/`:ProcessStep`, 이미 보유)과 KAMP 공정명을 매핑(KO-EN 사전 + 토큰 overlap). 매핑된 ProcessStep → FailureMode로 CAN_CAUSE 생성.
   - 7키 메타: `source_type='kamp_manufacturing'`, `source_id='kamp:<dataset_id>#<row>'`, `confidence_score=0.80`, `validated_status='candidate'`, `snapshot_year=<연도>`, `extraction_method='deterministic'`, `schema_version='vX'`.
3. **ProcessStep 통계 속성 (PG → N4J 속성)**
   - 불량률·주요 센서 분포(평균/표준편차)를 `auto.process_metrics`(회사 비귀속)에 적재 후, `:ProcessStep` 노드 속성으로 요약 부여(`defect_rate_mean`, `key_signal_stats`).
4. **가이드북 텍스트 (VEC)**
   - 가이드북 PDF → 청크 → BGE-M3 임베딩 → `vec.chunks(source='kamp_guidebook', process_hint=...)`. "이 공정 불량은 보통 어떤 원인?" 류 질의의 의미 검색 근거.

#### 합치기 (요약)
- 정적 등급표에 `kamp_manufacturing=B` 한 줄. 공정명은 산단공 `:Process` 사전에 정규화해 붙임. 회사귀속 엣지(PERFORMED_AT) 금지(익명) — `load_performed_at.py` allowlist가 자동 차단.

---

### 2.2 ◎ MaintNet — Layer 1 텍스트(자동차 정비 로그북)

실제 고장 서술 → `:FailureMode` 추출(P3) + VEC. 다리(DEFECT_MATCHES)의 의미 밀도를 끌어올린다. **CC BY 4.0**.

#### 다운로드 (아주 상세)
1. 논문/라이브러리 진입: arXiv `https://arxiv.org/abs/2005.12443` (MaintNet) → 본문의 프로젝트 링크/GitHub 저장소로 이동.
2. 저장소에서 **aviation / automotive / facility** 3개 도메인 로그북 CSV + 도구(전처리·클러스터링·약어/용어집) 클론.
```bash
mkdir -p data/raw/maintnet
# 예시 (실제 org/repo 이름은 라이브러리 페이지에서 확인)
git clone https://github.com/<maintnet-repo>/MaintNet.git data/raw/maintnet
ls data/raw/maintnet   # automotive/*.csv, aviation/*.csv, facilities/*.csv, termbank/*
```
- **형식**: 자유 텍스트 로그북 CSV(정비 서술 + 라벨/클러스터), 약어·용어집 리스트
- **특징**: 정비 기록이 약 36개 정비 이슈 유형으로 클러스터링됨 → `:FailureMode` 그룹 시드로 즉시 활용
- **라이선스**: CC BY 4.0 (출처 표기). `_license.py`에 `maintnet = cc_by_4_0` 등록

#### 활용 (아주 상세)
1. **`:FailureMode` 추출 (P3 LLM, 대상 한정)**
   - automotive 로그북 텍스트에서 "부위 + 증상 + 원인" 패턴을 schema-aware로 추출 → `:FailureMode {name, symptom, component_hint}`. P4 cross-validate 후 candidate.
   - 36개 클러스터를 상위 `:FailureModeGroup`으로 두고 추출 결과를 그 하위로 매단다(검색 시 카테고리 navigation).
2. **VEC 적재**
   - 로그북 청크 → BGE-M3 → `vec.chunks(source='maintnet_auto')`. 약어/용어집은 정규화 사전으로 써서 임베딩 품질 향상(비표준 표기·약어 보정).
3. **다리 의미 밀도 ↑**
   - MaintNet automotive 텍스트가 풍부해질수록 recall `component_text` ↔ `:FailureMode` 코사인이 더 정확해진다 → DEFECT_MATCHES 신뢰도 상승.

#### 합치기 (요약)
- `_license.py`에 `maintnet=cc_by_4_0` 등록. P3 추출은 기존 `run_p3` 파이프라인 재사용(대상만 maintnet으로 한정). 노드는 grade C candidate.

---

### 2.3 ○ NASA PCoE (C-MAPSS / Bearing / Battery / IGBT / Milling) — Equipment 고장모드

raw 시계열은 그래프에 안 넣고, **고장모드 taxonomy + 열화 패턴**만 `:Equipment`/`:FailureMode`에 반영.

#### 다운로드 (아주 상세)
1. 저장소(둘 중 하나):
   - NASA 공식: `https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/`
   - PHM Society 미러: `https://data.phmsociety.org/nasa/`
2. C-MAPSS 터보팬 직접 다운(예시 링크):
```bash
mkdir -p data/raw/nasa_pcoe
curl -L -o data/raw/nasa_pcoe/cmapss.zip \
  "https://phm-datasets.s3.amazonaws.com/NASA/6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip"
unzip data/raw/nasa_pcoe/cmapss.zip -d data/raw/nasa_pcoe/cmapss
# 베어링/배터리/IGBT/밀링 셋은 저장소 목록에서 동일 방식으로 zip 다운
```
- **형식**: 텍스트/zip(센서 채널 시계열 + readme). C-MAPSS는 FD001~FD004 4개 서브셋(운영조건·고장모드 조합)
- **라이선스**: 공공(US Gov). 사용 시 NASA PCoE + 원저자 인용 요청
- **등급**: A(공식)이나 **회사 비귀속**(항공 엔진/일반 설비)

#### 활용 (아주 상세)
1. **`:Equipment` 고장모드 taxonomy (N4J)** — raw 신호 대신 readme/문헌의 고장모드만 노드화.
   - C-MAPSS: HPC degradation, Fan degradation 등 → `:FailureMode`를 `:Equipment {turbofan/회전기계}`에 `SUBJECT_TO`로 연결.
   - Bearing/Battery 셋의 고장모드도 동일하게 회전기계·배터리 Equipment에 매핑.
2. **`:ProcessStep` 보강** — 자동차 공정 중 회전기계(가공·이송·펌프) 관련 ProcessStep에 일반 고장모드(베어링 마모·열화)를 연결해 검색 커버 확장.
3. (선택) RUL/열화 패턴은 PG `auto.equipment_failure_patterns`에 요약 통계로만 저장(노드 속성 참조용). 시계열 원본은 그래프 밖.

#### 합치기 (요약)
- Equipment taxonomy 시드라 기여는 작지만, "이 설비는 어떤 식으로 고장나나" 검색 커버를 넓힘. 회사귀속 금지.

---

### 2.4 ○ CWRU / Paderborn 베어링 — 베어링 고장모드

#### 다운로드 (아주 상세)
- **CWRU**: `https://engineering.case.edu/bearingdatacenter/download-data-file`
  - 정상(Normal Baseline) / 드라이브엔드(DE) / 팬엔드(FE) 결함, 12kHz·48kHz. 내륜·외륜·볼에 EDM으로 결함 가공.
  - 원본은 `.mat`. 정제본: Zenodo `https://doi.org/10.5281/zenodo.10987113`(`.npz`), Kaggle `astrollama/cwru-...`.
```bash
mkdir -p data/raw/cwru
# Zenodo 정제본(.npz) 또는 case.edu .mat 다운 후 보관
```
- **Paderborn(PU)**: 베어링 결함 벤치마크(또 다른 표준). 대학 페이지에서 신청/다운.
- **라이선스**: 오픈(연구용, 출처 표기)

#### 활용 (아주 상세)
1. **`:FailureMode {내륜결함/외륜결함/볼결함/케이지}` (N4J)** — `:Equipment {rolling_bearing}`에 `SUBJECT_TO`.
2. NASA bearing 셋과 합쳐 회전기계 고장모드 사전을 단단히 만든 뒤, 자동차 ProcessStep(가공·이송)과 연결.

#### 합치기 (요약)
- NASA PCoE와 같은 Equipment taxonomy 레인. 중복 고장모드는 dedupe. 회사귀속 금지.

---

### 2.5 ○ SECOM (UCI) — 공정 센서 ↔ 수율 패턴

반도체지만 **"공정 센서 다수 → 양/불 yield"** 의 전형. 자동차 공정의 yield-fault 추론 패턴 참고 + ProcessStep 통계 속성.

#### 다운로드 (아주 상세)
1. UCI: `https://archive.ics.uci.edu/dataset/179/secom`
2. python `ucimlrepo`로 바로:
```bash
pip install ucimlrepo
python - <<'PY'
from ucimlrepo import fetch_ucirepo
secom = fetch_ucirepo(id=179)
X = secom.data.features      # 1567 x 590 센서 피처
y = secom.data.targets       # pass/fail (104 fail)
X.to_csv("data/raw/secom/secom_features.csv", index=False)
y.to_csv("data/raw/secom/secom_labels.csv", index=False)
PY
```
- **구조**: 1,567 샘플 × 590 피처 + 라벨/타임스탬프, 결측 ~4.5%, 극심한 불균형(약 1:0.07)
- **라이선스**: CC BY 4.0

#### 활용 (아주 상세)
- **그래프에 raw는 안 넣음.** 대신 (1) "공정 모니터링 시그널 → 수율 결함" 이라는 **추론 패턴 검증용**(L3/L4 cross QA의 reasoning 검증), (2) `:ProcessStep` 통계 속성(불량률·결측 패턴)의 예시 스키마로 활용.
- 자동차 ProcessStep의 센서-결함 통계 컬럼 설계를 SECOM 구조에 맞춰 표준화하면 KAMP 데이터 적재가 일관됨.

#### 합치기 (요약)
- 직접 노드/엣지 적재는 안 함. 통계 속성 스키마 레퍼런스 + 패턴 검증용. 등급 표기 불필요(그래프 미적재).

---

### 2.6 ○ AI Hub — 이송장치 열화 예지보전 71567 / 용접 AI(창원) / 부품검사 578

#### 다운로드 (AI Hub 공통 절차 — 아주 상세)
1. 가입·로그인: `https://aihub.or.kr/` (실명/기관 인증 필요할 수 있음).
2. 데이터셋 상세 페이지 진입(예: `.../view.do?dataSetSn=71567`) → **"다운로드" 버튼 → 활용 목적 입력 → 승인** 절차. 승인 후 다운로드/오픈API 가능.
3. **분할압축 병합**(AI Hub 특성): 파일이 `*.zip.part*`로 분할되어 받아진다. Linux 권장(Windows는 WSL).
```bash
# 분할 zip 병합 (AI Hub 안내 명령)
find "다운로드폴더경로" -name "파일명.zip.part*" -print0 \
  | sort -zt'.' -k2V | xargs -0 cat > "파일명.zip"
unzip "파일명.zip" -d data/raw/aihub/<set>
# 병합 파일 용량이 0이면 폴더경로 오타 → 재확인
```
- **대상 셋**:
  - **71567 이송장치 열화 예지보전 멀티모달** — OHT/AGV 센서+열화상, 탄화 예측. 총 ~124,263세트. 등급 **B(비귀속)**.
  - **용접 AI 학습 데이터(창원 지역 특화)** — 용접 공정 데이터. AI Hub 목록에서 dataSetSn 확인 후 동일 절차.
  - **578 부품 품질 검사(자동차)** — 이미 component taxonomy 22개로 사용 중(이미지 자체는 미사용).
- **라이선스**: 공공/AI Hub 이용약관(승인 기반)

#### 활용 (아주 상세)
1. **71567** → ProcessStep/Equipment 통계 속성(열화 지표) + 멀티모달 메타 텍스트 VEC. 회사 비귀속이라 PERFORMED_AT 금지(allowlist 자동 차단).
2. **용접 AI** → 용접 `:ProcessStep` 하위 `:FailureMode/:DefectType`(기공/슬래그/융합불량/균열 등) 시드 + 텍스트 VEC.
3. **578** → 현행 유지(부품 분류 시드).

#### 합치기 (요약)
- 모두 grade B(익명/비귀속). 정적 등급표에 이미 `aihub_*=B`. 공정명은 산단공 사전에 정규화.

---

### 2.7 ⚠️ 한국 자동차 리콜 (Layer 2) — 15089863은 보류, NHTSA 우선

**상태 정정** — `data.go.kr/data/15089863`(국토교통부_자동차 리콜정보 API)는 존재하지만, OpenAPI 제공이 **car.go.kr 사전협의(`/rs/cnter/intrcn.do?tabNum=6`)를 전제**로 한다. 사전협의 채널이 막혀 있으면 자유 발급이 안 되므로 **현 시점 사실상 사용 불가**. 따라서 Layer 2 회사귀속 리콜은 아래 순서로 간다.

#### 1순위 — NHTSA (이미 보유, 무키)
- 시스템에 이미 적재됨(recall 493 / complaint 16,005 / investigation 154). 한국 OEM의 **미국 판매분** 리콜·결함신고를 회사귀속(grade A)으로 커버. 추가 다운로드 없이 **DEFECT_MATCHES 다리의 기준 케이스**로 바로 사용.

#### 2순위 — car.go.kr 리콜현황/리콜통계 (웹 열람)
- 자동차리콜센터(`https://car.go.kr/ri/stat/list.do`)에 **리콜현황·리콜통계·리콜보도자료**가 공개되어 사람이 열람 가능. 한국 시장 리콜(국내 출시 전 차종)을 메우려면 여기가 후보.
- **단, OpenAPI가 막혔다고 웹 크롤링이 허용되는 건 아니다.** `robots.txt` + 이용약관을 먼저 확인하고, 허용 범위 내에서만(또는 보도자료 단위 수동 수집) 진행. 시스템의 라이선스 게이트(`_license.py`)에 출처·허용 여부를 명시 등록.

#### 3순위 — KOTSA 검사 데이터 (리콜 대체 보강)
- 리콜은 아니지만 회사귀속 가능한 정형: `data.go.kr/data/15057736`(자동차 종합정보 검사정보 서비스, OpenAPI, **인증키 자동발급**) + KOTSA의 **EV 배터리 셀 전압 데이터(2023 CSV, 제작사·차명·검사일자·주행거리 포함)** 등. 제작사 필드가 있어 일부는 회사귀속 가능.

#### 활용 / 합치기 (요약)
- 어느 출처든 `auto.events_recalls`(또는 검사는 `auto.events_inspections`) 스키마에 union, `source_type`만 다르게(`nhtsa_recall` / `car_go_kr_web` / `datagokr_inspection`). 7키 메타·grade A 유지. corp_code 매칭분은 `bridge.corp_entity`로 finance cross. **15089863는 "사전협의 해제 시 활성화" 트리거로만 코드에 남겨둔다(현재는 비활성).**

---

### 2.8 ○ EU Safety Gate (구 RAPEX) — Layer 2 EU 커버

- `https://ec.europa.eu/safety-gate-alerts/` 에서 주간 리콜/경보(자동차 포함, 회사·모델 귀속) 열람·다운. EU/비미국 케이스 보강.
- 다운로드 형식·API는 페이지에서 직접 확인(주간 알림 / 검색 export). `auto.events_recalls`에 `source_type='eu_safety_gate'`, grade A로 union.
- **검증 주의**: EU 사이트도 형식·엔드포인트가 바뀔 수 있으니 적재 전 현재 export 방식 확인.

---

## 3. Bridge 구현 — DEFECT_MATCHES (BGE-M3 유사도)

회사 못 찾는 고장지식 ↔ 회사 붙은 실제 케이스를 **측정된 유사도**로 잇는다. 기존 인프라(BGE-M3 + pgvector + Reranker) 재사용 → 코드만 추가.

```python
# 1) DefectType/FailureMode 설명 임베딩(이미 BGE-M3 서버 가동 중)
# 2) recall.component_text 임베딩 (대부분 vec.chunks에 이미 있음)
# 3) 코사인 top-k 매칭 → 엣지 생성
def build_defect_match_edges(min_sim=0.78, top_k=5):
    for recall in recalls_with_embedding():
        for dt, sim in nearest_defecttypes(recall.embedding, top_k):
            if sim >= min_sim:
                merge_edge(
                    ("Recall", recall.id), "DEFECT_MATCHES", ("DefectType", dt.id),
                    meta=dict(
                        source_type="embedding_similarity",
                        source_id=f"bgem3:{recall.id}->{dt.id}",
                        confidence_score=round(sim, 3),   # 유사도를 그대로 confidence로
                        validated_status="candidate",
                        snapshot_year=recall.year,
                        extraction_method="hybrid",
                        schema_version="vX",
                    ),
                )
```

- **정직성**: `confidence_score`=코사인 유사도, `validated_status='candidate'`, 답변 시 "유사도 0.83으로 매칭된 실제 케이스"로 표기. fabricated attribution이 아님 → §4.0 등급 정책 무충돌.
- (선택) `SIMILAR_CASE_OF`: recall↔recall 임베딩 유사도로 "유사 케이스" 군집(같은 고장의 타사 사례 탐색).

---

## 4. 기존 데이터와 합치기 (전체 요약)

1. **등급표 한 줄씩 추가** — `SOURCE_TO_GRADE`에 `kamp_manufacturing=B`, `maintnet=C`, `nhtsa_recall=A`, `car_go_kr_web=A`, `eu_safety_gate=A`, `datagokr_inspection=A`, `nasa_pcoe=A(비귀속)` 등. `_license.py`에 라이선스/허용여부 키 등록(`maintnet=cc_by_4_0`, `car_go_kr_web`은 robots/ToS 확인 후 등록).
2. **공정명 정규화** — KAMP/AI Hub/용접 공정명은 산단공 `:Process` 사전(이미 보유)에 매핑(KO-EN 사전 + 토큰 overlap)해서 붙인다.
3. **노드 2종 추가** — `:FailureMode`, `:DefectType`. `ontology/auto/entities.yaml`에 정의, 7키 메타는 기존 `EDGE_REQUIRED_META_KEYS` 그대로.
4. **엣지 3종 추가** — `CAN_CAUSE`, `MANIFESTS_AS`, `DEFECT_MATCHES`(+ 선택 `SIMILAR_CASE_OF`). `relations.yaml`에 `edge_required_meta` 7키 일치시켜 `audit-ontology` 통과.
5. **회사귀속 금지 유지** — KAMP/AI Hub/NASA/CWRU/SECOM은 전부 익명/비귀속 → `load_performed_at.py` allowlist가 PERFORMED_AT 적재를 자동 차단(정직성 가드 그대로).
6. **회사귀속은 리콜/검사로만** — NHTSA(우선) / car.go.kr 웹열람(ToS 확인) / EU Safety Gate / KOTSA 검사(15057736 계열)만 grade A 회사귀속, Bridge로 finance cross. **15089863(사전협의 게이트)은 현재 비활성** — 해제 시 활성화 트리거로만 보관.

---

## 5. 우선순위 + 체크리스트

| 순위 | 작업 | 키/의존성 | 산출 |
|---|---|---|---|
| 1 | **KAMP(15089213)** 다운 → `:FailureMode`/`:DefectType` 첫 적재 | 무인증(파일) / KAMP 가입 | Layer 1 고장지식 백본 |
| 2 | **MaintNet** 다운 → automotive 텍스트 P3 추출 + VEC | 없음(CC BY 4.0) | 다리 의미 밀도 ↑ |
| 3 | **DEFECT_MATCHES** 엣지 구현(BGE-M3) | 데이터 불필요(코드) | 회사무관↔회사케이스 다리 |
| 4 | **Layer 2 리콜 = NHTSA(보유) 활용** + car.go.kr 웹열람(ToS) | 무키 / 15089863은 사전협의 게이트라 보류 | Layer 2 회사귀속 케이스 |
| 5 | **NASA PCoE + CWRU/Paderborn** 고장모드 taxonomy | 없음 | `:Equipment` 고장모드 보강 |
| 6 | **AI Hub 71567 / 용접(창원)** | 로그인·승인 | ProcessStep 통계 + 용접 결함 시드 |
| 7 | **EU Safety Gate** | 없음 | 리콜 케이스 EU 커버 |

체크리스트:
- [ ] `SOURCE_TO_GRADE` / `_license.py` 신규 source 등록
- [ ] `:FailureMode` / `:DefectType` 온톨로지 정의 + `audit-ontology` PASS
- [ ] `CAN_CAUSE` / `MANIFESTS_AS` / `DEFECT_MATCHES` 7키 메타 일치
- [ ] KAMP/AI Hub 공정명 → 산단공 `:Process` 사전 매핑 사전 작성
- [ ] PERFORMED_AT allowlist에 익명 출처 미포함 확인(회사귀속 차단 유지)
- [ ] DEFECT_MATCHES `min_sim`/`top_k` 튜닝 + 답변 표기("유사도 N으로 매칭")

---

## 6. 출처(레퍼런스)

- KAMP: data.go.kr/data/15089213/fileData.do · kamp-ai.kr
- MaintNet: arxiv.org/abs/2005.12443 (CC BY 4.0)
- NASA PCoE: nasa.gov PCoE repository · data.phmsociety.org/nasa (C-MAPSS S3 zip)
- CWRU: engineering.case.edu/bearingdatacenter · Zenodo 10.5281/zenodo.10987113
- SECOM: archive.ics.uci.edu/dataset/179/secom (CC BY 4.0)
- AI Hub: aihub.or.kr (71567 이송장치 / 578 부품검사 / 용접 창원)
- 한국 자동차 리콜: data.go.kr/data/15089863 (⚠️ OpenAPI는 car.go.kr 사전협의 게이트 — 보류) · car.go.kr/ri/stat/list.do (웹 열람, ToS 확인)
- KOTSA 검사: data.go.kr/data/15057736 (종합정보 검사, 키 자동발급) · 15155857(수리검사)은 미검증 — 포털에서 ID 확인 필요
- EU Safety Gate: ec.europa.eu/safety-gate-alerts
- AI4I 2020: archive.ics.uci.edu/dataset/601 (CC BY 4.0)
- AI허브 데이터셋 목록(메타): data.go.kr/data/15135578/fileData.do