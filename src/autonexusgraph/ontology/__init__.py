"""Domain-agnostic 온톨로지 스키마 — pydantic v2 검증 (PRD §10 DoD #17 (c)).

각 도메인 (auto / finance / ip 예정) 의 yaml SSOT 는 본 모듈의
``OntologyFile`` 으로 1차 검증 후 사용된다. extra='forbid' 로 미지정 키 reject
→ yaml 오타·키 드리프트 즉시 차단.

핵심 결정:
- **schema_version 을 온톨로지 헤더로 끌어올림** — 엣지마다 반복 (per-edge
  metadata) 대신 파일 헤더 1곳 SoT. 엣지 적재 helper 가 헤더 값을 자동 부여.
- file 의 ``version`` (int) 은 yaml 포맷 버전. ``schema_version`` (str)
  은 PRD/도메인 모델 버전. 두 의미 분리.
"""

from .schema import (
    EDGE_REQUIRED_META_KEYS,
    EntitySpec,
    OntologyFile,
    OntologyValidationError,
    RelationSpec,
    load_and_validate,
    validate_dict,
)

__all__ = [
    "EDGE_REQUIRED_META_KEYS",
    "EntitySpec",
    "OntologyFile",
    "OntologyValidationError",
    "RelationSpec",
    "load_and_validate",
    "validate_dict",
]
