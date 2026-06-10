"""Pre-synth number guard — PRD §7.3 "재무 수치는 절대 LLM 이 생성하지 않는다".

Synthesizer 가 LLM 에 보내는 context 안에서 큰 숫자를 **출처와 함께 명시적으로 라벨링**
하고, evidence 본문에 등장한 숫자 외에는 prompt 에 노출되지 않도록 정리한다.
Validator 가 post-hoc 으로 잡지만, 이 guard 는 LLM 이 잘못된 숫자를 답변에 옮기는
근본 입력을 차단한다.

전략:
1. tool_results 의 큰 숫자를 모두 수집 → ``approved_numbers`` 화이트리스트
2. evidence chunks 의 본문에서도 추출 → 동일 화이트리스트 누적
3. system prompt 에 "다음 숫자만 인용 가능: …" 형태로 명시 (10개 cap)
4. evidence text 에서 큰 숫자를 ``[수치:<n>]`` 로 마킹 (LLM 이 인지 쉽게)
5. 미승인 숫자는 evidence text 안에서 ``[검증불가:NUM]`` 으로 치환 → LLM 이 사용 안 하게 유도

큰 숫자 정규식은 ``_number_patterns.BIG_NUMBER_RE`` (SSOT) 를 그대로 사용. validator
도 같은 모듈을 import — pre/post 가드가 어긋나지 않는다.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

from ._number_patterns import BIG_NUMBER_RE, collect_numbers_from_state, normalize_number

log = logging.getLogger(__name__)

# 외부(tests/) 호환을 위해 alias 유지. SSOT 는 ``_number_patterns`` 모듈.
_BIG_NUMBER_RE = BIG_NUMBER_RE


def _normalize(num: str) -> str:
    """콤마 제거된 정규형 — backward-compat shim."""
    return normalize_number(num)


def _format_with_commas(n: str) -> str:
    """비교 표시용 — int 면 천 단위 콤마."""
    s = _normalize(n)
    if not s.isdigit():
        return n
    try:
        return f"{int(s):,}"
    except ValueError:
        return n


def collect_approved_numbers(state: Mapping[str, Any]) -> set[str]:
    """tool_results + evidence_chunks 에 등장한 큰 숫자(정규형) 수집.

    SSOT 헬퍼 ``_number_patterns.collect_numbers_from_state`` 를 거치므로
    validator 의 ``hallucinated_numbers`` 검사와 정확히 같은 집합을 반환한다.
    """
    return collect_numbers_from_state(state)


def sanitize_evidence_for_synth(
    evidence_chunks: list[dict] | tuple[dict, ...],
    approved: set[str],
    *,
    cap: int = 6,
    text_max: int = 400,
) -> list[dict]:
    """evidence chunks 의 본문에서 미승인 숫자를 [검증불가:NUM] 으로 치환.

    원본 chunks 는 건드리지 않고 새 list 반환. cap / text_max 는 synthesizer
    가 컨텍스트에 사용하는 값과 동일.
    """
    out: list[dict] = []
    for ch in (evidence_chunks or [])[:cap]:
        if not isinstance(ch, dict):
            continue
        text = str(ch.get("text") or "")[:text_max]

        def _repl(m: re.Match[str]) -> str:
            n = _normalize(m.group(0))
            if n in approved:
                return f"[수치:{m.group(0)}]"
            return f"[검증불가:{m.group(0)}]"

        new_text = _BIG_NUMBER_RE.sub(_repl, text)
        new_ch = dict(ch)
        new_ch["text"] = new_text
        out.append(new_ch)
    return out


def format_approved_for_prompt(approved: set[str], *, limit: int = 10) -> str:
    """system prompt 에 박을 화이트리스트 한 줄.

    너무 많으면 limit 만 노출하고 '외 N개' 로 표시.
    """
    if not approved:
        return "(이번 답변에서 인용 가능한 정량 수치 없음 — 수치 인용 금지)"
    sorted_nums = sorted(approved, key=lambda x: (len(x), x))
    head = sorted_nums[:limit]
    formatted = ", ".join(_format_with_commas(n) for n in head)
    extra = len(sorted_nums) - len(head)
    if extra > 0:
        formatted += f", 외 {extra}개"
    return formatted


__all__ = [
    "collect_approved_numbers",
    "sanitize_evidence_for_synth",
    "format_approved_for_prompt",
]
