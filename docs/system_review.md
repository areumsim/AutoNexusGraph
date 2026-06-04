# System Review — 한계 통합·자랑 vs 실제·시급도 매트릭스

> **본 문서의 위치**: 시스템의 한계가 흩어진 3 곳 (`data_inventory.md §3 B-issue` 운영 이슈 + `mental_model.md §5` 설계 이슈 + `README §11` 개발 백로그) 을 통합 cross-link + 시급도 매트릭스 + "자랑 vs 실제" 솔직 review.
>
> **목적**: 외부 평가자 / 본인 회고 / 신규 합류자가 시스템을 **칭찬 없이 솔직히** 보는 진입점. 칭찬은 README §1~§10 이 다 한다 — 본 문서는 의도적으로 **냉정**.
>
> cold review 출처: 2026-06-02 사용자 review.

---

## 1. 한계 통합 — 3 문서 cross-link

### 1.1 한계 카테고리 매핑

| 카테고리 | 출처 문서 | 항목 수 | 본 review 의 우선순위 |
|---|---|---:|---|
| **운영 이슈** (B-issue) | [data_inventory.md §3](data_inventory.md) | 11 (8 해결 + 4 미해결) | 미해결 4 건 모두 §2 표 |
| **설계 이슈** (열린 질문) | [mental_model.md §5](mental_model.md) | 11 (§5.1~§5.10 + §5.11 우선순위) | §5.12 통합 우선순위 표 흡수 |
| **개발 백로그** | [README §11](../README.md) | 8 (§11.1~§11.7 + §11.8) | §11.1 (P0+ 상용 신호) 가 최우선 |
| **자랑 vs 실제** | 본 문서 §3 | 7 항목 | 본 문서 단독 |

### 1.2 한계 통합 표 (한계의 뿌리 — 데이터 / 설계 / 운영)

| 한계 표현 | 뿌리 | 출처 (한계 정의 문서) | 출처 (해결 후보 문서) | 시급도 |
|---|---|---|---|---|
| `SUPPLIED_BY` 30 edges 가 manual seed (P176 rate-limit) | 데이터 | [autograph.md §5.1](autograph.md) / data_inventory §3 B7 | [data_inventory.md §3 B7 해결 후보 4개](data_inventory.md) + system_review §3 (자랑 vs 실제) | ⭐⭐⭐ P0 |
| `confidence_score` 정량 calibration 미검증 | 설계 | mental_model §5.2 + §5.12 | [learning_guide §11.4.0 Platt routine](learning_guide.md) + README §4.0 (cross-link 완료) | ⭐⭐⭐ P0 |
| gold QA 자기충족 (외부 큐레이터 0%) | 설계 + 운영 | mental_model §5.7 + §5.12 | [gold_qa_guide §6 외부 큐레이터 30% 정책](gold_qa_guide.md) | ⭐⭐⭐ P0 |
| Bridge candidate 4,790 영속 누적 (검토 SOP 미설계) | 운영 | mental_model §5.3 + §5.12 + data_inventory §3 B10 | README §11.4 P1 | ⭐⭐⭐ P0 |
| `:Supplier` Neo4j 노드 중복 (PG 4,812 vs Neo4j 9,642) | 운영 | data_inventory §3 B10 | data_inventory §3 B10 해결 후보 3개 | ⭐⭐ P1 |
| ip 도메인 `gold_answer` 비어있음 (gold_qa_ip 30 row) | 데이터 | gold_qa_guide §1 / mental_model §5.12 | KIPRIS_API_KEY + USPTO ODP bulk (data_lineage §5.4 P0) | ⭐⭐ P1 |
| BOM L5 `:Part` 0 노드, L6 부분 | 데이터 | autograph.md §5 / data_sources.md §6 | data_lineage §5.4 P0 (plants.yaml 확장) + autograph §2.5.4 | ⭐⭐ P1 |
| Cross-Domain QA "정답" 시점 정의 모호 | 설계 | mental_model §5.8 + §5.12 | gold_qa_guide §2.3 (snapshot_year 강제) | ⭐⭐ P1 |
| NHTSA complaint 65% 매칭 실패 (B11) | 데이터 | data_inventory §3 B11 | data_inventory §3 B11 해결 후보 2개 | ⭐ P2 |
| AI-Hub aggregate model name mismatch (B6) | 데이터 | data_inventory §3 B6 | data_inventory §3 B6 해결 (현재 정합 양호) | ⭐ P2 |
| "코어 변경 < 5%" 의 baseline reset 의존 정직성 | 설계 | mental_model §5.12 P0+ | [core_diff_baseline_ledger §D 정직 review (완료)](../eval/reports/core_diff_baseline_ledger.md) | ⭐ P2 |
| API 인증 없음 (`/chat` 등 5 endpoint open) | 운영 | README §11.2 P1 | README §11.2 P1 운영 보안 백로그 | ⭐⭐ P1 (외부 노출 시) |
| 동명이인 충돌 (`(name, birth_year)` 키만) | 설계 | mental_model §5.6 + §5.12 | (name, birth_year, 회사) 보조 키 + faq Q6.3 HITL clarification | ⭐ P2 |

