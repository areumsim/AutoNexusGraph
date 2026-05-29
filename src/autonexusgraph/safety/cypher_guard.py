"""Cypher 정적 가드 (흡수: _legacy/v1/src/agent/cypher_guard.py).

PRD §7.5.9 — 자유 Cypher 생성 금지, 템플릿 + 파라미터만 허용.
LLM 이 만든 Cypher 라도 실행 직전 정적 검사로 쓰기/위험 CALL 차단.

가드 정책 (READ-ONLY 강제):
    * 쓰기 키워드: CREATE / MERGE / DELETE / DETACH / SET / REMOVE / LOAD CSV / DROP
    * 위험 CALL — 쓰기/스키마/관리 procedure:
      - apoc.periodic.*, apoc.trigger.*, apoc.export.*, apoc.import.*, apoc.load.*
      - apoc.refactor.*  (관계/노드 재배치 — 실제 write)
      - apoc.merge.*     (노드/관계 생성)
      - apoc.create.*    (createUUIDs 같은 read-only 도 있으나 보수적으로 차단)
      - apoc.atomic.*    (atomic.add / subtract — 속성 in-place 갱신)
      - apoc.cypher.*    (run / runWrite / doIt — 임의 Cypher 동적 실행 = 가드 우회)
      - apoc.lock.*      (트랜잭션 lock 획득 — read 흐름과 무관)
      - apoc.schema.*    (assert / drop — 스키마 변경)
      - apoc.nodes.link / connect / delete / collapse
      - apoc.do.*        (절차 안에서 쓰기 호출 가능)
      - dbms.security.*, gds.graph.* (관리/스키마)
      - db.index.fulltext.{createNodeIndex|createRelationshipIndex|drop}
      - db.create{Label|Index|Property|RelationshipType}
      camelCase procedure (mergeNodes 등) 는 word boundary 가 쓰기 키워드 정규식을
      비활성화하므로 procedure 패턴 매칭이 마지막 방어선이다.
    * 라인/블록 주석 안에 숨긴 키워드도 검사 (주석 제거 후 탐색)
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


_WRITE_KEYWORDS_RE = re.compile(
    r"\b(?:CREATE|MERGE|DELETE|DETACH|SET|REMOVE|LOAD\s+CSV|DROP)\b",
    re.IGNORECASE,
)

# read-only CALL (CALL db.index.fulltext.queryNodes 등) 은 허용.
# camelCase procedure 이름은 \b(CREATE|MERGE|...) 키워드 정규식이 잡지 못하므로
# 여기서 procedure namespace 별로 명시 차단해야 한다 (예: apoc.refactor.mergeNodes).
_DANGEROUS_CALL_RE = re.compile(
    r"\bCALL\s+("
    r"apoc\.(?:periodic|trigger|export|import|load|refactor|merge|create|do"
    r"|atomic|cypher|lock|schema)\."
    r"|apoc\.nodes\.(?:link|connect|delete|collapse)\b"
    r"|dbms\.security\."
    r"|gds\.graph\."
    r"|db\.index\.fulltext\.(?:createNodeIndex|createRelationshipIndex|createRelationshipTypeIndex|drop)"
    r"|db\.create(?:Label|Index|Property|RelationshipType)\b"
    r")",
    re.IGNORECASE,
)

_LINE_COMMENT_RE = re.compile(r"//[^\n]*", re.MULTILINE)
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


class CypherGuardError(ValueError):
    """Cypher 정적 가드 실패."""


def _strip_comments(query: str) -> str:
    return _BLOCK_COMMENT_RE.sub("", _LINE_COMMENT_RE.sub("", query))


def assert_read_only(query: str) -> None:
    """쓰기 키워드·위험 CALL 가 없음을 보장. 위반 시 CypherGuardError.

    문자열 리터럴 안의 단어도 탐지될 수 있으나 보수적 운영을 위해 과탐 감수.
    LLM 프롬프트에 명시된 키워드는 답변에만 존재, Cypher 에는 없어야 정상.
    """
    if not isinstance(query, str) or not query.strip():
        raise CypherGuardError("빈 Cypher 쿼리")
    stripped = _strip_comments(query)
    m = _WRITE_KEYWORDS_RE.search(stripped)
    if m:
        raise CypherGuardError(f"쓰기 키워드 금지: '{m.group(0)}'")
    m = _DANGEROUS_CALL_RE.search(stripped)
    if m:
        raise CypherGuardError(f"위험 CALL 금지: '{m.group(0).strip()}'")


def extract_bind_params(query: str) -> set[str]:
    """쿼리에서 `$param` 형태의 바인드 파라미터 이름 수집."""
    if not isinstance(query, str):
        return set()
    return set(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", query))


def assert_templates_params_match(
    scenario: str,
    cypher: str,
    required_params: list[str],
    provided_params: dict[str, object] | None,
) -> None:
    """템플릿 실행 전 바인드 파라미터 이름 정확 일치 검증.

    * 필수 파라미터가 provided 에 없으면 실패.
    * cypher 가 참조하는 $name 이 provided 에 없으면 실패.
    """
    provided = dict(provided_params or {})
    required = set(required_params or [])
    missing_required = sorted(required - set(provided))
    if missing_required:
        raise CypherGuardError(
            f"{scenario} 필수 파라미터 누락: {missing_required}"
        )

    bind = extract_bind_params(cypher)
    missing_bind = sorted(bind - set(provided))
    if missing_bind:
        raise CypherGuardError(
            f"{scenario} 바인드 파라미터 누락: {missing_bind} (cypher 내 $name)"
        )


__all__ = [
    "CypherGuardError",
    "assert_read_only",
    "extract_bind_params",
    "assert_templates_params_match",
]
