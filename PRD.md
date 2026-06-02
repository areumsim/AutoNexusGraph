# PRD: 자동차 제품·부품·리콜·공급망 + 특허·기술혁신 GraphRAG 에이전트 시스템 v2.2

**문서 버전:** 2.2
**작성일:** 2026-05-27 (v2.1) · 2026-06-01 (v2.2 IPGraph 흡수)
**v2.2 개정 사유:** 도메인3 = 특허 (IPGraph) 정식 흡수 + 4번째~ 도메인 영구 비목표 강등 + 상용 신호 (MCP/Langfuse/SHACL/축소 평가 매트릭스) DoD 승격 + 배터리·소재 부분 진입.

**v2.2 주요 변경:**
- 제목 확장 (§1.2 — auto + finance + ip 3 도메인)
- §2.3 비목표 — 4번째~ (의약품/전자제품/에너지/식품) 영구 비목표 강등 + 공정·소재 부분 진입 표기
- §10 DoD — #15 (ip 코어 변경 < 5% 재측정) + #16 (ip gold seed + CD ip 결합) + #17 (상용 신호 4 항) 신설
- §12.5 도메인3 (IPGraph) 정식 흡수 — 어댑터 슬롯·데이터 소스·Bridge 신규 join·작업 순서·측정 게이트 SSOT
- §13 부록 — v2.2 의사결정 6 행 추가 (도메인3 선택 / Bridge 확장 / 배터리·소재 / 4번째~ 강등 / 상용 신호 승격 / 평가 매트릭스 축소 / baseline reset)
- 설계 상세 SSOT 분리: [docs/ipgraph.md](./docs/ipgraph.md) (IPGraph) + [docs/autograph.md](./docs/autograph.md) §2.5.4 (배터리·소재 L5/L6 부록)
- **시스템 구조 SSOT 분리**: [docs/architecture.md](./docs/architecture.md) — 패키지 토폴로지 (autonexusgraph ← autograph ← ipgraph) · 도메인 모듈 매트릭스 · SQL 24 마이그레이션 · LangGraph 11 노드 · plug-in 등록 메커니즘 · SSOT 위치 색인

**v2.0 → v2.1 주요 변경:**
- 제목·포지셔닝 변경 (§1.2)
- ER 마스터 키 구조 재설계 (§4.5 신설, §6.1 수정)
- Bridge 스키마 일반화 (§4.6 신설)
- BOM 깊이별 가용성 매트릭스 (§3.4 신설)
- 출처별 신뢰도 등급 (§3.5 신설)
- 관계 엣지 필수 메타데이터 정의 (§6.7 신설)
- Cross-Domain QA 4단계 층화 (§8.1 수정)
- MVP 수집 범위 축소 (§3.3 수정)

---

## 1. 프로젝트 개요

### 1.1 배경

AutoNexusGraph(금융 GraphRAG)는 다음을 입증했다:

- **3-Store 하이브리드**(Neo4j + PostgreSQL + pgvector)가 단일 Vector RAG로 풀 수 없는 멀티홉 질문을 해결
- **Multi-Agent + Planning(LangGraph)** 구조가 재현 가능·디버깅 가능한 추론을 만든다
- **Deterministic-first 추출**(정형 직매핑 + 선택적 LLM)이 환각을 원천 차단한다
- **LLM 어댑터 패턴**으로 벤더 종속 없이 운영 가능

그러나 AutoNexusGraph는 다음 한계를 가진다:

- **도메인 단일성:** 금융 한 영역에만 한정 — 시스템 일반성을 입증하지 못함
- **관계 평면성:** 자회사/임원/주주 관계가 모두 동일 평면. "메인 홉"과 "사이드 홉"의 구분이 없음
- **이벤트 빈도 낮음:** 공시·뉴스는 분기/월 단위
- **물리적 계층 부재:** 모든 엔티티가 법인. 제품·소재·공정 같은 물리적 계층이 없음

이 PRD는 AutoNexusGraph의 검증된 코어 엔진을 그대로 재사용하면서, **자동차 제품·부품·리콜·공급망 도메인**으로 도메인 어댑터만 교체하여:
1. 시스템의 도메인 일반성을 입증하고
2. 명시적 계층 구조(완성차 → 시스템 → 모듈 → 부품)를 통해 "메인 홉" 개념을 도입하며
3. AutoNexusGraph와 Bridge로 연결하여 **Cross-Domain 멀티홉 추론**이라는 GraphRAG-Only 가치 영역을 개척한다.

### 1.2 프로젝트 한 줄 정의 [v2.1 수정]

> **"자동차 제품·부품·리콜·공급망 공개 데이터를 기반으로, 완성차–시스템–모듈–부품의 계층 관계와 리콜·공급망 이벤트를 그래프로 추론하여 답변하는 GraphRAG 에이전트. 선택적으로 AutoNexusGraph와 Wikidata QID 기반 Bridge로 연결해 Cross-Domain 추론(제품/품질 ↔ 재무) 수행"**

**v2.0의 "자동차 제조 도메인"이라는 표현은 공정·라인·설비·원가·생산량을 기대하게 한다. 본 시스템의 실제 데이터 가용 범위는 공개 차량 제원·리콜·결함·NCAP·공급망이므로 "제품·부품·리콜·공급망"으로 포지셔닝한다.** Material/Process Level 6은 장기 확장 영역으로 분리.

### 1.3 핵심 변경사항 (AutoNexusGraph → AutoGraph)

| 영역 | AutoNexusGraph (AS-IS) | AutoGraph (TO-BE) | 변경 이유 |
|---|---|---|---|
| 인프라(Docker/Neo4j/PG/pgvector) | 그대로 | **그대로** | 코어 엔진 재사용 |
| LangGraph Multi-Agent | 그대로 | **그대로** | 노드 구조 동일, Tool만 교체 |
| Safety guards | 그대로 | **그대로** | 도메인 무관 |
| BGE-M3 임베딩 | 그대로 | **그대로** | 다국어 지원 |
| LLM 어댑터 | 그대로 | **그대로** | Provider 전환 환경변수 1줄 |
| **Entity Resolution 마스터** | **`corp_code` 단일 중심키** | **`entity_id` + `entity_type` 다형 키** | **법인·차량·부품 분리 [v2.1]** |
| **Bridge 테이블** | 없음 | **`bridge.corp_entity` (manufacturer + supplier 통합)** | **확장성 [v2.1]** |
| 데이터 소스 | DART/KRX/ECOS | NHTSA / car.go.kr / KATRI / Wikidata | 도메인 교체 |
| 핵심 엔티티 | Company / Person | **Manufacturer / Vehicle / Component / Supplier / Recall** | 도메인 교체 |
| 핵심 관계 | SUBSIDIARY_OF / EXECUTIVE_OF (평면) | PART_OF / SUPPLIED_BY / AFFECTED_BY (계층 + 시점) | 메인 홉 명시 |
| 정량 수치 | 재무제표 | 제원·NCAP·결함률 | 도메인 교체 |
| 이벤트 | 뉴스·공시 | 리콜·결함신고·NCAP 평가 | 도메인 교체 |
| **관계 엣지 메타** | snapshot_year + source | **필수 7키** (source_type / source_id / confidence_score / validated_status / snapshot_year / extraction_method / schema_version — §6.7) + 라이프타임 엣지는 valid_from/to 추가 **[v2.1]** | **공급 관계 신뢰도 통제 + audit-ontology / audit-edge-meta 강제** |

---

## 2. 목적 및 목표

### 2.1 비즈니스 목적

1. **단일 도메인 GraphRAG의 한계를 넘는다**
   - 도메인 내: "현대 쏘나타의 에어백 리콜과 관련된 공급사는?" (멀티홉 + 시점)
   - Cross-Domain: "삼성SDI 배터리를 쓰는 OEM의 모회사 영업이익은?" (Vector RAG로 절대 불가)

2. **시스템의 도메인 일반성을 입증한다**
   - 동일 코어 엔진이 금융·자동차 양쪽에서 작동
   - 도메인 어댑터 레이어 교체만으로 새 도메인 진입 가능

3. **명시적 계층(메인 홉)으로 그래프 폭발을 통제한다**
   - 자연스러운 BOM 계층 (Manufacturer → Vehicle → System → Module → Part)
   - Planner가 계층 인지 깊이 우선 탐색 → 토큰·latency 절감

### 2.2 기술 목표 [v2.1 — Cross-Domain 층화 반영]

| 목표 | 측정 지표 | 목표치 |
|---|---|---|
| 한국어 자동차 RAG 정확도 | Answer Accuracy (LLM-as-judge) | 85%+ |
| Multi-hop 추론 성공률 (도메인 내) | 2-hop 이상 정답률 | 75%+ |
| **Cross-Domain L1 (제조사 ↔ 상장사 직접 Bridge)** | 정답률 | **80%+** |
| **Cross-Domain L2 (모델 ↔ 제조사 ↔ 재무)** | 정답률 | **70%+** |
| **Cross-Domain L3 (부품/공급사 ↔ OEM ↔ 재무)** | 정답률 | **50~60%** |
| **Cross-Domain L4 (시점 포함 공급망 ↔ 재무/ESG)** | 정답률 | **40~50%** |
| Hybrid 우위 입증 | Vector 단독 대비 Multi-hop 격차 | +30%p 이상 |
| 도메인 어댑터 교체 비용 | 코어 엔진 코드 변경량 | < 5% |
| 메인 홉 효율 | 평균 노드 탐색 수 (vs 평면 그래프) | 30% 감소 |
| 평균 응답 latency | 도메인 내 | < 8초 |
| Cross-Domain latency | Bridge join 포함 | < 12초 |
| 환각률 | Faithfulness (Ragas) | 90%+ |

**v2.0의 "Cross-Domain 60%+ 일률 목표"는 질문 난이도에 따라 너무 쉽거나 너무 어렵다. L1~L4 층화로 평가 신뢰도 확보.**

### 2.3 비목표 (Non-Goals) [v2.1 명시화 + v2.2 IPGraph 흡수]

**영구 non-goal — 본 시스템이 다루지 않는다고 단정:**

- 차량 가격 예측 / 중고차 시세
- 비공개 OEM 내부 BOM
- 자율주행 안전성 인증 대체
- 정비 매뉴얼 기반 DIY 가이드
- 실시간 텔레매틱스

**현 단계 (v2.2) 비목표 — ip 가 §10.12 < 5% 를 실측 증명한 뒤 재의사결정:**