→ **모두 합쳐 P0 4건 / P1 5건 / P2 4건 = 13 한계.** 본 표가 시스템 전체 한계의 **단일 진입점**.

---

## 2. B-issue 미해결 4 건 — 우선순위 종합

| ID | 한 줄 | 영향 | 시급도 | 해결 추정 비용 |
|---|---|---|---|---|
| **B7** | Wikidata P176 rate-limit (1 req/min) → staging 0 | "공급망 자동 추출 부재" — 시스템 자랑 핵심 깎임 | ⭐⭐⭐ P0 | 우회 4 옵션 (data_inventory §3 B7 / autograph §5.1) — manual seed 50+ 확장이 가장 즉시 |
| **B10** | `:Supplier` Neo4j 9,642 vs PG 4,812 약 2배 중복 | 매칭 정확도 — strong_match 필터로 회피 가능 | ⭐⭐ P1 | dedupe routine 1주 |
| **B11** | NHTSA complaint 65% (10,390/16,005) 짧은 카테고리 매칭 실패 | COMPLAINT_OF +10k edges 기대 | ⭐ P2 | L3 system 매칭 확장 2주 |
| **B6** | AI-Hub aggregate model name mismatch | 현재 24 edges OK — 명목적 ⚠️ | ⭐ P2 (사실상 P3) | 추가 작업 불필요 |

상세 진단 SOP 는 [data_inventory.md §3](data_inventory.md) (이번 라운드 보강 완료).

**실시간 측정 routine (P2-10 보강 2026-06-02)**: `make audit-b-issues` — 4 건 모두 PG/Neo4j 실측 + 자동 RESOLVED/ACTIVE/MONITORING 분류 + JSON 산출 (`data/reports/b_issues.json`). 베이스라인 (2026-06-02): B6 ⚠️ 26 rows / B7 🟡 0 / B10 🟡 1 / B11 🟡 0.682. `make audit-b-issues ARGS="--strict"` 로 CI 게이트 가능.

---

## 3. 자랑 vs 실제 — 솔직 review (7 항목)

> 본 절은 사용자 cold review (2026-06-02) 의 P1-(4)/(5)/(6)/(7) + P0-(2)/(3) 종합. **칭찬 없이 정직히**.

### 3.1 "3 도메인 한 turn 안에 묶기"

| 자랑 | 실제 |
|---|---|
| README §1 + README §1 / §3.4.1 — "finance + auto + ip 3 도메인을 bridge.corp_entity 로 한 turn 안에 묶는 GraphRAG" | ✅ **개념·코드 수준 정합** — runbook_traces.md §5 (CD-L1) / §6 (CD-L3) 시연. ⚠️ **단, ip 도메인 cross-domain (§7 CD-L4-IP) 은 wire-up 만 완료 — 실제 답변 불가** (ip.patents 0 row). 실제 작동하는 cross-domain 은 finance+auto 2 도메인 한정 |

### 3.2 "공급망 추론" (SUPPLIED_BY)

| 자랑 | 실제 |
|---|---|
| README §1.2 + README §3.6 — "공급망 그래프 추론" 이 시스템 핵심 가치 | ⚠️ **manual `supplier_seed.yaml` 19 공급사 × 46 매핑 의존** — Wikidata P176 rate-limit 으로 자동 추출 0 row. 새 공급사 추가 = yaml 수기. 시스템 차원 "자동 공급망 추출" 자랑은 정직히 보강 필요 ([autograph.md §5.1](autograph.md)) |

