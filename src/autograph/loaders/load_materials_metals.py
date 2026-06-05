"""materials_metals_seed.yaml → Neo4j :Material (metal_alloy) 노드 + MADE_OF 엣지.

L6-2 후속 — materials_seed.yaml(cathode chem) loader 인 ``load_usgs_minerals`` 가
같이 처리하는 패턴과 동일. 본 모듈은 metal_alloy 분기만 단독으로:

  1. seed `ontology/auto/materials_metals_seed.yaml` 읽기 (`MaterialsMetalsFile`
     strict 검증은 `scripts/audit/ontology_validate.py` 가 별도로 수행).
  2. Anxg_Material 노드 MERGE — code/name/material_class/alloy_family/aliases/
     typical_processes/typical_modules/density_kg_m3.
  3. `module_to_materials` 매핑마다 (:Anxg_Module {name})-[:MADE_OF]->(:Anxg_Material)
     UNWIND 적재. 7-key edge meta (PRD §6.7).

등급 정합:
  - :Material 노드 = manual seed B 등급 (표준 규격 명세).
  - MADE_OF 엣지 = **candidate / 0.50 (C)** — Module name 매칭은 추론. ontology
    relations.yaml MADE_OF 의 default 0.80 보다 낮은 이유: cathode chem (정확히
    "배터리팩" → NCM811 같은 정합 매핑) 과 달리 metals 의 module name 매칭은
    제조 OEM 별로 다양 (DP980 가 모든 OEM "차체 외판" 인 건 아님). OEM IR/MSDS
    출처 들어오면 validated 격상.

매칭 없으면 graceful skip (UNWIND 후 MATCH 0건 = 0 MERGE — Neo4j 정상 동작).

CLI:
    python -m autograph.loaders.load_materials_metals
    python -m autograph.loaders.load_materials_metals --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from autonexusgraph.db.neo4j import get_session

from ._neo4j_helpers import default_schema_version as _default_schema_version


log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
SEED_PATH = ROOT / "ontology" / "auto" / "materials_metals_seed.yaml"

_SCHEMA_VERSION = _default_schema_version()
# Material 노드 자체는 manual seed B (표준 규격 명세).
_CONF_NODE_B = 0.80
# MADE_OF 엣지는 candidate C — Module 매칭이 OEM-별 추론.
_CONF_EDGE_C = 0.50
_SOURCE_TYPE = "materials_metals_seed"
_SOURCE_ID = "ontology/auto/materials_metals_seed.yaml"


@dataclass
class LoadStats:
    materials_merged: int = 0
    module_mappings_seen: int = 0
    made_of_merged: int = 0
    made_of_skipped_no_module: int = 0
    errors: list[str] = field(default_factory=list)


# ── seed load ──────────────────────────────────────────────────────

def load_seed(seed_path: Path | None = None) -> dict | None:
    p = seed_path or SEED_PATH
    if not p.exists():
        log.warning("[load:metals] seed 없음: %s", p)
        return None
    return yaml.safe_load(p.read_text(encoding="utf-8"))


# ── Cypher ─────────────────────────────────────────────────────────

_CONSTRAINT_MATERIAL = (
    "CREATE CONSTRAINT material_code IF NOT EXISTS "
    "FOR (m:Anxg_Material) REQUIRE m.code IS UNIQUE"
)

# Material 노드 UNWIND MERGE — metals 분기 속성 일괄.
_MERGE_MATERIALS = """
UNWIND $rows AS row
MERGE (m:Anxg_Material {code: row.code})
SET   m.name              = row.name,
      m.material_class    = row.material_class,
      m.alloy_family      = row.alloy_family,
      m.aliases           = row.aliases,
      m.typical_processes = row.typical_processes,
      m.typical_modules   = row.typical_modules,
      m.density_kg_m3     = row.density_kg_m3,
      m.updated_at        = datetime()
"""

# (:Anxg_Module {name})-[:MADE_OF]->(:Anxg_Material {code}) — 7-key edge meta.
# Module 매칭 없으면 0 MERGE (graceful skip — RETURN count 로 측정).
_MERGE_MADE_OF = """
UNWIND $rows AS row
MATCH (mod:Anxg_Module {name: row.module_name})
MATCH (mat:Anxg_Material {code: row.material_code})
MERGE (mod)-[r:MADE_OF]->(mat)
SET   r.source_type       = $source_type,
      r.source_id         = $source_id,
      r.confidence_score  = $confidence_score,
      r.validated_status  = $validated_status,
      r.snapshot_year     = $snapshot_year,
      r.extraction_method = $extraction_method,
      r.schema_version    = $schema_version,
      r.updated_at        = datetime()
