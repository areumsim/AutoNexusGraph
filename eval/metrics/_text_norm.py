"""한국어 + 영문 혼합 평가 텍스트의 정규화 / 토큰화 헬퍼.

설계:
- 외부 의존성 없이 stdlib 만 사용 (mecab/kkma 미사용 — 평가 가벼움).
- 한국어 토큰화는 (a) 공백 split + (b) 한글 char-bigram 의 합집합.
- EM 비교용 normalize 와 F1/Faithfulness 용 tokenize 두 함수.
"""

from __future__ import annotations

import re
import unicodedata


_PUNCT_RE = re.compile(r"[\s　 \.,;:!\?\(\)\[\]\{\}<>\"'`~/\\|@#\$%\^&\*_\-+=]+")


def normalize_text(s: str) -> str:
    """NFKC + 공백/구두점 제거 + 소문자. EM / Hits@k entity 매칭용."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = _PUNCT_RE.sub("", s)
    return s.lower()


def _has_hangul(s: str) -> bool:
    """Hangul Syllables block U+AC00(가) ~ U+D7A3(힣) 포함 여부."""
    return any("가" <= ch <= "힣" for ch in s)


def tokenize(s: str) -> list[str]:
    """token-F1 / faithfulness 용 토큰화.

    - 공백 단위 split (영어 단어)
    - 한글 3글자 이상 단어는 whole word + char-bigram 까지
      (예: "코오롱" → ["코오롱", "코오", "오롱"])
    - 한글 1~2글자는 whole word 만 (2글자는 유일 bigram = whole word 중복)
    """
    if not s:
        return []
    norm = unicodedata.normalize("NFKC", s).lower()
    tokens: list[str] = []
    for w in norm.split():
        w = _PUNCT_RE.sub("", w)
        if not w:
            continue
        tokens.append(w)
        if _has_hangul(w) and len(w) > 2:
            for i in range(len(w) - 1):
                tokens.append(w[i : i + 2])
    return tokens
