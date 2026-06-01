"""auto.master_manufacturers 의 한국어 alias 보강 — 한국 OEM/공급사 매칭율 ↑.

backfill 대상:
- 기존 NHTSA-derived 영문 entries (HYUNDAI/KIA/GENESIS/CHEVROLET) 의 aliases
  배열에 한국어 변형 추가
- SSANGYONG / KGM / RENAULT_KOREA 등 한국 시장 단독 OEM 신규 entry 등록

매칭 우선순위 (load_datagokr_recalls._resolve_manufacturer_id 호환):
1. name_norm / name exact
2. aliases array contains
3. _KO_MFR_ALIAS dict fallback

본 loader 가 1+2 를 채워 신규 한국 데이터 (data.go.kr 키 도착 후 etc.) 매칭율
극대화.

2026-06-01 신규.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys


log = logging.getLogger(__name__)


# 기존 entry 의 aliases 보강 — (canonical_name, ko_aliases[]).
# canonical_name 은 auto.master_manufacturers.name (NHTSA vPIC 표준형).
EXISTING_ALIASES: dict[str, list[str]] = {
    "HYUNDAI": [
        "현대자동차", "현대차", "현대자동차주식회사", "(주)현대자동차",
        "Hyundai Motor Company", "HMC",
    ],
    "KIA": [
        "기아", "기아자동차", "기아주식회사", "(주)기아",
        "Kia Motors", "Kia Corporation",
    ],
    "GENESIS": [
        "제네시스", "Genesis Motors",
    ],
    "CHEVROLET": [
        "쉐보레", "한국지엠", "지엠코리아", "GM Korea",
        "Chevrolet Korea",
    ],
    "FORD": [
        "포드", "포드코리아", "포드세일즈서비스코리아",
        "Ford Motor Korea",
    ],
    "TESLA": [
        "테슬라", "테슬라코리아", "Tesla Korea",
    ],
    "TOYOTA": [
        "토요타", "도요타", "Toyota Korea",
    ],
    "HONDA": [
        "혼다", "Honda Korea",
    ],
    "NISSAN": [
        "닛산", "Nissan Korea",
    ],
    "BMW": [
        "BMW코리아", "비엠더블유", "비엠더블유코리아",
    ],
    "MERCEDES-BENZ": [
        "메르세데스-벤츠", "메르세데스벤츠", "벤츠",
        "Mercedes-Benz Korea",
    ],
    "AUDI": [
        "아우디", "Audi Korea",
    ],
    "VOLKSWAGEN": [
        "폭스바겐", "Volkswagen Korea",
    ],
    "PORSCHE": [
        "포르쉐", "Porsche Korea",
    ],
    "VOLVO": [
        "볼보", "Volvo Korea",
    ],
    "JAGUAR": [
        "재규어",
    ],
    "LAND ROVER": [
        "랜드로버", "랜드로버코리아",
    ],
    "PEUGEOT": [
        "푸조",
    ],
}

# 신규 OEM 등록 — NHTSA vPIC 에는 없지만 한국 시장에 존재.
# manufacturer_id 는 ≥ 2_000_000_500 으로 manual 영역 사용 (충돌 회피).
NEW_OEMS: list[dict] = [
    {
        "manufacturer_id": 2000000500,
        "name": "KGM",
        "name_norm": "kgm",
        "country": "KR",
        "source": "manual",
        "source_ref": "manual_korean_alias_2026_06_01",
        "aliases": [
            "KG모빌리티", "케이지모빌리티", "KG MOBILITY",
            "쌍용자동차", "쌍용차", "SsangYong",
        ],
        "wikidata_qid": "Q1144748",   # SsangYong Motor
    },
    {
        "manufacturer_id": 2000000501,
        "name": "RENAULT KOREA",
        "name_norm": "renault korea",
        "country": "KR",
        "source": "manual",
        "source_ref": "manual_korean_alias_2026_06_01",
        "aliases": [
            "르노코리아", "르노삼성자동차", "르노삼성",
            "Renault Korea Motors", "Renault Samsung Motors",
        ],
        "wikidata_qid": "Q484404",   # Renault Korea
    },
]


def _backfill_existing(conn) -> int:
    """기존 entry 의 aliases 가 비어있으면 EXISTING_ALIASES 적용."""
    n = 0
    with conn.cursor() as cur:
        for name, aliases in EXISTING_ALIASES.items():
            # 비어있는 aliases 만 — 이미 채워진 건 건드리지 않음 (수동 보강 보호)
            cur.execute("""
                UPDATE auto.master_manufacturers
                   SET aliases = %s::text[],
                       updated_at = now()
                 WHERE name = %s
                   AND (aliases = '{}' OR aliases IS NULL)
                 RETURNING manufacturer_id
            """, (aliases, name))
            updated = cur.fetchall()
            if updated:
                n += len(updated)
                log.info("[ko_aliases] %s: %d entries +%d aliases",
                         name, len(updated), len(aliases))
    return n


def _insert_new_oems(conn) -> int:
    """신규 한국 OEM entry 등록 — ON CONFLICT skip (멱등)."""
    n = 0
    with conn.cursor() as cur:
        for oem in NEW_OEMS:
            cur.execute("""
                INSERT INTO auto.master_manufacturers
                  (manufacturer_id, name, name_norm, country, wikidata_qid,
                   aliases, source, source_ref, confidence, validated_status)
                VALUES (%s, %s, %s, %s, %s,
                        %s::text[], %s, %s, 0.950, 'verified')
                ON CONFLICT (manufacturer_id) DO UPDATE SET
                  aliases = EXCLUDED.aliases,
                  updated_at = now()
                RETURNING (xmax = 0) AS is_new
            """, (
                oem["manufacturer_id"], oem["name"], oem["name_norm"],
                oem["country"], oem.get("wikidata_qid"),
                oem["aliases"], oem["source"], oem["source_ref"],
            ))
            is_new = cur.fetchone()[0]
            if is_new:
                n += 1
                log.info("[ko_aliases] NEW OEM: %s (id=%d)",
                         oem["name"], oem["manufacturer_id"])
    return n


def run(*, dry_run: bool = False) -> dict:
    if dry_run:
        return {
            "existing_to_update": sum(len(a) for a in EXISTING_ALIASES.values()),
            "new_oems": len(NEW_OEMS),
            "applied": 0,
        }

    from autonexusgraph.db.postgres import get_connection
    conn = get_connection()
    existing_updated = _backfill_existing(conn)
    new_oems = _insert_new_oems(conn)
    conn.commit()
    log.info("[ko_aliases] existing updated=%d, new OEMs inserted=%d",
             existing_updated, new_oems)
    return {"existing_updated": existing_updated,
            "new_oems_inserted": new_oems}


def main() -> int:
    ap = argparse.ArgumentParser(prog="autograph.loaders.load_master_korean_aliases")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    out = run(dry_run=args.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "run", "EXISTING_ALIASES", "NEW_OEMS",
    "_backfill_existing", "_insert_new_oems",
]