### 3.3 "코어 변경 < 5%" (README §10.15)

| 자랑 | 실제 |
|---|---|
| README §10.15 / README §10.12 — "ip 도메인 추가 후 baseline reset 414bc1b 후 0/15,396 LOC = 0.00% ✅" | ⚠️ **baseline reset 정책의 산물** — bab9411 → 414bc1b 의 1,877 LOC (13.32%) 가 의도된 inflection 으로 reset. **자랑할 만한 메커니즘은 plug-in 패턴 자체** (`register_handler` 부작용 + `discover_plugins`). "0%" 단독은 정의 의존. 정직 review 는 [core_diff_baseline_ledger.md §D](../eval/reports/core_diff_baseline_ledger.md) (완료) |

### 3.4 "confidence calibration" (README §4.0)

| 자랑 | 실제 |
|---|---|
| README §4.0 — confidence A=0.95 / B=0.80 / C=0.50, validator 임계 0.5 | ⚠️ **calibration 미실측** — A/B/C 가 실제 정답률과 단조 관계인지 미검증. `eval/metrics/confidence_weighted.py` 측정 도구만 있고 실행 안 됨. 즉 시스템 신뢰성 자랑이 이론적. 5분 routine 은 [learning_guide §11.4.0 Platt scaling](learning_guide.md) (완료) — LLM 키 활성 + `make eval-full` 후 5분 |

### 3.5 "축소 평가 매트릭스 thesis" (README §10.7, DoD #17 (d))

| 자랑 | 실제 |
|---|---|
| README §10.7 — Hybrid vs Vector multi-hop +30%p, DoD #17 (d) | ⚠️ **실측 미실시** — `make audit-eval-matrix` simulation 모드 wire-up 만 완료 (LLM 비용 0). full 모드 (`--full`) 사용자 환경 별도 트리거. 즉 "thesis headline" 이 아직 정량 증거 부재. 즉시 실행 가능 (gold QA 120 row 충족, LLM 키 + 비용 ~$5~20) |

### 3.6 "gold QA 평가셋"

| 자랑 | 실제 |
|---|---|
| README §6 / README §6 — finance 30 / auto 46 / cross 44 / ip 30 = 150 row | ⚠️ 4 중 정직 표기 필요 (2026-06-02 실측):<br>(a) **모든 row 가 시스템 작성자 작성** — 외부 큐레이터 비율 **0%**. 정책 30% 미달.<br>(b) **refusal row (is_answerable=false) 평균 5.3%** (finance 3.3% / auto 4.3% / cross 9.1% / ip 0%). 정책 10% 미달.<br>(c) **`gold_answer_text` paraphrase 평균 = finance 0.23 / auto 0.41 / cross 0.00** — 정책 3개 미달. EM/F1 매우 엄격 → 점수 낮아질 가능성 큼.<br>(d) **ip 30 row 의 gold_answer_text 모두 비어있음** — KIPRIS/USPTO 적재 후 채움.<br>→ 평가 점수는 **sanity check 수준** — 정량 증거로 활용 시 본 한계 명시 필수 (mental_model §5.7 / learning_guide §8.2.1 / gold_qa_guide §2.2 인지) |

### 3.7 "MCP / Langfuse / SHACL / 평가 매트릭스" (README §10.17 = 4 상용 신호)

| 자랑 | 실제 |
|---|---|
| README §10.17 — 4 상용 신호 모두 (wired) 또는 (wired, partial) | (a) **MCP** — typed tool pool 59 tools + JSON Schema 자동 변환 + stdio server. 외부 (Claude Desktop / Cursor / Cline) 호출 가능. ✅ 정합. (b) **Langfuse 실측 ON** — OTEL native + ContextVar 격리 + meta JSONB 적재. ✅ 정합. (c) **SHACL** — pydantic v2 로 대체 (`make audit-ontology`). 의도된 trade-off (PRD §11.1). (d) **축소 평가 매트릭스** — wire-up 완료, **실측 미실시** (§3.5 와 같은 한계) |

---