- **N-domain 4번째 ~ (의약품 / 전자제품 / 에너지 / 식품)** — 본 PR 에서는 다루지 않는다. 도메인3 (IPGraph) 가 §10.12 "코어 변경 < 5%" 를 실측 증명한 뒤 Phase D/E 진입 여부를 재의사결정 (§12.5). 즉 "영원히 안 한다" 가 아니라 "ip 증명 전까지 보류". 산만함 방지 차원의 의도적 강등.

**MVP 비목표였지만 v2.2 에서 부분 진입:**

- **공정·라인·설비·원가·생산량 데이터** — DART 사업보고서 가동률 표 + 산단공 합성 공정 + KAMA 매크로 + 팩토리온 (DATA_GO_KR) 으로 부분 진입 (정형, LLM 0%)
- **Level 6 (소재·공법)** — 배터리 셀 chem (Wikidata) + 핵심광물 (USGS) + 무역통계 (관세청) 로 부분 진입. 회사단위 셀↔OEM 소싱은 grade C candidate 정직 표기 (sparse)

---

## 3. 데이터 정책

### 3.1 오픈 데이터 활용 원칙

AutoNexusGraph와 동일 원칙. 공공·라이선스 명시 데이터만 수집. 코드 레벨 라이선스 강제(`src/autograph/ingestion/_license.py`).

### 3.2 데이터 소스

#### 구축용 (Knowledge Source)

| 데이터 | 출처 | 라이선스 | 용도 |
|---|---|---|---|
| 차량 마스터 (제원·VIN 디코드) | NHTSA vPIC API | 공공(US) | `master.vehicles` |
| 리콜 (한국) | 자동차리콜센터 car.go.kr Open API | 공공 | `events.recalls` |
| 리콜 (글로벌) | NHTSA Recalls API | 공공 | `events.recalls` |
| 결함 신고 | NHTSA Complaints | 공공 | `vec.chunks` |
| 안전 평가 | KNCAP, NCAP, Euro NCAP | 공공 | `spec.measurements` |
| 자기인증·형식승인 | 국토부 KATRI | 공공 | `events.certifications` |
| 차량/제조사 글로벌 매핑 | Wikidata SPARQL | CC0 | `master.entity_map` + `wiki.wikidata_facts` |
| 차량/부품 위키 본문 | Wikipedia (ko/en) | CC BY-SA | `wiki.wikipedia_pages` + `vec.chunks` |
| 공급사 마스터 | KATECH, KAMA 공개자료 | 공공 | `master.suppliers` |
| 부품사 IR 자료 | 전자공시 + 공식 IR 사이트 | 공공 | `doc.manuals` + `vec.chunks` |

### 3.3 수집 범위 (MVP 1차) [v2.1 — 대폭 축소]

| 항목 | v2.0 (원안) | **v2.1 MVP** | 확장(post-MVP) |
|---|---|---|---|
| OEM | 20사 | **5~8사** (현대·기아·제네시스·KGM·르노코리아 + 토요타·BMW·테슬라) | 20사 |
| 모델 | 300종 | **30~50종** (대표 베스트셀러) | 300종 |
| 연식 | 2020~2024 | **2022~2024** | 2020~2024 |
| BOM 깊이 | Level 0~6 | **Level 0~4** | Level 5~6 |
| 리콜 | 한국+미국 5년 전수 | **NHTSA + 한국 주요 OEM 우선** | 5년 전수 |
| Cross-Domain QA | 30문항 | **10문항 seed → 30문항** | 50+ 문항 |
| Bridge 대상 | 30사 | **10~15사** (한국 OEM + 주요 부품사) | 30사+ |

**MVP는 5주 로드맵 내 실제 작동하는 시스템을 우선한다. 정합성 작업이 데이터 양에 묻히는 것을 방지.**

### 3.4 BOM 깊이별 데이터 가용성 매트릭스 [v2.1 신설]

| 계층 | 가용성 | MVP 포함 여부 | 권장 데이터 출처 |
|---|---|---|---|
| Level 0: Manufacturer | **높음** | ✅ 필수 | Wikidata + NHTSA + KAMA |
| Level 1: Vehicle Model | **높음** | ✅ 필수 | NHTSA vPIC + 리콜 + Wikipedia |
| Level 2: Trim/Year | **중간** | ✅ 필수 | NHTSA + 국내 매핑 수동 보강 |
| Level 3: System | **중간** | ✅ 포함 | KS/SAE 표준 분류 사전 + 리콜 분류 |
| Level 4: Module | **낮음~중간** | ⚠️ 부분 포함 (coverage 명시) | 공개 매뉴얼 + IR + 리콜 본문 LLM 추출 |
| Level 5: Part | **낮음** | ❌ MVP 제외 | 리콜/결함 중심으로만 진입 (post-MVP) |
| Level 6: Material/Process | **낮음** | ❌ MVP 제외 | 부품사 공개자료 / 일반 공법 지식 (장기) |

**MVP 성공 기준은 Level 0~4 안정 구축. Level 5는 리콜에 등장한 부품만 부분 포함. Level 6은 장기 로드맵.** 사용자에게도 UI에서 BOM 트리 표시 시 "Level 4까지 신뢰도 높음, 그 이하는 부분 데이터" 명시.

### 3.5 출처별 신뢰도 등급 [v2.1 신설]

PRD v2.0의 "출처 명시" 원칙을 정량화. 모든 그래프 엣지는 출처 등급에 따라 `confidence_score` **할당값**이 결정된다.

> **두 개념을 구별할 것 — 동일한 0.5 라는 숫자가 의미하는 바가 다르다:**
> - **할당값 (`confidence_score`)** — ingestion·loader 가 엣지 생성 시점에 출처 등급에 따라 부여하는 신뢰도. LLM 추출(P3) 의 기본 할당값이 **0.50** (이 표).
> - **fail 임계값 (`LOW_CONFIDENCE_THRESHOLD = 0.5`)** — `agents/validator.py:43` 의 답변 검증 게이트. 답변 근거 그래프 엣지의 `confidence_score < 0.5` 면 hard fail (`all_low`) 또는 soft warning (`some_low`). 단독 근거 금지.

| 출처 | 신뢰도 등급 | 기본 confidence_score | 적용 관계 |
|---|---|---|---|
| NHTSA / 자동차리콜센터 공식 리콜 | **A (높음)** | 0.95 | `AFFECTED_BY`, `RECALL_OF` |
| NHTSA vPIC | **A** | 0.95 | `MANUFACTURES`, `HAS_VARIANT` |
| KNCAP / NCAP / Euro NCAP | **A** | 0.95 | `SAFETY_RATED_BY` |
| Wikidata | **B (중간)** | 0.80 | 글로벌 ID 매핑, `MANUFACTURES` (보조) |
| Wikipedia | **B~C** | 0.70 | 설명 문서, 보조 근거 |
| 부품사 IR (공식 공시) | **B** | 0.75 | `SUPPLIED_BY` (후보) |
| 매뉴얼 / 브로셔 | **B** | 0.75 | `CONTAINS_*` (시스템·모듈) |
| LLM 추출 (P3) | **C** | 0.50 | P4 cross-validate 필수. validator 임계와 같은 0.5 — 단독 근거 시 soft warning |
| 커뮤니티 / 분해 자료 | **C (낮음)** | 0.40 | 후보 추출만, 확정 관계 금지. validator 임계 미달 — hard fail 가능 |
| 수동 검토 확정 | **A+** | 1.00 | 모든 관계 |

**`validated_status='validated'` 승급 정책:**
- `SUPPLIED_BY` 등 공급 관계는 **A 또는 B 출처 + P4 cross-validate 통과** 시에만 `validated_status='validated'`
- 그 외는 `candidate` 또는 `needs_review`
- C 등급 단독 출처는 절대 `validated` 금지

**Validator 게이트 동작** (코드 SSOT — `agents/validator.py:125-162`):
- 답변 근거 그래프 엣지 (`tool_results.graph_subgraph`) 의 `confidence_score` 검사.
- 전부 `< 0.5` → `all_low` hard fail → replan 트리거.
- 일부만 `< 0.5` → `some_low` soft warning → 답변에 "후보 정보" 명시.
- 0.5 이상 + `validated_status='rejected'` 가 아닌 엣지만 단독 인용 가능.

> **⚠️ Calibration 미검증 (P1-4) — 실측 routine wired (2026-06-02)** — 본 표의 confidence 할당값 (A=0.95 / B=0.80 / C=0.50) 이 실제 정답률과 단조 관계인지 미실측 (LLM 키 부재로 gold QA 측정 결과 EM=0/120). 측정 인프라 완료: `scripts/audit/calibrate_confidence.py` (신규) — Platt scaling (sklearn LogisticRegression) + 10-bin reliability diagram (matplotlib PNG) + `a < 0.9` ⇒ overconfident / `a > 1.1` ⇒ underconfident 자동 분류. `make audit-calibrate` 1줄 실행. 합성 데이터 smoke PASS (overconfident 패턴 0.6×conf+0.1 → 적합 σ(0.718x − 0.482) → "overconfident" 정확 분류). 실측 절차 + reverse-feed 흐름: [docs/learning_guide.md §11.4.0](docs/learning_guide.md). **LLM 키 활성 후 `make eval-full` 실행 → `make audit-calibrate` 1회**. 결과가 systematic 어긋남이면 본 §3.5 표 할당값 재조정.

### 3.5.1 row 단위 동적 confidence 격상 [v2.2-rev1 신설 — auto 공정 데이터 전용]

§3.5 의 정적 등급표는 **데이터셋 단위 할당값**이다. 이와 별개로, 합성/LLM 등 **C 등급 출처의 row 도 외부 A/B 출처 시그널이 충분히 누적되면 row 단위로 0.80 (B) 까지 승급**할 수 있다 — 현 단계 운영 대상은 **`auto.processes` (산단공 합성 15151075, C 0.50) 단독**, 410 공정명 중 외부 매칭 가능한 row 한정 (예상 격상률 15~30%, 70~85% 는 C 유지).

> 정적 등급표 행 추가가 **아닌** row 단위 동적 컬럼 갱신이므로 §3.5 본문·기존 SSOT (`src/autograph/ingestion/_confidence.py::SOURCE_TO_GRADE`) 무변경. `agents/validator.py:LOW_CONFIDENCE_THRESHOLD = 0.5` 도 무변경. 격상 후 row 가 validator 게이트를 자연 통과.

**격상 시그널 (cross_validate 8 시그널 — `src/autograph/extractors/process_confidence.py` SSOT)**:

