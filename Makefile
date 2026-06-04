.PHONY: help install fmt lint test test-int smoke-e2e up down logs health clean \
        bridge-kpi bridge-expire persons-collision freshness metrics serve-metrics backup restore \
        ingest-corp ingest-krx ingest-ecos ingest-targets ingest-bulk \
        ingest-structural ingest-wikidata ingest-wikipedia \
        ingest-news ingest-fss ingest-ftc ingest-kosis \
        ingest-sec ingest-gleif ingest-gleif-enrich ingest-gleif-enrich-dry \
        ingest-openalex ingest-openalex-dry load-openalex \
        ingest-kipris load-cpc load-cpc-dry load-assignee-corp-map load-assignee-corp-map-dry ingest-uspto-odp \
        ingest-law ingest-kcgs \
        serve-embeddings embed-chunks embed-status serve-api serve-ui \
        eval-smoke eval-full p3-extract-dry p3-extract p4-load \
        ingest-step1 ingest-step2 ingest-step3 ingest-step4 \
        ingest-step5 ingest-step6 ingest-step7 ingest-step8 \
        ingest-all inventory \
        load-companies load-filings load-financials load-all \
        load-entity-map load-persons load-graph-structural \
        load-wikidata load-wikipedia load-news load-graph-news \
        load-sec load-gleif load-kcgs \
        build-wiki-chunks validate-quality \
        migrate-schema install-agent enable-langgraph trace-on trace-off \
        llm-status llm-on llm-off llm-reset \
        ingest-auto-vpic ingest-auto-recalls ingest-auto-complaints \
        ingest-auto-wikidata ingest-auto-safety ingest-auto-wikipedia \
        ingest-auto-epa ingest-auto-investigations ingest-auto-sec-oem \
        ingest-auto-mfrcomm ingest-auto-all \
        load-auto-pg load-auto-neo4j load-auto-bridge \
        build-chunks-auto neo4j-init-auto load-auto-all eval-auto \
        load-auto-recall-components load-auto-supplier-edges \
        load-auto-seed-standards-plants load-auto-complaints-neo4j \
        load-auto-aihub load-auto-specs load-auto-safety load-auto-epa \
        load-auto-investigations load-auto-oem-sec load-auto-mfrcomm \
        derive-auto-contains-system load-wikidata-part-supplies \
        extract-auto-p3 extract-auto-p3-cost validate-auto-p4 extract-validate-auto \
        audit-bom-coverage audit-edge-meta audit-trace audit-ontology audit-eval-matrix audit-eval-matrix-full audit-mcp audit-ipgraph audit-dod \
        validate-gold-qa eval-cross eval-ip \
        ingest-datagokr-recalls ingest-datagokr-inspections \
        ingest-car-go-kr ingest-katri ingest-kncap \
        load-manufactured-at load-performed-at load-performed-at-dry load-factoryon-plants load-factoryon-plants-dry load-recall-process-map load-recall-process-map-dry load-produced-by load-produced-by-dry load-datagokr-recalls load-datagokr-inspections \
        load-kncap \
        load-sandang-processes load-sandang-processes-dry \
        ingest-factoryon-company ingest-factoryon-factory-no ingest-factoryon-complex \
        migrate-schema-pg migrate-auto-production migrate-auto-kama \
        migrate-auto-oem-news \
        load-kama-macro load-kama-macro-dry \
        load-usgs-minerals load-usgs-minerals-dry \
        load-dart-production audit-data-channels \
        load-factoryon load-factoryon-dry load-kosis load-kosis-dry \
        ingest-wikidata-cell-chem \
        ingest-oem-ir-hyundai ingest-oem-ir-mobis ingest-oem-ir-policies \
        load-oem-ir-news load-oem-ir-news-dry

# 호스트가 Ubuntu/Debian 계열이면 `python` 없이 `python3` 만 있을 수 있음 — auto-detect.
# 명시 지정하려면: make PYTHON=python3.11 ...
PYTHON ?= $(shell command -v python3 || command -v python || echo python3)
PIP ?= $(shell command -v pip3 || command -v pip || echo pip3)
DOCKER_COMPOSE ?= docker compose