### 3.8 Trace 별 자랑 vs 실제 매핑 (9 시나리오 — runbook_traces §10 흡수)

본 표는 [docs/runbook_traces.md](runbook_traces.md) 의 9 대표 시나리오를 trace 단위로 자랑 vs 실제 매핑.

| Trace | 시스템 자랑 (README/PRD) | 실제 상태 | gap |
|---|---|---|---|
| **§1 finance L1** | "DART XBRL 정확한 수치 인용" | ✅ 완전 작동 — gold 30 row | LLM 키 활성 후 실측 미실시 |
| **§2 finance L2** | "multi-hop 추론" | ✅ 작동 가능 | gold curation + multi_hop_em/f1 측정 필요 |
| **§3 auto L2** | "리콜 ↔ variant 매칭" | ✅ 작동 | gold + Korean 시장 fallback (NHTSA + KR 리콜 통합) |
| **§4 auto L3** | "공급망 추론" | ⚠️ **manual seed 의존** (SUPPLIED_BY 30 edges, [autograph.md §5.1](autograph.md) 정직 표시) | 자동 공급망 추출 routine 부재 — 본 review §3.2 와 동일 뿌리 |
| **§5 CD-L1** | "한 turn 안에 finance + auto 묶기" | ✅ Bridge reviewed 매핑 11 으로 작동 | latency 측정 미실시 |
| **§6 CD-L3** | "3 도메인 cross" | ⚠️ supplier candidate 정확도 한계 + 글로벌 OEM 분기 routine 부재 | planner 분기 보강 필요 — 본 review §1.2 P0 (Bridge candidate SOP) 와 연결 |
| **§7 CD-L4-IP** | "특허 + 재무 + 자동차 한 turn" | ⚠️ **`ip.patents` 0 row** → wire-up 만 완료 | KIPRIS/USPTO 적재 후 실측 가능. 본 review §3.1 와 동일 뿌리 |
| **§8 IP L1** | "특허 카운트" | ⚠️ **gold_answer 비어있음** | KIPRIS/USPTO 적재 후 채움 — 본 review §3.6 (d) 와 동일 |
| **§9 refusal** | "환각 차단 정책" | ✅ number_guard + validator 작동 | refusal precision 측정 미실시 — 본 review §3.6 (b) 와 연결 (refusal row 비율 5.3% 정책 미달) |

**종합** (본 review 자랑 vs 실제 7 항목 + trace 9 시나리오 통합):
- 9 trace 중 **4 즉시 작동** (§1/§2/§3/§5) — finance + auto 단순/중간 + CD-L1 까지 정합
- **3 부분 작동** (§4/§6/§7) — 모두 `SUPPLIED_BY` manual seed / Bridge candidate / ip 적재 의존
- **2 wire-up 완료 / 측정 대기** (§8/§9) — ip 적재 + LLM 실측 대기

→ **시스템 차원 결론**: finance+auto 2 도메인 단순/중간 시나리오는 정합, **3 도메인 cross (§6/§7) + 자동 공급망 (§4) + ip (§7/§8) + refusal 측정 (§9)** 4 영역이 측정·정직 보강 후순위. cold review 의 P0 우선순위 (§1.2 표) 와 1:1 매칭.

---

## 4. 시급도 매트릭스 (영향 × 노력)

가로 = 영향 (Low / Medium / High), 세로 = 노력 (Low / Medium / High).

```
                            영향 →
                  Low            Medium           High
        Low   |                 | B6, B11        | confidence calibration   |
              |                 |                | gold QA 외부 큐레이터 30% |
              |                 |                | rerank ablation 실측      |
              |                 |                |                          |
노력    Med   | core_diff       | B10 dedupe     | Bridge candidate SOP     |
↓             | 정직 표기 (완료)|                | API 인증 + 운영 보안     |
              |                 |                | ip.patents 적재          |
              |                 |                |                          |
        High  |                 | Qwen3-Emb GPU  | SHACL 도입 (기각)        |
              |                 | 업그레이드     | manual SUPPLIED_BY 50+   |
```

**즉시 실행 권장 (High 영향 + Low 노력)** — 3 건:
1. **confidence calibration** — sklearn 1줄, 5분 (learning_guide §11.4.0)
2. **gold QA 외부 큐레이터** — Allganize 흡수 (gold_qa_guide §6.3)
3. **rerank ablation 실측** — `make audit-eval-matrix --full`