RETURN count(r) AS n
"""


def _build_material_rows(seed: dict) -> list[dict]:
    """seed.materials dict → MERGE 입력 row list."""
    out: list[dict] = []
    for code, info in (seed.get("materials") or {}).items():
        out.append({
            "code":              code,
            "name":              info.get("name") or code,
            "material_class":    info.get("material_class") or "metal_alloy",
            "alloy_family":      info.get("alloy_family"),
            "aliases":           list(info.get("aliases") or []),
            "typical_processes": list(info.get("typical_processes") or []),
            "typical_modules":   list(info.get("typical_modules") or []),
            "density_kg_m3":     info.get("density_kg_m3"),
        })
    return out


def _build_made_of_rows(seed: dict) -> list[dict]:
    """seed.module_to_materials → flat (module_name, material_code) row list."""
    out: list[dict] = []
    for entry in (seed.get("module_to_materials") or []):
        mname = entry.get("module_name")
        if not mname:
            continue
        for mat_code in entry.get("materials") or []:
            out.append({"module_name": mname, "material_code": mat_code})
    return out


# ── runner ─────────────────────────────────────────────────────────

def run(*, dry_run: bool = False, snapshot_year: int | None = None,
        seed_path: Path | None = None) -> dict:
    from datetime import datetime
    snapshot_year = snapshot_year or datetime.utcnow().year

    stats = LoadStats()
    seed = load_seed(seed_path)
    if seed is None:
        log.warning("[load:metals] seed 없음 — graceful skip")
        return {"stats": stats.__dict__, "snapshot_year": snapshot_year}

    mat_rows = _build_material_rows(seed)
    edge_rows = _build_made_of_rows(seed)
    stats.module_mappings_seen = len(edge_rows)

    if dry_run:
        return {
            "stats": stats.__dict__,
            "snapshot_year": snapshot_year,
            "preview": {
                "n_materials": len(mat_rows),
                "n_made_of_rows": len(edge_rows),
                "sample_material": mat_rows[0] if mat_rows else None,
                "sample_made_of": edge_rows[0] if edge_rows else None,
            },
        }

    edge_meta = {
        "source_type":       _SOURCE_TYPE,
        "source_id":         _SOURCE_ID,
        "confidence_score":  _CONF_EDGE_C,
        "validated_status":  "candidate",
        "snapshot_year":     snapshot_year,
        "extraction_method": "manual",
        "schema_version":    _SCHEMA_VERSION,
    }

    with get_session() as session:
        session.run(_CONSTRAINT_MATERIAL)

        # 1) Material 노드 MERGE — UNWIND 한 번.
        if mat_rows:
            session.run(_MERGE_MATERIALS, rows=mat_rows)
            stats.materials_merged = len(mat_rows)

        # 2) MADE_OF UNWIND — Module 매칭 0건이면 0 MERGE (graceful).
        if edge_rows:
            try:
                res = session.run(_MERGE_MADE_OF, rows=edge_rows, **edge_meta)
                stats.made_of_merged = int((res.single() or {}).get("n", 0))
                stats.made_of_skipped_no_module = (
                    len(edge_rows) - stats.made_of_merged
                )
            except Exception as exc:   # noqa: BLE001 — Module 매칭 0건이거나 일부 매칭 실패 흡수 → log + 통계 (적재 부분 성공 보존)
                log.warning("[load:metals:made_of] UNWIND 실패: %s", exc)
                stats.errors.append(f"made_of: {exc}")

    log.info("[load:metals] materials=%d  made_of=%d (mappings_seen=%d, no_module=%d)",
             stats.materials_merged, stats.made_of_merged,
             stats.module_mappings_seen, stats.made_of_skipped_no_module)
    return {"stats": stats.__dict__, "snapshot_year": snapshot_year}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="autograph.loaders.load_materials_metals",
        description=__doc__.split("\n")[0],
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="seed parse + preview, Neo4j 적재 없음")
    ap.add_argument("--snapshot-year", type=int, default=None,
                    help="엣지 snapshot_year (기본 UTC year)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    out = run(dry_run=args.dry_run, snapshot_year=args.snapshot_year)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["run", "load_seed", "LoadStats",
           "_build_material_rows", "_build_made_of_rows"]