| 시그널 | 매칭 후보 | 가중 w | grade boost |
|---|---|---:|---|
| M1 | NHTSA `:Module` taxonomy (KO-EN 사전 매핑) | 0.15 | A (1.00) |
| M2 | DART 사업보고서 narrative BGE-M3 cos ≥ 0.78 | 0.15 | B (0.80) |
| M3 | OEM IR/뉴스 본문 regex mention ≥ 1 | 0.10 | B (0.80) |
| M4 | KSIC C30xxx 산업분류 직접 매핑 | 0.05 | A (1.00) |
| M5 | DART `plant_capacity.product_name` 토큰 overlap ≥ 0.5 | 0.10 | B (0.80) |
| M6 | NHTSA recall `component_text` + LLM P3 → `CAUSED_BY_PROCESS` (P4 검증 후) | 0.10 | A (0.95) |
| M7 | KS X 9001 + ISO 18629 PSL manual seed 정확 매칭 | 0.05 | A (1.00) |
| C1 | 충돌 시그널 (예: M1 매핑 component vs M6 무관 카테고리) | — | penalty −0.20 |

**계산 식**:

```
conf = clip(0.50 + Σ w_i · s_i · grade_i − 0.20 · |conflicts|, 0.30, 1.00)
```

이론 max boost = +0.70 (clip 시 0.95). 평균 시나리오 (M1+M2+M3 일치): 0.50 + 0.15 + 0.12 + 0.08 = **0.85 → B 격상**.

**승급 후 정책**:
- `confidence_score ≥ 0.80` → row UPDATE 후 `validator._check_edge_confidence` 게이트 자연 통과
- `validated_status` 는 별도 — A/B 출처 + P4 통과 시에만 `validated`. **C 단독 격상은 `candidate` 유지** (§3.5 단독 근거 금지 원칙 보존).
- 답변 인용 시 "산단공 합성 + 외부 N개 소스 cross-validated" 출처 표시 의무

**격상 실패 row** (예상 70~85%):
- C 등급 + `validated_status='candidate'` 유지 — taxonomy 사전 전용 (회사·차량 단위 매핑 불가)
- agent tool `search_processes` 검색 결과에 "합성/패턴" 라벨 강제 (gold QA AUTO0051 시나리오)

**SSOT 분리**:
- 정적 등급: `src/autograph/ingestion/_confidence.py::SOURCE_TO_GRADE` (변경 없음)
- 동적 격상: `src/autograph/extractors/process_confidence.py` (P0-B 시그니처 + P3-B 구현)
- staging: `auto.staging_process_signals` (`infra/postgres/init/16_process_signals.sql` 신규)
- 운영: `scripts/upgrade_processes_confidence.py` (1회 풀런 ≤ $2 + GPU 1분, idempotent)

설계 SSOT — [PRD_process_graph.md](./PRD_process_graph.md) §8 등급 정책 (사용자 작성 중, `docs/process_graph.md` 로 이관 예정).

---

## 4. 시스템 아키텍처 방향성

### 4.1 컨테이너 토폴로지

AutoNexusGraph와 동일 인프라. 컨테이너는 그대로, 데이터만 다름.

```
[데이터 계층]
├─ Neo4j 5.18    : 차량·부품·공급사·리콜 그래프 (계층 + 시점 + confidence)
└─ PostgreSQL 16 : 제원 수치 / 차량·법인 마스터 / 평가 QA / 채팅 히스토리 /
                   LangGraph checkpoint / 문서 청크 벡터(pgvector) /
                   master.entities (다형 ER) / bridge.corp_entity

[모델 계층]
├─ BGE-M3        : 임베딩 (GPU) — AutoNexusGraph와 공유
└─ BGE-Reranker  : 재랭킹 (GPU) — 공유

[애플리케이션 계층]
├─ Ingestion Worker : NHTSA / car.go.kr / KATRI / Wikidata / Wikipedia / IR
├─ API (FastAPI)    : 에이전트 + 도메인 모드 라우팅
└─ Web (Streamlit)  : 도메인 토글 UI

[Bridge 계층]
└─ bridge.corp_entity : Wikidata QID + LEI + 사업자등록번호 기반 다형 join

[외부 의존성]
└─ LLM Provider : OpenAI / Anthropic / 로컬
```

### 4.2 데이터 흐름

AutoNexusGraph와 동일 5단계 + Bridge:
1. 수집 → PG 정형
2. 청킹 → pgvector
3. 그래프 구축 (계층 + confidence + provenance)
4. **Bridge: `master.entities.wikidata_qid` ↔ AutoNexusGraph `master.entity_map.wikidata_qid` 자동 매칭**
5. 질의 → 에이전트 → 답변
6. 평가 → 대시보드

### 4.3 그래프 vs 정형 DB 역할 분담

AutoNexusGraph 원칙 그대로:
- **Neo4j (관계 + 시점 + confidence):** BOM 계층, 공급 관계, 리콜 영향 범위
- **PostgreSQL (수치 + 의미):** 제원·NCAP 수치 + 매뉴얼/리콜 본문 청크 + 벡터
- **`master.entities` (신규):** 다형 ER 마스터 — 법인·차량·부품·리콜 통합 식별

**핵심 원칙:** 제원 수치는 절대 LLM이 생성하지 않는다.

### 4.4 메인 홉 계층 [v2.1 수정 — Level 4까지 안정, Level 5~6 분리]

```
[Level 0] Manufacturer       예: 현대자동차, 토요타       ← MVP 안정
   │ MANUFACTURES (class='main_hop')
   ▼
[Level 1] Vehicle Model      예: 쏘나타 DN8, 캠리 XV70    ← MVP 안정
   │ HAS_VARIANT (class='main_hop')
   ▼
[Level 2] Trim/Year          예: 쏘나타 1.6T 2024         ← MVP 안정
   │ CONTAINS_SYSTEM (class='main_hop')
   ▼
[Level 3] System             예: 파워트레인, ADAS         ← MVP 포함
   │ CONTAINS_MODULE (class='main_hop')
   ▼
[Level 4] Module             예: 가솔린 엔진, 배터리팩    ← MVP 부분 (coverage 명시)
   │ CONTAINS_PART (class='main_hop')
   ▼
[Level 5] Part               예: 인젝터, BMS              ← Post-MVP (리콜 등장만)
   │ MADE_OF / USES_PROCESS
   ▼
[Level 6] Material + Process 예: 알루미늄 합금 + 다이캐스팅 ← 장기 (확장 영역)

[사이드 홉]
- SUPPLIED_BY → Supplier      (Level 3~5, class='side_hop')
- MANUFACTURED_AT → Plant     (Level 1~2)
- COMPLIES_WITH → Standard    (Level 1~5)
- AFFECTED_BY → Recall        (Level 1~5, 시점 필수)
- COMPETES_WITH → Vehicle     (Level 1)
```

### 4.5 Entity Resolution 마스터 재설계 [v2.1 신설]

v2.0의 `vehicle_id` 단일 중심은 자동차 도메인에 부적합. 법인·차량·부품·리콜은 서로 다른 식별 체계가 필요.

```sql
CREATE TABLE master.entities (
    entity_id        VARCHAR PRIMARY KEY,        -- 내부 통합 ID (UUID 또는 prefix+seq)
    entity_type      VARCHAR NOT NULL,           -- manufacturer | supplier | vehicle_model
                                                  -- | vehicle_variant | component | recall | standard | plant
    canonical_name   VARCHAR NOT NULL,
    canonical_name_en VARCHAR,
    -- 외부 식별자 (entity_type에 따라 일부만 채워짐)
    wikidata_qid     VARCHAR,
    lei              VARCHAR,                    -- 법인만
    corp_code        VARCHAR,                    -- 한국 상장사만 (AutoNexusGraph 연동 키)
    business_no      VARCHAR,                    -- 한국 법인만
    cik              VARCHAR,                    -- SEC 등록 법인만
    nhtsa_model_id   VARCHAR,                    -- 차량 모델만
    nhtsa_campaign_id VARCHAR,                   -- 리콜만
    car_go_kr_id     VARCHAR,                    -- 한국 리콜만
    -- 메타
    source_priority  INT,                        -- 1=primary, 2=alias, ...
    confidence_score NUMERIC,
    valid_from       DATE,
    valid_to         DATE,
    schema_version   VARCHAR,
    created_at       TIMESTAMP DEFAULT NOW(),
    updated_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_entities_type ON master.entities(entity_type);
CREATE INDEX idx_entities_qid ON master.entities(wikidata_qid) WHERE wikidata_qid IS NOT NULL;
CREATE INDEX idx_entities_corp ON master.entities(corp_code) WHERE corp_code IS NOT NULL;
CREATE INDEX idx_entities_lei ON master.entities(lei) WHERE lei IS NOT NULL;
```

**엔티티 타입별 Primary Key 매핑:**

| 엔티티 타입 | 권장 식별자 (entities 행에서 활용) |
|---|---|
| Manufacturer | `entity_id`, `wikidata_qid`, `lei`, `corp_code` |
| Vehicle Model | `entity_id`, `wikidata_qid`, `nhtsa_model_id` |
| Vehicle Variant (Trim/Year) | `entity_id` (내부 생성) |
| Component | `entity_id` (내부 생성) |
| Supplier | `entity_id`, `wikidata_qid`, `lei`, `corp_code` |
| Recall | `entity_id`, `nhtsa_campaign_id`, `car_go_kr_id` |

**AutoNexusGraph와의 자연스러운 연결:** `entities.corp_code`가 채워진 행이 곧 Bridge 대상.

### 4.6 Bridge 일반화: `corp_entity` [v2.1 신설]

v2.0의 `bridge.corp_manufacturer`는 완성차 OEM만 다룬다. 실제 Cross-Domain 가치는 배터리사·반도체사·타이어사·ADAS 공급사까지 확장될 때 발현.

```sql
CREATE TABLE bridge.corp_entity (
    bridge_id         BIGSERIAL PRIMARY KEY,
    corp_code         VARCHAR NOT NULL,         -- AutoNexusGraph 키
    entity_id         VARCHAR NOT NULL,         -- AutoGraph master.entities.entity_id
    entity_type       VARCHAR NOT NULL,         -- manufacturer | supplier
                                                 --   (sub: battery_supplier | component_supplier
                                                 --    | semiconductor_supplier | tire_supplier | adas_supplier)
    -- 매칭에 사용된 식별자들 (감사·재현용)
    wikidata_qid      VARCHAR,
    lei               VARCHAR,
    cik               VARCHAR,
    business_no       VARCHAR,
    -- 매칭 메타
    match_method      VARCHAR NOT NULL,         -- qid_exact | lei_exact | business_no_exact
                                                 --   | corp_code_exact | fuzzy_name | manual
    confidence_score  NUMERIC NOT NULL,         -- 0.0 ~ 1.0
    -- 시점
    valid_from        DATE,
    valid_to          DATE,
    -- 거버넌스
    source            VARCHAR,                  -- wikidata | gleif | manual | derived
    reviewed_status   VARCHAR DEFAULT 'auto',   -- auto | reviewed | rejected
    reviewed_by       VARCHAR,
    reviewed_at       TIMESTAMP,
    schema_version    VARCHAR,
    created_at        TIMESTAMP DEFAULT NOW(),
    UNIQUE(corp_code, entity_id, valid_from)
);

CREATE INDEX idx_bridge_corp ON bridge.corp_entity(corp_code);
CREATE INDEX idx_bridge_entity ON bridge.corp_entity(entity_id);
CREATE INDEX idx_bridge_type ON bridge.corp_entity(entity_type);
```

