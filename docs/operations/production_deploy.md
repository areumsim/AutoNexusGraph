# Production 배포 가이드 (O-2)

> **SSOT**: 본 문서 = production 배포 절차. **dev 환경은 [docs/quickstart.md](../quickstart.md) / [docs/operations/docker_setup.md](docker_setup.md)** 로 분리 — 본 문서는 dev 절차를 반복하지 않는다.
>
> **범위**: 이미지 빌드 · compose prod 프로파일 · health probe · reverse proxy/TLS · secrets · k8s · blue-green/canary · 멀티 인스턴스 스케일. **백업·DR (O-3)** 은 [§8](#8-백업--dr-o-3) 에서 요약 + 후속 항목 링크.
>
> **상태**: 배포 산출물 (`infra/Dockerfile`, `docker-compose.prod.yml`) 은 본 PR 에서 신설 (실행 가능). k8s 매니페스트는 예시 (적용 전 환경값 치환 필요).

---

## 0. dev vs production — 무엇이 다른가

| 항목 | dev (Quickstart) | production (본 문서) |
|---|---|---|
| 앱 실행 | `make serve-api` (`uvicorn --reload`, :31020) | 빌드 이미지 + `--workers N` (--reload 없음) |
| 소스 | 컨테이너 안 직접 / bind-mount | 이미지에 COPY (불변) |
| DB 비밀번호 | `autonexusgraph_dev` (compose 기본) | env 필수 주입 — 기본값 사용 금지 |
| API 인증 | `API_KEYS` 미설정 = open 모드 | **`API_KEYS` 필수** (O-1) |
| 외부 노출 | uvicorn http 직접 | reverse proxy + TLS 뒤에만 |
| DB 포트 | 호스트 31009/31010/31011 노출 | 127.0.0.1 바인딩 또는 미노출 |
| 시크릿 | `.env` 한 곳 | `.env.prod` (배포 호스트 only) / vault / k8s secret |

---

## 1. 사전 점검 (배포 전 게이트)

```bash
# 1) mock 정합성 (DB·LLM 없이) — pre-push 게이트
make smoke-e2e

# 2) DoD 트래픽라이트 — 보고는 `make audit-dod`. strict 게이트(❌ 1건 이상 exit 1)는
#    make 가 --strict 를 가로채므로 스크립트 직접 호출:
PYTHONPATH=src python scripts/audit/dod_audit.py --strict

# 3) 시크릿 점검 — .env.prod 에 dev 기본값/placeholder 가 남아있지 않은지
grep -E 'autonexusgraph_dev|changeme|your-key' .env.prod && echo "❌ 기본값 잔존" || echo "✅ ok"
```

`.env.prod` 필수 키 (없으면 기동 실패):

```ini
# DB (compose 기본값 덮어씀)
POSTGRES_PASSWORD=<강한 비밀번호>
NEO4J_PASSWORD=<강한 비밀번호>
DB_DATA_ROOT=/srv/autonexusgraph/data      # 영속 볼륨 루트

# 앱 접속 (컨테이너 네트워크 내부 이름 사용)
POSTGRES_HOST=ar-postgres
NEO4J_URI=bolt://ar-neo4j:7687

# API 보안 (O-1) — 외부 노출 시 필수
API_KEYS=<token>:<user_id>,...
API_RATE_LIMIT_PER_MIN=120

# LLM (필요 provider 만)
ANTHROPIC_API_KEY=...        # 또는 OPENAI_API_KEY / GOOGLE_API_KEY
LLM_COST_HARD_LIMIT_USD=50   # prod 누적 한도 (dev 기본 5)

# 운영
APP_ENV=production
IMAGE_TAG=<git sha 또는 버전>
API_WORKERS=4
```

> `.env.prod` 는 절대 커밋 금지 — `.gitignore` 가 `.env.*` 무시 + `!.env.example` 예외 (O-2 에서 추가). placeholder 는 `.env.example` 만 추적.

---

## 2. 이미지 빌드

`infra/Dockerfile` — multi-stage (builder venv → slim runtime), non-root(uid 10001), `/health` curl probe 포함. api/web/ingestion-worker 공용 (command override).

```bash
docker build -f infra/Dockerfile -t autonexusgraph:$(git rev-parse --short HEAD) .

# 런타임 extras 변경 (예: 데이터 적재 worker 는 ingest 추가):
docker build -f infra/Dockerfile \
  --build-arg RUNTIME_EXTRAS=agent,llm,db,ui,ingest \
  -t autonexusgraph:ingest .
```

레지스트리 push (k8s/원격 배포 시):

```bash
docker tag autonexusgraph:<tag> <registry>/autonexusgraph:<tag>
docker push <registry>/autonexusgraph:<tag>
```

---

## 3. Compose prod 프로파일

base `docker-compose.yml` (DB 2개) + `docker-compose.prod.yml` 오버레이 (api/web 활성 + DB 비밀번호 강제).

```bash
# 검증 — 머지 결과 확인 (먼저!)
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod config

# 기동
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d

# 상태/로그
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f --tail=100 api
```

오버레이 핵심:
- `api` / `web` 빌드 이미지 사용, `restart: unless-stopped`, `depends_on: { condition: service_healthy }` (DB 준비 후 기동).
- 포트는 **127.0.0.1 바인딩** (`127.0.0.1:8000:8000`) — 직접 외부 노출 X, reverse proxy 경유.
- DB 비밀번호는 `${POSTGRES_PASSWORD:?...}` 로 **미설정 시 거부**.
- `deploy.resources.limits` 로 CPU/메모리 상한.

---

## 4. 마이그레이션 (스키마)

PG init SQL (`infra/postgres/init/*.sql`, 현재 31개) 은 **빈 볼륨 첫 기동 시 자동 적용**. 기존 볼륨에 신규 SQL 적용은 **멱등 hot-apply** — 상세 [docs/operations/migrations.md](migrations.md).

```bash
# 신규 init SQL 을 기동 중 인스턴스에 hot-apply (멱등 — 변경 0 이면 무동작)
for f in infra/postgres/init/*.sql; do
  docker exec -i ar-postgres psql -U autonexusgraph -d autonexusgraph < "$f"
done

# Neo4j 스키마 정합성 마이그레이션 (1회, 멱등) — make migrate-schema 와 동일
docker compose ... exec api python scripts/migrate_neo4j_schema.py
```

> 배포 순서: **DB 기동 → 마이그레이션 확인 → app 기동**. 오버레이의 `depends_on healthy` 가 DB ready 를 보장하지만, 스키마 변경 배포는 app 롤아웃 전에 적용.

---

## 5. Reverse proxy + TLS

uvicorn/Streamlit 을 직접 외부에 노출하지 않는다. reverse proxy 가 TLS 종료 + 라우팅 + (선택) 글로벌 rate limit 담당.

**Caddy (자동 TLS — 권장):** `infra/caddy/Caddyfile`

```caddy
api.example.com {
    reverse_proxy localhost:8000
}
app.example.com {
    reverse_proxy localhost:8501
}
```

`docker-compose.prod.yml` 의 `caddy` 서비스 주석 해제 후 재기동. Let's Encrypt 인증서 자동 발급·갱신.

**nginx 대안:** TLS 인증서 (certbot) + `proxy_pass` + SSE 를 위한 `proxy_buffering off;` (스트리밍 `/chat/stream` 필수) + `proxy_read_timeout 120s;`.

> O-1 의 in-memory rate limit 은 **worker/인스턴스 별** 이다. 하드 글로벌 한도가 필요하면 reverse proxy 계층에서 추가 (Caddy `rate_limit`, nginx `limit_req`).

---

## 6. Health probe

`/health` 엔드포인트 (인증 불요) — PG/Neo4j ping 결과 JSON. CLI: `python scripts/healthcheck.py`.

- **Compose**: `api` 서비스에 curl `/health` healthcheck 내장 (오버레이).
- **k8s**: liveness = TCP/HTTP `/health`, readiness 동일하되 `start_period`/`initialDelaySeconds` 로 DB 연결 대기.

```yaml
# k8s probe 예시
livenessProbe:
  httpGet: { path: /health, port: 8000 }
  initialDelaySeconds: 30
  periodSeconds: 15
readinessProbe:
  httpGet: { path: /health, port: 8000 }
  initialDelaySeconds: 20
  periodSeconds: 10
```

> 주의: `/health` 는 DB 실패 시에도 HTTP 200 + 본문에 `"postgres":"error: ..."` 를 반환한다 (fail-soft). 엄격한 readiness 가 필요하면 본문 파싱 probe 또는 `/health` 를 strict 모드로 확장.

---

## 7. Kubernetes (예시)

compose 로 충분하면 생략. 멀티 인스턴스·오토스케일이 필요할 때.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: autonexusgraph-api }
spec:
  replicas: 3
  selector: { matchLabels: { app: anxg-api } }
  strategy:
    type: RollingUpdate
    rollingUpdate: { maxSurge: 1, maxUnavailable: 0 }   # 무중단
  template:
    metadata: { labels: { app: anxg-api } }
    spec:
      containers:
        - name: api
          image: <registry>/autonexusgraph:<tag>
          ports: [{ containerPort: 8000 }]
          envFrom:
            - secretRef: { name: anxg-secrets }    # API_KEYS / DB 비번 / LLM 키
          env:
            - { name: APP_ENV, value: production }
            - { name: API_WORKERS, value: "2" }
          livenessProbe:  { httpGet: { path: /health, port: 8000 }, initialDelaySeconds: 30 }
          readinessProbe: { httpGet: { path: /health, port: 8000 }, initialDelaySeconds: 20 }
          resources:
            requests: { cpu: "500m", memory: 1Gi }
            limits:   { cpu: "2",    memory: 2Gi }
