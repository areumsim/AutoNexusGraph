"""common.neo4j_loader SSOT + cross-domain ontology 바인딩 회귀 가드.

배경: 이전엔 edge_meta_cypher/run_batched 가 ``autograph.loaders._neo4j_helpers`` 에만
있어 ``ipgraph`` 로더가 **타 도메인 private 모듈을 cross-import** 했고, ip 엣지가
schema_version 누락 시 **auto 헤더 값을 fallback** 으로 받던 latent 결함이 있었다.
common 으로 제네릭 로직을 분리하고 각 도메인이 자기 ontology(meta keys + schema_version)
를 주입하도록 정합화 — 본 가드가 회귀를 막는다.
"""

from __future__ import annotations

from pathlib import Path

from common.neo4j_loader import edge_meta_cypher, run_batched

ROOT = Path(__file__).resolve().parents[1]


def test_edge_meta_cypher_injects_schema_version() -> None:
    """주입한 schema_version 이 coalesce fallback 으로 — 하드코딩/cross-domain 오염 없음."""
    out = edge_meta_cypher(("source_type", "snapshot_year", "schema_version"),
                           "vTEST", rel_var="edge")
    assert "edge.schema_version = coalesce(r.schema_version, 'vTEST')" in out
    assert "edge.snapshot_year = coalesce(r.snapshot_year, date().year)" in out
    assert "edge.source_type = r.source_type" in out


def test_edge_meta_cypher_domain_versions_isolated() -> None:
    """도메인별 주입 버전이 서로 격리 — auto 와 ip 가 같은 헬퍼로 다른 버전 바인딩."""
    a = edge_meta_cypher(("schema_version",), "vAUTO")
    b = edge_meta_cypher(("schema_version",), "vIP")
    assert "'vAUTO'" in a and "'vIP'" in b and a != b


class _FakeSession:
    def __init__(self) -> None:
        self.chunks: list[int] = []

    def run(self, cypher: str, rows: list[dict]) -> None:  # noqa: ARG002
        self.chunks.append(len(rows))


def test_run_batched_chunks() -> None:
    s = _FakeSession()
    n = run_batched(s, "UNWIND $rows AS r RETURN r",
                    [{"i": i} for i in range(1200)], batch=500)
    assert n == 1200
    assert s.chunks == [500, 500, 200]
    assert run_batched(s, "...", [], batch=500) == 0


def test_ipgraph_no_autograph_private_import() -> None:
    """ipgraph 어느 파일도 autograph private _neo4j_helpers 를 cross-import 하지 않는다."""
    ip_dir = ROOT / "src" / "ipgraph"
    offenders = [
        str(p.relative_to(ROOT))
        for p in ip_dir.rglob("*.py")
        if "autograph.loaders._neo4j_helpers" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, f"ip→auto private cross-import 잔존: {offenders}"


def test_autograph_adapter_api_preserved() -> None:
    """autograph._neo4j_helpers 어댑터가 기존 public API 보존(22 caller 비파괴)."""
    from autograph.loaders import _neo4j_helpers as h

    assert callable(h.edge_meta_cypher) and callable(h.run_batched)
    assert callable(h.default_schema_version)
    assert isinstance(h.EDGE_META_KEYS, tuple) and "schema_version" in h.EDGE_META_KEYS
    out = h.edge_meta_cypher("r")   # 무인자 호출이 auto 헤더로 바인딩
    assert "r.schema_version = coalesce(r.schema_version," in out