**매칭 우선순위 (Confidence 산정):**
1. `wikidata_qid` exact match → 0.95
2. `lei` exact match → 0.93
3. `business_no` exact match → 0.90
4. `corp_code` direct (AutoNexusGraph entity_map → AutoGraph 직접) → 0.95
5. Fuzzy name match (한글·영문 normalize 후) → 0.60~0.75
6. Manual → 1.00

**Confidence < 0.7은 자동 `needs_review` 큐로.**

이렇게 하면 "한온시스템 부품을 쓰는 차종의 한온시스템 재무 리스크"도 자연스럽게 풀린다.

---

## 5. LLM 추상화 전략

AutoNexusGraph와 100% 동일. 같은 `LLMClient`, 같은 어댑터, 같은 환경변수.

---

## 6. 도메인 변경에 따른 코드 재구성

### 6.1 마이그레이션 1:1 매핑 [v2.1 수정 — entities 통합 반영]

| AutoNexusGraph 자산 | AutoGraph 매핑 | 변경 정도 |
|---|---|---|
| `master.companies` | `master.entities` (entity_type='manufacturer') | **통합 ER로 일반화** |
| `master.persons` | `master.entities` (entity_type='supplier') 또는 별도 `master.persons` 유지 | 도메인 선택 |
| `master.entity_map` | `master.entities` 안에 흡수 | **단일 테이블로 통합** |
| `fin.financials` | `spec.measurements` | 시계열 구조 동일 |
| `fin.filings` | `doc.manuals` | 메타 구조 동일 |
| `news.articles` | `events.recalls` + `events.complaints` | 시점·멘션 구조 동일 |
| `wiki.*` | `wiki.*` | **완전히 동일** |
| `vec.chunks` | `vec.chunks` | **완전히 동일** (메타에 entity_id) |
| Neo4j `Company` 노드 | `Manufacturer` + `Vehicle` + `VehicleVariant` + `Component` + `Supplier` + `Recall` | 라벨 다양화 |
| `SUBSIDIARY_OF` | `MANUFACTURES` / `CONTAINS_*` (계층 main_hop) | 메인 홉 등급 부여 |
| `EXECUTIVE_OF` | `SUPPLIED_BY` / `MANUFACTURED_AT` | 인적 → 공급망 |

### 6.2~6.5 v1/v2/web/공통 재구성

본질은 §6.1 마이그레이션 매핑 표가 모두 흡수 — `master.companies → master.entities`, `fin.* → spec.* + events.*`, `news.* → events.recalls + events.complaints` 의 1:1 치환만 적용하면 v1 (P1/P2 deterministic) / v2 (P3 LLM + P4 cross-validate) / web (FastAPI + Streamlit) / 공통 (Docker / BGE-M3 / LLM 어댑터) 모두 변경 0건으로 작동.

세부 코드 토폴로지·패키지 분리·LangGraph 11 노드 등록 메커니즘은 **[docs/architecture.md](./docs/architecture.md)** 가 SSOT. v2.0 본문의 4개 절은 본 PR 시점에는 별도 유지 가치가 없어 인덱스만 남기고 위임.

### 6.6 추출 전략: AutoNexusGraph 4-Pass + Bridge Pass

| Pass | 입력 | 방식 | 산출물 | LLM 비중 |
|---|---|---|---|---|
| **P1 (Det)** | NHTSA vPIC / KNCAP / NCAP | 직접 매핑 | `spec.measurements` | 0% |
| **P2 (Det)** | 자동차리콜센터 정형, OEM 공개 BOM | 직접 매핑 | Neo4j 계층 + AFFECTED_BY | 0% |
| **P3 (LLM)** | 매뉴얼·결함신고·IR 본문 | Schema-aware LLM 추출 | 관계 후보 (SUPPLIED_BY 등) | 100% |
| **P4 (Validate)** | P3 산출 + P1/P2 + 출처 등급 | confidence 산정 + cross-validate | validated 관계 (§3.5 정책) | 보조 |
| **P5 (Bridge)** | `entities.wikidata_qid` ↔ AutoNexusGraph | 직접 매핑 + fuzzy fallback | `bridge.corp_entity` | 0% |

### 6.7 관계 엣지 필수 메타데이터 [v2.1 신설]

**필수 7키 — `EDGE_REQUIRED_META_KEYS` SSOT** (`src/autonexusgraph/ontology/schema.py:28-36`):

1. `source_type` — `recall | ir_disclosure | manual | wikidata | wikipedia | llm_extraction | manual_curation`
2. `source_id` — `NHTSA-25V-001 | DART-20240315-... | chunk_id:...`
3. `confidence_score` — `0.0 ~ 1.0` (할당값. fail 임계 0.5 와 구별, §3.5)
4. `validated_status` — `candidate | validated | rejected | needs_review`
5. `snapshot_year` — `2024` (해당 데이터의 측정·발표 연도)
6. `extraction_method` — `deterministic | llm | hybrid | manual`
7. `schema_version` — yaml 헤더의 ontology 스키마 버전 (`_helpers.ontology_schema_version()` 가 자동 부여, B1 fix)

`ontology/<domain>/relations.yaml::edge_required_meta` 가 7키와 정확히 일치하지 않으면 `audit-ontology` fail (`scripts/audit/ontology_validate.py`).

**옵션 키 (라이프타임 / 거버넌스 — 일부 관계만):**

- `source_url` — 인용 URL (recall / wikipedia / IR 등)
- `extractor_version` — `p2-v1 | p3-llm-v2 | ...`
- `valid_from` / `valid_to` — **라이프타임 엣지에만** (`SUPPLIED_BY`, `MANUFACTURED_AT`, `COMPLIES_WITH` 등 시점 구간이 의미 있는 관계). 일회성 엣지 (예: `RECALL_OF`) 는 미사용.
- `created_at` — 적재 시각 (`datetime()`)
- `reviewed_by` — 수동 검토자 ID

```cypher
CREATE (a)-[r:SUPPLIED_BY {
    // ── 필수 7키
    source_type:        'manual_supplier_seed',
    source_id:          'supplier_seed.yaml#row42',
    confidence_score:   0.95,
    validated_status:   'validated',
    snapshot_year:      2024,
    extraction_method:  'manual',
    schema_version:     'v2.2',   // ontology/<domain>/relations.yaml 헤더 SSOT (v 접두사 포함)
    // ── 라이프타임 (이 관계는 시점 구간이 있음)
    valid_from:         date('2024-01-01'),
    valid_to:           date('2024-12-31'),
    // ── 거버넌스 (선택)
    source_url:         'https://...',
    created_at:         datetime(),
    reviewed_by:        'admin'
}]->(b)
```

**Validator Agent 강제 규칙** (코드 SSOT — `agents/validator.py:125-162`):
- `validated_status='candidate'` 엣지는 답변 인용 시 "후보 정보" 명시
- `validated_status='rejected'` 엣지는 쿼리 시 자동 제외 (bridge tool 도 동일)
- `confidence_score < 0.5` 엣지는 단독 근거 금지 (`LOW_CONFIDENCE_THRESHOLD=0.5`). 전부 < 0.5 → `all_low` hard fail → replan. 일부만 → `some_low` soft warning.
- 7키 invariant 검증은 `make audit-edge-meta --strict` (`scripts/audit/edge_meta_invariants.py`).

---

## 7. 에이전트 동작 방향성

### 7.0~7.6

v2.0의 §7 구조 그대로 + 다음 두 가지 신규 반영:

1. **Validator의 confidence 게이트:** §6.7 규칙을 Validator 단계에서 강제. confidence < 0.5인 엣지가 답변 근거에 포함되면 자동 fail → Replan.
2. **Bridge Tool의 confidence 표시:** `bridge_corp_to_manufacturer()` 호출 시 반환에 `bridge_confidence` 포함. UI는 0.7 이상은 ✓, 0.7 미만은 ⚠ 아이콘으로 표시.

### 7.2 도구 추상화 [v2.1 — entities 기반 시그니처]

#### `tools/spec.py`
- `lookup_entity(query, entity_type=None, limit=10)` — 통합 식별 (manufacturer/vehicle/supplier)
- `get_vehicle_info(entity_id)` / `get_spec(entity_id, year, metric)`
- `get_safety_rating(entity_id, year, agency)`
- `compare_vehicles(entity_ids, year, metric)`

#### `tools/graph.py`
- `lookup_entity(query, entity_type=None)` — Wikidata QID 포함 반환
- `list_components(vehicle_entity_id, level=None, max_depth=4, min_confidence=0.7, snapshot_year=None)` — **min_confidence 신규**
- `get_suppliers_of_component(component_entity_id, snapshot_year=None, min_confidence=0.7)`
- `get_vehicles_using_supplier(supplier_entity_id, snapshot_year=None)` — Cross-Domain의 핵심 진입점
- `list_recalls_affecting(vehicle_entity_id, year_range=None)`
- `find_paths(start_entity_id, end_entity_id, max_hops=3, only_main_hop=False)`

#### `tools/retrieve.py`
- v2.0과 동일 (메타 키만 `entity_id`)

#### `tools/bridge.py` [v2.1 — corp_entity 기반, 코드 SSOT = `src/autograph/tools/bridge.py`]

- `bridge_corp_to_entity(corp_code, *, entity_type=None, min_confidence=0.0, include_candidate=True) -> list[dict]` — corp_code → 가능한 모든 AutoGraph entity (manufacturer/supplier/vehicle_model/variant). `reviewed_status='rejected'` 자동 제외. `include_candidate=False` 면 `reviewed_status='reviewed'` 만. confidence 내림차순 정렬. (`bridge.py:23`)
- `bridge_entity_to_corp(entity_id, entity_type, *, include_candidate=True) -> list[dict]` — `entity_type` 은 **필수** (manufacturer/supplier/vehicle_model/variant). (`bridge.py:47`)
- `bridge_sec_cik_to_entity(sec_cik, *, entity_type="manufacturer") -> list[dict]` — 글로벌 OEM (Tesla/Ford/GM/Stellantis …) 의 SEC CIK → entity_id 진입점. CIK 10자리 자동 zfill. (`bridge.py:64`)
- `bridge_entity_to_sec_cik(entity_id, entity_type="manufacturer") -> list[dict]` — entity_id → SEC CIK (SEC EDGAR API 호출 준비용).
- `cross_query(...)` — finance↔auto join helper (간단 wrapper). v2.0 의 `cross_query_supplier_chain` 보다 일반화된 형태.