---
apiVersion: v1
kind: Secret
metadata: { name: anxg-secrets }
type: Opaque
stringData:
  POSTGRES_PASSWORD: "<...>"
  NEO4J_PASSWORD: "<...>"
  API_KEYS: "<token>:<user>"
  ANTHROPIC_API_KEY: "<...>"
```

> PG/Neo4j 는 k8s 안에 띄우기보다 **관리형 DB (RDS/AuraDB) 또는 StatefulSet + PVC** 권장 — 본 앱은 stateless (체크포인트는 PG `anxg_chat` 스키마에 위임).

---

## 8. 멀티 인스턴스 스케일 — 주의점

| 컴포넌트 | 멀티 인스턴스 안전성 | 비고 |
|---|---|---|
| LangGraph PG checkpointer | ✅ 공유 가능 | 상태는 PG `chat` 스키마. 동시 write 는 thread_id 단위 (충돌 드묾) |
| `/chat` 세션 | ✅ stateless | history 는 매 turn PG 로드 |
| **O-1 rate limit** | ⚠️ **per-worker/per-pod** | in-memory — N workers ⇒ 실질 한도 ×N. 하드 글로벌 한도는 reverse proxy/redis (§5) |
| **Langfuse trace** | ✅ | ContextVar 격리, worker-local 송신 |
| LLM cost hard limit | ⚠️ per-process | `LLM_COST_HARD_LIMIT_USD` 는 프로세스 누적. 글로벌 비용 통제는 provider 측 한도 병행 |
| 임베딩 (BGE-M3) | 별도 서비스 | GPU TEI 컨테이너 또는 외부 endpoint (`EMBEDDING_URL`) 공유 |

---

## 9. Blue-green / Canary

**Blue-green (compose):** 새 `IMAGE_TAG` 로 `api` 를 다른 컨테이너명/포트(예: 8002)로 기동 → `/health` 확인 → reverse proxy upstream 을 green 으로 전환 → blue 종료. 롤백 = upstream 을 blue 로 되돌림.

**Canary (k8s):** 두 Deployment(stable/canary) + Service selector 가중치 (Argo Rollouts / 서비스메시) 로 5%→50%→100% 단계 증가. 각 단계에서 error rate / latency (Langfuse + `/health`) 확인.

**롤백:** 이전 `IMAGE_TAG` 재배포 (이미지는 불변). **스키마 변경이 포함된 배포는 forward-compatible (멱등 + additive) 로 작성** — init SQL 은 `IF NOT EXISTS` / `ON CONFLICT` 라 롤백 시 구버전 앱도 동작.

---

## 10. 백업 · DR (O-3)

> **SSOT**: [backup_dr.md](backup_dr.md). 스크립트 `scripts/ops/{backup,restore}.sh`.

```bash
make backup                                          # PG pg_dump -Fc + Neo4j community dump (보존 prune)
make restore ARGS="--pg <dump> --neo4j <dump>"       # 파괴적 복원 (FORCE=1 로 프롬프트 생략)
# cron 예: 0 3 * * *  cd /srv/autonexusgraph && bash scripts/ops/backup.sh >> /var/log/anxg_backup.log 2>&1
```

- `anxg_vec.chunks` 임베딩은 PG dump 에 **포함** → 정상 복원 시 재생성 불필요. RPO ≤ 24h(일일 cron) / RTO 수~수십 분(dump 보유).
- Neo4j community = online backup 불가 → 대상 DB STOP→dump→START (다운타임 = dump 시간).
- 재앙(dump 소실) 시에만 raw 재적재 + BGE-M3 재임베딩 ~수 시간. off-site 동기화 + 분기 복원 드릴 권장 — 상세 [backup_dr.md](backup_dr.md).

---

## 11. 운영 체크리스트

- [ ] `.env.prod` 에 dev 기본값/placeholder 없음, `API_KEYS` 설정됨
- [ ] `make smoke-e2e` + `PYTHONPATH=src python scripts/audit/dod_audit.py --strict` 통과
- [ ] 이미지 빌드 + 레지스트리 push (k8s)
- [ ] `docker compose ... config` 머지 검증 OK
- [ ] DB 포트 외부 미노출 (127.0.0.1 바인딩 / 방화벽)
- [ ] reverse proxy TLS 인증서 발급 + SSE 버퍼링 off
- [ ] `/health` 200, PG/Neo4j ok
- [ ] 첫 인증 요청 (`X-API-Key`) 200 / 무키 401 확인
- [ ] 모니터링·알람 (Prometheus/Grafana) — backlog O-5
- [ ] 백업 cron — backlog O-3

---

**관련 문서**: [docker_setup.md](docker_setup.md) (dev 스택) · [migrations.md](migrations.md) (스키마) · [agents.md](agents.md) (런타임 동작) · [../../README.md §12.3](../../README.md) · [../../BACKLOG.md](../../BACKLOG.md) O-2/O-3/O-5
