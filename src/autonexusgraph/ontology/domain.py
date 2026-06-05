"""노드 라벨 → 도메인 namespace 매핑 SSOT.

Neo4j Community Edition은 multi-database 미지원 → 단일 DB `neo4j` 안에서
**노드 속성 `domain`** 으로 namespace 분리.

규칙:
- 도메인 전속 노드: 단일 문자열 (예: "auto")
- 공유 노드: 문자열 list (예: ["auto","finance"]) — Supplier/Person/Institution 등
- 매핑 없으면 None — 사용자 검토 대상

쿼리 예시 (도메인 필터):
    MATCH (n:Anxg_Manufacturer) WHERE 'auto' IN coalesce(n.domain, []) OR n.domain = 'auto' RETURN n
    또는 한 번 normalize 후:
    MATCH (n) WHERE 'auto' IN n.domains RETURN n  ← Backfill 시 항상 list 로 통일하면 더 깔끔

본 모듈은 **항상 list** 형태로 정규화 반환 (단일 도메인도 ["auto"]). 적재·쿼리 일관성 우선.
"""

from __future__ import annotations


# 라벨 → 도메인 리스트 (SSOT)
_DOMAIN_MAP: dict[str, list[str]] = {
    # ── AutoGraph (자동차) ────────────────────────────────────────
    "Manufacturer":   ["auto"],
    "VehicleModel":   ["auto"],
    "VehicleVariant": ["auto"],
    "Recall":         ["auto"],
    "Complaint":      ["auto"],
    "Investigation":  ["auto"],
    "System":         ["auto"],
    "Module":         ["auto"],
    "Part":           ["auto"],
    "Component":      ["auto"],
    "Process":        ["auto"],
    "ProcessStep":    ["auto"],
    "Plant":          ["auto"],
    "Material":       ["auto"],
    "Mineral":        ["auto"],
    "Standard":       ["auto"],
    "NewsEvent":      ["auto"],
    "Equipment":      ["auto"],
    "DefectType":     ["auto"],   # 신규 (DEFECT_MATCHES bridge)
    "FailureMode":    ["auto"],   # 예약 (가이드 §1.x)
    # ── IPGraph (특허) ────────────────────────────────────────────
    "CPCCode":  ["ip"],
    "Patent":   ["ip"],
    "Inventor": ["ip"],
    "Assignee": ["ip"],
    "Work":     ["ip"],
    # ── Finance / Corp ─────────────────────────────────────────────
    "Company":  ["finance"],
    "Industry": ["finance"],
    "Sector":   ["finance"],
    "Market":   ["finance"],
    "Group":    ["finance"],
    # ── 공유 (multi-domain) ───────────────────────────────────────
    "Supplier":    ["auto", "finance"],            # OEM 공급망 + 코퍼레이트 엔티티
    "Person":      ["auto", "finance", "ip"],     # 인물 (executive/inventor/저자 etc)
    "Institution": ["auto", "finance", "ip"],     # 학·기관 (KOTSA, NHTSA, KAIST 등)
}


KNOWN_DOMAINS: frozenset[str] = frozenset({"auto", "ip", "finance"})


def domain_for(label: str) -> list[str] | None:
    """라벨 → 도메인 리스트. 미정의 라벨은 None (사용자 검토 필요)."""
    return _DOMAIN_MAP.get(label)


def all_labels() -> list[str]:
    """매핑된 모든 라벨 (backfill 순회용)."""
    return sorted(_DOMAIN_MAP.keys())


def labels_in_domain(domain: str) -> list[str]:
    """특정 도메인에 속한 모든 라벨 (공유 노드 포함)."""
    return sorted(lab for lab, doms in _DOMAIN_MAP.items() if domain in doms)


__all__ = [
    "KNOWN_DOMAINS",
    "domain_for",
    "all_labels",
    "labels_in_domain",
]