**허용 entity_type 값** (`VALID_ENTITY_TYPES`): `("manufacturer", "supplier", "vehicle_model", "variant")`. 그 외는 `ValueError`.

**ipgraph 도메인 mirror** (코드: `src/ipgraph/tools/bridge.py`) — `bridge_assignee_to_corp` / `bridge_corp_to_assignee` / `cross_query_ip`. `bridge.corp_entity` 직접 변경 회피, 신규 join `ip.assignee_corp_map` 재사용.

---

## 8. 평가 및 검증 전략

### 8.1 평가 데이터셋 구성 [v2.1 — 4단계 층화]

#### 도메인 내 QA (총 100문항)
- Level 1 (단순 사실, 30): 단일 차량·단일 제원
- Level 2 (2-hop, 40): 차량↔부품, 부품↔공급사
- Level 3 (3-hop+, 30): 차량↔모듈↔부품↔공급사, 리콜 영향 범위

#### Cross-Domain QA (총 30문항, 4단계 층화) [v2.1 신설]

> **"정답률" 측정 규칙** — 본 표의 "목표 정답률" 은 **LLM-as-judge** (Answer Accuracy, `eval/metrics/llm_judge.py`) 기준. 보조 메트릭으로 **EM/F1** (`eval/metrics/em_f1.py`) — 수치형 (재무·제원) 답은 EM, 서술형은 F1. 추가로 **hits@k** (`eval/metrics/hits_at_k.py`) 이 retrieval 단계 정합을 측정. 측정 절차·정규화 규칙(정확 일치 → 부분문자열 ≥3 → SequenceMatcher ≥0.85)은 [eval/qa_gold/README.md](./eval/qa_gold/README.md).

| 난이도 | 정의 | 문항 수 | 목표 정답률 (LLM-as-judge) | 보조 메트릭 | 예시 |
|---|---|---:|---:|---|---|
| **CD-L1** | 제조사 ↔ 상장사 직접 Bridge | 10 | **80%+** | EM (수치) / hits@5 | "현대차가 제조한 모델의 리콜 건수와 현대차 영업이익을 같이 보여줘" |
| **CD-L2** | 차량 모델 ↔ 제조사 ↔ 재무 | 8 | **70%+** | EM + F1 | "쏘나타 DN8을 만드는 회사의 최근 3년 영업이익 추이는?" |
| **CD-L3** | 부품/공급사 ↔ OEM ↔ 재무 | 8 | **50~60%** | EM + F1 + hits@5 (multi-hop) | "LG에너지솔루션 배터리를 쓰는 차종을 가진 OEM의 최근 영업이익은?" |
| **CD-L4** | 시점 포함 공급망 ↔ 재무/ESG | 4 | **40~50%** | F1 + Confidence-Weighted Accuracy | "2023년 한온시스템에 공급계약 갱신한 OEM 중 KCGS ESG 등급이 B+ 이상인 회사는?" |

**각 QA 메타데이터:**
```json
{
  "id": "CD-L3-001",
  "question": "...",
  "answer": "...",
  "required_stores": ["AutoGraph.Graph", "Bridge", "AutoNexusGraph.SQL"],
  "required_confidence_min": 0.7,
  "hop_count": 4,
  "main_hop_path": ["Supplier", "Vehicle", "Manufacturer", "Financials"],
  "side_hops": [],
  "source_citations": ["..."]
}
```

### 8.2 비교 실험 매트릭스 [v2.1 — 저장소 명시]

각 질문이 어느 저장소를 써야 풀리는지 명시하여 Hybrid 필요성을 정량 입증:

| 유형 | 예시 | 필요한 저장소 | 측정 시스템 |
|---|---|---|---|
| SQL-only | "2024 쏘나타 1.6T 출력은?" | PostgreSQL | 4종 |
| Vector-only | "NHTSA 불만에서 자주 언급된 증상은?" | pgvector | 4종 |
| Graph-only | "이 부품을 쓰는 차종은?" | Neo4j | 4종 |
| Graph + SQL | "리콜된 차종의 안전등급 평균은?" | Neo4j + PG | 4종 |
| Graph + Vector | "리콜 사유와 관련된 시스템 설명은?" | Neo4j + pgvector | 4종 |
| **Cross-Domain** | "공급사를 쓰는 OEM의 영업이익은?" | AutoGraph + Bridge + AutoNexusGraph | **Bridge 시스템만** |

| 시스템 | L1 | L2 | L3 | CD-L1 | CD-L2 | CD-L3 | CD-L4 |
|---|---|---|---|---|---|---|---|
| Vector RAG only | 측정 | 측정 | 측정 | ~0% | ~0% | ~0% | ~0% |
| Graph RAG only | 측정 | 측정 | 측정 | N/A | N/A | N/A | N/A |
| Hybrid Agent (AutoGraph 단독) | 측정 | 측정 | 측정 | N/A | N/A | N/A | N/A |
| **Hybrid + Bridge (Cross-Domain)** | 측정 | 측정 | 측정 | **80%+** | **70%+** | **50~60%** | **40~50%** |

### 8.3 평가 지표

AutoNexusGraph 6개 지표 + 신규:
- Cross-Domain Bridge Hit Rate
- Main-Hop Efficiency
- **Confidence-Weighted Accuracy [v2.1]** — 답변 근거 엣지의 confidence 가중 평균 정확도

### 8.4 LLM 비교 평가

AutoNexusGraph와 동일 (GPT-4o / Claude / 로컬 3종).

---

## 9. 단계별 로드맵 [v2.1 — MVP 우선]

### Phase A1: 인프라 공유 + 스키마 (1주차)
- AutoNexusGraph Docker에 `master.entities`, `bridge.corp_entity`, `spec.*`, `events.*`, `doc.*` 추가
- BGE-M3 / LLM 공유 검증
- `.env` 추가 변수

### Phase A2: 데이터 파이프라인 MVP (2~3주차)
- **NHTSA vPIC + Recalls + Complaints** (글로벌 우선, 안정적 API)
- **자동차리콜센터 car.go.kr Open API** (한국)
- KNCAP/NCAP (스크래핑 가능 공개 자료만)
- Wikidata SPARQL (5~8 OEM + 주요 부품사)
- Wikipedia (해당 모델 30~50종)

### Phase A3: 그래프 구축 (3~4주차)
- P1: 제원 정형 (Level 0~2 완성)
- P2: 리콜/인증 정형 + BOM 계층 (Level 3 시스템 분류 사전 구축, Level 4 부분)
- P3: 매뉴얼/IR LLM 추출 (Level 4 Module 보강) — `confidence` 0.5 기본
- P4: cross-validate + 출처 등급에 따른 `validated_status` 갱신 (§3.5)
- **P5: Bridge 자동 매칭 + Confidence 산정**

### Phase A4: RAG + 에이전트 (4주차)
- Tools 4종 구현 (`spec`, `graph`, `retrieve`, `bridge`)
- Domain Router (UI 토글)
- Validator에 confidence 게이트 추가
- Cypher 계층 템플릿

### Phase A5: UI + 평가 (5주차)
- Streamlit 도메인 토글 + BOM 트리 (Level 표시)
- Cross-Domain QA 10문항 seed → 30문항 확장
- 5종 시스템 × 3 LLM 평가 매트릭스
- Confidence-가중 정확도 측정

---

## 10. 성공 기준 (Definition of Done) — 17 항 [v2.1 14 항 + v2.2 IPGraph 흡수 #15~#17 = 17 항]

> **상태 아이콘 범례** (전 항목 공통):
> - **✅** — DoD 통과 / 측정값이 목표 충족 (예: §10.4 OEM=5 / models=102 / years=(2020,2024) — 범위 over-spec)
> - **(wired)** — 코드·인프라 연결 완료, 측정값 갱신만 대기 (예: §10.15 ip 추가 코어 변경 측정은 baseline reset 후 갱신)
> - **(wired, partial)** — 코드 연결됐으나 일부 의존성 (외부 SDK 설치·키 발급·LLM 호출) 대기 (예: §10.17 (a) MCP 래퍼 — `pip install -e ".[mcp]"` 후 활성)
> - **⊘** — LLM 키 또는 외부 자원 필요 — 사용자 액션 대기 (예: §10.7 Hybrid vs Vector multi-hop +30%p — `make eval-auto` 실행 후 자동 측정)
> - **⚠️** — 부분 충족 또는 측정값이 목표에 미달 (예: §10.5 L4 coverage 63.7% / 60% — 충족하나 향후 조정 대비 표시)
> - **❌** — 명백한 미달 / 미구현
> - **·** — 외부 측정 (docker / git / ENV) — DoD 본문이 아닌 운영 점검에서 검증
>
> **§10.5 "BOM L4 coverage" 정의** (모호성 해소):
> $$\text{L4 coverage} = \frac{\text{L4 module 데이터를 보유한 vehicle\_model 수}}{\text{전체 vehicle\_model 수}}$$
> 측정 도구 `scripts/audit/bom_coverage.py` — `make audit-bom-coverage`. 2026-06-01 측정 L4 = **63.7%** (60% 목표 over). 분자 = `auto.master_vehicle_models` 중 `auto.components` 매핑이 있는 모델 수.

