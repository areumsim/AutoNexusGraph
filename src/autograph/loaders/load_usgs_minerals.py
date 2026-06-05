"""USGS MCS → ``anxg_auto.master_minerals`` PG 적재 + Neo4j ``:Mineral`` / ``:Material``
+ ``:DERIVED_FROM`` 엣지 적재.

흐름:
    1. ``autograph.ingestion.usgs_mcs.fetch_and_parse_all()`` 로 PDF → row.
    2. PG ``anxg_auto.master_minerals`` UPSERT (commodity, snapshot_year PK).
    3. ``ontology/auto/materials_seed.yaml`` 로 ``:Material`` / ``:Mineral`` 노드 +
       ``:DERIVED_FROM`` 엣지 (7키 메타) MERGE.
    4. (있으면) 'name' 기반 ``:Module`` ↔ ``:Material`` ``MADE_OF`` 엣지 MERGE.

PRD §3.5 — USGS MCS = A 등급, confidence 0.95.
PRD §6.7 — 7-key edge meta (source_type/source_id/confidence_score/validated_status/
            snapshot_year/extraction_method/schema_version).

CLI:
    python -m autograph.loaders.load_usgs_minerals --year 2025 --dry-run
    python -m autograph.loaders.load_usgs_minerals --year 2025
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
SEED_PATH = ROOT / "ontology" / "auto" / "materials_seed.yaml"

from ._neo4j_helpers import default_schema_version as _default_schema_version

# _SCHEMA_VERSION 은 ontology 헤더 SoT (lazy 회수). 본 모듈 외에서 import 하지 마라.
# PRD §10 DoD #17 (c) — yaml schema_version 헤더 변경 시 자동 전파.
_SCHEMA_VERSION = _default_schema_version()
_CONF_A = 0.95         # USGS MCS A grade
_CONF_B = 0.80         # manual seed (materials_seed)


# ── 1. PG: anxg_auto.master_minerals UPSERT ────────────────────────────

def _upsert_minerals(cur, rows: list[dict]) -> tuple[int, int, int]:
    """rows → anxg_auto.master_minerals UPSERT. (inserted, updated, skipped)."""
    ins = upd = skip = 0
    for r in rows:
        if not r.get("commodity") or r.get("snapshot_year") is None:
            skip += 1
            continue
        cur.execute("SAVEPOINT sp_min")
        try:
            cur.execute("""
                INSERT INTO anxg_auto.master_minerals
                  (commodity, snapshot_year,
                   world_production, us_production, us_import_reliance,
                   us_imports, us_exports, us_reserves, world_reserves,
                   price_usd_per_ton, source, raw)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (commodity, snapshot_year) DO UPDATE SET
                  world_production    = EXCLUDED.world_production,
                  us_production       = EXCLUDED.us_production,
                  us_import_reliance  = EXCLUDED.us_import_reliance,
                  us_imports          = EXCLUDED.us_imports,
                  us_exports          = EXCLUDED.us_exports,
                  us_reserves         = EXCLUDED.us_reserves,
                  world_reserves      = EXCLUDED.world_reserves,
                  price_usd_per_ton   = EXCLUDED.price_usd_per_ton,
                  raw                 = EXCLUDED.raw,
                  updated_at          = now()
                RETURNING (xmax = 0) AS is_new
            """, (
                r["commodity"],
                int(r["snapshot_year"]),
                _to_int(r.get("world_production")),
                _to_int(r.get("us_mine_production") or r.get("us_production")),
                _to_dec(r.get("us_import_reliance")),
                _to_int(r.get("us_imports")),
                _to_int(r.get("us_exports")),
                _to_int(r.get("us_reserves")),
                _to_int(r.get("world_reserves")),
                _to_dec(r.get("price_usd_per_ton")),
                "usgs_mcs",
                json.dumps({k: v for k, v in r.items() if k != "raw"} | (r.get("raw") or {}),
                           ensure_ascii=False),
            ))
            is_new = bool(cur.fetchone()[0])
            if is_new:
                ins += 1
            else:
                upd += 1
            cur.execute("RELEASE SAVEPOINT sp_min")
        except Exception as exc:   # noqa: BLE001
            cur.execute("ROLLBACK TO SAVEPOINT sp_min")
            log.warning("[load:usgs] %s upsert fail: %s", r.get("commodity"), exc)
            skip += 1
    return ins, upd, skip


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _to_dec(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── 2. Neo4j: Material/Mineral 노드 + DERIVED_FROM 엣지 ─────────────

def _load_seed() -> dict | None:
    if not SEED_PATH.exists():
        log.warning("[load:usgs:neo4j] seed 없음: %s", SEED_PATH)
        return None
    return yaml.safe_load(SEED_PATH.read_text(encoding="utf-8"))


_CONSTRAINTS_CYPHER = [
    "CREATE CONSTRAINT material_code IF NOT EXISTS FOR (m:Anxg_Material) REQUIRE m.code IS UNIQUE",
    "CREATE CONSTRAINT mineral_code  IF NOT EXISTS FOR (m:Anxg_Mineral)  REQUIRE m.code IS UNIQUE",
    "CREATE INDEX     material_family IF NOT EXISTS FOR (m:Anxg_Material) ON (m.chem_family)",
]

# 7-key edge meta — PRD §6.7.
_EDGE_META = {
    "source_type":       "usgs_mcs",
    "source_id":         "usgs_mcs_2025",
    "confidence_score":  _CONF_A,
    "validated_status":  "validated",
    "extraction_method": "deterministic",
    "schema_version":    _SCHEMA_VERSION,
}


def _neo4j_load(seed: dict, snapshot_year: int,
                pg_commodities: list[str]) -> dict:
    """Material/Mineral 노드 + DERIVED_FROM 엣지 적재. (있으면) Module-MADE_OF-Material."""
    # cartesian-product performance INFO 노티는 unique key 매칭이라 무해 — 묵음.
    logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)
    from neo4j import GraphDatabase
    uri  = os.environ["NEO4J_URI"]
    user = os.environ.get("NEO4J_USER", "neo4j")
    pw   = os.environ["NEO4J_PASSWORD"]
    drv = GraphDatabase.driver(uri, auth=(user, pw))

    stats = {
        "materials_merged": 0,
        "minerals_merged":  0,
        "derived_from_merged": 0,
        "made_of_merged":   0,
    }
    try:
        with drv.session(database=os.environ.get("NEO4J_DATABASE") or None) as s:
            for q in _CONSTRAINTS_CYPHER:
                s.run(q)

            # Mineral 노드 — PG 적재된 commodity 만.
            for code, info in (seed.get("minerals") or {}).items():
                if code not in pg_commodities:
                    continue
                s.run("""
                    MERGE (n:Anxg_Mineral {code: $code})
                    SET n.name = $name,
                        n.element_symbol = $sym,
                        n.aliases = $aliases,
                        n.updated_at = datetime()
                """, code=code, name=info.get("name"),
                     sym=info.get("element_symbol"),
                     aliases=info.get("aliases", []))
                stats["minerals_merged"] += 1

            # Material 노드 + DERIVED_FROM 엣지.
            edge_meta = dict(_EDGE_META, snapshot_year=snapshot_year)
            for mat_code, info in (seed.get("materials") or {}).items():
                s.run("""
                    MERGE (m:Anxg_Material {code: $code})
                    SET m.name = $name,
                        m.chem_family = $fam,
                        m.cathode_ratio = $ratio,
                        m.aliases = $aliases,
                        m.updated_at = datetime()
                """, code=mat_code, name=info.get("name"),
                     fam=info.get("chem_family"),
                     ratio=info.get("cathode_ratio"),
                     aliases=info.get("aliases", []))
                stats["materials_merged"] += 1
                for min_code in info.get("minerals", []) or []:
                    if min_code not in pg_commodities:
                        # 광물이 PG 에 없으면 엣지 skip — 정합성 유지.
                        continue
                    # 'source_id' 는 row 별로 (mat→mineral) 결정 — 결정적.
                    eid = f"usgs_mcs_{snapshot_year}:{mat_code}->{min_code}"
                    s.run("""
                        MATCH (mat:Anxg_Material {code: $mat}), (min:Anxg_Mineral {code: $min})
                        MERGE (mat)-[r:DERIVED_FROM]->(min)
                        SET r.source_type       = $source_type,
                            r.source_id         = $source_id,
                            r.confidence_score  = $confidence_score,
                            r.validated_status  = $validated_status,
                            r.snapshot_year     = $snapshot_year,
                            r.extraction_method = $extraction_method,
                            r.schema_version    = $schema_version,
                            r.updated_at        = datetime()
                    """, mat=mat_code, min=min_code,
                         **(edge_meta | {"source_id": eid}))
                    stats["derived_from_merged"] += 1

            # Module → MADE_OF → Material — 이름 매칭 (있을 때만).
            module_edge_meta = dict(_EDGE_META,
                                     source_type="materials_seed",
                                     source_id="ontology/auto/materials_seed.yaml",
                                     confidence_score=_CONF_B,
                                     extraction_method="manual",
                                     snapshot_year=snapshot_year)
            for entry in (seed.get("module_to_materials") or []):
                mname = entry.get("module_name")
                if not mname:
                    continue
                for mat_code in entry.get("materials", []) or []:
                    res = s.run("""
                        MATCH (mod:Anxg_Module), (mat:Anxg_Material {code: $mat})
                        WHERE mod.name = $mname
                        MERGE (mod)-[r:MADE_OF]->(mat)
                        SET r.source_type       = $source_type,
                            r.source_id         = $source_id,
                            r.confidence_score  = $confidence_score,
                            r.validated_status  = $validated_status,
                            r.snapshot_year     = $snapshot_year,
                            r.extraction_method = $extraction_method,
                            r.schema_version    = $schema_version,
                            r.updated_at        = datetime()
                        RETURN count(r) AS n
                    """, mat=mat_code, mname=mname, **module_edge_meta)
                    stats["made_of_merged"] += (res.single() or {}).get("n", 0)
    finally:
        drv.close()
    return stats


# ── 3. 메인 ────────────────────────────────────────────────────

def run(*, year: int = 2025, dry_run: bool = False,
        skip_neo4j: bool = False) -> dict:
    from autograph.ingestion import usgs_mcs

    rows = usgs_mcs.fetch_and_parse_all(year=year)
    if not rows:
        log.warning("[load:usgs] no rows parsed from MCS %s — graceful skip", year)
        return {"pg": {}, "neo4j": {}, "n_rows": 0}

    out: dict[str, Any] = {"n_rows": len(rows), "snapshot_year": rows[0]["snapshot_year"]}

    if dry_run:
        out["preview"] = [
            {k: v for k, v in r.items() if k != "raw"} for r in rows
        ]
        return out

    # PG.
    import psycopg2
    dsn = os.environ.get("POSTGRES_DSN") or _dsn_from_env()
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            ins, upd, skip = _upsert_minerals(cur, rows)
        conn.commit()
    finally:
        conn.close()
    out["pg"] = {"inserted": ins, "updated": upd, "skipped": skip}
    log.info("[load:usgs:pg] ins=%d upd=%d skip=%d", ins, upd, skip)

    # Neo4j.
    if not skip_neo4j:
        seed = _load_seed()
        if seed is None:
            log.warning("[load:usgs:neo4j] seed not found — neo4j load skip")
            out["neo4j"] = {"skipped": True, "reason": "no seed"}
        else:
            pg_commodities = [r["commodity"] for r in rows]
            out["neo4j"] = _neo4j_load(seed, rows[0]["snapshot_year"], pg_commodities)
            log.info("[load:usgs:neo4j] %s", out["neo4j"])

    return out


def _dsn_from_env() -> str:
    # POSTGRES_DSN 미설정 시 .env 파싱 (단순 fallback).
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("POSTGRES_DSN="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("POSTGRES_DSN 미설정 — .env 또는 환경변수 필요")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-neo4j", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    out = run(year=args.year, dry_run=args.dry_run, skip_neo4j=args.skip_neo4j)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["run"]
