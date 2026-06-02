# FAQ · Troubleshooting

> 자주 막히는 지점과 진단 트리. 본 문서는 **인덱스 역할** — 상세 절차는 각 operations 가이드 또는 코드 라인 인용으로 위임. 사용자 1단계 검토에서 "mental_model §9 열린 질문과 별개" 로 신설 승인.

---

## Q1. 환경·부팅

### Q1.1 `make up` 후 `make health` 가 실패

**증상**: `pg_isready` 또는 `wget localhost:7474` 실패.

**진단**:

```bash
docker compose ps                                    # 컨테이너 상태 확인
docker compose logs postgres | tail -50              # PG 로그
docker compose logs neo4j   | tail -50              # Neo4j 로그
```

**자주 발생하는 원인**:
- **포트 충돌** — `31009`/`31010`/`31011` 이 이미 사용 중 → `lsof -i :31011` 로 확인 후 충돌 프로세스 종료 또는 `docker-compose.yml` 의 host 포트 변경
- **데이터 볼륨 권한** — `~/arsim/DB_FG/` 가 root 소유 → `sudo chown -R $USER ~/arsim/DB_FG`
- **메모리 부족** — Neo4j 가 OOMKilled → `docker stats` 확인, `JAVA_OPTS=-Xmx2G` 환경에서 4G+ 권장
- **스키마 초기화 실패** — 빈 볼륨이 아닌데 init/*.sql 가 재실행 시도 → 이미 적용된 환경에는 hot-apply ([docs/operations/migrations.md](operations/migrations.md))

### Q1.2 `python -c "import autonexusgraph"` 가 ModuleNotFoundError

**진단**: `pip install -e .` 또는 `pip install -e ".[all]"` 실행 여부 확인.

```bash
pip show autonexusgraph                              # editable install 확인
python3 -c "import autonexusgraph; print(autonexusgraph.__file__)"
```

**원인**: editable install 미실행, 또는 다른 venv 활성. `make install` 재실행.

### Q1.3 도메인 plug-in (`autograph`/`ipgraph`) 이 활성화 안 됨

**증상**: `auto_detect_domain` 이 `auto` / `ip` 도메인을 인식 못 함.

**진단**:

```bash
python3 -c "
import os
print('ENV AUTONEXUSGRAPH_DOMAIN_PLUGINS =', os.getenv('AUTONEXUSGRAPH_DOMAIN_PLUGINS', '(unset → default \"autograph\")'))
from autonexusgraph.agents._domain_handler import discover_plugins, _HANDLERS
discover_plugins(force=True)
print('등록된 핸들러:', sorted(_HANDLERS.keys()))
"
```

**해결**: `.env` 에 `AUTONEXUSGRAPH_DOMAIN_PLUGINS=autograph,ipgraph` 추가.

---

## Q2. LLM·비용

### Q2.1 LLM 호출이 `[FAKE LLM]` 응답으로 떨어짐

**원인**: LLM provider 키 (OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY) 미설정.

**해결**: `.env` 에 한 개 이상 설정. provider 자동 dispatch (`llm/base.py::detect_provider`).

### Q2.2 `cost approval needed` interrupt 발생

**증상**: turn 추정 비용이 `LLM_COST_AUTO_APPROVE_USD` (기본 $0.50) 초과 → HITL 승인 요청.

**해결**:
- Streamlit UI: 다이얼로그에서 승인/거절
- API: `POST /chat/resume` 에 승인 응답 전달
- 폴백 환경 (langgraph 미설치): 자동 통과 + 경고 로그

**임계 조정**: `LLM_COST_AUTO_APPROVE_USD=2.00` 으로 ENV override.

### Q2.3 세션 hard limit 도달 — 후속 turn 차단

**증상**: `data/cost_log.jsonl` 누적이 `LLM_SESSION_HARD_LIMIT_USD` (기본 $10) 초과 → 차단.

**해결**: 세션 재시작 (`cost_log.jsonl` 은 누적이라 재시작해도 누적값 유지 — 운영 환경에서는 일·주별 rotate 필요, §11.2 운영 보안 P1).

---

## Q3. 데이터 적재·정합

### Q3.1 `make load-auto-all` 중 foreign key 위반

**진단**: 의존 순서 누락. Makefile 의 `load-auto-all` 타깃이 다음을 강제:

```
neo4j-init → pg → specs → neo4j → bridge → standards/plants → safety → epa → aihub
            → nhtsa-taxonomy → supplier-edges → complaints-neo4j
            → recall-components → complaint-components → investigations → oem-sec
            → derive-contains-system → wikidata-part-supplies → manufactured-at
            → build-chunks-auto
```

**해결**: 개별 타깃을 호출하지 말고 `make load-auto-all` 사용. 일부 단계 실패 시 멱등이라 재실행 안전.

### Q3.2 Wikidata P176 (manufactured by) staging 이 0 row

**원인**: Wikidata SPARQL endpoint 의 rate-limit (1 req/min, 429 응답). `auto.staging_relations` 미적재가 정상 상태 — `docs/data_inventory.md §3 B-issue` 추적 중.

**해결**: `supplier_seed.yaml` 19 공급사 × 46 매핑 (Neo4j `SUPPLIED_BY` 30 distinct edges) 으로 대체. P3 LLM 추출은 후속.

### Q3.3 `:Supplier` Neo4j 9,642 vs PG `auto.master_suppliers` 4,812 — 2배 중복?

**원인**: 미해결 이슈 (`data_inventory.md §3 B10`). `supplier_seed.yaml` + `auto.suppliers_edges` loader 의 중복 적재 의심. 진단 routine 미구현.

**임시 우회**: 그래프 쿼리에서 `WHERE confidence_score >= 0.9 AND reviewed_status = 'reviewed'` 필터 적용.

### Q3.4 embedding backfill 진행률 확인

**진단**:

```sql
-- pgvector 의 embedding 컬럼 NULL 비율
SELECT
    section,
    COUNT(*) AS total,
    SUM(CASE WHEN embedding IS NULL THEN 1 ELSE 0 END) AS missing,
    ROUND(100.0 * SUM(CASE WHEN embedding IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS missing_pct
FROM vec.chunks
GROUP BY section
ORDER BY total DESC;
```

**현재 상태** (2026-06-01): finance 748K 중 일부 backfill 진행 중, auto 16,435 모두 완료, ip 423 (OpenAlex abstract) backfill 대기.

**재시도**: `make embed-chunks` (멱등, NULL 만 채움).

---

## Q4. Cypher·Neo4j

### Q4.1 `assert_read_only` 가 쿼리를 차단

**증상**: `RuntimeError: query contains write keyword: CREATE|MERGE|DELETE...`.

**원인**: cypher_guard (`safety/cypher_guard.py:35-50`) 가 쓰기 키워드 + 위험 CALL 을 차단. agent worker 는 read-only 강제.

**해결**: 자유 Cypher 금지 — `tools/graph.py` 의 사전 정의 함수 (cypher_templates 경유) 만 호출. 새 use case 는 템플릿 추가 (자유 Cypher 영구 금지).

### Q4.2 답변 confidence 낮음 (`some_low` / `all_low` warning)

**원인**: validator 의 confidence edge guard (`LOW_CONFIDENCE_THRESHOLD=0.5`) 가 답변 근거 엣지의 `confidence_score < 0.5` 감지.

- `all_low` → hard fail → replan 트리거 (max 2회)
- `some_low` → soft warning → 답변에 "후보 정보" 명시

**해결**: 출처 등급 (`docs/data_lineage.md` 채널별 §7키 메타 항목의 `confidence_score`) 확인 후 더 높은 등급 (A/B) 의 데이터로 보강. 또는 `bridge.corp_entity` 의 supplier candidate 검토 SOP 적용 (4,790 row 영속 누적 — 운영 미설계, README §11.4 P1).

### Q4.3 multi-hop 쿼리가 폭발 (timeout)

**원인**: `(:Manufacturer)-[:CONTAINS_MODULE*1..N]->(:Module)` 같은 미제한 traversal.

**해결**: 템플릿이 항상 `*1..3` 등 cap 강제 (`cypher_templates_auto.py`). 새 use case 도 동일 패턴 + `LIMIT` 추가. ip 도메인 `get_citation_network` 는 `depth ≤ 2`, `limit_nodes ≤ 300`, `max_total ≤ 1000` 강제 (`src/ipgraph/tools/graph.py`).

---

## Q5. 평가·DoD

### Q5.1 `make eval-full` 이 LLM 비용 폭주

**원인**: 100 문항 × 4 어댑터 × LLM 1종 = 400 호출. LLM provider 의 토큰 단가에 따라 $5~$20 가능.

**해결**:
- 먼저 `make eval-smoke` (3 row) 로 wire-up 확인
- `make audit-eval-matrix` simulation 모드 (LLM 비용 0) 로 cell enumeration 검증
- 비용 가드: `LLM_SESSION_HARD_LIMIT_USD` 적절히 설정
- 축소 매트릭스 (DoD #17 (d)): 4 어댑터 × FAST tier 1종 = 4 조합 우선

### Q5.2 `make audit-dod` 의 일부 항목이 `⊘`

**의미**: LLM 키 필요 / 외부 자원 필요 — 사용자 액션 대기. PRD §10 의 17항 중 5~7항이 ⊘ (LLM 실측 + 외부 trace).

**해결**: 해당 항목의 "필요 작업" 컬럼 (`eval/reports/dod_v2.2.md`) 참조. 예: `§10.7 Hybrid vs Vector +30%p` → `make eval-auto` 실행 후 자동 측정.

### Q5.3 `audit-edge-meta --strict` 가 fail

**원인**: Neo4j 엣지 중 일부가 7키 (`source_type / source_id / confidence_score / validated_status / snapshot_year / extraction_method / schema_version`) 누락. `EDGE_REQUIRED_META_KEYS` SSOT = `src/autonexusgraph/ontology/schema.py:28-36`.

**해결**: loader 의 `edge_meta_cypher()` 헬퍼 (`src/autograph/loaders/_neo4j_helpers.py`) 가 7키 자동 부여. 헬퍼 우회한 직접 CREATE 가 원인. 누락 엣지 식별:

```cypher
MATCH ()-[r]->() WHERE r.source_type IS NULL RETURN type(r), count(*) ORDER BY count(*) DESC LIMIT 20;
```

---

## Q6. 관측·디버깅

### Q6.1 Langfuse / LangSmith trace 안 보임

**진단**:

```bash
grep TRACE_BACKEND .env
# expected: TRACE_BACKEND=langfuse  또는  TRACE_BACKEND=langsmith
grep LANGFUSE_HOST .env
# Langfuse 자체 호스팅 또는 SaaS URL
```

**해결**:
- Langfuse: `.env` 에 `TRACE_BACKEND=langfuse` + `LANGFUSE_HOST` + `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY`
- LangSmith: `LANGSMITH_API_KEY` + `LANGSMITH_PROJECT`
- fail-soft 정책 — 키 없거나 endpoint 실패 시 silent skip (앱 동작은 영향 없음)

### Q6.2 replan 무한 루프 의심

**확인**: `MAX_REPLANS = 2` (`agents/validator.py:36`) 가 hard cap. 3번째 replan 시 finalize 노드가 `⚠️ 검증 실패 (replan 2/2 후)` 프리픽스로 답변 패키징.

**진단**: `state.n_replans` 값 확인. SSE stream 에서 노드 진행 표시.

### Q6.3 모호한 회사명 → HITL clarification interrupt

**증상**: "이재용" 같은 동명이인 → `pending_interrupt.kind = 'clarification'`.

**해결**:
- Streamlit UI: 다이얼로그에서 선택
- API: `POST /chat/resume` 에 선택 인덱스 전달
- 자동 해결 조건: 후보 margin (`is_ambiguous_company` 판정) ≥ 10% 면 단일 후보 자동 채택

---

## Q7. 운영·보안

### Q7.1 외부 노출 시 누가 thread 히스토리 조회 가능?

**현재**: thread_id 만 알면 누구나 조회 가능 — **API 인증 없음** (§11.2 운영 보안 P1).

**해결**: reverse proxy (nginx/caddy) + OAuth2/API key middleware + thread_id 의 user_id binding. 본 시스템 단독으로는 dev 한정.

### Q7.2 비밀 키 누출 위험

**점검**:

```bash
git ls-files | xargs grep -l "API_KEY=sk-\|SECRET_KEY=" 2>/dev/null
# expected: 0 (모든 .env 는 gitignored)
```

**원칙**: `.env` 는 절대 commit 금지. prod 는 vault / k8s secret. `.env.example` 만 placeholder.

### Q7.3 `data/cost_log.jsonl` 비대화

**현재**: 영속 append, size 무제한 (gitignored).

**해결**: 일·주별 rotate cron + 보존 기간 정책. `python -m autonexusgraph.llm.cost_history` 가 누계 집계.

---

## 진단 트리 요약

```
앱이 안 뜬다
  → docker compose ps → 헬스 fail? → §Q1.1
  → import error? → §Q1.2
  → 도메인 인식 안 됨? → §Q1.3

답변이 이상하다
  → [FAKE LLM] 표시? → §Q2.1
  → confidence 낮음 / replan? → §Q4.2 / §Q6.2
  → 회사명 모호 interrupt? → §Q6.3

데이터가 비어있다
  → load 중 FK 위반? → §Q3.1
  → P176 staging 0? → §Q3.2
  → Supplier 중복? → §Q3.3
  → embedding NULL? → §Q3.4

쿼리가 차단된다
  → assert_read_only? → §Q4.1
  → timeout? → §Q4.3
  → 7키 missing? → §Q5.3

비용 폭주
  → eval 비용? → §Q5.1
  → cost approval interrupt? → §Q2.2
  → hard limit 도달? → §Q2.3

관측 안 됨
  → Langfuse trace 안 보임? → §Q6.1
  → DoD ⊘? → §Q5.2
```

---

## 더 깊이

- 도구 시그니처·반환 스키마: [docs/api_reference.md](api_reference.md)
- 운영 절차: [docs/operations/](operations/) (migrations / docker_setup / agents / data_pipeline / rag_tools)
- 결정·트레이드오프·열린 질문: [docs/mental_model.md](mental_model.md) §5 (11 열린 질문)
- 시스템 구조: [docs/architecture.md](architecture.md)
