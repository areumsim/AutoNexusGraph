# ProcessGraph — 제조 공정(BoP) 축 · auto 도메인 수직 심화 · 주요 축 · 설계+구현 SSOT (v3.0)

> **단일 SSOT** = 본 문서. README + PRD 통합 v3.0 (2026-06-02) 에서 PRD_process_graph.md 흡수 후 단일화. 모델링 청사진·학술 근거·로드맵·구현 현황 모두 본 문서에서 다룬다.
> **요구사항·DoD·작업 항목 SSOT** = [README §10.18~20](../README.md#10-dod-definition-of-done--20-항).

**위계 (README §0):** ProcessGraph 는 auto 도메인의 **수직 심화 = 본체 일부**. BoM(부품 = 무엇)과 BoP(공정 = 어떻게)가 직교 축. "주요 축 (1급 BoM⟂BoP 모델 + sparse 인스턴스)" = 모델은 적재 완료(`:Process` 410 / `:ProcessStep` 550 / `INSTANTIATES` 550 / `PRECEDES` 410, C grade), 회사 귀속 인스턴스는 데이터 대기.

새 도메인이 아니라 **auto 도메인의 BoM ⟂ BoP 직교 확장**. "부품이 무엇인가(BoM)" 와
"어떻게 만들어지는가(BoP)" 를 분리·연결. core/finance/ip 무변경, 확장은 `src/autograph` +
`ontology/auto/*` 한정 (§10.12 < 5% 보존, 별도 패키지 아님).

**핵심 등급 정책 (README §4.0 + §4.0.1 row 단위 격상)**: 회사 귀속 사실("X사가 Y공정/공장 수행")은 **DART(B)/팩토리온(A)
에서만**. 산단공·KAMP·AI Hub(합성·익명)는 회사 귀속 엣지 **절대 금지** — `:ProcessStep` 통계
속성으로만. 모든 엣지 7키 메타 의무, grade A(0.95)/B(0.80)/C(0.50), C 단독 근거 금지.

---

## 1. 모델 (ontology/auto/{entities,relations}.yaml)

별도 `process.yaml` 없음 — 기존 SSOT 2파일 확장(로더/감사 무수정 자동 동작).

**노드**: `Process`(공정유형 taxonomy, key=`process_name_norm`) · `ProcessStep`(부품별 공정 단계
인스턴스, key=`step_id`) · `Equipment`(설비, key=`code`, scaffold). `Material`/`Plant`/`Mineral`
은 기존 정의 재사용.

**엣지 (7)**: `PRODUCED_BY`(Part→ProcessStep) · `PRECEDES`(ProcessStep→ProcessStep, 순서) ·
`INSTANTIATES`(ProcessStep→Process) · `USES_EQUIPMENT` · `CONSUMES_MATERIAL`(→L6) ·
`PERFORMED_AT`(ProcessStep→Plant, **회사 귀속 A/B 만**) · `CAUSED_BY_PROCESS`(Recall→Process, P3).
grade 는 `confidence_default`(float) 로 인코딩(`grade` 키 없음). pydantic `extra='forbid'` 강제.

## 2. 구현 현황 (2026-06-02, 정직)

| 산출물 | 적재 | grade | 코드 | 상태 |
|---|--:|:--:|---|---|
| `:Process` | **410** | C | `loaders/load_auto_process_nodes.py` | ✅ |
| `:ProcessStep` | **550** | C | `loaders/load_auto_process_routes.py` | ✅ |
| `INSTANTIATES` | **550** | C | 〃 | ✅ 7키 100% |
| `PRECEDES` (선형 체인) | **410** | C | 〃 | ✅ 7키 100%, depth cap 질의서 *0..10 |
| `PERFORMED_AT` | **94** | B(35)+A공장/candidate공정(59) | `load_performed_at.py` + `load_factoryon_plants.py` | ✅ manual_seed 35 validated + factoryon 59 candidate |
| `PRODUCED_BY` | **46** | C(candidate) | `loaders/load_produced_by.py` | ✅ :Part system→공정 추론 (candidate 0.50, 외주=의장) |
| `CONSUMES_MATERIAL` / `USES_EQUIPMENT` | 0 | — | — | ⏳ 산단공 소재·설비 정보 부재 |
| `CAUSED_BY_PROCESS` | **96** | C(candidate) | `loaders/load_recall_process_map.py` | ✅ 한글 리콜 결함→공정 (deterministic 키워드+결함지시어, conf 0.50) |
| `auto.process_metrics` (KAMP) | 0 rows | B | `loaders/load_kamp_process_metrics.py` + `init/25_*.sql` | ⏳ scaffold (corp_code 부재=익명) |

**기존 재사용 (회사 귀속·자원, 이미 grade 정합)**: `MANUFACTURED_AT` 99(B) + `OWNS_PLANT` 53(A)
= 회사→공장 ; `MADE_OF` 8(B) + `DERIVED_FROM` 17(A) = Module→Material→Mineral L6 체인.

## 3. 도구·Cypher (tools/process.py · auto_proc_*)

- **동작(실데이터)**: `lookup_process` · `get_process_info` · `list_process_route`(PRECEDES) ·
  `list_steps_of_process`. Cypher: `auto_proc_route`/`auto_proc_info`/`auto_proc_steps_of_process`.
- **ready·빈결과(출처 부재)**: `list_plants_of_process` · `list_materials_of_process` ·
  `get_process_metrics`. (비활성 엣지 템플릿은 `ontology_validate` 가 거부 → 미등록, 함수는 `[]`.)

## 4. 평가 (eval/qa_gold)

`gold_qa_auto_v0.jsonl` 공정 L1~L3 **10문항** + `gold_qa_cross_v0.jsonl` **CD-Process 5문항**
(answerable 8 + 정직 `is_answerable=false` refusal 7). cross 실증 2종: **소재 리스크**
(Battery Pack→NCM811→[Ni,Co,Mn,Li]) · **생산 vs 거시**(가동률↔KAMA). 축소 매트릭스 simulation PASS.

## 5. 감사

- `python3 scripts/audit/ontology_validate.py` — 스키마 + cypher↔relations 화이트리스트(enabled 엣지만).
- `make audit-edge-meta` (`--strict`) — 7키 + grade 정합 + 회사귀속 위반 0. `edge_meta_invariants.py`
  의 auto 라벨 화이트리스트에 `Process/ProcessStep/Equipment` 추가(BoP 엣지 포함 감사).

## 6. DoD ([README §10 #18~20](../README.md#10-dod-definition-of-done--20-항))

- **#18 BoP 모델**: ✅ 달성 (410/550/410 + 7엣지 + audit PASS).
- **#19 회사 귀속 인스턴스**: ✅ 충족 (PERFORMED_AT **94** ≥ 30; 비귀속 위반 0 ✅). (a) `load_performed_at.py`+`performed_at_seed.yaml` manual_seed **35 validated**(B, 한국 OEM 9공장 × 4대공정+파워트레인). (b) `load_factoryon_plants.py` factoryon **59 candidate**(:Plant A등급 + 업종→공정 추론 conf 0.60 — plant A등급을 추론 공정엣지에 전가 금지). :Plant 29→103, OWNS_PLANT 53→60. ontology PERFORMED_AT `enabled:true`.
- **#20 공정 cross + 내부 데이터 수용 규격**: ⚠️ 부분 (AUTO 10·CD 5 ✅; cross 실증 2종 answerable, 2종 refusal). **수용 규격 = `load_performed_at.py` source allowlist hard-check + `process_confidence.py` row 단위 격상 (8 시그널 C→B/A)** — 내부 데이터 들어오면 코드 변경 없이 즉시 적재 가능.

## 7. 활성화 트리거 (보류분 해소 조건)

| 보류 | 트리거 |
|---|---|
| PERFORMED_AT 확대 | DART 생산·설비 파생 + factoryon 90행 plant 매칭 (현 35 = manual_seed 9 OEM 공장) |
| process_metrics (cycle_time/yield) | KAMP 15089213 CSV 확보 → `load_kamp_process_metrics.py` |
| CAUSED_BY_PROCESS | KOTSA 한글 리콜(키) 또는 영문 공정 taxonomy → P3+P4 |
| PRODUCED_BY / CONSUMES_MATERIAL | 부품↔공정·공정↔소재 결정적 매핑 출처 |

---

## 8. 학술 근거 (설계 정당화)

본 BoP 모델은 임의 설계가 아니라 다음 학술·표준 정렬:

- **공정 KG 2층 구축**: 머시닝 공정 KG 논문(2025)은 schema layer (top-down 온톨로지) + data layer (bottom-up 엔티티추출) 를 Neo4j 에서 매핑해 공정 경로 추천을 구현 — 본 설계의 2층 구조 근거 (§3 schema + data layer 분리).
- **BoP = directed graph**: state node(부품/재고)와 task node(공정)를 교대 연결하면 각 경로가 BoM + bill of resources 를 정의 (USPTO 6347256). → `(:Part)-[:PRODUCED_BY]->(:ProcessStep)` 모델의 정당화.
- **제조 온톨로지 표준**:
  - **MASON** (OWL, 제품·공정·operation·자원·도구·인력) — 본 ontology 의 `:Process` / `:ProcessStep` / `:Equipment` / `:Material` 분리 베이스
  - **PSL (Process Specification Language)** — 공정 순서·자원 의미론. `PRECEDES` 엣지의 직접 baseline
  - **ISO 18629** PSL 계열 / **ISO 13399** 절삭공구 / **ISO 15531** 제조관리 데이터
  - **AMO** (process · material · information)
  - **ADACOR** (분산 제조 제어 → 도구 화이트리스트 패턴)
- **자동차 제조 KG 요구사항**: Mercedes-Benz BIW assembly KG 평가 + **RAMI 4.0 기반 RGOM** 참조 모델 — Industry 4.0 표준 정렬.
- **재무 결합 사례**: **FACTLOG** (Horizon 2020) cognitive twin — 자동차 OEM 생산계획·수요예측 KG. 본 시스템의 cross-domain 추론 (공정 ↔ 재무) 의 학술 baseline.
- **데이터 소스 보강 패턴**: **MMKG** (금속재료 KG, DBpedia/Wikipedia 활용) + **FabKG** (SME 제조과학 KG, structured+unstructured 혼합) — 본 시스템의 vec.chunks 보강 패턴 (manuals + IR + recall 본문) 와 일치.

> 따라서 "임의 설계" 가 아니라 **MASON/PSL/ISO 18629·13399·15531 / RAMI 4.0 RGOM** 정렬. pydantic strict + `make audit-ontology` 가 학술 정렬 invariant 강제.

## 9. 부록 — 적용하면 좋을 최신 기술 (미적용, 참고)

본 단계에는 도입하지 않은 최신 연구. 향후 ProcessGraph 가 회사 귀속 인스턴스를 확보한 뒤 단계적으로 도입 검토.

- **LLM 기반 KG 구축 (2024–2025)** — **ATLAS** (Automated Triple Linking And Schema induction) 류: 문서에서 triple 추출 + schema induction 자동화. P3 추출 고도화 시 참조 (비용·환각 게이트 유지 — `validator.py` `LOW_CONFIDENCE_THRESHOLD=0.5` 보존).
- **Cognitive twin / 동적 KG** — **FACTLOG** 류: 생산계획·수요예측을 KG 위 추론으로. 거시·가동률 결합 확장 시 참조 (KAMA + DART 가동률 + KOSIS 광공업동향 → 시점 정합 추론).
- **RAMI 4.0 / RGOM** — Industry 4.0 참조 아키텍처 기반 일반화 온톨로지. 표현력 확장 시 참조 — Asset Administration Shell (AAS) 호환성, 잠재적 외부 시스템 통합.
- **FabKG / MMKG** — SME 제조과학·금속재료 KG. structured + unstructured 혼합, DBpedia/Wikipedia 보강 패턴 — 본 시스템의 wiki.chunks + manuals.chunks 보강 패턴과 일치, 추가 외부 KG cross-link 검토 시 참조.
