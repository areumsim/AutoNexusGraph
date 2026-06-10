#!/usr/bin/env python3
"""PRD §10 DoD #17 (c) — 온톨로지 pydantic strict 검증 audit.

본 스크립트는 ``ontology/{auto,ip}/{entities,relations}.yaml`` + ``ontology/{entities,
relations}.yaml`` (finance) 를 ``autonexusgraph.ontology.OntologyFile`` 로
strict-validate.

검증 항목:
  1. yaml syntax 정상 (parse 실패 즉시 FAIL)
  2. 모든 키가 schema 에 정의됨 (extra='forbid' — 오타·드리프트 reject)
  3. enum 값 (cardinality/class/provenance/pass) 정합
  4. relation.from / to 가 entities 에 존재 (entities 와 relations 같이 검증 시)
  5. edge_required_meta 가 PRD §6.7 7키 SoT 와 일치
  6. schema_version 헤더 존재 (DoD #17 (c) 의 "온톨로지 레벨" 핵심)
  7. cypher_templates 의 엣지 타입 ⊆ relations.yaml 정의된 관계명
  8. **(Y-1)** 보조 yaml strict (extractors / system_taxonomy / plants) —
     pydantic extra='forbid' 로 field-name 드리프트 reject

종료 코드:
    0: 모든 파일 pass
    1: 하나 이상 fail
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from autonexusgraph.ontology import (  # noqa: E402
    OntologyFile,
    OntologyValidationError,
    load_and_validate,
)

log = logging.getLogger(__name__)


# 검증 대상 — (label, path, must_have_schema_version).
# auto 측 entities/relations 가 primary (실 코드가 로딩). finance 측은 SSOT only.
# ip 측은 도메인3 (PRD §12.5) — yaml + cypher_templates_ip 동기화 검증.
DEFAULT_TARGETS: list[tuple[str, Path, bool]] = [
    ("auto.entities",     ROOT / "ontology" / "auto" / "entities.yaml",  True),
    ("auto.relations",    ROOT / "ontology" / "auto" / "relations.yaml", True),
    ("ip.entities",       ROOT / "ontology" / "ip"   / "entities.yaml",  True),
    ("ip.relations",      ROOT / "ontology" / "ip"   / "relations.yaml", True),
    ("finance.entities",  ROOT / "ontology" / "entities.yaml",           True),
    ("finance.relations", ROOT / "ontology" / "relations.yaml",          True),
]


# Cypher 의 엣지 타입 추출 정규식. 예: -[:SUPPLIED_BY]-> / -[r:RECALL_OF]-> /
# <-[:CITES]- / -[:SUBCLASS_OF*1..3]->. label 만 capture.
_CYPHER_EDGE_RE = re.compile(r"-\[[a-zA-Z0-9_]*:([A-Z][A-Z0-9_]*)")


# 도메인별 cypher templates 모듈·dict 위치 — yaml ↔ cypher cross-check 에 사용.
# finance 의 ``TEMPLATES`` 는 자체 정의분만 (autograph/ipgraph 가 register_templates 로
# 머지하기 전 import). 그대로 비교 가능.
CYPHER_TEMPLATE_REGISTRIES: list[tuple[str, str, str, Path]] = [
    # (domain, import_path, dict_name, relations_yaml_path)
    ("finance", "autonexusgraph.tools.cypher_templates", "TEMPLATES",
     ROOT / "ontology" / "relations.yaml"),
    ("auto", "autograph.cypher_templates_auto",  "AUTO_TEMPLATES",
     ROOT / "ontology" / "auto" / "relations.yaml"),
    ("ip",   "ipgraph.cypher_templates_ip",      "IP_TEMPLATES",
     ROOT / "ontology" / "ip"   / "relations.yaml"),
]


# ── 보조 yaml strict 모델 (Y-1) — extractors / system_taxonomy / plants ──
# extra='forbid' 로 field-name 드리프트(오타·미정의 키) reject. 이질적 내부 값은
# Any 로 두어 값-형태 변동에 brittle 하지 않게 (목적 = 키 드리프트 탐지, §10.17c).
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ExtractorSource(_Strict):
    type: str | None = None
    endpoint: str | None = None
    params: Any = None
    url: str | None = None
    table: str | None = None
    tables: Any = None
    filter: Any = None
    function: str | None = None
    lib: str | None = None
    ref: Any = None
    refs: Any = None


class ExtractorOut(_Strict):
    entities: list[str] = []
    relations: list[str] = []


class Extractor(_Strict):
    pass_: str = Field(alias="pass")           # 'pass' 는 예약어 → alias
    source: ExtractorSource | str | None = None  # dict 또는 free-text (cross_validate 등)
    method: str | None = None
    out: ExtractorOut | None = None
    impl: Any = None                           # str 또는 dict
    target: dict | None = None
    idempotency: str | None = None
    status: str | None = None
    confidence: Any = None
    confidence_gate: Any = None
    llm: Any = None
    logic: Any = None
    notes: Any = None


class ExtractorsFile(_Strict):
    version: int
    last_updated: Any = None
    status_summary: Any = None
    extractors: dict[str, Extractor]


class SystemEntry(_Strict):
    code: str
    name: str
    description: str | None = None
    alias_codes: list[str] = []


class SystemTaxonomyFile(_Strict):
    version: int
    last_updated: Any = None
    systems: list[SystemEntry]


class PlantEntry(_Strict):
    code: str
    name: str
    manufacturer_name: str
    country: str
    city: str | None = None
    wikidata_qid: str | None = None
    notes: str | None = None


class PlantsFile(_Strict):
    version: int
    last_updated: Any = None
    plants: list[PlantEntry]


class MaterialMetalEntry(_Strict):
    """알루미늄/강철 합금 entry — materials_metals_seed.yaml 의 materials dict 값."""
    name: str
    material_class: str            # 'metal_alloy' 고정 (확장 시 'polymer' 등)
    alloy_family: str | None = None
    aliases: list[str] = []
    typical_processes: list[str] = []
    typical_modules: list[str] = []
    density_kg_m3: int | float | None = None
    wikidata_qid: str | None = None


class MetalsModuleMapping(_Strict):
    """Module → Material 매핑 entry."""
    module_name: str
    materials: list[str]


class MaterialsMetalsFile(_Strict):
    version: int
    last_updated: Any = None
    materials: dict[str, MaterialMetalEntry]
    module_to_materials: list[MetalsModuleMapping]


# (label, path, model, item_attr) — item_attr 로 개수 카운트.
AUX_TARGETS: list[tuple[str, Path, type[BaseModel], str]] = [
    ("auto.extractors",      ROOT / "ontology" / "auto" / "extractors.yaml",              ExtractorsFile,      "extractors"),
    ("finance.extractors",   ROOT / "ontology" / "extractors.yaml",                       ExtractorsFile,      "extractors"),
    ("auto.system_taxonomy", ROOT / "ontology" / "auto" / "system_taxonomy.yaml",         SystemTaxonomyFile,  "systems"),
    ("auto.plants",          ROOT / "ontology" / "auto" / "plants.yaml",                  PlantsFile,          "plants"),
    ("auto.materials_metals", ROOT / "ontology" / "auto" / "materials_metals_seed.yaml",  MaterialsMetalsFile, "materials"),
]


def _validate_aux(label: str, path: Path, model: type[BaseModel], item_attr: str) -> dict:
    """보조 yaml 1개 strict 검증 — 키 드리프트(extra forbid) reject."""
    if not path.exists():
        return {"label": label, "path": str(path), "passed": False, "reason": "파일 없음"}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        obj = model.model_validate(data)
        items = getattr(obj, item_attr)
        return {"label": label, "path": str(path), "passed": True, "n_items": len(items)}
    except Exception as e:   # noqa: BLE001 — pydantic ValidationError 포함
        return {"label": label, "path": str(path), "passed": False,
                "reason": str(e).splitlines()[0][:200]}


def _validate_one(label: str, path: Path, require_schema_version: bool) -> dict:
    if not path.exists():
        return {"label": label, "path": str(path), "passed": False,
                "reason": "파일 없음"}
    try:
        ont: OntologyFile = load_and_validate(path)
    except OntologyValidationError as e:
        return {"label": label, "path": str(path), "passed": False,
                "reason": f"validation 실패: {e.cause}"}
    if require_schema_version and not ont.schema_version:
        return {"label": label, "path": str(path), "passed": False,
                "reason": "schema_version 헤더 누락 (PRD §10 DoD #17 (c))"}
    return {
        "label":          label,
        "path":           str(path),
        "passed":         True,
        "schema_version": ont.schema_version,
        "n_entities":     len(ont.entities or {}),
        "n_relations":    len(ont.relations or {}),
    }


def _load_all_yaml_relations() -> dict[str, set[str]]:
    """전 도메인 relations.yaml 의 relation 키 집합 — cross-domain reference 판별용."""
    out: dict[str, set[str]] = {}
    for label, path, _ in DEFAULT_TARGETS:
        if not label.endswith(".relations") or not path.exists():
            continue
        domain = label.rsplit(".", 1)[0]
        try:
            ont = load_and_validate(path)
            out[domain] = set((ont.relations or {}).keys())
        except OntologyValidationError:
            out[domain] = set()
    return out


def _validate_cypher_relations(domain: str, import_path: str, dict_name: str,
                                relations_yaml: Path,
                                all_yaml_rels: dict[str, set[str]],
                                strict_cross: bool = False) -> dict:
    """Cypher 템플릿에서 사용된 엣지 타입이 relations.yaml 에 정의되어 있는지 검증.

    cross-domain reference (예: ip.cypher 가 auto.SUPPLIED_BY 참조) 는 기본 WARN.
    진짜 누락 (어느 도메인 yaml 에도 없는 엣지) 만 ERROR.

    Y-2: ``strict_cross=True`` (CLI ``--strict-cross``) 면 cross-domain reference 도
    ERROR 로 강등 — 도메인 격리를 엄격히 강제할 때.
    """
    label = f"{domain}.cypher-vs-yaml"
    if not relations_yaml.exists():
        return {"label": label, "passed": False,
                "reason": f"relations.yaml 없음: {relations_yaml}"}
    try:
        ont = load_and_validate(relations_yaml)
        # enabled: false 인 rel 은 cypher 의 의도적 미사용 (ablation 후 활성, OpenAlex
        # 적재 대기 등) → unused_in_cypher 에서 제외하여 진짜 결손만 노출.
        yaml_rels = {
            name for name, rel in (ont.relations or {}).items()
            if getattr(rel, "enabled", True)
        }
    except OntologyValidationError as e:
        return {"label": label, "passed": False,
                "reason": f"relations.yaml validation 실패: {e.cause}"}

    try:
        import importlib
        mod = importlib.import_module(import_path)
        templates: dict = getattr(mod, dict_name)
    except (ImportError, AttributeError) as e:
        return {"label": label, "passed": False,
                "reason": f"cypher templates 모듈 import 실패: {e}"}

    cypher_rels: set[str] = set()
    for tpl in templates.values():
        cypher = tpl.get("cypher", "") if isinstance(tpl, dict) else ""
        cypher_rels |= set(_CYPHER_EDGE_RE.findall(cypher))

    # 도메인 외 yaml 정의 union (cross-domain reference 판별).
    other_yaml_union: set[str] = set()
    for d, rels in all_yaml_rels.items():
        if d != domain:
            other_yaml_union |= rels

    own_missing = cypher_rels - yaml_rels
    cross_domain_refs = sorted(own_missing & other_yaml_union)
    true_missing = sorted(own_missing - other_yaml_union)
    unused_in_cypher = sorted(yaml_rels - cypher_rels)

    if true_missing:
        return {
            "label":             label,
            "passed":            False,
            "reason":            f"cypher 에서 사용되나 어느 yaml 에도 미정의: {true_missing}",
            "cypher_rels":       sorted(cypher_rels),
            "yaml_rels":         sorted(yaml_rels),
            "true_missing":      true_missing,
            "cross_domain_refs": cross_domain_refs,
            "unused_in_cypher":  unused_in_cypher,
        }

    if strict_cross and cross_domain_refs:
        return {
            "label":             label,
            "passed":            False,
            "reason":            f"cross-domain reference (--strict-cross): {cross_domain_refs}",
            "n_cypher_rels":     len(cypher_rels),
            "n_yaml_rels":       len(yaml_rels),
            "cross_domain_refs": cross_domain_refs,
            "unused_in_cypher":  unused_in_cypher,
        }

    return {
        "label":             label,
        "passed":            True,
        "n_cypher_rels":     len(cypher_rels),
        "n_yaml_rels":       len(yaml_rels),
        "cross_domain_refs": cross_domain_refs,
        "unused_in_cypher":  unused_in_cypher,
    }


def main() -> int:
    p = argparse.ArgumentParser(prog="audit-ontology", description=__doc__.split("\n")[0])
    p.add_argument("--out-dir", type=Path,
                   default=ROOT / "data" / "reports",
                   help="JSON 리포트 저장 디렉토리")
    p.add_argument("--paths", nargs="*", type=Path,
                   help="검증할 yaml 경로 (생략 시 기본 6 파일)")
    p.add_argument("--cross", action="store_true", default=True,
                   help="cypher templates ↔ relations.yaml cross-check 수행 (기본 on)")
    p.add_argument("--no-cross", action="store_false", dest="cross",
                   help="cross-check 건너뛰기")
    p.add_argument("--strict-cross", action="store_true", default=False,
                   help="Y-2: cross-domain cypher reference 를 ERROR 로 (기본 WARN)")
    p.add_argument("--log-level", default="WARNING")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level)

    targets: list[tuple[str, Path, bool]]
    if args.paths:
        targets = [(p.name, p, True) for p in args.paths]
    else:
        targets = DEFAULT_TARGETS

    results = [_validate_one(label, path, must) for label, path, must in targets]

    # 보조 yaml strict 검증 (Y-1) — extractors / system_taxonomy / plants.
    if not args.paths:
        for label, path, model, item_attr in AUX_TARGETS:
            results.append(_validate_aux(label, path, model, item_attr))

    # cypher templates ↔ relations.yaml cross-check.
    if args.cross and not args.paths:
        all_yaml = _load_all_yaml_relations()
        for domain, imp, dn, rels_path in CYPHER_TEMPLATE_REGISTRIES:
            results.append(
                _validate_cypher_relations(domain, imp, dn, rels_path, all_yaml,
                                           strict_cross=args.strict_cross)
            )

    failed = [r for r in results if not r["passed"]]
    overall = len(failed) == 0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out_dir / f"audit_ontology_{ts}.json"
    payload = {
        "passed":  overall,
        "n_total": len(results),
        "n_pass":  sum(1 for r in results if r["passed"]),
        "n_fail":  len(failed),
        "results": results,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    if overall:
        # 기본 yaml 결과는 (E/R/schema_version) 표기, cross-check 결과는 별도.
        yaml_summary = " · ".join(
            f"{r['label']}({r['n_entities']}E/{r['n_relations']}R/{r['schema_version']})"
            for r in results
            if r.get("n_entities") is not None
        )
        aux_summary = " · ".join(
            f"{r['label']}({r['n_items']})"
            for r in results
            if r.get("n_items") is not None
        )
        cross_summary = " · ".join(
            f"{r['label']}({r['n_cypher_rels']}cy/{r['n_yaml_rels']}yml)"
            for r in results
            if r.get("n_cypher_rels") is not None
        )
        line = f"[audit-ontology] PASS — {yaml_summary}"
        if aux_summary:
            line += f"  ▸ aux: {aux_summary}"
        if cross_summary:
            line += f"  ▸ cross: {cross_summary}"
        print(f"{line}  ({out_path})")
        # Y-2: cross-domain reference 는 PASS 라도 WARN 으로 가시화 (--strict-cross 시 ERROR).
        for r in results:
            if r.get("passed") and r.get("cross_domain_refs"):
                print(f"  ⚠️ {r['label']}: cross-domain reference (WARN, "
                      f"--strict-cross 시 ERROR): {r['cross_domain_refs']}")
    else:
        print(f"[audit-ontology] FAIL — {len(failed)}/{len(results)} checks  ({out_path})")
        for r in failed:
            path_hint = f" ({r['path']})" if r.get("path") else ""
            print(f"  ✗ {r['label']}{path_hint}: {r['reason']}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
