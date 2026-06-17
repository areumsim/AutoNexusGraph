"""도메인 횡단 Neo4j 적재 헬퍼 — 7키 엣지 메타 SET 절 + 배치 실행 SSOT.

finance/auto/ip 가 공유하는 "진짜 공통" 만 둔다. **도메인 의존(ontology) 0** —
``meta_keys`` 와 ``schema_version`` 을 인자로 받아 호출자가 자기 도메인 ontology 에서
주입한다. 도메인별 thin 어댑터(예: ``autograph.loaders._neo4j_helpers.edge_meta_cypher``)
가 자기 도메인 헤더를 바인딩해 호출.

배경(왜 common 으로 올렸나): 이전엔 본 로직이 ``autograph.loaders._neo4j_helpers`` 에만
있어 ``ipgraph`` 로더가 **타 도메인 private 모듈을 cross-import** 했고, 그 결과 ip 엣지가
schema_version 누락 시 **auto 헤더 값을 fallback** 으로 받고 EDGE_META_KEYS 도 auto 것을
쓰는 latent 결함이 있었다(현재는 두 도메인이 같은 v2.2/7키라 미관측). 본 모듈로 분리해
각 도메인이 자기 ontology 를 주입하도록 정합화.

본 모듈은 DB·ontology·neo4j 드라이버 의존 0 — pure helper (session 은 인자로 주입).
"""

from __future__ import annotations

from collections.abc import Sequence


def edge_meta_cypher(
    meta_keys: Sequence[str], schema_version: str, rel_var: str = "r",
) -> str:
    """의무 메타(``meta_keys``)를 한 줄 SET 절로 — ``UNWIND $rows AS r`` 가정.

    각 row dict 는 ``meta_keys`` 를 모두 포함해야 한다. ``snapshot_year`` 와
    ``schema_version`` 만 누락 시 coalesce 로 보강 (year=현재, schema_version=호출
    도메인 헤더). schema_version fallback 은 **호출자가 주입한 도메인 값** —
    cross-domain 오염 없음.
    """
    pieces: list[str] = []
    for key in meta_keys:
        if key == "snapshot_year":
            pieces.append(f"{rel_var}.{key} = coalesce(r.{key}, date().year)")
        elif key == "schema_version":
            pieces.append(f"{rel_var}.{key} = coalesce(r.{key}, '{schema_version}')")
        else:
            pieces.append(f"{rel_var}.{key} = r.{key}")
    return ",\n      ".join(pieces)


def run_batched(session, cypher: str, rows: Sequence[dict], batch: int = 500) -> int:
    """``session.run(cypher, rows=chunk)`` 를 ``batch`` 단위로 반복.

    rows 가 비어 있으면 0 반환. cypher 는 ``UNWIND $rows AS r`` 로 시작 가정.
    """
    if not rows:
        return 0
    n = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        if not chunk:
            continue
        session.run(cypher, rows=chunk)
        n += len(chunk)
    return n


__all__ = ["edge_meta_cypher", "run_batched"]
