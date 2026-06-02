#!/usr/bin/env bash
# O-3 복원 — backup.sh 산출물에서 PostgreSQL + Neo4j 복구. **파괴적**.
#
# 사용:
#   bash scripts/ops/restore.sh --pg <pg_dump> --neo4j <neo4j_dump>   # 둘 다
#   bash scripts/ops/restore.sh --pg <pg_dump>                        # PG 만
#   FORCE=1 ... (확인 프롬프트 생략 — cron/CI)
#
# 기존 데이터를 덮어쓴다 (PG: --clean --if-exists / Neo4j: --overwrite-destination).
# 복원 전 현재 상태를 backup.sh 로 1회 떠두는 것을 강력 권장. docs/operations/backup_dr.md
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-ar-postgres}"
NEO4J_CONTAINER="${NEO4J_CONTAINER:-ar-neo4j}"
PG_USER="${PG_USER:-autonexusgraph}"
PG_DB="${PG_DB:-autonexusgraph}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-autonexusgraph_dev}"
NEO4J_DB="${NEO4J_DB:-neo4j}"

PG_DUMP="" ; NEO4J_DUMP=""
while [ $# -gt 0 ]; do
    case "$1" in
        --pg)     PG_DUMP="$2"; shift 2;;
        --neo4j)  NEO4J_DUMP="$2"; shift 2;;
        *) echo "unknown arg: $1"; exit 2;;
    esac
done
if [ -z "${PG_DUMP}" ] && [ -z "${NEO4J_DUMP}" ]; then
    echo "사용: restore.sh --pg <dump> [--neo4j <dump>]"; exit 2
fi

if [ "${FORCE:-0}" != "1" ]; then
    echo "⚠️  파괴적 복원 — 현재 PG('${PG_DB}')/Neo4j('${NEO4J_DB}') 데이터를 덮어씁니다."
    read -r -p "계속하려면 'yes' 입력: " ans
    [ "${ans}" = "yes" ] || { echo "취소."; exit 1; }
fi

# ── PostgreSQL ─────────────────────────────────────────────────────────
if [ -n "${PG_DUMP}" ]; then
    [ -f "${PG_DUMP}" ] || { echo "PG dump 없음: ${PG_DUMP}"; exit 1; }
    echo "[restore] PG ← ${PG_DUMP}"
    docker exec -i "${PG_CONTAINER}" pg_restore -U "${PG_USER}" -d "${PG_DB}" \
        --clean --if-exists --no-owner < "${PG_DUMP}"
    echo "[restore] PG done"
fi

# ── Neo4j (community: STOP → load → START) ─────────────────────────────
if [ -n "${NEO4J_DUMP}" ]; then
    [ -f "${NEO4J_DUMP}" ] || { echo "Neo4j dump 없음: ${NEO4J_DUMP}"; exit 1; }
    cyp() { docker exec "${NEO4J_CONTAINER}" cypher-shell -u "${NEO4J_USER}" -p "${NEO4J_PASSWORD}" -d system "$1"; }
    # neo4j-admin load 는 <db>.dump 고정명을 from-path 에서 찾는다 → 임시로 컨테이너에 복사.
    docker exec "${NEO4J_CONTAINER}" mkdir -p /data/restore
    docker cp "${NEO4J_DUMP}" "${NEO4J_CONTAINER}:/data/restore/${NEO4J_DB}.dump"
    echo "[restore] Neo4j STOP DATABASE ${NEO4J_DB}"
    cyp "STOP DATABASE ${NEO4J_DB};"
    docker exec "${NEO4J_CONTAINER}" neo4j-admin database load "${NEO4J_DB}" \
        --from-path=/data/restore --overwrite-destination=true
    cyp "START DATABASE ${NEO4J_DB};"
    docker exec "${NEO4J_CONTAINER}" rm -f "/data/restore/${NEO4J_DB}.dump"
    echo "[restore] Neo4j done"
fi

echo "[restore] ✅ 완료 — make health 로 검증 권장"
