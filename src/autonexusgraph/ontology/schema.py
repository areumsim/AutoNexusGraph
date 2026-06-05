"""Pydantic v2 모델 — domain-agnostic 온톨로지 스키마.

PRD §10 DoD #17 (c) 충족:
  "온톨로지 SHACL/pydantic 검증 (schema_version 온톨로지 레벨)"

설계 결정:
- LPG (Neo4j Labeled Property Graph) 가 그래프 모델 — RDF 모델은 conceptual
  mismatch. 따라서 pydantic 으로 단일화 (SHACL/rdflib/pyshacl 의존 회피).
- ``extra='forbid'`` 로 미지정 키 reject — yaml 오타·드리프트 즉시 차단.
- ``schema_version`` 을 파일 헤더로 끌어올림 — 엣지 단위 7키 (PRD §6.7) 에서는
  여전히 ``schema_version`` 이 존재하나, ontology 파일 헤더가 그 값의 SoT.
- ``from`` / ``class`` / ``pass`` 가 Python keyword → alias 사용.
  ``model_dump(by_alias=True)`` 로 raw dict 환원 — 기존 ``spec['from']`` /
  ``spec.get('class')`` 같은 dict access 호출자 호환.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ── §6.7 의무 메타 7키 — relations.yaml::edge_required_meta SoT ───
EDGE_REQUIRED_META_KEYS: tuple[str, ...] = (
    "source_type",
    "source_id",
    "confidence_score",
    "validated_status",
    "snapshot_year",
    "extraction_method",
    "schema_version",
)


# ─── Enum (literal) ────────────────────────────────────────────────
Cardinality = Literal["one-to-one", "one-to-many", "many-to-one", "many-to-many"]
EdgeClass = Literal["main_hop", "side_hop"]
Provenance = Literal["deterministic", "llm", "hybrid", "manual"]
ExtractionPass = Literal["P1", "P2", "P3", "P4", "P5"]


# ─── EntitySpec ────────────────────────────────────────────────────
class EntitySpec(BaseModel):
    """엔티티 (Neo4j 라벨) 정의."""
    model_config = ConfigDict(extra="forbid")

    description: str
    # 자연 키 — 단일 ('id', 'corp_code') 또는 복합 (['corp_code', 'bsns_year']).
    key: str | list[str] = "id"
    required: list[str] = Field(default_factory=list)
    optional: list[str] = Field(default_factory=list)
    bom_level: int | None = None
    # PG 매핑 — 도메인별 별칭 (auto: pg_table / finance: sql_table).
    pg_table: str | None = None
    sql_table: str | None = None
    provenance_src: list[str] = Field(default_factory=list)

    @field_validator("bom_level")
    @classmethod
    def _bom_level_range(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 6):
            raise ValueError(f"bom_level out of range [0, 6]: {v}")
        return v


# ─── RelationSpec ──────────────────────────────────────────────────
class RelationSpec(BaseModel):
    """관계 (Neo4j 엣지 타입) 정의."""
    # ``from`` / ``class`` / ``pass`` 는 Python keyword — alias 로 받음.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: str = Field(..., alias="from")
    to: str
    directed: bool = True
    cardinality: Cardinality = "many-to-many"
    class_: EdgeClass | None = Field(None, alias="class")
    provenance: Provenance | None = None
    pass_: ExtractionPass | None = Field(None, alias="pass")
    confidence_default: float = Field(0.7, ge=0.0, le=1.0)
    enabled: bool = True
    description: str | None = None
    notes: str | None = None
    # Finance 도메인 호환 — auto 와 다른 패턴.
    properties: list[dict[str, Any]] | None = None     # 엣지 속성 스키마 정의 (deterministic)
    confidence: float | str | None = None              # 적재 임계 (확정 적재 cutoff) — auto 의 confidence_default 와 별개


# ─── OntologyFile (top-level) ──────────────────────────────────────
class OntologyFile(BaseModel):
    """단일 yaml 파일 모델 — entities + relations 또는 둘 중 하나만 가능."""
    # 헤더에 추가 메타 (last_updated 등) 허용. entities/relations 내부는 forbid.
    model_config = ConfigDict(extra="allow")

    # 파일 포맷 버전 — yaml 자체 구조 변경 시 증가.
    version: int = 1
    # **온톨로지 레벨 schema_version** — 본 단계에서 끌어올린 핵심 필드.
    # PRD §6.7 의 엣지 단위 schema_version 의 source-of-truth 가 된다.
    schema_version: str | None = None
    domain: str | None = None
    # yaml 의 ``2026-05-28`` 같은 unquoted date 자동 파싱 → date object 그대로 허용.
    last_updated: str | _dt.date | None = None
    entities: dict[str, EntitySpec] | None = None
    relations: dict[str, RelationSpec] | None = None
    edge_required_meta: list[str] | None = None
    naming_conventions: dict[str, str] | list[str] | None = None

    @model_validator(mode="after")
    def _cross_validate(self) -> "OntologyFile":
        # 1. relation.from / to 가 entities 에 존재 (둘 다 있을 때만).
        if self.relations and self.entities:
            labels = set(self.entities.keys())
            errors: list[str] = []
            for rt, rel in self.relations.items():
                if rel.from_ not in labels:
                    errors.append(f"relation {rt}: from='{rel.from_}' 라벨이 entities 에 없음")
                if rel.to not in labels:
                    errors.append(f"relation {rt}: to='{rel.to}' 라벨이 entities 에 없음")
            if errors:
                raise ValueError("ontology cross-validation 실패:\n  - " + "\n  - ".join(errors))

        # 2. edge_required_meta 가 7키 SoT 와 일치 (있을 때만).
        if self.edge_required_meta is not None:
            declared = set(self.edge_required_meta)
            expected = set(EDGE_REQUIRED_META_KEYS)
            missing = expected - declared
            extra = declared - expected
            if missing:
                raise ValueError(
                    f"edge_required_meta 누락 키: {sorted(missing)}. "
                    f"PRD §6.7 SoT = {EDGE_REQUIRED_META_KEYS}"
                )
            if extra:
                raise ValueError(
                    f"edge_required_meta 잉여 키: {sorted(extra)}. "
                    f"PRD §6.7 SoT = {EDGE_REQUIRED_META_KEYS}"
                )
        return self


# ─── 예외 ──────────────────────────────────────────────────────────
class OntologyValidationError(ValueError):
    """ontology 검증 실패 — 파일 경로 + 원인 ValidationError 묶음."""

    def __init__(self, path: Path | str, cause: Exception) -> None:
        super().__init__(f"{path}: {cause}")
        self.path = Path(path)
        self.cause = cause


# ─── 진입점 ────────────────────────────────────────────────────────
def validate_dict(data: dict[str, Any]) -> OntologyFile:
    """dict (이미 yaml.safe_load 된 것) → OntologyFile.

    pydantic ValidationError 가 그대로 raise 됨.
    """
    return OntologyFile(**data)


def load_and_validate(path: Path | str) -> OntologyFile:
    """yaml 파일 → OntologyFile. 검증 실패 시 ``OntologyValidationError``."""
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:   # noqa: BLE001 — yaml 파싱 실패 → OntologyValidationError 변환 (raise)
        raise OntologyValidationError(p, e) from e
    if not isinstance(raw, dict):
        raise OntologyValidationError(p, ValueError("최상위 구조가 dict 아님"))
    try:
        return validate_dict(raw)
    except Exception as e:   # noqa: BLE001 — 검증 실패 → OntologyValidationError 변환 (raise)
        raise OntologyValidationError(p, e) from e
