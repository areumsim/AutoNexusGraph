"""문서 파싱·청킹 모듈 — 원문을 벡터 인덱스(anxg_vec.chunks)용 청크로 변환 (deterministic).

과거 이름 ``extraction/`` — LLM 추출 엔진 ``extractors/`` 와 혼동되어 ``chunking/`` 로 개명.
(extractors/ = LLM 엔티티·관계 추출 / 본 패키지 = 결정적 파싱·청킹.)

dart_parser: DART 사업보고서 zip → 섹션별 텍스트 (결정적 파싱)
chunker:     텍스트 → 청크 (slide window + overlap)
"""

from .chunker import Chunk, chunk_text
from .dart_parser import ParsedSection, parse_dart_zip

__all__ = ["ParsedSection", "parse_dart_zip", "Chunk", "chunk_text"]
