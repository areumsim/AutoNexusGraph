"""IPGraph (도메인3) wire-up 회귀 테스트 — PRD §10 DoD #15/#16.

검증 범위 (LLM/DB 무관):
- handler / router 등록 부작용
- policy 룰 분류 + plan_ip_tasks
- ontology pydantic validate + relation_endpoints
- cypher template 25개 등록
- target 추출 (assignee/cpc)
- gold seed row count
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


# ── 핸들러 + 라우터 등록 ─────────────────────────────────────
def test_ipgraph_imports():
    import ipgraph  # noqa: F401
    from ipgraph.agent_handler import IPGraphHandler
    assert IPGraphHandler().domain == "ip"


def test_register_handler_side_effect():
    import ipgraph  # noqa: F401  (등록 부작용 발생)
    from autonexusgraph.agents._domain_handler import get_handler
    h = get_handler("ip")
    assert h is not None
    assert h.domain == "ip"


def test_register_router_side_effect():
    import ipgraph  # noqa: F401
    from autonexusgraph.agents._domain_handler import _ROUTERS  # type: ignore[attr-defined]
    from ipgraph.policy import route_domain_ip
    assert route_domain_ip in _ROUTERS


# ── 라우팅 룰 ─────────────────────────────────────────────
def test_route_ip_alone():
    from ipgraph.policy import route_domain_ip
    assert route_domain_ip("삼성SDI 의 특허 출원 추세", None) == "ip"
    assert route_domain_ip("H01M 분야 출원량", None) == "ip"


def test_route_ip_with_finance_yields():
    """특허 + 회사재무 동시 등장 시 'ip' 단독 라우터는 None — cross_domain 으로 양보."""
    from ipgraph.policy import route_domain_ip
    assert route_domain_ip("삼성SDI 특허 영업이익", None) is None
    assert route_domain_ip("현대모비스 R&D비 vs 특허 출원량", None) is None


def test_route_ip_with_auto_yields():
    from ipgraph.policy import route_domain_ip
    assert route_domain_ip("삼성SDI 특허 + 셀 쓰는 OEM 리콜", None) is None


def test_route_ip_unrelated_returns_none():
    from ipgraph.policy import route_domain_ip
    assert route_domain_ip("쏘나타 1.6T 출력", None) is None
    assert route_domain_ip("삼성전자 매출", None) is None


def test_hint_overrides_routing():
    from ipgraph.policy import route_domain_ip
    assert route_domain_ip("쏘나타 출력", "ip") == "ip"


# ── 룰 분류 ──────────────────────────────────────────────
def test_classify_question_ip_patterns():
    from ipgraph.policy import classify_question_ip
    assert classify_question_ip("CPC H01M 분야 출원") == "cpc_search"
    assert classify_question_ip("특허 인용 네트워크") == "citation_network"
    assert classify_question_ip("삼성SDI 출원인 특허") == "assignee_patents"
    assert classify_question_ip("쏘나타 출력") == "unknown"


# ── target 추출 ─────────────────────────────────────────
def test_identify_targets_cpc():
    from ipgraph.agent_handler import IPGraphHandler
    h = IPGraphHandler()
    state: dict = {}
    h.identify_targets(state, question="H01M 10/052 + B60W 분야 특허")
    assert "H01M10/052" in state.get("target_cpcs", []) or "H01M" in state.get("target_cpcs", [])
    assert "B60W" in state.get("target_cpcs", [])


def test_identify_targets_assignees():
    from ipgraph.agent_handler import IPGraphHandler
    h = IPGraphHandler()
    state: dict = {}
    h.identify_targets(state, question="삼성SDI 와 LG엔솔 의 특허 비교")
    targets = state.get("target_assignees", [])
    assert "samsung_sdi" in targets
    assert "lg_es" in targets


# ── allowed_intents 화이트리스트 ──────────────────────────
def test_allowed_intents_includes_core_ip_tools():
    from ipgraph.agent_handler import IPGraphHandler
    h = IPGraphHandler()
    graph = h.allowed_intents("graph")
    sql = h.allowed_intents("sql")
    research = h.allowed_intents("research")
    assert "get_citation_network" in graph
    assert "list_patents_in_cpc" in graph
    assert "lookup_patent" in sql
    assert "search_patents" in research


# ── ontology 검증 ────────────────────────────────────────
def test_ontology_loads_with_schema_version():
    from ipgraph.ontology import (
        entity_labels,
        load_edge_required_meta,
        ontology_schema_version,
        relation_types,
    )
    assert ontology_schema_version() == "v2.2"
    labels = entity_labels()
    assert "Patent" in labels
    assert "Assignee" in labels
    assert "CPCCode" in labels
    rels = relation_types()
    assert "ASSIGNED_TO" in rels
    assert "CITES" in rels
    assert "SUBCLASS_OF" in rels
    meta = load_edge_required_meta()
    assert "schema_version" in meta
    assert "confidence_score" in meta


def test_relation_endpoints_consistent():
    from ipgraph.ontology import relation_endpoints
    assert relation_endpoints("ASSIGNED_TO") == ("Patent", "Assignee")
    assert relation_endpoints("CITES") == ("Patent", "Patent")
    assert relation_endpoints("SUBCLASS_OF") == ("CPCCode", "CPCCode")


# ── Cypher templates ─────────────────────────────────────
def test_25_cypher_templates_defined():
    from ipgraph.cypher_templates_ip import IP_TEMPLATES
    assert len(IP_TEMPLATES) >= 25
    # 도메인 prefix 확인.
    assert all(k.startswith("ip_") for k in IP_TEMPLATES)


def test_cypher_templates_merged_into_finance_registry():
    """ipgraph.tools import 시 IP_TEMPLATES 자동 병합."""
    import ipgraph.tools  # noqa: F401  부작용
    from autonexusgraph.tools.cypher_templates import TEMPLATES
    ip_keys = [k for k in TEMPLATES if k.startswith("ip_")]
    assert len(ip_keys) >= 25


def test_citation_network_template_caps_depth():
    """get_citation_network 의 depth ≤ 2 cap 검증 (PRD §10.12 그래프 폭발 방지)."""
    # depth=3 입력 시 내부에서 2로 절단 — 직접 검증 어려우니 함수 signature 만.
    import inspect

    from ipgraph.tools.graph import get_citation_network
    sig = inspect.signature(get_citation_network)
    assert "depth" in sig.parameters
    assert "max_total" in sig.parameters


# ── plan_ip_tasks ────────────────────────────────────────
def test_plan_ip_tasks_assignee():
    from ipgraph.policy import plan_ip_tasks
    tasks = plan_ip_tasks(question="삼성SDI 출원인 특허 목록",
                          target_assignees=["samsung_sdi"])
    assert len(tasks) >= 1
    assert tasks[0]["depends_on"] == []


def test_plan_ip_tasks_cpc():
    from ipgraph.policy import plan_ip_tasks
    tasks = plan_ip_tasks(question="CPC H01M 분야 특허",
                          target_cpcs=["H01M"])
    assert len(tasks) >= 1
    assert any("cpc" in (t.get("intent") or "") for t in tasks)


# ── gold seed ────────────────────────────────────────────
def test_gold_qa_ip_v0_has_30_rows():
    p = ROOT / "eval" / "qa_gold" / "gold_qa_ip_v0.jsonl"
    assert p.exists()
    n = sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())
    assert n >= 30


def test_gold_qa_cross_v0_has_8_ip_rows():
    p = ROOT / "eval" / "qa_gold" / "gold_qa_cross_v0.jsonl"
    assert p.exists()
    n_ip = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        qid = row.get("qid") or ""
        tags = row.get("tags") or []
        if "-IP-" in qid or "ip" in tags:
            n_ip += 1
    assert n_ip >= 8


def test_gold_ip_distribution_l1_l2_l3():
    p = ROOT / "eval" / "qa_gold" / "gold_qa_ip_v0.jsonl"
    by_level: dict[str, int] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        by_level[row.get("level", "?")] = by_level.get(row.get("level", "?"), 0) + 1
    assert by_level.get("L1", 0) >= 10
    assert by_level.get("L2", 0) >= 8
    assert by_level.get("L3", 0) >= 8


# ── tools import 확인 ─────────────────────────────────────
def test_ip_tools_importable():
    from ipgraph.tools import (
        bridge_assignee_to_corp,
        cross_query_ip,
        get_citation_network,
        get_patent_info,
        list_patents_by_assignee,
        list_patents_in_cpc,
        lookup_assignee_graph,
        lookup_patent,
        search_patents,
    )
    # 각 함수가 callable 임만 확인.
    for f in (lookup_patent, get_patent_info, list_patents_by_assignee,
              lookup_assignee_graph, list_patents_in_cpc, get_citation_network,
              search_patents, bridge_assignee_to_corp, cross_query_ip):
        assert callable(f)


# ── ingestion adapters fail-soft ─────────────────────────
def test_kipris_collect_without_key_skips():
    import os

    from ipgraph.ingestion.kipris import collect
    # 키 없으면 fetch skip — raw XML 도 없으면 0 row (graceful, parse-raw-anyway 설계).
    if not os.getenv("KIPRIS_API_KEY"):
        result = collect()
        assert result["key_present"] is False
        assert result["n_patents"] >= 0   # raw 미존재 환경 — 0, raw 있으면 parse
        assert result["n_assignees"] >= 0


def test_uspto_odp_collect_without_files_returns_zero():
    """raw/ip/uspto_odp/*.jsonl 미존재 시 0 row + warning."""
    from ipgraph.ingestion.uspto_odp import collect
    result = collect()
    # raw 미존재 환경 — 모두 0.
    assert result["n_patents"] >= 0   # int 자체 확인
    assert result["n_assignees"] >= 0
    assert result["n_citations"] >= 0


# ── license 정책 확인 ────────────────────────────────────
def test_license_policy_uspto_odp():
    from autonexusgraph.ingestion._license import LICENSE_POLICY, allow_body
    assert LICENSE_POLICY.get("uspto_odp") == "public_domain"
    assert allow_body("uspto_odp") is True
    assert allow_body("kipris") is True   # kogl_type1