help:
	@echo "AutoNexusGraph — 개발/운영 타깃"
	@echo ""
	@echo "  install         pip install -e \".[all]\" (개발용 전체 설치)"
	@echo "  fmt             ruff format"
	@echo "  lint            ruff check + mypy"
	@echo "  test            pytest (integration 제외)"
	@echo "  test-int        pytest -m integration (실제 DB/LLM 필요)"
	@echo "  smoke-e2e       DB·LLM 없이 돌아가는 모든 mock 정합성 검증 (pre-push 게이트)"
	@echo ""
	@echo "  up              docker compose up -d (Neo4j + PG + Qdrant)"
	@echo "  down            docker compose down"
	@echo "  logs            docker compose logs -f --tail=100"
	@echo "  health          모든 인프라 (Neo4j/PG/Qdrant/임베딩/DART/ECOS) ping"
	@echo ""
	@echo "  ingest-corp     DART 회사 코드 마스터 다운로드"
	@echo "  ingest-krx      KRX 상장사 + 시가총액 상위 200/100"
	@echo "  ingest-ecos     ECOS 거시지표 (ECOS_API_KEY 필요)"
	@echo "  ingest-targets  corp_code × stock_code 매칭 → ingest_targets.jsonl"
	@echo "  ingest-bulk     KOSPI200+KOSDAQ100 × 3년 일괄 (이어받기·실패추적 지원)"
	@echo "  ingest-docs     사업보고서 원문 zip 다운로드 (~1,149건, ~수 분)"
	@echo "  ingest-all      corp → krx → targets → bulk 전체 순차"
	@echo ""
	@echo "  inventory       data/raw 인벤토리 + 누락 검증"
	@echo ""
	@echo "  load-companies  master.companies 적재"
	@echo "  load-filings    fin.filings 적재"
	@echo "  load-financials fin.financials 적재 (184K+ rows)"
	@echo "  load-all        위 3종 순차 (PG 컨테이너 가동 필요)"
	@echo "  build-chunks    DART zip → vec.chunks (embedding NULL, ~73만 row)"
	@echo "  embed-chunks    BGE-M3 호출 → embedding 채우기 (BGE 서버 필요)"
	@echo "  load-graph      Neo4j Company/Market/Sector/Person 노드 + 관계"
	@echo ""
	@echo "── AutoGraph (자동차 도메인) ──"
	@echo "  ingest-auto-all                   NHTSA vPIC/recalls/complaints/safety + Wikidata"
	@echo "  ingest-auto-safety                NHTSA SafetyRatings (NCAP 5★ 등급)"
	@echo "  ingest-auto-wikipedia             자동차 모델/제조사 Wikipedia 본문 (ko fallback en)"
	@echo "  load-auto-all                     PG → Neo4j 풀 체인 (specs/safety/aihub/seed/recall→comp/derive 포함)"
	@echo "  load-auto-aihub                   AI Hub 71347/578 → :Module + CONTAINS_COMPONENT"
	@echo "  load-auto-specs                   canspec → spec_measurements + variant 보강"
	@echo "  load-auto-safety                  NCAP raw → spec_measurements(safety.*) + SAFETY_RATED_BY"
	@echo "  load-auto-supplier-edges          supplier_seed.yaml → :SUPPLIED_BY (manual A grade)"
	@echo "  load-auto-nhtsa-taxonomy          NHTSA recall component_text → auto.components (level=4)"
	@echo "  load-auto-recall-components       recall.component_text → :RECALL_OF (deterministic)"
	@echo "  load-auto-complaint-components    complaint.components → :COMPLAINT_OF (taxonomy 후행)"
	@echo "  load-auto-seed-standards-plants   :Standard + :Plant + :OWNS_PLANT 시드"
	@echo "  load-auto-complaints-neo4j        :Complaint + :REPORTED_IN"
	@echo "  derive-auto-contains-system       (VehicleModel)-[:CONTAINS_SYSTEM]->(System) 유도 적재"
	@echo "  extract-auto-p3-cost              P3 LLM 비용 dry-run (호출 없이 토큰 추정)"
	@echo "  extract-auto-p3                   P3 LLM 추출 → auto.staging_relations"
	@echo "  validate-auto-p4                  P4 cross-validate → Neo4j 적재"
	@echo "  extract-validate-auto             P3 → P4 한 번에"
	@echo "  eval-auto                         자동차 QA 평가셋 실행"
	@echo "  eval-cross                        Cross-Domain QA (PRD §8.1 CD-L1~L4)"
	@echo "  eval-ip                           IPGraph QA 평가셋 (gold_qa_ip_v0.jsonl × hybrid)"
	@echo ""
	@echo "── DoD audit (PRD §10) ──"
	@echo "  audit-bom-coverage                Level 0~5 노드 + L4 coverage 측정"
	@echo "  audit-edge-meta                   PRD §6.7 의무 메타 invariant (strict)"
	@echo "  audit-trace                       PRD §10 DoD #17 (b) Langfuse 실측 (turn별 token/cost/replan)"
	@echo "  audit-ontology                    PRD §10 DoD #17 (c) 온톨로지 pydantic strict 검증"
	@echo "  audit-eval-matrix                 PRD §10 DoD #17 (d) 축소 매트릭스 simulation (ARGS=\"--full --limit N\" 전달 가능)"
	@echo "  audit-eval-matrix-full            동일 매트릭스 --full 모드 (limit 30 default, §10.7 thesis 측정)"
	@echo "  audit-mcp                         PRD §10 DoD #17 (a) MCP 래퍼 wire-up (mcp SDK 미설치 시 SKIPPED)"
	@echo "  audit-ipgraph                     PRD §10 DoD #15/#16 IPGraph (도메인3) plug-in wire-up"
	@echo "  audit-dod                         17 항목 트래픽라이트 리포트 (v2.2 — IPGraph + 상용신호 4종 포함)"
	@echo "  validate-gold-qa                  eval/qa_gold/*.jsonl 스키마/엔티티 lint"
	@echo ""
	@echo "── 외부 데이터 (graceful skip 패턴 — 키 없으면 스킵) ──"
	@echo "  ingest-datagokr-recalls           data.go.kr 3048950 한국 리콜 CSV (무인증)"
	@echo "  ingest-datagokr-inspections       data.go.kr 15155857 수리검사"
	@echo "  ingest-car-go-kr                  [PLACEHOLDER] car.go.kr — 키 미설정 시 raw/auto/car_go_kr/ CSV 수동 다운로드 후 normalize"
	@echo "  ingest-katri                      [PLACEHOLDER] KATRI / bigdata-tic.kr — OAuth client_id/secret 발급 필요"
	@echo "  ingest-kncap                      [PLACEHOLDER] KNCAP — 공식 API 미공개, 수동 CSV 또는 KNCAP_API_KEY 설정 시 동작"
	@echo "  load-manufactured-at              모델↔공장 seed → MANUFACTURED_AT"
	@echo "  load-performed-at                 회사귀속 공정 seed → PERFORMED_AT (DoD #19)"
	@echo "  load-factoryon-plants             factoryon → :Plant(A) + OWNS_PLANT + PERFORMED_AT(candidate)"
	@echo "  load-recall-process-map           한글 리콜 결함 → CAUSED_BY_PROCESS (candidate, G-4)"
	@echo "  load-produced-by                  부품 → 공정 PRODUCED_BY (candidate, G-2)"
	@echo ""
	@echo "  clean           __pycache__/.pytest_cache 삭제"

install:
	$(PIP) install -e ".[all]"

install-agent:                                       # langgraph + tracing 의존성만
	$(PIP) install -e ".[agent]"

enable-langgraph:                                    # 활성화 헬스체크
	@$(PYTHON) -c "from langgraph.graph import StateGraph; print('✓ langgraph import 성공')" || \
	    (echo '✗ langgraph 미설치 — make install-agent 먼저 실행' && exit 1)
	@$(PYTHON) -c "from autonexusgraph.agents.graph import _HAS_LANGGRAPH; \
	    print(f'✓ _HAS_LANGGRAPH = {_HAS_LANGGRAPH}')"
	@$(PYTHON) -c "from autonexusgraph.agents.checkpointer import get_checkpointer; \
	    c = get_checkpointer(); \
	    print(f'✓ checkpointer = {type(c).__name__ if c else None}')"

trace-on:                                            # 환경변수로 tracing 활성 확인
	@echo "TRACE_BACKEND=$${TRACE_BACKEND:-(unset)}"
	@$(PYTHON) -c "from autonexusgraph.agents.tracing import describe_backend; print(describe_backend())"

trace-off:                                           # tracing 비활성 — 환경변수만 unset 안내
	@echo "TRACE_BACKEND 을 빈 값으로 두거나 'none' 으로 설정하세요. (.env 또는 export TRACE_BACKEND=)"

llm-status:                                          # LLM 가드 상태 + 누적/한도 (COST_GUARD.md)
	@$(PYTHON) llm_guard.py status

llm-on:                                              # LLM 호출 허용 (.env LLM_ENABLED=true)
	@$(PYTHON) llm_guard.py on

