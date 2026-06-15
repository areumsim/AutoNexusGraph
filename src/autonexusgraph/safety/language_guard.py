"""답변 언어 강제 가드 (흡수: _legacy/v1/src/agent/language_guard.py).

원칙: 모든 최종 답변은 한국어. 고유명사 (DART, GLEIF 등) 원문은 허용하되,
본문·해석·설명은 한국어여야 한다. LLM 이 영어로 응답하거나 한영 혼용으로
응답한 경우 감지 → 재시도 신호.

판정: 측정 대상 문자 = 한글 + 라틴 알파벳. 한글 비율이
FINGRAPH_MIN_KOREAN_RATIO (기본 0.30) 미만이면 fail.
"""

from __future__ import annotations

import os

_MIN_KOREAN_RATIO = float(os.getenv("FINGRAPH_MIN_KOREAN_RATIO", "0.30"))
_MIN_MEASURED_CHARS = int(os.getenv("FINGRAPH_MIN_LANG_CHARS", "20"))


def _strip_terms(text: str, ignore_terms: object) -> str:
    """데이터 유래 고유명(외래 entity 명 등)을 본문에서 제거 — 언어 판정 전처리.

    docstring 원칙("고유명사 원문은 허용, 본문·해석은 한국어") 구현: tool 결과에서
    인용된 외래 고유명(예: 'F-150', 'Transit Connect')을 denom 에서 빼, 에이전트의
    *서술* 자체가 한국어인지를 측정한다. ignore_terms 미지정이면 원문 그대로.
    """
    if not ignore_terms:
        return text
    out = text
    # 긴 항목부터 제거 — 'Transit Connect' 가 'Transit' 보다 먼저 빠지도록.
    for term in sorted({str(t) for t in ignore_terms if t}, key=len, reverse=True):
        if len(term) >= 2:
            out = out.replace(term, " ")
    return out


def korean_char_ratio(text: str, *, ignore_terms: object = None) -> tuple[float, int]:
    """한글 비율 + 측정에 쓰인 유의미 문자 수 반환.

    유의미 문자 = 한글 + 라틴 알파벳. (한글)/(한글+라틴).
    숫자/공백/구두점 제외. ignore_terms (데이터 유래 고유명) 는 측정 전 제거.
    """
    if not text:
        return 1.0, 0
    measured = _strip_terms(text, ignore_terms)
    hangul = sum(1 for ch in measured if "가" <= ch <= "힣")
    latin = sum(1 for ch in measured if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    denom = hangul + latin
    if denom == 0:
        return 1.0, 0
    return hangul / denom, denom


def check_korean(text: str, *, ignore_terms: object = None) -> tuple[bool, float]:
    """답변이 한국어 위주인지. (ok, ratio) 반환.

    측정 문자 수가 너무 적으면 통계적으로 판정 불가 → ok=True (보류).
    ignore_terms 지정 시 데이터 유래 고유명을 제외하고 *서술* 의 한국어 비율 측정
    (외래 entity 명 다수 나열 답변의 오탐 방지 — 모듈 docstring 의 '고유명사 허용' 구현).
    """
    ratio, denom = korean_char_ratio(text or "", ignore_terms=ignore_terms)
    if denom < _MIN_MEASURED_CHARS:
        return True, ratio
    return (ratio >= _MIN_KOREAN_RATIO), ratio


__all__ = ["korean_char_ratio", "check_korean"]
