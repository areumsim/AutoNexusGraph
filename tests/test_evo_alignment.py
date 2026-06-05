"""L6-5 EVO alignment 회귀 가드.

`ontology/auto/evo_alignment.yaml` 의 우리 라벨이 실제 `entities.yaml` /
`relations.yaml` 에 존재하는지 + 형식 정합 검증. 매핑 IRI 값 자체는 검증 안 함
(후속 검증 대상 placeholder 다수).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPO = Path(__file__).resolve().parents[1]
ALIGN = REPO / "ontology" / "auto" / "evo_alignment.yaml"
ENTITIES = REPO / "ontology" / "auto" / "entities.yaml"
RELATIONS = REPO / "ontology" / "auto" / "relations.yaml"


@pytest.fixture
def alignment():
    return yaml.safe_load(ALIGN.read_text(encoding="utf-8"))


@pytest.fixture
def our_entities():
    data = yaml.safe_load(ENTITIES.read_text(encoding="utf-8"))
    return set((data.get("entities") or {}).keys())


@pytest.fixture
def our_relations():
    data = yaml.safe_load(RELATIONS.read_text(encoding="utf-8"))
    return set((data.get("relations") or {}).keys())


# ── 기본 형식 ───────────────────────────────────────────────────
def test_alignment_file_exists():
    assert ALIGN.is_file()


def test_upstream_meta_expected_counts(alignment):
    """upstream 메타가 BACKLOG L6-5 기재한 EVO 카운트와 일치 (20/17/54)."""
    up = alignment.get("upstream") or {}
    counts = up.get("expected_counts") or {}
    assert counts.get("classes") == 20, f"classes: {counts.get('classes')}"
    assert counts.get("object_properties") == 17
    assert counts.get("datatype_properties") == 54


def test_upstream_source_arxiv_id(alignment):
    """upstream source 가 arXiv:2304.04893 명시."""
    up = alignment.get("upstream") or {}
    src = (up.get("source") or "")
    assert "2304.04893" in src, f"upstream.source 가 arXiv ID 누락: {src!r}"


# ── 우리 라벨 정합 ────────────────────────────────────────────────
def test_all_entity_labels_exist(alignment, our_entities):
    """alignment.entities 의 라벨이 우리 entities.yaml 에 모두 존재.

    회귀 가드: rename / 삭제 시 alignment 가 stale 되는 것 차단.
    """
    aligned = set((alignment.get("entities") or {}).keys())
    missing = aligned - our_entities
    assert not missing, (
        f"alignment entities 중 entities.yaml 에 없는 라벨: {sorted(missing)}"
    )


def test_all_relation_types_exist(alignment, our_relations):
    """alignment.relations 의 타입이 우리 relations.yaml 에 모두 존재."""
    aligned = set((alignment.get("relations") or {}).keys())
    missing = aligned - our_relations
    assert not missing, (
        f"alignment relations 중 relations.yaml 에 없는 타입: {sorted(missing)}"
    )


# ── 각 매핑 entry 형식 ───────────────────────────────────────────
def test_entity_entries_have_required_fields(alignment):
    """각 entity 매핑은 evo_class + iri 필드 보유 (iri 는 null 허용)."""
    violations: list[str] = []
    for label, mapping in (alignment.get("entities") or {}).items():
        if not isinstance(mapping, dict):
            violations.append(f"{label}: not a dict")
            continue
        if "evo_class" not in mapping:
            violations.append(f"{label}: missing 'evo_class'")
        if "iri" not in mapping:
            violations.append(f"{label}: missing 'iri'")
    assert not violations, "\n".join(violations)


def test_relation_entries_have_required_fields(alignment):
    """각 relation 매핑은 evo_property + iri 필드 보유."""
    violations: list[str] = []
    for rel, mapping in (alignment.get("relations") or {}).items():
        if not isinstance(mapping, dict):
            violations.append(f"{rel}: not a dict")
            continue
        if "evo_property" not in mapping:
            violations.append(f"{rel}: missing 'evo_property'")
        if "iri" not in mapping:
            violations.append(f"{rel}: missing 'iri'")
    assert not violations, "\n".join(violations)


def test_non_applicable_entries_have_null_iri(alignment):
    """applicable=false 표시한 entry 는 iri 도 null (의도된 비매핑 일관성)."""
    violations: list[str] = []
    for section in ("entities", "relations"):
        for name, m in (alignment.get(section) or {}).items():
            if not isinstance(m, dict):
                continue
            if m.get("applicable") is False and m.get("iri") is not None:
                violations.append(
                    f"{section}.{name}: applicable=false 인데 iri={m.get('iri')!r}"
                )
    assert not violations, "\n".join(violations)


def test_no_false_iri_committed(alignment):
    """매핑 IRI 값이 채워졌으면 (null 아님) 'TBD'/'추정'/'(추정)' placeholder 가 아님.

    회귀 가드: 후속 매핑 작업 시 placeholder 텍스트가 실수로 IRI 자리에 박히지 않도록.
    """
    fake_markers = ("TBD", "추정", "placeholder", "(추정)", "?")
    violations: list[str] = []
    for section in ("entities", "relations"):
        for name, m in (alignment.get(section) or {}).items():
            if not isinstance(m, dict):
                continue
            iri = m.get("iri")
            if iri is None:
                continue
            iri_s = str(iri)
            for fake in fake_markers:
                if fake in iri_s:
                    violations.append(
                        f"{section}.{name}: iri={iri_s!r} placeholder 표기 포함"
                    )
                    break
            # 실제 IRI 라면 http:// 또는 urn: scheme.
            if not (iri_s.startswith("http://") or iri_s.startswith("https://")
                    or iri_s.startswith("urn:")):
                violations.append(
                    f"{section}.{name}: iri={iri_s!r} URI scheme 미준수 (http/https/urn)"
                )
    assert not violations, (
        "iri 필드에 부적합 값 발견 (placeholder 또는 잘못된 scheme):\n"
        + "\n".join(violations)
    )


# ── 진척 통계 (informational) ──────────────────────────────────
def test_progress_is_informational_only(alignment):
    """채워진 매핑 비율 측정 — fail 조건 없음, 진척 가시화용 echo."""
    total_e = len(alignment.get("entities") or {})
    filled_e = sum(
        1 for m in (alignment.get("entities") or {}).values()
        if isinstance(m, dict) and m.get("iri") is not None
    )
    total_r = len(alignment.get("relations") or {})
    filled_r = sum(
        1 for m in (alignment.get("relations") or {}).values()
        if isinstance(m, dict) and m.get("iri") is not None
    )
    # 진척 0% 가 본 단계 정상 (스켈레톤). 후속 PR 마다 채워지면 자연 증가.
    assert total_e >= 10 and total_r >= 5, \
        f"alignment 항목 부족: entities={total_e}, relations={total_r}"
    # 본 정보만 print (pytest -v 시 stdout 노출).
    print(f"\n[evo_alignment] entities filled={filled_e}/{total_e}, "
          f"relations filled={filled_r}/{total_r}")