llm-off:                                             # LLM 호출 차단 (kill-switch)
	@$(PYTHON) llm_guard.py off

llm-reset:                                           # cost_log.jsonl 아카이브 → 누적 리셋
	@$(PYTHON) llm_guard.py reset

fmt:
	ruff format src tests scripts

lint:
	ruff check src tests scripts
	mypy src

test:
	pytest

test-int:
	pytest -m integration

# DB·LLM 없이 돌아가는 모든 정합성 smoke — CI 미설정 환경의 1-shot pre-push 게이트.
# pytest 전체 + 온톨로지 (cypher cross-check 포함) + 평가 매트릭스 simulation +
# gold QA lint + MCP/IPGraph/Trace simulation. 외부 DB·LLM 키 불필요.
smoke-e2e:
	@echo "[smoke-e2e] mock-mode 정합성 일괄 검증 시작"
	$(MAKE) test
	$(MAKE) audit-ontology
	$(MAKE) audit-eval-matrix
	$(MAKE) audit-mcp
	$(MAKE) audit-ipgraph
	$(MAKE) audit-trace
	# validate-gold-qa: DB 가용 시 evidence_corp_codes 실재 검증 포함 (2026-06-02 추가),
	# DB 미가용 환경은 validator 가 자동 skip + stderr warning — pre-push 게이트 차단 없음.
	$(PYTHON) scripts/audit/validate_gold_qa.py eval/qa_gold/*.jsonl
	@echo "[smoke-e2e] ✅ 모든 mock-mode 검증 통과"

up:
	$(DOCKER_COMPOSE) up -d
	@echo ""
	@echo "기동됨. 헬스체크:"
	@echo "  Neo4j    : http://localhost:7474"
	@echo "  Postgres : psql -h localhost -U autonexusgraph -d autonexusgraph"
	@echo "  Qdrant   : http://localhost:6333/dashboard"

down:
	$(DOCKER_COMPOSE) down

logs:
	$(DOCKER_COMPOSE) logs -f --tail=100

health:
	$(PYTHON) scripts/healthcheck.py

ingest-corp:
	$(PYTHON) scripts/ingest/download_corp_codes.py

ingest-krx:
	$(PYTHON) scripts/ingest/download_listings.py

ingest-ecos:
	$(PYTHON) scripts/ingest/download_ecos.py

ingest-targets:
	$(PYTHON) scripts/ingest/build_targets.py

ingest-bulk:
	$(PYTHON) scripts/ingest/bulk_dart.py

ingest-docs:
	$(PYTHON) scripts/ingest/download_documents.py

ingest-all: ingest-corp ingest-krx ingest-targets ingest-bulk ingest-ecos

inventory:
	$(PYTHON) scripts/data_inventory.py

load-companies:
	$(PYTHON) scripts/load/load_companies.py

load-filings:
	$(PYTHON) scripts/load/load_filings.py

load-financials:
	$(PYTHON) scripts/load/load_financials.py

load-all:
	$(PYTHON) scripts/load/load_all.py

build-chunks:
	$(PYTHON) scripts/load/build_chunks.py

# NOTE: embed-chunks 의 실제 정의는 line ~183 (EMBEDDING_URL 주입 포함).
# 여기서 중복 선언하면 GNU make 가 첫 정의로 shadow 하므로 별도 정의 두지 않는다.

load-graph:
	$(PYTHON) scripts/load/load_graph_companies.py

migrate-schema:                                      # Neo4j 스키마 정합성 마이그레이션 (README §11.6)
	$(PYTHON) scripts/migrate_neo4j_schema.py

# ── 백업 · DR (O-3) ───────────────────────────────────────────────────
backup:                                              # PG + Neo4j dump (docs/operations/backup_dr.md)
	bash scripts/ops/backup.sh

restore:                                             # 복원 (파괴적) — ARGS="--pg <dump> --neo4j <dump>"
	bash scripts/ops/restore.sh $(ARGS)

# ── Bridge candidate 검토 운영 (Q-1) ──────────────────────────────────
bridge-kpi:                                          # 검토 진행률 KPI (JSON)
	PYTHONPATH=src $(PYTHON) -m autonexusgraph.bridge_review kpi

bridge-expire:                                       # N일 미검토 candidate 자동 거부 (dry-run; ARGS="--days 180 --apply")
	PYTHONPATH=src $(PYTHON) -m autonexusgraph.bridge_review expire $(ARGS)

persons-collision:                                   # master.persons 동명·동년생 충돌 측정 (Q-3, read-only; --json)
	PYTHONPATH=src $(PYTHON) -m autonexusgraph.persons_collision $(ARGS)

freshness:                                           # source별 데이터 freshness + stale 판정 (Q-5, read-only; stale 시 exit 1)
	PYTHONPATH=src $(PYTHON) -m autonexusgraph.freshness $(ARGS)

metrics:                                             # Prometheus 메트릭 1회 출력 (O-5)
	PYTHONPATH=src $(PYTHON) -m autonexusgraph.metrics_exporter --once

serve-metrics:                                       # Prometheus exporter HTTP 서버 (O-5; :9105/metrics)
	PYTHONPATH=src $(PYTHON) -m autonexusgraph.metrics_exporter $(ARGS)

# ── PG hot-apply (운영 중 컨테이너에 신규 init/*.sql 멱등 적용) ────────────
# docker-entrypoint-initdb.d 는 빈 볼륨 첫 기동 시에만 실행되므로, 신규
# 마이그레이션 파일을 추가하면 본 타겟으로 수동 적용. 모든 신규 SQL 은
# `CREATE ... IF NOT EXISTS` 로 멱등이어야 함.
#   make migrate-schema-pg MIGRATE_FILE=15_autograph_production.sql
migrate-schema-pg:
	@test -n "$(MIGRATE_FILE)" || (echo "MIGRATE_FILE=NN_xxx.sql 필요" && exit 1)
	$(DOCKER_COMPOSE) exec -T postgres \
	    psql -U autonexusgraph -d autonexusgraph -v ON_ERROR_STOP=1 \
	    -f /docker-entrypoint-initdb.d/$(MIGRATE_FILE)

migrate-auto-production:
	$(MAKE) migrate-schema-pg MIGRATE_FILE=15_autograph_production.sql

migrate-auto-kama:
	$(MAKE) migrate-schema-pg MIGRATE_FILE=16_autograph_kama_macro.sql

migrate-auto-oem-news:
	$(MAKE) migrate-schema-pg MIGRATE_FILE=17_autograph_oem_news.sql

# ── Step별 묶음 target — 데이터 통합 고도화 (천천히 안 터지게) ───────────────
ingest-structural:    ; $(PYTHON) scripts/ingest/bulk_dart_structural.py
ingest-wikidata:      ; $(PYTHON) scripts/ingest/download_wikidata.py
ingest-wikipedia:     ; $(PYTHON) scripts/ingest/download_wikipedia.py
ingest-news:          ; $(PYTHON) scripts/ingest/download_news_rss.py
ingest-fss:           ; $(PYTHON) scripts/ingest/download_fss_press.py
ingest-ftc:           ; $(PYTHON) scripts/ingest/download_ftc_groups.py --year 2024
ingest-kosis:         ; $(PYTHON) scripts/ingest/download_kosis.py
ingest-sec:           ; $(PYTHON) scripts/ingest/download_sec_edgar.py
ingest-gleif:         ; $(PYTHON) scripts/ingest/download_gleif.py

# GLEIF KR API 보강 (registeredAs → business_no/jurir_no → corp_code 매칭).
# 무인증, public CC BY 4.0. sec.lei.corp_code + master.entity_map(id_type='lei')
# + bridge.corp_entity.lei 멱등 UPSERT. strong-match 승급률 측정.
ingest-gleif-enrich:     ; $(PYTHON) -m autonexusgraph.ingestion.gleif_enrich
ingest-gleif-enrich-dry: ; $(PYTHON) -m autonexusgraph.ingestion.gleif_enrich --dry-run --max-pages 1

# OpenAlex (특허×논문×재무 3중 cross) — ip.institution / ip.works + Neo4j Work/Institution/AUTHORED_AT.
# OPENALEX_API_KEY 필요 (없으면 mailto polite pool). 무료 키, 하루 10만 크레딧.
# NOTE: ipgraph 는 `src/` layout — `pip install -e .` 안 한 경우 PYTHONPATH=src 필요.
ingest-openalex:     ; PYTHONPATH=src:. $(PYTHON) -m ipgraph.ingestion.openalex --works-per-inst 20 --from-year 2020
ingest-openalex-dry: ; PYTHONPATH=src:. $(PYTHON) -m ipgraph.ingestion.openalex --dry-run --qids Q20718,Q59243,Q497534
load-openalex:       ; PYTHONPATH=src:. $(PYTHON) -m ipgraph.loaders.load_openalex
ingest-kipris:        ; PYTHONPATH=src:. $(PYTHON) -m ipgraph.ingestion.kipris
# KIPRIS XML → PG + Neo4j (source_type='kipris', jurisdiction='KR'). 7-key meta 100%.
# raw XML 이 raw/ip/kipris/*.xml 있거나, KIPRIS_API_KEY 설정 시 fetch + 적재.
load-kipris:          ; PYTHONPATH=src:. $(PYTHON) -m ipgraph.loaders.load_kipris
load-kipris-dry:      ; PYTHONPATH=src:. $(PYTHON) -m ipgraph.loaders.load_kipris --dry-run
# CPC scheme bulk (USPTO+EPO 공동, 무인증) → PG ip.cpc_scheme + Neo4j :CPCCode + :SUBCLASS_OF.
load-cpc:             ; PYTHONPATH=src:. $(PYTHON) -m ipgraph.loaders.load_cpc
load-cpc-dry:         ; PYTHONPATH=src:. $(PYTHON) -m ipgraph.loaders.load_cpc --skip-neo4j --sections A
# ip.assignee_corp_map PG → Neo4j (Assignee)-[:MAPPED_TO]->(Company) cross-domain bridge.
load-assignee-corp-map:     ; PYTHONPATH=src:. $(PYTHON) -m ipgraph.loaders.load_assignee_corp_map
load-assignee-corp-map-dry: ; PYTHONPATH=src:. $(PYTHON) -m ipgraph.loaders.load_assignee_corp_map --dry-run
# USPTO Open Data Portal bulk (PatentsView 후속) — raw/ip/uspto_odp/ 에 jsonl 있으면 적재.
# ingestion: parse only. loader: PG + Neo4j 7-key edge meta 100%. raw 미존재 시 graceful skip.
ingest-uspto-odp:     ; PYTHONPATH=src:. $(PYTHON) -m ipgraph.ingestion.uspto_odp
load-uspto-odp:       ; PYTHONPATH=src:. $(PYTHON) -m ipgraph.loaders.load_uspto_odp
load-uspto-odp-dry:   ; PYTHONPATH=src:. $(PYTHON) -m ipgraph.loaders.load_uspto_odp --dry-run
load-uspto-odp-smoke: ; PYTHONPATH=src:. $(PYTHON) -m ipgraph.loaders.load_uspto_odp --limit 100
ingest-law:           ; $(PYTHON) scripts/ingest/download_law.py
ingest-kcgs:          ; $(PYTHON) scripts/ingest/download_kcgs.py --with-body

load-entity-map:        ; $(PYTHON) scripts/load/load_entity_map.py
load-persons:           ; $(PYTHON) scripts/load/load_persons.py
load-graph-structural:  ; $(PYTHON) scripts/load/load_graph_structural.py
load-wikidata:          ; $(PYTHON) scripts/load/load_wikidata.py
load-wikipedia:         ; $(PYTHON) scripts/load/load_wikipedia.py
load-news:              ; $(PYTHON) scripts/load/load_news.py
load-graph-news:        ; $(PYTHON) scripts/load/load_graph_news_corel.py
load-sec:               ; $(PYTHON) scripts/load/load_sec_edgar.py
load-gleif:             ; $(PYTHON) scripts/load/load_gleif.py
load-kcgs:              ; $(PYTHON) scripts/load/load_kcgs.py --year 2024
build-wiki-chunks:      ; $(PYTHON) scripts/load/build_chunks_wikipedia.py

# ── BGE-M3 임베딩 서버 + backfill ────────────────────────────────────
serve-embeddings:                                    # 별도 터미널에서 띄우기
	CUDA_VISIBLE_DEVICES=0 $(PYTHON) scripts/serve_embeddings.py --embed-port 8080 --no-rerank --host 127.0.0.1

embed-chunks:                                        # vec.chunks.embedding 채우기 (서버 가동 후)
	EMBEDDING_URL=http://127.0.0.1:8080 $(PYTHON) scripts/load/embed_chunks.py --batch-size 64

embed-status:                                        # vec.chunks 임베딩 backfill 진행률 (Q-4, read-only; --json)
	PYTHONPATH=src $(PYTHON) -m autonexusgraph.embed_status $(ARGS)

# ── API + Web UI ────────────────────────────────────────────────────────────
serve-api:                                           # FastAPI /chat 엔드포인트
	$(PYTHON) -m uvicorn autonexusgraph.api.main:app --host 0.0.0.0 --port 31020 --reload

serve-ui:                                            # Streamlit 채팅 UI
	streamlit run src/autonexusgraph/ui/app.py --server.port 31021 --server.address 0.0.0.0

# ── 평가 ────────────────────────────────────────────────────────────────────
eval-smoke:                                          # 3 row 빠른 검증
	$(PYTHON) -m eval.runners.run_qa_eval \
	    --gold eval/qa_gold/gold_qa_v0.example.jsonl \
	    --adapters vector,graph,hybrid,sql_vec --max-cost-usd 0.10

eval-full:                                           # 100문항 풀 매트릭스 (gold 큐레이션 후)
	$(PYTHON) -m eval.runners.run_qa_eval \
	    --gold eval/qa_gold/gold_qa_v0.jsonl \
	    --adapters vector,graph,hybrid,sql_vec \
	    --max-cost-usd 5.00

# ── P3 / P4 LLM 추출 ───────────────────────────────────────────────────────
p3-extract-dry:                                      # 비용 추정만 — LLM 호출 0
	$(PYTHON) scripts/load/extract_business_report_relations.py \
	    --top-by-market-cap 30 --year 2024 --dry-run

p3-extract:                                          # 실제 호출 (가드 통과 후)
	$(PYTHON) scripts/load/extract_business_report_relations.py \
	    --top-by-market-cap 30 --year 2024 --max-cost 1.0

p4-load:
	$(PYTHON) scripts/load/load_validated_relations.py

ingest-step1: ingest-corp ingest-krx ingest-targets        # 마스터
ingest-step2: ingest-bulk ingest-structural                # DART 정형
ingest-step3: ingest-wikidata
ingest-step4: ingest-wikipedia
ingest-step5: ingest-ftc ingest-kosis ingest-fss
ingest-step6: ingest-news
ingest-step7: ingest-sec ingest-gleif ingest-kipris ingest-law
ingest-step8: ingest-kcgs                                  # KCGS 보도자료 모니터
	@echo ""
	@echo "→ KCGS 등급표 CSV 다운로드 후 data/raw/kcgs/<year>/ratings.csv 에 두고 make load-kcgs"

validate-quality:
	$(PYTHON) scripts/validate_cross_source.py

clean:
	find . -type d -name __pycache__ -not -path './_legacy/*' -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info


# ──────────────────────────────────────────────────────────────
# AutoGraph (자동차 도메인 — PRD v2.0)
# ──────────────────────────────────────────────────────────────
# 변수 (override 가능):
#   MAKE   ?= HYUNDAI
#   YEAR   ?= 2024
#   MAKES  ?= HYUNDAI,KIA
#   YEARS  ?= 2022-2024
MAKE  ?= HYUNDAI
YEAR  ?= 2024
MAKES ?= HYUNDAI,KIA,GENESIS
YEARS ?= 2022-2024

ingest-auto-vpic:
	$(PYTHON) -m autograph.ingestion.nhtsa_vpic --makes $(MAKES) --years $(YEARS)

ingest-auto-recalls:
	$(PYTHON) -m autograph.ingestion.nhtsa_recalls --make $(MAKE) --year $(YEAR)

ingest-auto-complaints:
	$(PYTHON) -m autograph.ingestion.nhtsa_complaints --make $(MAKE) --year $(YEAR)

ingest-auto-wikidata:
	$(PYTHON) -m autograph.ingestion.wikidata_auto --all

ingest-auto-safety:
	$(PYTHON) -m autograph.ingestion.nhtsa_safety_ratings --make $(MAKE) --year $(YEAR)

# Wikipedia 자동차 본문 (ko 1차 + en fallback). PG 의 master 테이블에서 entity 리스트 추출.
ingest-auto-wikipedia:
	$(PYTHON) -m autograph.ingestion.wikipedia_auto --all --lang ko --fallback-lang en

# EPA fueleconomy.gov bulk CSV (US 차량 연비·엔진·배출 spec, 키 불필요).
ingest-auto-epa:
	$(PYTHON) -m autograph.ingestion.epa_fueleconomy

# NHTSA ODI Investigations — 리콜 전단계 결함 조사 bulk flat-file (키 불필요, daily).
ingest-auto-investigations:
	$(PYTHON) -m autograph.ingestion.nhtsa_investigations

# SEC EDGAR Company Facts — 글로벌 OEM XBRL 재무 (키 불필요).
ingest-auto-sec-oem:
	$(PYTHON) -m autograph.ingestion.sec_oem

# NHTSA Manufacturer Communications (TSB) — manual download mode (URL retired).
# 사용자 안내 출력 후 종료. 다운로드한 zip 을 data/raw/auto/nhtsa_mfrcomm/ 에 배치.
ingest-auto-mfrcomm:
	$(PYTHON) -m autograph.ingestion.nhtsa_mfrcomm

ingest-auto-all: ingest-auto-vpic ingest-auto-wikidata ingest-auto-recalls ingest-auto-complaints ingest-auto-safety ingest-auto-wikipedia ingest-auto-epa ingest-auto-investigations ingest-auto-sec-oem
	@echo "[autograph] ingest-auto-all done."

neo4j-init-auto:
	$(PYTHON) -m autograph.loaders.neo4j_init

load-auto-pg:
	$(PYTHON) -m autograph.loaders.load_auto_pg --source all

load-auto-neo4j:
	$(PYTHON) -m autograph.loaders.load_auto_neo4j

load-auto-bridge:
	$(PYTHON) -m autograph.loaders.load_bridge

build-chunks-auto:
	$(PYTHON) -m autograph.loaders.build_chunks_auto --source all

# BOM 계층 + 공급망 / 표준 / 공장 / 컴플레인 / 리콜→부품 매칭 (P2 deterministic 추가 패스).
load-auto-nhtsa-taxonomy:
	$(PYTHON) -m autograph.loaders.load_nhtsa_component_taxonomy

load-auto-recall-components:
	$(PYTHON) -m autograph.loaders.load_recall_components

load-auto-complaint-components:
	$(PYTHON) -m autograph.loaders.load_complaint_components

load-auto-supplier-edges:
	$(PYTHON) -m autograph.loaders.load_supplier_edges

load-auto-seed-standards-plants:
	$(PYTHON) -m autograph.loaders.load_seed_standards_plants

load-auto-complaints-neo4j:
	$(PYTHON) -m autograph.loaders.load_complaints_neo4j

load-auto-aihub:
	$(PYTHON) -m autograph.loaders.load_auto_aihub --dataset all

load-auto-specs:
	$(PYTHON) -m autograph.loaders.load_auto_specs

load-auto-safety:
	$(PYTHON) -m autograph.loaders.load_auto_safety

# EPA fueleconomy.gov CSV → spec_measurements. variant 매칭 후 멱등 적재.
load-auto-epa:
	$(PYTHON) -m autograph.loaders.load_auto_epa

# NHTSA ODI Investigations → auto.events_investigations + Neo4j INVESTIGATED_BY.
load-auto-investigations:
	$(PYTHON) -m autograph.loaders.load_auto_investigations

# SEC EDGAR OEM facts → auto.oem_financials_sec + bridge.corp_entity (sec_cik).
load-auto-oem-sec:
	$(PYTHON) -m autograph.loaders.load_auto_oem_sec

# NHTSA TSB / Manufacturer Communications → vec.chunks (source='nhtsa_tsb').
# zip 이 raw 디렉토리에 없으면 안내만 출력. (URL 자동 다운 불가 — manual mode.)
load-auto-mfrcomm:
	$(PYTHON) -m autograph.loaders.load_auto_mfrcomm

# (VehicleModel)-[:CONTAINS_SYSTEM]->(System) — derived after CONTAINS_COMPONENT 적재.
derive-auto-contains-system:
	$(PYTHON) -m autograph.loaders.derive_contains_system

# Wikidata P176 (manufactured by) — 부품↔공급사 staging seed (B 등급 0.80).
# 이후 validate-auto-p4 가 Neo4j SUPPLIED_BY 로 promote.
load-wikidata-part-supplies:
	$(PYTHON) -m autograph.loaders.load_wikidata_part_supplies

# 전체 P2 적재 — 의존 순서를 명시.
#   neo4j-init → master → standards seed → safety/epa → 계층/공급/컴플 → derive → wikidata staging
# load-auto-safety 는 standards 시드 이후 (Standard {code:'NCAP_US'} 노드 필요).
# load-auto-epa 는 variant 마스터 적재 이후 (matching 대상).
# derive-auto-contains-system 은 aihub (CONTAINS_COMPONENT) 이후.
# load-wikidata-part-supplies 는 wikidata raw 적재 이후 — staging 만 채움 (Neo4j 는 P4).
load-auto-all: neo4j-init-auto load-auto-pg load-auto-specs load-auto-neo4j \
               load-auto-bridge load-auto-seed-standards-plants \
               load-auto-safety load-auto-epa load-auto-aihub \
               load-auto-nhtsa-taxonomy \
               load-auto-supplier-edges \
               load-auto-complaints-neo4j load-auto-recall-components \
               load-auto-complaint-components \
               load-auto-investigations load-auto-oem-sec \
               derive-auto-contains-system \
               load-wikidata-part-supplies \
               load-manufactured-at \
               load-sandang-processes \
               load-kama-macro \
               load-dart-production \
               build-chunks-auto
	@echo "[autograph] load-auto-all done."

# ── P3 LLM 추출 + P4 검증 (LLM 호출 비용 발생 — 명시적으로만 실행).
# 비용만 추정 (LLM 호출 안 함): make extract-auto-p3-cost
extract-auto-p3-cost:
	$(PYTHON) -m autograph.extractors.run_p3 \
	    --manufacturer-ids $(MFR_IDS) --limit $(P3_LIMIT) --dry-run-cost

P3_LIMIT ?= 50
MFR_IDS  ?= 498
# 실제 LLM 호출 — hard limit USD (BudgetExceeded 보호).
P3_HARD_LIMIT ?= 2.0
extract-auto-p3:
	$(PYTHON) -m autograph.extractors.run_p3 \
	    --manufacturer-ids $(MFR_IDS) --limit $(P3_LIMIT) \
	    --hard-limit-usd $(P3_HARD_LIMIT)

validate-auto-p4:
	$(PYTHON) -m autograph.extractors.cross_validate

# P3 → P4 → Neo4j (전체).
extract-validate-auto: extract-auto-p3 validate-auto-p4
	@echo "[autograph] P3+P4 done."

eval-auto:
	$(PYTHON) -m eval.runners.run_qa_eval \
	    --gold eval/qa_gold/gold_qa_auto_v0.jsonl \
	    --adapters hybrid \
	    --run-id "auto_$$(date +%Y%m%d_%H%M%S)"

# Cross-Domain QA — PRD §8.1 (CD-L1~L4 4단계 층화) 전용.
eval-cross:
	$(PYTHON) -m eval.runners.run_qa_eval \
	    --gold eval/qa_gold/gold_qa_cross_v0.jsonl \
	    --adapters hybrid \
	    --run-id "cross_$$(date +%Y%m%d_%H%M%S)"

# IPGraph QA — gold_qa_ip_v0.jsonl × hybrid. PRD §10 DoD #16.
eval-ip:
	$(PYTHON) -m eval.runners.run_qa_eval \
	    --gold eval/qa_gold/gold_qa_ip_v0.jsonl \
	    --adapters hybrid \
	    --run-id "ip_$$(date +%Y%m%d_%H%M%S)" \
	    --max-cost-usd 1.0

# ─── DoD audit (PRD §10) ─────────────────────────────────────────
audit-bom-coverage:
	$(PYTHON) scripts/audit/bom_coverage.py

audit-edge-meta:
	$(PYTHON) scripts/audit/edge_meta_invariants.py --strict

audit-trace:
	# PRD §10 DoD #17 (b) — Langfuse 실측 (turn별 token/cost/replan).
	# 기본 = simulation (LLM 비용 0). --full 옵션으로 실제 run_agent 호출 가능.
	PYTHONPATH=src:. $(PYTHON) scripts/audit/trace_smoke.py

audit-ontology:
	# PRD §10 DoD #17 (c) — 온톨로지 pydantic strict 검증 (핵심+보조 yaml + cypher cross).
	# Y-2: 도메인 격리 엄격 검증은 ARGS="--strict-cross" (cross-domain ref → ERROR).
	PYTHONPATH=src:. $(PYTHON) scripts/audit/ontology_validate.py $(ARGS)

audit-eval-matrix:
	# PRD §10 DoD #17 (d) — 축소 평가 매트릭스 (4 어댑터 × FAST × rerank ablation).
	# 기본 = simulation (LLM 비용 0). --full 옵션으로 실제 LLM 호출.
	# 사용자 ARGS 전달 가능: make audit-eval-matrix ARGS="--full --limit 30"
	PYTHONPATH=src:. $(PYTHON) scripts/audit/eval_matrix_smoke.py $(ARGS)

audit-eval-matrix-full:
	# PRD §10.7 thesis 측정 — --full + multi-hop 16 row 포함 위해 limit 30 (default).
	# 비용 추정: 8 cells × 30 row ≈ $3 (gpt-4o-mini, hybrid 비중 큼).
	PYTHONPATH=src:. $(PYTHON) scripts/audit/eval_matrix_smoke.py --full

audit-mcp:
	# PRD §10 DoD #17 (a) — MCP 래퍼 wire-up.
	# mcp SDK 미설치 시 SKIPPED + tool discovery 52건만 검증.
	# 설치 시 build_mcp_server boot + tool list 검증.
	PYTHONPATH=src:. $(PYTHON) scripts/audit/mcp_smoke.py

audit-ipgraph:
	# PRD §10 DoD #15/#16 — IPGraph (도메인3) 의 plug-in wire-up.
	# handler/router/ontology/cypher_templates(25)/gold(ip=30+cross=8) 검증.
	PYTHONPATH=src:. $(PYTHON) scripts/audit/ipgraph_smoke.py

audit-calibrate:
	# PRD §3.5 P1-(4) confidence calibration 실측 — Platt scaling + reliability diagram.
	# 최신 eval/reports/<run>/ 자동 선택. EM=0 인 LLM-broken 데이터셋 시 --metric f1 시도 권장.
	# sklearn/matplotlib 미설치 시 graceful skip. 정답 클래스 단일이면 SKIPPED.
	PYTHONPATH=src:. $(PYTHON) scripts/audit/calibrate_confidence.py $(ARGS)

audit-external-ratio:
	# P1-(7) 외부 큐레이터 비율 측정 — PRD §11.6 / gold_qa_guide §6 KPI.
	# tags / notes / qid 의 external_curator/allganize_external/academic 마크 검출.
	# `--strict` 옵션 시 30% 미달 → exit 1 (CI 게이트). 기본은 보고만.
	PYTHONPATH=src:. $(PYTHON) scripts/audit/external_curator_ratio.py $(ARGS)

audit-b-issues:
	# P2-(10) data_inventory.md §3 B-issue 미해결 4 건 (B6/B7/B10/B11) 의 실시간 상태.
	# 진단 SOP (SQL/cypher) 를 runnable Python 으로 응축. RESOLVED/ACTIVE/MONITORING 분류.
	# `--strict` 옵션 시 ACTIVE 또는 ERROR 있으면 exit 1 (CI 게이트).
	PYTHONPATH=src:. $(PYTHON) scripts/audit/b_issues.py $(ARGS)

convert-allganize:
	# Allganize RAG-Evaluation-Dataset-KO → 본 시스템 스키마 변환.
	# ARGS 로 --src / --domain / --out 지정. 예:
	#   make convert-allganize ARGS="--src data/external/allganize-rag-kor/finance \
	#                                  --domain finance \
	#                                  --out eval/qa_gold/staging/gold_qa_allganize_v0.jsonl"
	PYTHONPATH=src:. $(PYTHON) scripts/audit/convert_allganize_gold.py $(ARGS)

# ── 제조 데이터 끝까지 (M-11~M-14) — 정형, LLM 0% ─────────────
load-factoryon:
	# 팩토리온 raw json → auto.factoryon_registry PG (data.go.kr 15087611).
	PYTHONPATH=src:. $(PYTHON) -m autograph.loaders.load_factoryon

load-factoryon-dry:
	PYTHONPATH=src:. $(PYTHON) -m autograph.loaders.load_factoryon --dry-run

load-kosis:
	# KOSIS raw json → macro.kosis_series PG.
	PYTHONPATH=src:. $(PYTHON) -m autograph.loaders.load_kosis_industry

load-kosis-dry:
	PYTHONPATH=src:. $(PYTHON) -m autograph.loaders.load_kosis_industry --dry-run

ingest-wikidata-cell-chem:
	# Wikidata 배터리 셀 chem (cathode) 메타 수집 — CC0, 무인증.
	PYTHONPATH=src:. $(PYTHON) -m autograph.ingestion.wikidata_cell_chem

audit-dod:
	# CORE_DIFF_BASELINE 이력 (PRD §10.12 / §11.1):
	#   - 4049caf  : 2026-05 Phase B 안정화 (도메인1+2 finance+auto 완료) — 본 PR 이전 anchor.
	#   - bab9411  : 2026-06-01 도메인3 (ipgraph) 통합 직전 reset.
	#   - 414bc1b  : 2026-06-01 도메인3 (ipgraph) 통합 + audit/MCP/ontology 인프라 일괄 PR
	#                완료 anchor. bab9411 → 414bc1b: +1,877 LOC = 13.32%
	#                (의도된 통합 변경 — MCP wire-up / ontology schema / plugin registration).
	#   - 831e72d  : 2026-06-02 상용화 P0/P1 기능 일괄 (O-1 인증 / Q-1 bridge 검토 /
	#                Q-4 embed-status / E-3 hop 메트릭) 완료 anchor (current default).
	#                414bc1b → 831e72d: +1,425/-158 = 1,583 LOC = 10.28% (의도된 기능 추가).
	# 도메인 추가/대형 리팩터/대형 기능 일괄 마다 reset → 누적 ratio 가 5% 위협 시 의도된
	# 변경 인지 식별. 운영자가 별도 commit 으로 baseline 이동 원하면 env override.
	PYTHONPATH=src CORE_DIFF_BASELINE=$${CORE_DIFF_BASELINE:-831e72d} $(PYTHON) scripts/audit/dod_audit.py

validate-gold-qa:
	$(PYTHON) scripts/audit/validate_gold_qa.py eval/qa_gold/*.jsonl

# ─── 외부 데이터 소스 (graceful skip — 키 없으면 0 byte) ───────────
ingest-datagokr-recalls:
	$(PYTHON) -m autograph.ingestion.datagokr_recalls

ingest-datagokr-inspections:
	$(PYTHON) -m autograph.ingestion.datagokr_inspections

ingest-car-go-kr:
	$(PYTHON) -m autograph.ingestion.car_go_kr_recalls

ingest-katri:
	$(PYTHON) -m autograph.ingestion.katri_tic

ingest-kncap:
	$(PYTHON) -m autograph.ingestion.kncap

load-datagokr-recalls:
	$(PYTHON) -m autograph.loaders.load_datagokr_recalls

load-datagokr-inspections:
	$(PYTHON) -m autograph.loaders.load_datagokr_inspections

load-kncap:
	$(PYTHON) -m autograph.loaders.load_kncap

load-manufactured-at:
	$(PYTHON) -m autograph.loaders.load_manufactured_at

# 회사 귀속 공정 — (:ProcessStep)-[:PERFORMED_AT]->(:Plant). manual_seed B등급.
# 선행: load-auto-seed-standards-plants (:Plant code). DoD #19 (≥30 회사 귀속).
load-performed-at:
	$(PYTHON) -m autograph.loaders.load_performed_at

load-performed-at-dry:
	$(PYTHON) -m autograph.loaders.load_performed_at --dry-run

# factoryon registry → :Plant 승격(A) + OWNS_PLANT + PERFORMED_AT 확대(candidate).
# 선행: load-factoryon (PG auto.factoryon_registry).
load-factoryon-plants:
	$(PYTHON) -m autograph.loaders.load_factoryon_plants

load-factoryon-plants-dry:
	$(PYTHON) -m autograph.loaders.load_factoryon_plants --dry-run

# 한글 리콜 결함 → 공정 (:Recall)-[:CAUSED_BY_PROCESS]->(:Process). candidate.
# 선행: KR 리콜 적재 (auto.events_recalls source=datagokr_kotsa) + :Recall 노드.
load-recall-process-map:
	$(PYTHON) -m autograph.loaders.load_recall_process_map

load-recall-process-map-dry:
	$(PYTHON) -m autograph.loaders.load_recall_process_map --dry-run

# 부품 → 공정 (:Part)-[:PRODUCED_BY]->(:ProcessStep). candidate (system 추론). G-2.
load-produced-by:
	$(PYTHON) -m autograph.loaders.load_produced_by

load-produced-by-dry:
	$(PYTHON) -m autograph.loaders.load_produced_by --dry-run

# ─── 제조 공정 / 생산 — 사용자 명시 P0 ─────────────────────────
# 산단공 합성 공정데이터 (15151075) — 수동 CSV 다운로드 → :Process 사전.
load-sandang-processes:
	$(PYTHON) -m autograph.loaders.load_sandang_processes

load-sandang-processes-dry:
	$(PYTHON) -m autograph.loaders.load_sandang_processes --dry-run

# 팩토리온 공장등록정보 (15087611) — DATA_GO_KR_API_KEY 필요, graceful skip.
#   make ingest-factoryon-company NAME=현대자동차
ingest-factoryon-company:
	$(PYTHON) -m autograph.ingestion.factoryon_registry --by-company "$(NAME)"

ingest-factoryon-factory-no:
	$(PYTHON) -m autograph.ingestion.factoryon_registry --by-factory-no "$(FNO)"

ingest-factoryon-complex:
	$(PYTHON) -m autograph.ingestion.factoryon_registry --by-industrial-complex "$(COMPLEX)"

# KAMA 매크로 통계 (data.go.kr 15051116/15051118) — CSV 형식, 키 불필요.
load-kama-macro:
	$(PYTHON) -m autograph.loaders.load_kama_macro

load-kama-macro-dry:
	$(PYTHON) -m autograph.loaders.load_kama_macro --dry-run

# USGS Mineral Commodity Summaries (MCS) — L6 핵심광물 (Li/Ni/Co/Mn/Graphite).
# 무인증, PDF 다운 → text 파싱 → auto.master_minerals + Neo4j :Mineral/:Material/:DERIVED_FROM.
load-usgs-minerals:
	$(PYTHON) -m autograph.loaders.load_usgs_minerals --year 2025

load-usgs-minerals-dry:
	$(PYTHON) -m autograph.loaders.load_usgs_minerals --year 2025 --dry-run

# DART 사업보고서 "III. 생산 및 설비" → auto.plant_capacity + plant_production
# + (선택) Neo4j (:Manufacturer)-[:MANUFACTURED_AT]->(:Plant) 동기화.
# 대상 6 OEM: 현대차/기아/모비스/한온/만도/위아.
load-dart-production:
	$(PYTHON) -m autograph.loaders.load_dart_production

load-dart-production-dry:
	$(PYTHON) -m autograph.loaders.load_dart_production --dry-run

load-dart-production-no-neo4j:
	$(PYTHON) -m autograph.loaders.load_dart_production --no-neo4j

# 데이터 채널 트래픽라이트 — 산단공/DART/KAMA/팩토리온/리콜 상태 한눈에.
audit-data-channels:
	$(PYTHON) scripts/audit/data_channels.py

# ── OEM IR/뉴스룸 — 사용자 명시 P1 (B2). 약관 준수 crawler ──────
# robots.txt + ToS 게이트 (_license.OEM_NEWSROOM_POLICY). Kia 한국은
# robots.txt Disallow 라 active=False — 기본 비활성. 키 불필요.
ingest-oem-ir-hyundai:
	$(PYTHON) -m autograph.ingestion.oem_ir_newsroom --oem hyundai --limit 50

ingest-oem-ir-mobis:
	$(PYTHON) -m autograph.ingestion.oem_ir_newsroom --oem mobis --limit 50

ingest-oem-ir-policies:
	$(PYTHON) -m autograph.ingestion.oem_ir_newsroom --list-policies

load-oem-ir-news:
	$(PYTHON) -m autograph.loaders.load_oem_ir_news --all

load-oem-ir-news-dry:
	$(PYTHON) -m autograph.loaders.load_oem_ir_news --all --dry-run

# LLM P3 IR 추출 — IRRelationExtractor 경유.
# 본문 → MANUFACTURED_AT / CAPACITY_REPORTED 후보 → auto.staging_relations.
# 비용 추정 ($0.024 / 25 chunks @ gpt-4o-mini):
extract-ir-p3-cost:
	$(PYTHON) -m autograph.extractors.run_p3_ir --oems hyundai --dry-run-cost

# 실제 호출 — IR_P3_HARD_LIMIT 보호 (기본 $1.0).
IR_P3_HARD_LIMIT ?= 1.0
extract-ir-p3:
	$(PYTHON) -m autograph.extractors.run_p3_ir \
	    --oems hyundai \
	    --hard-limit-usd $(IR_P3_HARD_LIMIT)

# Plant 노드 wiki 속성 보강 — Wikipedia plant 청크 → :Plant attributes.
load-plant-wiki-enrichment:
	$(PYTHON) -m autograph.loaders.load_plant_wiki_enrichment

# Korean OEM alias backfill — auto.master_manufacturers 의 aliases 배열에
# 한국어 변형 + KGM/RENAULT KOREA 신규 entry.
load-master-korean-aliases:
	$(PYTHON) -m autograph.loaders.load_master_korean_aliases
