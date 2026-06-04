# 모니터링 · 알람 (O-5)

> **SSOT**: 본 문서. exporter `src/autonexusgraph/metrics_exporter.py` · 설정 `infra/monitoring/` · 배포는 [production_deploy.md](production_deploy.md). Langfuse(turn별 trace)와 보완 — Langfuse 는 LLM turn 관측, 본 스택은 인프라·데이터·비용 시계열.

---

## 0. 구성

```
exporter(:9105/metrics)  ──scrape──>  Prometheus(:9090)  ──>  Grafana(:3000)
                                            └─ alerts.yml ──> (Alertmanager 연동은 후속)
```

- **exporter**: prometheus_client 의존 없이 텍스트 포맷 직접 렌더 (stdlib http.server). 기존 read-only audit 모듈(embed_status/bridge_review/freshness/cost_log) 조합.
- compose: `docker-compose.prod.yml` 의 `metrics`/`prometheus`/`grafana` 서비스 (prod 오버레이).

---

## 1. 노출 메트릭 (`anxg_*`)

| metric | type | 의미 |
|---|---|---|
| `anxg_up{component}` | gauge | postgres/neo4j 도달(1/0) |
| `anxg_vec_chunks_total` / `_embedded` | gauge | 청크 수 / 임베딩 완료 수 |
| `anxg_neo4j_nodes_total` | gauge | Neo4j 노드 수 |
| `anxg_bridge_entries{status}` | gauge | bridge candidate/reviewed/rejected/total |
| `anxg_llm_cost_usd_total` | counter | 누적 LLM 비용 (cost_log.jsonl) |
| `anxg_data_sources_stale` / `_total` | gauge | freshness stale 소스 수 (Q-5) |
| `anxg_llm_turns_total{status}` | counter | ops.llm_usage turn 수 (error rate 산출) |
| `anxg_scrape_errors` | gauge | 이번 scrape 실패 collector 수 |

각 collector graceful — 일부 실패해도 scrape 는 200, `anxg_scrape_errors` 로 카운트.

---

## 2. 로컬 확인

```bash
make metrics            # 1회 텍스트 출력 (DB 연결 필요)
make serve-metrics      # :9105/metrics HTTP 서버
curl localhost:9105/metrics
```

---

## 3. 배포 (prod 오버레이)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d \
    metrics prometheus grafana
```

- `.env.prod` 에 `GRAFANA_PASSWORD` 필수.
- Prometheus/Grafana 는 `127.0.0.1` 바인딩 — reverse proxy 뒤에서만 외부 노출.
- Grafana 접속 → datasource 에 Prometheus(`http://anxg-prometheus:9090`) 추가 → `infra/monitoring/grafana_dashboard.json` **Import** (datasource=Prometheus 선택).

---

## 4. 알람 (`infra/monitoring/alerts.yml`)

| alert | 조건 | severity |
|---|---|---|
| PostgresDown / Neo4jDown | `anxg_up==0` 2m | critical |
| ExporterDown | `up{job}==0` 2m | critical |
| LLMCostSpike | `increase(anxg_llm_cost_usd_total[1h]) > 5` | warning |
| DataSourcesStale | `anxg_data_sources_stale > 0` 30m | warning |
| MetricsScrapeErrors | `anxg_scrape_errors > 0` 10m | warning |

> 실제 알림 발송(Slack/email)은 **Alertmanager** 연동 필요 — 후속(임계·채널은 운영 환경별). 본 PR 은 규칙 정의까지.

---

**관련**: [production_deploy.md](production_deploy.md) · [backup_dr.md](backup_dr.md) · `src/autonexusgraph/metrics_exporter.py` · README §12.3 · BACKLOG O-5
