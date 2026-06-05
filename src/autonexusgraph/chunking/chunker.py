"""문자 기반 슬라이딩 윈도우 청커.

한국어는 토크나이저 의존성이 크므로 처음엔 char 기반으로 단순화.
BGE-M3 의 토큰 한도 8K → char 약 4,000 (한국어 ~2자/토큰) 이지만
검색 품질·context 효율 위해 700~1000자 청크 권장.

설계:
- 길이 기준 청크 + overlap
- 문장 경계(. ! ? 또는 줄바꿈) 에서 우선 자르기

토큰 추정:
- ``estimate_tokens(text)`` 가 단일 진실의 원천. 본 모듈 + ``loaders/chunks.py`` +
  ``autograph/loaders/build_chunks_auto.py`` 모두 이 함수를 사용 (과거 //2 vs //4
  의 불일치 해소).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# BGE-M3 (XLM-R BPE) 의 char/token 비율은 한국어 ~2, 영어 ~4, 한영혼합 비즈니스
# 문서 ~3 정도. 단일 휴리스틱은 한영 혼합 기준의 ``//3`` 이 가장 균형 잡힘.
# 정확한 토큰 카운트가 필요하면 transformers.AutoTokenizer('BAAI/bge-m3') 사용.
_CHARS_PER_TOKEN = 3


def estimate_tokens(text: str) -> int:
    """문자 길이 기반 BGE-M3 토큰 추정 (한영 혼합 기준).

    공통 휴리스틱으로 src/autonexusgraph/chunking + src/autonexusgraph/loaders/chunks
    + src/autograph/loaders/build_chunks_auto 가 동일 값을 산출.
    """
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


@dataclass(frozen=True)
class Chunk:
    """단일 청크."""

    idx: int               # 섹션 내 순번 (0부터)
    text: str
    char_count: int
    token_est: int         # estimate_tokens() 결과 — 한영 혼합 기준 char//3
    section_title: str | None = None


# 문장 경계 — 한국어/영어 공통
_SENT_BREAK = re.compile(r"([\.!?。](?:\s|$)|\n\n+)")


def _split_sentences(text: str) -> list[str]:
    """문장 단위로 자르기. 표 행 등은 그대로 한 단위."""
    parts: list[str] = []
    last = 0
    for m in _SENT_BREAK.finditer(text):
        end = m.end()
        parts.append(text[last:end])
        last = end
    if last < len(text):
        parts.append(text[last:])
    return [p.strip() for p in parts if p.strip()]


def chunk_text(
    text: str,
    *,
    target_chars: int = 800,
    overlap_chars: int = 100,
    section_title: str | None = None,
) -> list[Chunk]:
    """텍스트 → 청크 리스트.

    Args:
        target_chars: 청크 목표 길이 (문자). 700~1000 권장.
        overlap_chars: 인접 청크 중복 (검색 누락 방지).
    """
    if not text or not text.strip():
        return []

    sentences = _split_sentences(text)
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0

    for sent in sentences:
        if buf and buf_len + len(sent) > target_chars:
            chunks.append("".join(buf).strip())
            # overlap — 뒤쪽 N자 유지하고 새 청크 시작
            if overlap_chars > 0 and buf:
                tail = "".join(buf)[-overlap_chars:]
                buf = [tail]
                buf_len = len(tail)
            else:
                buf = []
                buf_len = 0
        # 한 문장이 target 보다 길면 통째로 한 청크
        if len(sent) > target_chars and not buf:
            chunks.append(sent[:target_chars * 2])    # 안전 상한
            continue
        buf.append(sent)
        buf_len += len(sent)
    if buf:
        chunks.append("".join(buf).strip())

    return [
        Chunk(
            idx=i,
            text=c,
            char_count=len(c),
            token_est=estimate_tokens(c),
            section_title=section_title,
        )
        for i, c in enumerate(chunks)
        if c
    ]
