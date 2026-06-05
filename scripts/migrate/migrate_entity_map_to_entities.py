#!/usr/bin/env python3
"""anxg_master.companies + anxg_master.entity_map → anxg_master.entities 멱등 마이그.

PRD §4.5 v2.1 — 다형 ER 마스터 (anxg_master.entities) 신설에 따라, 기존 v2.0 분리
구조 (anxg_master.companies + anxg_master.entity_map) 의 데이터를 entities 로 흡수한다.

전략:
    1. anxg_master.companies 한 행 = entities 한 행 (entity_type='manufacturer').
       - entity_id = 'mfr_' + corp_code (자연키 기반, prefix+seq 미사용).
       - canonical_name = corp_name.
    2. anxg_master.entity_map 의 외부 식별자 (id_type ∈ {wikidata_qid, lei,
       business_no, cik}) 를 entities 의 해당 컬럼에 enrich.
       - 같은 corp_code 에 여러 외부 ID 있어도 우선순위로 1개 선택
         (confidence 내림차순 → resolved_at 내림차순).
    3. anxg_master.entity_map 자체는 **삭제하지 않는다** — 기존 도메인 로더가
       의존. entities 는 폴리모픽 레이어로 공존.
    4. anxg_master.persons / company_aliases 는 손대지 않음 (PRD 384 행 '도메인 선택').

멱등성:
    - 모든 INSERT 가 ON CONFLICT (entity_id) DO UPDATE.
    - 재실행해도 row 수 변화 없음, NULL 외부 ID 만 새 값으로 갱신.

CLI:
    python -m scripts.migrate.migrate_entity_map_to_entities
    python -m scripts.migrate.migrate_entity_map_to_entities --dry-run
    python -m scripts.migrate.migrate_entity_map_to_entities --limit 100
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from autonexusgraph.db.postgres import get_connection  # noqa: E402

log = logging.getLogger(__name__)


# entity_map.id_type → entities 컬럼명 매핑.
ID_TYPE_TO_COLUMN: dict[str, str] = {
    "wikidata_qid": "wikidata_qid",
    "lei":          "lei",
    "business_no":  "business_no",
    "cik":          "cik",
}


def migrate(*, dry_run: bool = False, limit: int | None = None) -> dict:
    """anxg_master.companies → anxg_master.entities + entity_map enrich.

    Returns stats dict — {seen, inserted, updated, enriched, errors}.
    """
    stats = {"seen": 0, "inserted": 0, "updated": 0, "enriched": 0, "errors": 0}
    conn = get_connection()
    with conn.cursor() as cur:
        # 1) companies → entities upsert.
        sql_companies = """
            SELECT corp_code, corp_name, is_active
              FROM anxg_master.companies
             ORDER BY corp_code
        """
        if limit:
            sql_companies += f" LIMIT {int(limit)}"
        cur.execute(sql_companies)
        companies = cur.fetchall()
        log.info("[migrate] anxg_master.companies %d 행 처리", len(companies))

        for corp_code, corp_name, is_active in companies:
            stats["seen"] += 1
            entity_id = f"mfr_{corp_code}"
            try:
                cur.execute("""
                    INSERT INTO anxg_master.entities
                      (entity_id, entity_type, canonical_name, corp_code,
                       source_priority, confidence_score, valid_to, schema_version)
                    VALUES (%s, 'manufacturer', %s, %s, 1, 1.000,
                            CASE WHEN %s THEN NULL ELSE CURRENT_DATE END, 'v2.1')
                    ON CONFLICT (entity_id) DO UPDATE SET
                      canonical_name = EXCLUDED.canonical_name,
                      corp_code      = EXCLUDED.corp_code,
                      valid_to       = EXCLUDED.valid_to
                    RETURNING (xmax = 0) AS inserted
                """, (entity_id, corp_name, corp_code, is_active))
                row = cur.fetchone()
                if row and row[0]:
                    stats["inserted"] += 1
                else:
                    stats["updated"] += 1
            except Exception as e:   # noqa: BLE001
                stats["errors"] += 1
                log.warning("[migrate] companies %s 실패: %s", corp_code, e)
                conn.rollback()
                continue

        # 2) entity_map → entities enrich (각 id_type 별 최고 confidence 한 개).
        for id_type, col in ID_TYPE_TO_COLUMN.items():
            cur.execute("""
                WITH ranked AS (
                    SELECT corp_code, id_value,
                           ROW_NUMBER() OVER (
                               PARTITION BY corp_code
                               ORDER BY confidence DESC, resolved_at DESC
                           ) AS rn
                      FROM anxg_master.entity_map
                     WHERE id_type = %s
                )
                SELECT corp_code, id_value
                  FROM ranked
                 WHERE rn = 1
            """, (id_type,))
            mappings = cur.fetchall()
            log.info("[migrate] entity_map id_type=%s — %d 행 enrich",
                     id_type, len(mappings))

            for corp_code, id_value in mappings:
                entity_id = f"mfr_{corp_code}"
                try:
                    # 해당 컬럼이 NULL 일 때만 채움 (덮어쓰지 않음).
                    cur.execute(f"""
                        UPDATE anxg_master.entities
                           SET {col} = %s
                         WHERE entity_id = %s
                           AND {col} IS NULL
                    """, (id_value, entity_id))
                    if cur.rowcount > 0:
                        stats["enriched"] += 1
                except Exception as e:   # noqa: BLE001
                    stats["errors"] += 1
                    log.warning("[migrate] enrich %s/%s 실패: %s",
                                corp_code, id_type, e)
                    conn.rollback()
                    continue

    if dry_run:
        conn.rollback()
        log.info("[migrate] DRY-RUN — 롤백. stats=%s", stats)
    else:
        conn.commit()
        log.info("[migrate] commit. stats=%s", stats)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(prog="migrate_entity_map_to_entities")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None,
                    help="companies N행만 마이그 (smoke 용)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    migrate(dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    main()