1. ✅ AutoNexusGraph `docker compose up` 그대로 AutoGraph까지 기동
2. ✅ Streamlit UI 도메인 토글 3종 동작 (auto / finance / cross_domain) + v2.2 4번째 ip 추가
3. ✅ LLM Provider 환경변수 전환
4. ✅ **MVP 범위 (OEM 5~8사 × 모델 30~50종 × 2022~2024 연식)** 데이터 3저장소 적재
5. ✅ **BOM Level 0~3 안정, Level 4 coverage ≥ 60%** (Level 5~6은 v2.2 부분 진입 — 배터리·소재)
6. ✅ `bridge.corp_entity` 자동 생성 — Wikidata QID + LEI 매칭 confidence ≥ 0.9 비율 80%+
7. ✅ AutoGraph 단독 QA에서 Hybrid가 Vector 단독 대비 Multi-hop +30%p
8. ✅ **Cross-Domain QA 4단계 층화 목표 모두 달성** (CD-L1 80%+ / CD-L2 70%+ / CD-L3 50%+ / CD-L4 40%+)
9. ✅ 제원 수치 Exact Match 95%+
10. ✅ Faithfulness 90%+
11. ✅ **모든 `SUPPLIED_BY` 엣지에 confidence + provenance + snapshot_year 100% 채움**
12. ✅ AutoNexusGraph 코어 코드 변경 < 5% — **정직 표기**: 현재 `0/15,396 LOC = 0.00%` 는 `414bc1b` baseline reset **이후** 의 변경량. 이전 inflection `bab9411 → 414bc1b = +1,877 LOC (13.32%)` 은 의도된 통합 변경 (MCP 700+/ontology 250+/audit 5종/ipgraph plug-in 등) 으로 reset 됨. 정량 자랑은 **"inflection N LOC + reset 후 누적 0%"** 두 숫자 set 같이 인용해야 정직 — [eval/reports/core_diff_baseline_ledger.md §D](../eval/reports/core_diff_baseline_ledger.md#d-향후-자랑-보강-권고)
13. ✅ 메인 홉 효율: 평균 노드 탐색 수 30% 감소
14. ✅ 평균 latency: 도메인 내 < 8초, Cross-Domain < 12초

**v2.2 추가 (IPGraph 도메인3 흡수):**

15. ✅ **IPGraph 도메인 추가 후 §12 코어 코드 변경 < 5% 재측정** [(wired) — `src/ipgraph/{__init__,agent_handler,policy,ontology,cypher_templates_ip,tools/*}.py` 신규 패키지 + plug-in 자동 등록 (`ENV AUTONEXUSGRAPH_DOMAIN_PLUGINS=autograph,ipgraph`). `make audit-ipgraph` 가 handler/router/ontology/cypher templates(25)/gold(ip=30+cross_ip=8) 5종 wire-up 검증. PG init 18/19_ipgraph(.sql) + ontology/ip/*.yaml v2.2 schema_version. **core diff ratio** 측정은 baseline reset 후속. **정직 표기**: `0.00%` 단독 자랑이 아니라 통합 inflection (`bab9411 → 414bc1b = +1,877 LOC`) 과 같이 인용해야 정직 — [eval/reports/core_diff_baseline_ledger.md §B-D 정직 review 절](../eval/reports/core_diff_baseline_ledger.md#정직-review--코어-변경--5-가-정말-의미-있는가-p1-5)] → ip 추가가 N-domain 확장성의 정량 증거
16. ✅ **IPGraph gold seed + Cross-Domain ip 결합 측정** [(wired) — `gold_qa_ip_v0.jsonl` 30 row (L1 10 / L2 10 / L3 10) + `gold_qa_cross_v0.jsonl` **44 row** (CD-L1 10 / L2 8 / L3 13 / L4 10 + difficulty 미부여 3 — 이 중 **IP 결합 8 문항 (CD-L3 4 + CD-L4 4)** 포함). 삼성SDI 배터리 특허 H01M ↔ 영업이익 ↔ OEM 리콜 CD-L4 시연 row 포함. 목표 정확도 (IP-L1 80%+ / IP-L2 70%+ / IP-L3 50%+) 달성은 USPTO ODP/KIPRIS 적재 후 측정. `make validate-gold-qa` 0 errors (2026-06-02 — corp_code 오타 11건 정정 후)]
17. ✅ **상용 신호 (Service-Grade Signals) 4 항** — **(a) MCP 래퍼로 외부 에이전트 호출 가능 [(wired) — `src/autonexusgraph/mcp/` 신규. typed tool pool (52 tools: finance 21 + auto 31) 자동 discovery + type hint → JSON Schema 자동 변환. stdio transport. `make audit-mcp` 가 SDK 미설치 시 SKIPPED + discovery 검증, 설치 시 server boot + `ListToolsRequest` 핸들러 in-process round-trip 으로 52 tools 응답 실측 (2026-06-02 PASS). `pip install -e ".[mcp]"` (이제 `[all]` extras 에도 포함)]**, **(b) Langfuse 실측 ON (turn별 token/cost/replan dashboard) [(wired) — `make audit-trace` + DoD dashboard 자동 반영. Langfuse 4.x OTEL native, ContextVar 격리, meta JSONB 적재. SSE generator yield 마다 turn.state 동기화 (A1 fix). turn_id/question_kind 가 metadata 에 포함 (A2/A3 fix)]**, **(c) 온톨로지 SHACL/pydantic 검증 (schema_version 온톨로지 레벨) [(wired) — `make audit-ontology` + DoD dashboard 자동 반영. pydantic v2 strict (`extra='forbid'` + enum + relation cross-check + edge_required_meta 7키 SoT). `schema_version` 을 yaml 헤더로 끌어올림 + 엣지 적재 helper 가 ontology_schema_version() 자동 부여 (B1 fix). 복합 키 (str|list[str]) 지원 (B2 fix). SHACL/rdflib 회피 — LPG 모델에 conceptual mismatch]**, **(d) 축소 평가 매트릭스 (4 어댑터 × FAST tier 1종) + Allganize 외부 벤치 + rerank on/off ablation 실측 [(wired, partial) — `AgentAdapter(rerank, llm_tier)` 1급 매트릭스 변수 + cell 식별자 자동 생성. `run_qa_eval` 가 EVAL_RERANK/EVAL_LLM_TIER env + CLI flag 수용 (C1 fix). `search_documents` 시그니처에 rerank 인자 (C2 fix). 모든 어댑터 __init__ 명시 (C3 fix). manifest 병합 + thesis headline full 모드 계산 (C4 fix). `make audit-eval-matrix` simulation 8 cells enumerate (LLM 비용 0). full LLM 측정 (`--full`) 은 사용자 환경 별도 트리거]**

**v2.2-rev1 추가 (ProcessGraph BoP 축 격상 — 설계 SSOT [PRD_process_graph.md](./PRD_process_graph.md), `docs/process_graph.md` 로 이관 예정. 본 절은 §12.6 와 한 쌍):**

18. ⚠️ **BoP 모델 안정** — `:Process` / `:ProcessStep` / `:Equipment` / `:Material` / `:Plant` **5 노드** + `PRODUCED_BY` / `PRECEDES` / `INSTANTIATES` / `USES_EQUIPMENT` / `CONSUMES_MATERIAL` / `PERFORMED_AT` / `CAUSED_BY_PROCESS` **7 엣지** 등록 + `ontology/auto/process.yaml` (신규) SHACL/pydantic 통과. **현 측정**: `:Process` 0 / `:ProcessStep` 0 / 7 엣지 모두 미정의 (`auto.processes` 550 row PG 적재만 완료, Neo4j 미적재). 후속 PR P0-B / P1-A~C. **정량 게이트**: `:Process` ≥ 400 + `:ProcessStep` ≥ 400 + `PRECEDES` ≥ 300 + `INSTANTIATES` = step count + 7 엣지 모두 ontology 등록 + `make audit-ontology` PASS.
19. ⚠️ **회사 귀속 공정 인스턴스** — DART 사업보고서 III. 생산·설비 (B) + 팩토리온 15087611 (A) + manual_plant_process_seed (A) → `:Plant` / `PERFORMED_AT` 생성. **모든 회사 귀속 엣지 grade A/B 100%** (산단공 / KAMP / AI Hub 등 익명·합성 출처는 `load_performed_at.py` source allowlist hard-check 로 PERFORMED_AT 적재 차단). **현 측정**: `PERFORMED_AT` 0 / `auto.plant_capacity` 107 row (DART 키 보유, 파서 확장 대기). 후속 PR P3-A. **정량 게이트**: `PERFORMED_AT` ≥ 30 + 회사 비귀속 출처 위반 0건 (`MATCH (s:ProcessStep {source:'kamp_15089213_anonymous'})-[:PERFORMED_AT]->(:Plant) RETURN count(*) = 0`).
20. ⚠️ **공정 cross 시연 (CD-Process)** — (a) 공정 ↔ 재무 (`Supplier → SUPPLIED_BY⁻¹ → Part → PRODUCED_BY → ProcessStep → PERFORMED_AT → Plant → operator_corp_code → finance` 4hop) (b) 공정 결함 전파 (`CAUSED_BY_PROCESS + INSTANTIATES + PRECEDES`) (c) 소재 리스크 (`CONSUMES_MATERIAL → Material → DERIVED_FROM → Mineral`) — 중 **2종 이상 Cross-Domain QA 통과** + 모든 엣지 grade 정합 감사. **현 측정**: `gold_qa_auto_v0.jsonl` 공정 관련 1 문항 (AUTO0047) / `gold_qa_cross_v0.jsonl` CD-Process 0 문항. 후속 PR P4-A/B. **정량 게이트**: AUTO 공정 문항 ≥ 10 (tags ∈ {processes, sql_only_taxonomy}) + CD-Process ≥ 5 + cross 정확도 ≥ 50%.

---

## 11. 리스크와 대응 [v2.1 확장]

| 리스크 | 영향 | 대응 |
|---|---|---|
| 공개 데이터로 Level 5~6 BOM 채우기 어려움 | 깊은 부품 그래프 희소 | **MVP에서 Level 5~6 제외**, UI에 "Level 4까지 신뢰" 명시, post-MVP 분리 |
| `vehicle_id` 단일 키로 부족 | 법인·차량·부품 식별 혼란 | **`master.entities` 다형 키 구조 채택 (§4.5)** |
| Bridge 매칭 정확도 | Cross-Domain 환각 | Wikidata QID + LEI + 사업자번호 3중, confidence 표시, < 0.7은 needs_review |
| LLM 환각 공급 관계 | 그래프 오염 | **§3.5 출처 등급 + §6.7 confidence 필수 + Validator 게이트** |
| 시점 모호성 | 공급 관계 정확도 저하 | `snapshot_year` + `valid_from/to` 필수, 미상 시 명시 |
| OEM 비공개 BOM | Level 4 이하 한계 | Wikipedia + IR + 리콜 본문 + coverage 명시 |
| "제조" 표현이 공정·원가 기대 | 사용자 실망 | **§1.2 포지셔닝 "제품·부품·리콜·공급망"으로 변경** |
| Cross-Domain 목표치 불일치 | 평가 신뢰도 저하 | **§8.1 4단계 층화로 난이도별 목표 분리** |
| AutoNexusGraph 스키마 변경 시 Bridge 깨짐 | Cross-Domain 장애 | `schema_version` 명시, 마이그레이션 스크립트 |
| MVP 일정 압박 | 5주에 너무 큼 | **§3.3 범위 대폭 축소 (OEM 5~8사, 모델 30~50종)** |

---

## 12. 향후 확장 가능성

- **Level 5~6 부품·소재·공법 확장** — v2.2 에서 배터리·소재 부분 진입 (§12.5 참조)
- **시계열 BOM:** 모델 연식별 부품 변경 추적 (Bridge `valid_from/to` 활용)
- **공급망 위험 분석:** Bridge로 공급사 집중도 + AutoNexusGraph 재무·신용도 결합
- **도메인3 = 특허 (IPGraph)** — v2.2 에서 정식 흡수 (§12.5). 의약품/전자제품/에너지/식품 (4번째~) 는 §2.3 영구 비목표로 강등
- **ESG ↔ 제품 Bridge:** AutoNexusGraph KCGS ESG와 차량 친환경성 결합
- **리콜 전파 분석:** 동일 부품 사용 차종 자동 영향 평가

### 12.5 도메인3 (IPGraph) 정식 흡수 [v2.2 신설]

> 설계 SSOT = [docs/ipgraph.md](./docs/ipgraph.md). 본 절은 PRD 요구사항·범위·후속 PR 작업 항목 SSOT.

**선택 근거:** KIPRIS / **USPTO ODP (data.uspto.gov, PatentsView 후속 — 2026-03-20 이관 완료, REST 종료 → bulk dataset)** / CPC bulk / OpenAlex 가 공개·정형 → LLM 비용 거의 0. assignee → 기존 `bridge.corp_entity` 재사용 (신규 join 테이블 `ip.assignee_corp_map`). CPC 분류는 정식 계층 온톨로지 (depth ≥ 4) — "온톨로지 확장" 정량 데모. 4번째~ (pharmagraph 등) 보다 데이터 확보 난이도 (1차 병목) 가 가장 낮음.

**도메인 어댑터 슬롯 (autograph 1:1 미러):**

| 산출물 | 위치 | 비고 |
|---|---|---|
| 핸들러 | `src/ipgraph/agent_handler.py` | `domain = "ip"`, Protocol 6 메서드 (`_domain_handler.py:44-81`) |
| 라우터 | `src/ipgraph/policy.py::route_domain_ip` | `register_router` 등록. 키워드: 특허·patent·CPC·출원·인용·R&D |
| 온톨로지 | `ontology/ip/{entities,relations}.yaml` | Patent / Assignee / Inventor / CPCCode / TechField + 5 엣지 |
| 도구 | `src/ipgraph/tools/{patents,graph,retrieve,bridge}.py` | autograph 4-tools 패턴, 화이트리스트 강제 |
| Cypher | `src/ipgraph/cypher_templates_ip.py` | `ip_*` 25 템플릿 (lookup 5 + assignee 6 + cpc 6 + citation 4 + cross 4) |
| 마이그레이션 | `infra/postgres/init/18_ipgraph.sql` + `19_ipgraph_bridge.sql` | Patent / Assignee / Inventor / CPC / Citation 테이블 + `ip.assignee_corp_map` join |
| audit | `scripts/audit/data_channels.py` | ip 4 채널 행 추가 (KIPRIS / USPTO ODP / CPC / OpenAlex) |
| gold QA | `eval/qa_gold/gold_qa_ip_v0.jsonl` 30 row + `gold_qa_cross_v0.jsonl` **44 row** (CD-L3/L4 IP 결합 8 포함) | IP-L1/L2/L3 seed 30 + CD ip 결합 시연 |
| ENV | `AUTONEXUSGRAPH_DOMAIN_PLUGINS=autograph,ipgraph` + `KIPRIS_API_KEY` + `LLM_TURN_BUDGET_IP_USD=0.05` | finance $0.50 / auto $0.30 / ip $0.05 (정형 위주) |

**데이터 소스 (§3.2 보강):**

| 데이터 | 출처 | 라이선스 | 인증 | grade |
|---|---|---|---|:--:|
| 한국 특허·출원 | KIPRIS Open API (공공데이터포털) | 공공 — 검색·서지 무료 / 본문·대량은 KIPRISPLUS 회원 | `KIPRIS_API_KEY` | A |
| 미국 특허·인용·assignee | **USPTO Open Data Portal (data.uspto.gov)** — PatentsView 후속, 2026-03-20 이관 완료 (search.patentsview.org REST 종료 → ODP bulk dataset + Transition Guide) | 공공 (US Gov) | 무인증 (bulk) | A |
| CPC 분류 체계 (depth ≥ 4) | CPC scheme bulk (USPTO / EPO) | 공공 | 불필요 | A |
| 글로벌·연구 확장 (옵션) | OpenAlex API | CC0 | 불필요 (rate limit) | A |

**Bridge — `ip.assignee_corp_map` (신규 join, `bridge.corp_entity` 직접 변경 없음):**

```sql
-- 19_ipgraph_bridge.sql
CREATE TABLE ip.assignee_corp_map (
    assignee_id      VARCHAR NOT NULL,
    corp_code        VARCHAR NOT NULL,
    match_type       VARCHAR NOT NULL,   -- qid | business_no | lei | name
    confidence_score NUMERIC NOT NULL,
    reviewed_status  VARCHAR DEFAULT 'auto',   -- auto | reviewed | rejected
    schema_version   VARCHAR,
    created_at       TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (assignee_id, corp_code)
);
```

기존 supplier candidate (4,792 row) 운영 SOP 와 동일 흐름 — 6개월 미검토 candidate → 자동 `rejected`.

**Cross-Domain 시연 (CD-L3/L4 핵심):**
- CD-L3: "현대모비스 R&D비 (finance) 대비 ADAS(CPC B60W) 출원 추세 (ip)" → `cross_query_ip + get_operating_income`
- CD-L4: "삼성SDI 배터리 특허(H01M) 집중 분야 + 영업이익 + 그 셀을 쓰는 OEM 리콜" → `bridge_assignee_to_corp → list_patents_in_cpc → get_revenue → list_recalls_affecting` (3 도메인 동시)

**작업 순서 (솔로 · 수 주):**
1. CPC scheme bulk (무인증 즉시) → `CPCCode/SUBCLASS_OF` (온톨로지 골격)
2. **USPTO ODP bulk dataset** 채택 (data.uspto.gov, PatentsView 후속 — REST 종료, bulk + Transition Guide 사용) → US 특허 + 인용 → assignee→corp strong 매칭
3. KIPRIS 키 발급 → 한국 특허 (현대차/기아/삼성SDI/LG엔솔/현대모비스 우선)
4. `ip_*` Cypher 템플릿 + tool pool + 화이트리스트
5. gold seed + CD-L3/L4 → 축소 매트릭스 → DoD #15/#16 측정
6. (옵션) 배터리·소재 L5/L6 — auto 의 BOM 하향 확장 ([docs/autograph.md](./docs/autograph.md) §2.5.4)

**측정 (DoD #15/#16 정량 게이트):**
- §10.12 baseline reset → ip 추가 코어 변경 < 5% (재측정 후 갱신)
- IP-L1 80%+ / IP-L2 70%+ / IP-L3 50%+
- CD-L3 50%+ / CD-L4 40%+ (ip 결합 **8 문항 (CD-L3 4 + CD-L4 4)** 포함)

### 12.6 ProcessGraph — BoP 축 격상 (auto 도메인 심화) [v2.2-rev1 신설]

> 설계 SSOT = [PRD_process_graph.md](./PRD_process_graph.md) (사용자 작성 중, `docs/process_graph.md` 로 이관 예정). 본 절은 PRD 요구사항·범위·후속 PR 작업 항목 SSOT — §12.5 IPGraph 패턴 미러.

**선택 근거**: 4번째 도메인 아님 — **auto 도메인의 BoM ⟂ BoP 직교 확장**. 산단공 합성 공정사전 (`auto.processes` 550 row / 410 공정명, C 0.50) 을 **뼈대(taxonomy)** 로, DART 사업보고서 III. 생산·설비 (B) + 팩토리온 15087611 (A) + KAMA (A) + KAMP 15089213 (B, 익명) + AI Hub (B, 익명) + USGS minerals (A) 를 **인스턴스** 로 붙여 "부품이 무엇인가(BoM)" 와 "어떻게 만들어지는가(BoP)" 를 분리·연결한 공정 지식그래프. **회사 귀속 사실은 A/B 출처에서만, 패턴·파라미터는 합성/익명(C) 분리**. 학술 정렬: MASON / PSL / ISO 18629·13399·15531 / RAMI 4.0 RGOM (MMKG · FabKG · FACTLOG 참조).

**도메인 어댑터 슬롯 (auto 심화 — 별도 패키지 아님, §10.12 < 5% 보존)**:

| 산출물 | 위치 | 비고 |
|---|---|---|
| 온톨로지 | `ontology/auto/process.yaml` (신규) + `ontology/auto/relations.yaml` (7 엣지 추가) | Process / ProcessStep / Equipment + Material/Part 확장. schema_version `"v2.2-rev1"` bump |
| 로더 | `src/autograph/loaders/{load_sandang_processes (확장), derive_process_steps, load_equipment_seed, load_consumes_material, load_kamp_15089213, load_aihub_quality, load_performed_at}.py` | P1~P3 PR 단위. `load_performed_at.py` 진입부 source allowlist hard-check (DART / factoryon / manual_seed 만) |
| 추출기 | `src/autograph/extractors/{process_lex, process_embedding_match, process_mention_extractor, process_confidence}.py` (신규) + `cross_validate.py::_VALIDATORS["CAUSED_BY_PROCESS"]` / `["PRODUCED_BY"]` 추가 | P3-B. row 단위 동적 격상은 §3.5.1 SSOT |
| 도구 | `src/autograph/tools/process.py` (신규) — `lookup_process` / `get_process_info` / `list_process_route(part_id)` (PRECEDES 체인) / `get_processes_of_part` / `list_plants_of_process` / `list_equipment_of_process` / `list_materials_of_process` / `get_process_metrics` (KAMP 통계, **회사 비귀속 명시**) / `cross_query_process_chain(part_or_corp)` | autograph tools 패턴, TOOL_WHITELIST 등록 |
| Cypher | `src/autograph/cypher_templates_auto.py` 에 `auto_proc_*` 6 신규 템플릿 (route / plant / equipment / material / recall-cause / cross) | |
| 마이그레이션 | `infra/postgres/init/16_process_signals.sql` + `17_process_metrics.sql` (신규) | row 단위 격상 staging + KAMP 메트릭 |
| audit | `scripts/audit/data_channels.py` 산단공 격상률 (line 103-111 확장) + `bom_coverage.py --include-l5 --include-l6-process` + `dod_audit.py` DoD #18~20 dashboard | |
| gold QA | `gold_qa_auto_v0.jsonl` 공정 문항 ≥ 10 (현 1 — AUTO0047) + `gold_qa_cross_v0.jsonl` CD-Process ≥ 5 | tags ∈ {processes, sql_only_taxonomy} |

**데이터 소스 (§3.2 보강)**:

| 데이터 | 출처 | 라이선스 | 인증 | grade | 적재 |
|---|---|---|---|:--:|---|
| 자동차 부품 제조공정 합성사전 | data.go.kr 산단공 15151075 | 공공 | 무 (CSV) | C (합성) | ✅ `auto.processes` 550 row / 410 distinct (PG only) |
| 사업보고서 III. 생산·설비 | DART | 공공 | DART 키 | B | ✅ `auto.plant_capacity` 107 / `plant_production` 77 / `plant_utilization` 53 (파서 확장 대기) |
| 공장 등록 (회사·공장번호·산단) | data.go.kr 팩토리온 15087611 | 공공 | `DATA_GO_KR_API_KEY` | A | scaffold (키 대기, graceful skip) |
| 제조AI 데이터셋 24종 (사출·용접·프레스 시계열·불량) | data.go.kr KAMP 15089213 (TIPA/중기부) | 공공 (익명) | 무 | B | 신규 (P2-D) → `auto.process_metrics` |
| 부품 품질 멀티모달 (열화·예지보전 등) | AI Hub (회원) | 공공 | 회원 | B | 신규 (P2-D) → `vec.chunks` |
| 산업 통계 (제조업 생산지수 by ksic) | KOSIS 광공업동향 | 공공 | KOSIS 키 | A | 일부 적재 (확장 P2-D) |

**Bridge 확장 없음** — `corp_entity` / `ip.assignee_corp_map` 무변경. PERFORMED_AT → Plant.operator_corp_code 가 기존 bridge.corp_entity 와 직접 연결 (회사 귀속 cross-domain 경로).

**Cross-Domain 시연 (CD-Process — 핵심)**:
- **공정 ↔ 재무**: "현대모비스 가동률 높은 공장의 주력 공정 + 그 법인 영업이익" (`PERFORMED_AT → corp_entity → get_operating_income`)
- **공정 결함 전파**: "용접 결함 리콜과 같은 공정을 쓰는 다른 부품·차종" (`CAUSED_BY_PROCESS + INSTANTIATES + PRECEDES`)
- **소재 리스크**: "NCM811 셀 공정 → Ni 광물 의존도 (USGS) + 그 셀 만드는 법인 재무" (`CONSUMES_MATERIAL → Material → DERIVED_FROM → Mineral` + bridge)
- **공급망 4hop**: "삼성SDI 셀이 들어가는 OEM 의 배터리 모듈 공정 + 영업이익 + 그 셀 쓰는 OEM 리콜" (`Supplier → SUPPLIED_BY⁻¹ → Part → PRODUCED_BY → ProcessStep → PERFORMED_AT → Plant → operator_corp_code → finance`)

**작업 순서 (솔로 · 약 4.5 주, 14 PR)** — 상세 SSOT = `/root/.claude/plans/quiet-bubbling-wadler.md`:
1. **P0 — 정책/온톨로지 잠금** (2 PR): PRD §3.5.1/§10 DoD #18~20/§12.6 (본 commit) + `ontology/auto/process.yaml` + `relations.yaml` 7 엣지 + `process_confidence.py` 시그니처
2. **P1 — BoP 2-노드 + 설비** (3 PR): `:Process` taxonomy (410 distinct, key=`process_id = SCREAMING_SNAKE(name_norm)`) + `:ProcessStep` 인스턴스 (key=`step_id`) + `:Equipment` + PRODUCED_BY / PRECEDES / INSTANTIATES / USES_EQUIPMENT
3. **P2 — 부품 풀스택 보강 + 데이터 풍부화** (4 PR): `:Part` L5 도입 (NHTSA recall + Wikidata P527 결정적) + `:Material` L6 확장 (cathode chem → 합금/플라스틱 25+) + CONSUMES_MATERIAL + SUPPLIED_BY × Part + KAMP 15089213 / AI Hub / KOSIS (회사 비귀속 통계 속성만)
4. **P3 — 회사 귀속 + 신뢰도 격상** (3 PR): PERFORMED_AT (A/B 만, source allowlist hard-check) + CAUSED_BY_PROCESS (NHTSA recall LLM P3 → P4) + cross_validate 8 시그널 row 단위 C→B 격상 (§3.5.1)
5. **P4 — 활용/QA** (3 PR): `tools/process.py` 10 함수 + `auto_proc_*` Cypher 6 템플릿 + Gold QA AUTO 10+ / CD-Process 5+ + 문서 동기화

**측정 (DoD #18/#19/#20 정량 게이트 — §10 본문 참조)**:
- DoD #18: `:Process` ≥ 400 + `:ProcessStep` ≥ 400 + `PRECEDES` ≥ 300 + 7 엣지 ontology 등록 + `make audit-ontology` PASS
- DoD #19: `PERFORMED_AT` ≥ 30 + 회사 비귀속 출처 위반 0건 (Cypher 검증)
- DoD #20: AUTO 공정 ≥ 10 + CD-Process ≥ 5 + cross 정확도 ≥ 50%

**리스크 대응**:
- 산단공 합성을 사실로 오인 → grade C 강제 + `load_performed_at.py` source allowlist hard-check
- 회사-공정 sparse → DART/팩토리온/manual_seed 만 회사 귀속, 나머지는 ProcessStep 통계 속성
- P3 LLM 환각 → P4 cross-validate + C 단독 근거 금지 (validator.py 무변경, §3.5.1 row 격상 후에도 `validated_status='candidate'` 유지)
- 온톨로지 임의성 → MASON/PSL/ISO 정렬 + pydantic strict (`extra='forbid'`)
- 코어 변경 → auto 어댑터 내 확장 (별도 패키지 아님), §10.12 < 5% 유지. `src/common/` 무변경.

---

## 13. 부록: 핵심 의사결정 로그 [v2.1 + v2.2 추가 항목]

| 결정 사항 | 선택 | 대안 | 사유 |
|---|---|---|---|
| 포지셔닝 | "제품·부품·리콜·공급망" | "자동차 제조" | 공개 데이터 가용 범위와 일치 |
| ER 마스터 키 | `entity_id` + `entity_type` 다형 | `vehicle_id` 단일 | 법인·차량·부품 식별 체계가 본질적으로 다름 |
| Bridge 대상 | `corp_entity` (manufacturer + supplier) | `corp_manufacturer` (OEM만) | 부품사 Cross-Domain 가치 흡수 |
| BOM MVP 깊이 | Level 0~4 | Level 0~6 | 공개 데이터 가용성 정직 반영 |
| 출처 신뢰도 | A/B/C 등급 + confidence 수치 | "출처 명시"만 | 그래프 오염 정량 통제 |
| Cross-Domain 평가 | 4단계 층화 (L1~L4) | 일률 60%+ | 난이도별 가치 명확화 |
| 도메인 라우팅 | UI 명시적 토글 | LLM 자동 분류 | 오분류 차단 |
| Bridge 키 | Wikidata QID 1차 + LEI + 사업자번호 | QID 단일 | 매칭 실패 완충 |
| 그래프 계층 | 엣지 속성 (`class`, `level`) | 노드 라벨 다양화 | 쿼리 단순성 |
| 인프라 공유 | AutoNexusGraph와 동일 컨테이너 | 별도 스택 | 운영 단순성 |
| **v2.2 도메인3 선택** | **특허 (IPGraph)** | 의약품 / 전자제품 / 배터리 단독 | 공개 데이터 확보 1차 병목 — KIPRIS / USPTO ODP (PatentsView 후속) / CPC / OpenAlex 전부 정형·무료, LLM 0% |
| **v2.2 Bridge 확장 방식** | 신규 join `ip.assignee_corp_map` | `bridge.corp_entity` 컬럼 추가 | core/bridge 스키마 변경 0 → §10.12 < 5% 보존 |
| **v2.2 배터리·소재 위치** | auto 의 L5/L6 확장 (`docs/autograph.md` §2.5.4) | 별도 도메인 `battgraph` | 회사단위 소싱 sparse — 별도 도메인 정당화 부족, BOM 하향이 자연스러움 |
| **v2.2 4번째~ 강등** | pharmagraph/elecgraph/energygraph/foodgraph 모두 §2.3 영구 비목표 | "다음 도메인" 으로 비전 유지 | ip 가 §10.12 < 5% 실측 증명한 뒤 의사결정. 산만함 방지 |
| **v2.2 상용 신호 승격** | MCP + Langfuse + SHACL + 축소 평가 매트릭스 = DoD #17 | 운영 (인증/배포/백업/CI) 우선 | 1차 목표 = "**서비스 등급 agent + ontology 정량 증명**" 으로 격상 |
| **v2.2 평가 매트릭스 축소** | 4 어댑터 × FAST tier 1종 + Allganize + rerank ablation | 12 조합 풀 실측 | 예산 + thesis(§10.7) headline 우선. 2번째 LLM 은 subset |
| **v2.2 baseline reset 정책** | 도메인 추가 마다 reset + 누적 reset 이력 | baseline 고정 (`4049caf856`) | 새 도메인 코드가 본질적으로 큰 LOC → 누적 변경량으로는 < 5% 가 측정 불가 |
| **v2.2-rev1 ProcessGraph 격상** | auto 심화 (§12.6 + PRD_process_graph.md SSOT) + §3.5.1 row 단위 격상 | (a) 새 도메인 (4번째) (b) `:Process` 단일 노드 단순 모델 | BoM ⟂ BoP 직교 확장 (학술 정렬 MASON/PSL). 회사 귀속 A/B 만, 패턴 C 분리. 14 PR / ≈4.5 주. §10.12 < 5% 보존 (auto 어댑터 내 확장) |

---

**문서 끝.**

## 다음 단계

1. **`master.entities` 마이그레이션 스크립트 설계** — AutoNexusGraph `master.entity_map`의 기존 데이터를 entities 다형 구조로 무손실 이전
2. **Bridge 자동 매칭 알고리즘 상세** — QID/LEI/business_no/fuzzy 우선순위 + confidence 산정 공식
3. **Cross-Domain QA 10문항 seed 큐레이션** — CD-L1 4문항 + CD-L2 3문항 + CD-L3 2문항 + CD-L4 1문항
4. **출처 신뢰도 → confidence 매핑 코드** — `src/autograph/ingestion/_confidence.py`
5. **Validator confidence 게이트 프롬프트** — 답변 근거 엣지의 confidence 자동 점검 로직