# 백업 · 재해복구 (O-3)

> **SSOT**: 본 문서 = 백업/복원 절차 + RPO/RTO. 스크립트 `scripts/ops/{backup,restore}.sh` (`make backup` / `make restore`). 배포 전체는 [production_deploy.md](production_deploy.md).

---

## 0. 무엇을 백업하나

| 저장소 | 내용 | 백업 수단 |
|---|---|---|
| PostgreSQL (`ar-postgres`) | DART XBRL 184K · filings · **vec.chunks 748K (임베딩 포함)** · master.* · bridge.* · chat.* · auto.* · ip.* | `pg_dump -Fc` (custom format, 압축) |
| Neo4j (`ar-neo4j`, **community**) | Company/Person/지배구조 · auto BOM/공정 그래프 · ip 그래프 | `neo4j-admin database dump` (community = **online backup 불가**) |
| raw 데이터 | `data/raw/**` (DART zip 등) | host 파일시스템 스냅샷 (gitignore, DB_DATA_ROOT) |

> **핵심**: `vec.chunks.embedding` 은 PG dump 에 **포함**된다 → 정상 복원 시 임베딩 재생성 불필요. 재생성(수 시간)은 dump 마저 잃은 **재앙 시나리오**에서만 (§4).

---

## 1. 백업 실행

```bash
make backup          # = bash scripts/ops/backup.sh
```

- 산출: `${BACKUP_DIR}/pg/<db>_<ts>.dump` + `${BACKUP_DIR}/neo4j/neo4j_<ts>.dump`.
- 기본 `BACKUP_DIR=${DB_DATA_ROOT}/backups` (repo 밖, `.gitignore` 처리). 환경변수로 변경 가능: `PG_CONTAINER / NEO4J_CONTAINER / PG_USER / PG_DB / NEO4J_PASSWORD / BACKUP_DIR / RETENTION_DAYS`.
- **Neo4j community 절차**: 대상 DB(`neo4j`)만 `STOP` → dump → `START` (system DB 유지). 다운타임 = dump 시간(분 단위). 실패 시 trap 으로 START 복구.
- 보존: `RETENTION_DAYS`(기본 14일) 초과 `.dump` 자동 prune.

**cron (매일 03:00):**
```cron
0 3 * * *  cd /srv/autonexusgraph && NEO4J_PASSWORD=*** bash scripts/ops/backup.sh >> /var/log/anxg_backup.log 2>&1
```

> off-site 권장: backup 후 `${BACKUP_DIR}` 를 S3/원격으로 동기화 (`aws s3 sync` / `rclone`). 단일 호스트 디스크 손실 대비.

---

## 2. 복원 (파괴적)

```bash
# 둘 다
make restore ARGS="--pg <BACKUP_DIR>/pg/autonexusgraph_<ts>.dump --neo4j <BACKUP_DIR>/neo4j/neo4j_<ts>.dump"
# PG 만 / Neo4j 만 — 한쪽 인자만 전달
```

- PG: `pg_restore --clean --if-exists --no-owner` (기존 객체 교체).
- Neo4j: 대상 DB `STOP` → `neo4j-admin database load --overwrite-destination` → `START`.
- 확인 프롬프트 — `FORCE=1` 로 생략(cron/CI). **복원 전 현재 상태 1회 `make backup` 권장.**
- 복원 후 `make health` (PG/Neo4j ping) + 핵심 카운트 점검.

---

## 3. RPO / RTO

| 지표 | 값 | 근거 |
|---|---|---|
| **RPO** (허용 데이터 손실) | ≤ 백업 주기 (cron 일일 → **≤ 24h**) | 마지막 dump 이후 변경분 손실 |
| **RTO (정상 — dump 보유)** | **수~수십 분** | pg_restore(748K chunks+184K XBRL, 임베딩 포함) + neo4j load. GPU/재임베딩 불필요 |
| **RTO (재앙 — dump 소실)** | **수 시간** | raw → 파이프라인 재적재 + BGE-M3 재임베딩(finance 748K + auto 16K) (§4) |

> 실측 권장: 분기 1회 **복원 드릴** (별도 컨테이너/네임스페이스에 복원 → `make health` + 카운트 비교 → RTO 실측 기록).

---

## 4. 재앙 시나리오 (dump·DB 동시 소실)

raw 데이터(`data/raw/**`)만 있으면 전체 재생성 가능 — 단 시간 소요:
1. `docker compose up -d` (빈 볼륨 → init SQL 자동) → 마이그레이션.
2. 적재 파이프라인 재실행 ([data_pipeline.md](data_pipeline.md) / Quickstart §3~).
3. **BGE-M3 임베딩 backfill** (`make serve-embeddings` + `make embed-chunks`) — **수 시간** (진행률 `make embed-status`, Q-4).

raw 마저 없으면 외부 소스(DART/NHTSA/Wikidata 등) 재수집부터 — 키·rate limit 의존.

---

## 5. 검증 체크리스트

- [ ] `make backup` → pg/neo4j `.dump` 생성 + 크기 > 0
- [ ] Neo4j dump 시 STOP/START 정상 (로그) + 백업 중 외 시간 DB 가용
- [ ] `RETENTION_DAYS` prune 동작
- [ ] off-site 동기화 cron
- [ ] 분기 복원 드릴 → `make health` ok + RTO 기록
- [ ] prod 는 `NEO4J_PASSWORD` env 주입 (dev 기본값 금지)

---

**관련**: [production_deploy.md §10](production_deploy.md) · [../../BACKLOG.md](../../BACKLOG.md) O-3/O-5 · [docker_setup.md](docker_setup.md) · `scripts/ops/{backup,restore}.sh`
