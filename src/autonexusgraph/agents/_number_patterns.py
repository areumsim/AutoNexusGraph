"""큰 숫자(재무 수치) 추출 공통 SSOT — validator + number_guard 가 공유.

PRD §7.3 ("재무 수치는 절대 LLM 이 생성하지 않는다") 의 pre-synth 가드와
post-synth 가드가 동일 정규식을 사용해야 일관성이 보장된다.

큰 숫자 정의:
- 콤마 그룹 ≥ 2 (백만 이상)  예: 258,935,500,000,000
- OR leading-digit 1-9 + 7자리 이상 (천만 이상)  예: 9876543210
- 4자리 연도 / leading-zero 식별자(corp_code) / 비율(소수점) 등은 제외.
- ``\\b`` 대신 ``(?<![\\d,])(?![\\d,])`` — '원' 같은 한국어가 \\w 로 인식돼
  ``\\b`` 가 비활성화되는 문제 회피.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

BIG_NUMBER_RE: re.Pattern[str] = re.compile(
    r"(?<![\d,])(\d{1,3}(?:,\d{3}){2,}|[1-9]\d{6,})(?![\d,])"
)


def normalize_number(num: str) -> str:
    """콤마 제거된 정규형."""
    return num.replace(",", "")


def extract_big_numbers(text: str) -> set[str]:
    """텍스트 안의 큰 숫자 토큰을 정규형(콤마 제거)으로 추출."""
    if not text:
        return set()
    return {normalize_number(m.group(0)) for m in BIG_NUMBER_RE.finditer(text)}


def numbers_from_strings(strings: Iterable[object]) -> set[str]:
    """문자열 가능한 객체들에서 큰 숫자 정규형 집합 누적."""
    out: set[str] = set()
    for s in strings:
        out |= extract_big_numbers(str(s or ""))
    return out


def numbers_from_tool_results(tool_results: object) -> set[str]:
    """tool_results dict list 의 ``result`` 필드에서 큰 숫자 집합 추출.

    validator/number_guard 양쪽이 같은 입력 구조(``[{"tool":..., "result": ...}]``)
    를 처리하므로 SSOT 단일 진입점. dict 가 아닌 항목은 조용히 skip.
    """
    items = tool_results if isinstance(tool_results, (list, tuple)) else []
    return numbers_from_strings(
        t.get("result") for t in items if isinstance(t, dict)
    )


def numbers_from_evidence_chunks(chunks: object) -> set[str]:
    """evidence chunks (``[{"text": ..., ...}]``) 본문에서 큰 숫자 집합 추출."""
    items = chunks if isinstance(chunks, (list, tuple)) else []
    return numbers_from_strings(
        ch.get("text") for ch in items if isinstance(ch, dict)
    )


def collect_numbers_from_state(state: object) -> set[str]:
    """state 의 tool_results + evidence_chunks 합집합 — 환각 가드 ground truth.

    validator 의 ``hallucinated_numbers`` 검사와 number_guard 의
    ``collect_approved_numbers`` 가 동일한 합집합을 쓰므로 양쪽 호출이
    이 함수를 거치도록 한다.
    """
    if not isinstance(state, dict):
        return set()
    return (
        numbers_from_tool_results(state.get("tool_results") or [])
        | numbers_from_evidence_chunks(state.get("evidence_chunks") or [])
    )


__all__ = [
    "BIG_NUMBER_RE",
    "normalize_number",
    "extract_big_numbers",
    "numbers_from_strings",
    "numbers_from_tool_results",
    "numbers_from_evidence_chunks",
    "collect_numbers_from_state",
]