---

## 5. 한계가 cross-link 된 문서 일람

본 review 가 가리키는 문서:

| 문서 | 본 review 와의 관계 |
|---|---|
| [README §12 보완 백로그](../README.md) | 개발 백로그 P0+/P1/P2 — 본 review §1.2 와 동일 우선순위 시급도 |
| [README §4.0 신뢰도 등급](../README.md#40-출처별-신뢰도-등급-abc) | calibration 미검증 한계 표시 (cross-link 완료) |
| [data_inventory.md §3 B-issue](data_inventory.md) | B6/B7/B10/B11 진단 SOP — 본 review §2 |
| [mental_model.md §5 + §5.12](mental_model.md) | 11 열린 질문 + 우선순위 통합표 |
| [autograph.md §5.1](autograph.md) | SUPPLIED_BY manual 의존 정직 표시 — 본 review §3.2 |
| [eval/reports/core_diff_baseline_ledger.md §D](../eval/reports/core_diff_baseline_ledger.md) | "코어 변경 < 5%" 정직 review — 본 review §3.3 |
| [learning_guide.md §11.4.0](learning_guide.md) | Platt scaling 5분 routine — 본 review §3.4 |
| [gold_qa_guide.md §6](gold_qa_guide.md) | 외부 큐레이터 30% 운영 가이드 — 본 review §3.6 |
| [runbook_traces.md §10](runbook_traces.md) | 9 trace 별 자랑 vs 실제 매핑 — 본 review §3.1 |
| [data_lineage.md §5.4](data_lineage.md) | 더 필요한 데이터 P0/P1/P2 백로그 |

---

## 6. 본 review 의 의도된 사용법

### 6.1 외부 평가자

본 문서를 README 다음으로 읽기. README §1~§10 의 자랑 → 본 문서 §3 자랑 vs 실제 — gap 확인 → §1.2 한계 통합 표 — 시스템 전체 review.

### 6.2 본인 회고 / 분기별 검토

- §1.2 표의 13 한계 중 해결된 것은 ✅ 갱신
- §2 B-issue 미해결 4건 진행률 갱신
- §3 자랑 vs 실제 — 새로 발생한 gap 추가 (예: 신규 기능이 만들 한계)
- §4 시급도 매트릭스 — 우선순위 sort 재실행

### 6.3 신규 합류자

본 문서는 "이 시스템은 무엇을 못 하는가" 에 대한 솔직 답변. 합류 첫 주에 본 문서 + [learning_guide.md §0.6 트랙 A](learning_guide.md) 같이 읽으면 자랑·한계 균형 잡힘.

### 6.4 PR 리뷰

새 PR 이 본 review §1.2 표의 한계를 **새로 추가** 하는지 확인. 새 한계가 발생하면 본 표에 추가 + cross-link.

---

## 7. 본 review 의 미해결 정직 — 본 문서 자체의 한계

본 문서도 한계가 있음:

1. **시급도 매트릭스 §4 가 정성 estimate** — 영향·노력은 실측 아닌 author 판단. 분기별 갱신 시 신뢰성 검증 필요
2. **자랑 vs 실제 §3 의 7 항목은 author 판단** — 누가 자랑이고 누가 실제인지의 경계는 청중 따라 다름
3. **B-issue 4건의 해결 cost estimate** (1주 / 2주) **는 추정** — 실 실행 시 변동 가능
4. **본 문서 자체가 시스템 작성자 작성** — 외부 평가자가 본 문서까지 self-bias 의심 가능. **외부 독립 review** 가 진짜 cold review 의 완성 (P0 권장 추가)

---

## 8. 더 깊이

- 시스템 자랑 진입: [README](../README.md) §1~§10
- 5 분 직관: [learning_guide.md §0.5](learning_guide.md)
- 한계 카탈로그 (설계): [mental_model.md §5](mental_model.md)
- 한계 카탈로그 (운영): [data_inventory.md §3](data_inventory.md)
- 백로그: [README §11](../README.md)
- end-to-end 데이터 추적: [data_lineage.md](data_lineage.md)
- 의도된 호출 trace: [runbook_traces.md](runbook_traces.md)
