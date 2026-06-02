#!/usr/bin/env bash
# O-3 백업 — PostgreSQL(pg_dump -Fc) + Neo4j(neo4j-admin database dump).
#
# 사용:  bash scripts/ops/backup.sh        (또는 make backup)
# cron:  0 3 * * *  cd /srv/autonexusgraph && bash scripts/ops/backup.sh >> /var/log/anxg_backup.log 2>&1
#
# 산출:  ${BACKUP_DIR}/pg/autonexusgraph_<ts>.dump   (pg_restore 호환 custom format)
#        ${BACKUP_DIR}/neo4j/neo4j_<ts>.dump
# 보존:  RETENTION_DAYS(기본 14) 초과 .dump 자동 삭제.
#
# Neo4j community 는 online backup 불가 → 대상 DB 만 STOP → dump → START
# (system DB 는 유지, 다운타임 = dump 시간). /data 는 host bind-mount 라 dump 가
# host 에 그대로 남는다. 상세: docs/operations/backup_dr.md
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-ar-postgres}"
NEO4J_CONTAINER="${NEO4J_CONTAINER:-ar-neo4j}"
PG_USER="${PG_USER:-autonexusgraph}"
PG_DB="${PG_DB:-autonexusgraph}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-autonexusgraph_dev}"
NEO4J_DB="${NEO4J_DB:-neo4j}"
DB_DATA_ROOT="${DB_DATA_ROOT:-/home/user/arsim/DB_FG}"
BACKUP_DIR="${BACKUP_DIR:-${DB_DATA_ROOT}/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

TS="$(date +%Y%m%dT%H%M%SZ)"
mkdir -p "${BACKUP_DIR}/pg" "${BACKUP_DIR}/neo4j"

echo "[backup] ${TS} 시작 — BACKUP_DIR=${BACKUP_DIR}"

# ── 1. PostgreSQL (custom format: 압축 + pg_restore 선택 복원) ──────────
pg_out="${BACKUP_DIR}/pg/${PG_DB}_${TS}.dump"
echo "[backup] PG → ${pg_out}"
docker exec "${PG_CONTAINER}" pg_dump -U "${PG_USER}" -Fc -d "${PG_DB}" > "${pg_out}"
echo "[backup] PG done ($(du -h "${pg_out}" | cut -f1))"

# ── 2. Neo4j (community: STOP → dump → START) ──────────────────────────
cyp() { docker exec "${NEO4J_CONTAINER}" cypher-shell -u "${NEO4J_USER}" -p "${NEO4J_PASSWORD}" -d system "$1"; }
docker exec "${NEO4J_CONTAINER}" mkdir -p /data/backups
echo "[backup] Neo4j STOP DATABASE ${NEO4J_DB}"
cyp "STOP DATABASE ${NEO4J_DB};"
trap 'echo "[backup] (trap) START DATABASE ${NEO4J_DB}"; cyp "START DATABASE ${NEO4J_DB};" || true' EXIT
docker exec "${NEO4J_CONTAINER}" neo4j-admin database dump "${NEO4J_DB}" \
    --to-path=/data/backups --overwrite-destination=true
cyp "START DATABASE ${NEO4J_DB};"
trap - EXIT
# /data → host ${DB_DATA_ROOT}/neo4j/data. dump 파일명은 <db>.dump 고정 → ts 부여.
src="${DB_DATA_ROOT}/neo4j/data/backups/${NEO4J_DB}.dump"
neo_out="${BACKUP_DIR}/neo4j/${NEO4J_DB}_${TS}.dump"
if [ -f "${src}" ]; then
    mv "${src}" "${neo_out}"
    echo "[backup] Neo4j done ($(du -h "${neo_out}" | cut -f1))"
else
    echo "[backup] ⚠️ Neo4j dump 파일 미발견: ${src} (경로/권한 확인)"
fi

# ── 3. 보존 정책 ───────────────────────────────────────────────────────
find "${BACKUP_DIR}/pg" "${BACKUP_DIR}/neo4j" -name '*.dump' -type f \
    -mtime +"${RETENTION_DAYS}" -print -delete | sed 's/^/[backup] prune /' || true

echo "[backup] ✅ 완료 — pg=${pg_out} neo4j=${neo_out:-N/A}"
