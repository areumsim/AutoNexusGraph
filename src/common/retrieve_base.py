"""retrieve.py 공통 헬퍼 — 3 도메인 (finance/auto/ip) 의 중복 패턴 SSOT.

각 도메인의 `tools/retrieve.py` 는 자체 메타 필터 (corp_code / manufacturer_id /
assignee_id 등) 를 갖되, 다음 공통 부분은 본 모듈을 사용:
- ``DEFAULT_TOPK = 8`` / ``HARD_TOPK = 50`` — pgvector top-k 안전 cap
- ``cap_topk(k)`` — 캡 적용 헬퍼
- ``normalize_source_filter(source)`` — str | list[str] | None → list[str] | None

도메인별 메타 필터는 분리 유지 (PG 컬럼·인덱스가 다르므로). 본 모듈은
"진짜 중복" 만 흡수 — 도메인 자율성 보존.

본 모듈은 DB·LLM 의존 0 — pure helper.
"""

from __future__ import annotations

DEFAULT_TOPK: int = 8
HARD_TOPK: int = 50


def cap_topk(k: int | None) -> int:
    """top-k 를 [1, HARD_TOPK] 범위로 캡. None/음수면 DEFAULT_TOPK.

    finance/auto/ip 의 ``_cap`` 헬퍼와 동일 동작.
    """
    if k is None or k <= 0:
        return DEFAULT_TOPK
    return min(int(k), HARD_TOPK)


def normalize_source_filter(
    source: str | list[str] | tuple[str, ...] | None,
) -> list[str] | None:
    """source 필터를 단일 str/list/tuple → list[str] 로 정규화. None 은 None.

    빈 list/tuple → None (no filter). 도메인의 search_documents_* 에서 매번
    isinstance 분기하던 패턴을 흡수.
    """
    if source is None:
        return None
    if isinstance(source, str):
        return [source]
    if isinstance(source, (list, tuple)):
        out = [s for s in source if s]
        return out or None
    raise TypeError(f"source 는 str|list|tuple|None 이어야 함 — got {type(source)}")


__all__ = [
    "DEFAULT_TOPK",
    "HARD_TOPK",
    "cap_topk",
    "normalize_source_filter",
]
