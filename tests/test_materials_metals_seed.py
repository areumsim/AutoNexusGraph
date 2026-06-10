"""materials_metals_seed.yaml 일관성 회귀 가드.

`scripts/audit/ontology_validate.py` 의 `MaterialsMetalsFile` 가 strict 키 검증을
처리. 본 테스트는 그 위에 **내용 일관성** 검증:

1. typical_processes 가 KAMP catalog process_name_norm 사전과 정합
   (또는 L6-2 가 신규 도입한 process — extrusion/hot_stamping — 만 허용).
2. module_to_materials.materials 가 materials dict 키 안에 모두 존재.
3. typical_modules 도 module_to_materials 의 module_name 과 cross-link 유효.
4. material_class 는 'metal_alloy' 단일 분기.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
SEED = REPO / "ontology" / "auto" / "materials_metals_seed.yaml"

# KAMP catalog 의 process_name_norm 사전 + L6-2 신규 추가.
_ALLOWED_PROCESSES = {
    # KAMP catalog 8 카테고리 안 process_name_norm (load_kamp_catalog._PROCESS_NORM)
    "die_casting", "melting", "press", "fine_blanking", "plastic_forming",
    "cold_forging", "welding", "battery_welding", "heat_treatment",
    "plating", "electro_cleaning", "acid_pretreatment", "chromate",
    "hot_air_drying", "cnc_machining", "laser_machining", "nc_machining",
    "can_making", "can_filling", "injection_molding", "inspection",
    "visual_inspection", "outgoing_inspection", "battery_test",
    "rotating_machinery", "sterilization", "drying", "packaging", "dyeing",
    "mixing", "vmi_order", "production_plan", "full_supply_chain",
    # 8 KAMP category root (typical_processes 가 category 직접 참조 시 허용)
    "casting", "forging", "stamping", "machining", "assembly",
    "coating",
    # L6-2 가 신규 도입 — 운영 시 KAMP catalog 와 정합 추적 필요
    "extrusion", "hot_stamping",
}


@pytest.fixture
def seed():
    return yaml.safe_load(SEED.read_text(encoding="utf-8"))


def test_seed_file_exists():
    assert SEED.is_file(), f"missing: {SEED}"


def test_all_materials_are_metal_alloy(seed):
    for code, m in seed["materials"].items():
        assert m["material_class"] == "metal_alloy", \
            f"{code}: material_class={m['material_class']!r} (기대: 'metal_alloy')"


def test_typical_processes_in_taxonomy(seed):
    """typical_processes 의 모든 값이 KAMP catalog 사전 또는 L6-2 신규에 포함."""
    violations: list[str] = []
    for code, m in seed["materials"].items():
        for proc in m.get("typical_processes", []):
            if proc not in _ALLOWED_PROCESSES:
                violations.append(f"{code}: '{proc}' — 미지의 process_name_norm")
    assert not violations, (
        "typical_processes 가 KAMP catalog 또는 L6-2 신규 사전에 없음:\n"
        + "\n".join(violations)
    )


def test_module_to_materials_references_exist(seed):
    """module_to_materials.materials list 의 모든 코드가 materials dict 에 존재."""
    materials = set(seed["materials"].keys())
    violations: list[str] = []
    for mapping in seed["module_to_materials"]:
        for mat in mapping["materials"]:
            if mat not in materials:
                violations.append(
                    f"module='{mapping['module_name']}' references "
                    f"unknown material '{mat}'"
                )
    assert not violations, (
        "module_to_materials 가 미존재 material 참조:\n"
        + "\n".join(violations)
    )


def test_typical_modules_consistent_with_mapping(seed):
    """material 의 typical_modules 와 module_to_materials 의 module_name 가 양방향 일치.

    엄격 검사가 아니라 위양성 가능 — typical_modules 는 hint, mapping 은 실제 적재
    트리거. 양방향 0 매칭은 데이터 오류 신호. 한쪽만 누락은 WARN (테스트 fail 아님).
    """
    materials = seed["materials"]
    mapping_by_module: dict[str, set[str]] = {}
    for m in seed["module_to_materials"]:
        mapping_by_module.setdefault(m["module_name"], set()).update(m["materials"])

    # 각 material 의 typical_modules 가 mapping 에 적어도 1개라도 있어야 함
    # (완전 누락 = 데이터 오류). 부분 누락은 hint 보강 여지.
    fully_orphan: list[str] = []
    for code, m in materials.items():
        typ_mods = m.get("typical_modules", [])
        if not typ_mods:
            continue
        if not any(mod in mapping_by_module and code in mapping_by_module[mod]
                   for mod in typ_mods):
            fully_orphan.append(f"{code}: typical_modules={typ_mods} — mapping 0 매칭")
    assert not fully_orphan, (
        "material 의 typical_modules 가 module_to_materials 와 0 매칭 (데이터 오류):\n"
        + "\n".join(fully_orphan)
    )


def test_aliases_no_duplicate_codes(seed):
    """aliases 가 다른 material 의 code 와 충돌하지 않음 (lookup 모호 방지)."""
    codes = set(seed["materials"].keys())
    violations: list[str] = []
    for code, m in seed["materials"].items():
        for alias in m.get("aliases", []):
            if alias in codes and alias != code:
                violations.append(f"{code}: alias '{alias}' 가 다른 material code 와 충돌")
    assert not violations, "\n".join(violations)


def test_alloy_family_coverage(seed):
    """모든 material 에 alloy_family 명시 (분류·검색 안정성)."""
    missing = [c for c, m in seed["materials"].items() if not m.get("alloy_family")]
    assert not missing, f"alloy_family 누락: {missing}"


def test_seed_size_lower_bound(seed):
    """최소 시드 규모 — 차체용 alloy 다양성 보장. 9 → 차후 확장 가능."""
    assert len(seed["materials"]) >= 9, \
        f"materials {len(seed['materials'])} — 최소 9개 필요 (Al 4 + 강 4 + Ti 1)"
    assert len(seed["module_to_materials"]) >= 10, \
        f"module mappings {len(seed['module_to_materials'])} — 최소 10개 필요"
