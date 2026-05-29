"""프롬프트 인젝션 1차 방어 (흡수: _legacy/v1/src/agent/prompt_safety.py).

PRD §7.5.11 — 의심 패턴 탐지 + XML 경계 escape.

방어 전략:
    1. 사용자 입력은 XML 경계 태그(`<user_question>...</user_question>`)로 감싸 LLM 에
       데이터 영역임을 명시한다 (synthesizer prompt 에서).
    2. 본문에 `</user_question>` 가 들어오면 태그 위조로 탈출 가능 → `escape_for_xml_tag`
       가 `<`/`>`/`</tag>` 패턴을 안전한 대체 문자로 치환.
    3. `## system:` / "이전 지시 무시" 같은 메타 헤더 위장 — 신호 감지해 telemetry 에 기록.

엄격한 삭제보다 **escape + 경고 + 신호 표면화** 정책이다. 실제 차단 여부는
호출부(에이전트 nodes)가 결정.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# 닫힘 태그 — "</tag>" 형태는 치환 (경계 혼란 방지)
_TAG_CLOSE_RE = re.compile(r"</\s*([A-Za-z_][A-Za-z0-9_-]*)\s*>")

# 프롬프트 탈취 시도에서 자주 나타나는 메타 문구.
# 각 항목: (pattern, high_risk).
# - high_risk=True  → 단발 매칭만으로도 입력 거부 (triage 가 aborted_reason 설정)
# - high_risk=False → 텔레메트리 / 경고 로그만, 정상 흐름 통과
# "system prompt 비교는?" / "you are now in plan mode 라는 옵션은 뭐죠?" 같은 정상
# 질문을 차단하지 않기 위해 high_risk 는 보수적으로 선별 — ChatML 토큰처럼
# 일반 입력에 등장할 이유가 없는 패턴 또는 "ignore previous instructions" 처럼
# 의도가 분명한 패턴만.
_INJECTION_RULES: tuple[tuple[str, bool], ...] = (
    (r"이전\s*지시.*?무시",                                   True),
    (r"앞의\s*지시.*?무시",                                   True),
    (r"ignore\s+previous\s+(?:instructions|prompt)",          True),
    (r"disregard\s+(?:all|previous)",                         True),
    (r"<\s*\|\s*im_start\s*\|\s*>",                           True),
    (r"<\s*\|\s*im_end\s*\|\s*>",                             True),
    (r"\bjailbreak\b",                                        True),
    (r"###\s*system",                                         False),
    (r"##\s*instructions?\s*##",                              False),
    (r"너는\s*이제",                                          False),
    (r"you\s+are\s+now",                                      False),
    (r"system\s*prompt",                                      False),
    (r"reveal\s+your\s+prompt",                               False),
)

_INJECTION_PATTERNS: tuple[str, ...] = tuple(p for p, _ in _INJECTION_RULES)
_HIGH_RISK_PATTERNS: tuple[str, ...] = tuple(p for p, hr in _INJECTION_RULES if hr)
# SSOT 단일 rule 테이블에서 두 정규식 파생 — high_risk 가 injection 의 subset 임이
# 구조적으로 보장된다 (drift 차단). 한쪽 패턴만 바꾸는 실수 방지.
assert set(_HIGH_RISK_PATTERNS) <= set(_INJECTION_PATTERNS), (
    "_HIGH_RISK_PATTERNS must be a subset of _INJECTION_PATTERNS"
)

_INJECTION_SIGNAL_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)
_HIGH_RISK_RE = re.compile("|".join(_HIGH_RISK_PATTERNS), re.IGNORECASE)


def escape_for_xml_tag(text: str) -> str:
    """XML 경계 태그 안에 들어가는 값에서 닫힘 태그·제어문자를 무력화.

    * `</foo>` → `<\\/foo>`
    * null byte / control char 제거 (탭·개행·캐리지리턴은 유지)
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    text = "".join(ch for ch in text if ch in ("\t", "\n", "\r") or 0x20 <= ord(ch) < 0x10000)
    text = _TAG_CLOSE_RE.sub(r"<\\/\1>", text)
    return text


def detect_injection_signals(text: str) -> list[str]:
    """프롬프트 인젝션 의심 신호 반환. 빈 리스트면 clean."""
    if not isinstance(text, str) or not text:
        return []
    return [m.group(0) for m in _INJECTION_SIGNAL_RE.finditer(text)]


def is_high_risk_injection(text: str) -> bool:
    """high-confidence injection 패턴이 단발이라도 매칭되면 True.

    호출부(triage_node 등)는 이 결과를 보고 입력을 거부 (``aborted_reason``
    설정) 할 수 있다. low-confidence 신호 (``system prompt``, ``you are now``
    등) 는 정상 질문에도 등장 가능 → ``detect_injection_signals`` 만으로
    텔레메트리에 남긴다.
    """
    if not isinstance(text, str) or not text:
        return False
    return bool(_HIGH_RISK_RE.search(text))


def sanitize_user_input(text: str, *, context: str = "user_input") -> tuple[str, list[str]]:
    """사용자 입력 공통 전처리. (escape 된 텍스트, 감지된 신호 목록) 반환.

    저신뢰 신호는 경고 로그만, 고신뢰 신호 검출은 호출부(``triage_node``)가
    ``is_high_risk_injection`` 으로 판정 후 ``aborted_reason='prompt_injection'``
    으로 차단한다.
    """
    signals = detect_injection_signals(text)
    if signals:
        logger.warning(
            "prompt-injection signals (%s): %s",
            context, sorted({s.lower()[:40] for s in signals}),
        )
    return escape_for_xml_tag(text), signals


__all__ = [
    "escape_for_xml_tag",
    "detect_injection_signals",
    "is_high_risk_injection",
    "sanitize_user_input",
]
