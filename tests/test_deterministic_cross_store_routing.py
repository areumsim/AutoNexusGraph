"""B: 게이트 발화 cross-store 랭킹 결정적 라우팅 — 회귀 가드.

배경: LLM planner 가 compare 힌트를 비결정적으로 따라 동일 게이트에 compare 체인을
빠뜨려 EM 이 0.214↔0.500 으로 흔들리던 결함(CSV 실증). `ANXG_RANK_ROUTE=deterministic`
시 graph→compare_companies 체인을 룰이 직접 구성 → 변동 제거. 본 가드는 plan 구성의
결정성·정합(올바른 intent·$from 바인딩·metric SSOT·year 필수)을 검증한다(LLM/DB 불요).
"""

from __future__ import annotations

import pytest

from autonexusgraph.agents.llm_planner import (
    _deterministic_cross_store_plan,
    _extract_lead_person,
)
from autonexusgraph.agents.policy import rank_route_mode


def _neo4j_up() -> bool:
    try:
        from autonexusgraph.db.neo4j import get_session
        with get_session() as s:
            s.run("RETURN 1").single()
        return True
    except Exception:   # noqa: BLE001 — Neo4j 연결 실패 → DB 없음으로 간주(skip)
        return False


def test_extract_lead_person_strips_dual_josa() -> None:
    """'PERSON이(가) 임원으로…' 선두 인물 추출 — dual-josa 제거 + lookup 검증(Neo4j 필요).

    triage 의 deterministic 추출이 동명이인('김영규' 3명)을 거부해 target_persons 가
    비던 결함을 B-local 추출이 보강(이름만 — get_companies_of_person 가 traverse).
    """
    if not _neo4j_up():
        pytest.skip("Neo4j 부재 — 인물 lookup 불가")
    p = _extract_lead_person("김영규이(가) 임원으로 재직하는 회사 중 매출 1위는?")
    # DB 에 '김영규' 가 있으면 추출, 없으면 None (둘 다 정상 — 핵심은 dual-josa 미오염).
    assert p in ("김영규", None)
    assert p != "김영규이(가)" and p != "김영규이"   # 조사 오염 없음


def test_route_mode_default_deterministic_after_measured_flip(monkeypatch) -> None:
    """default=deterministic — 2026-06-17 실측 비회귀·우위 확인 후 플립(thesis §1)."""
    monkeypatch.delenv("ANXG_RANK_ROUTE", raising=False)
    assert rank_route_mode() == "deterministic"
    monkeypatch.setenv("ANXG_RANK_ROUTE", "llm")   # 롤백·ablation
    assert rank_route_mode() == "llm"
    monkeypatch.setenv("ANXG_RANK_ROUTE", "bogus")
    assert rank_route_mode() == "deterministic"   # 알 수 없는 값 → 안전 폴백


def test_person_chain_binds_corp_code() -> None:
    """person 출발 — get_companies_of_person→compare_companies, corp_code 바인딩."""
    plan = _deterministic_cross_store_plan(
        persons=["김영규"], targets=[], q="매출이 가장 큰 회사는?", year_hint=2023)
    assert plan is not None and len(plan) == 2
    g, s = plan
    assert g["intent"] == "get_companies_of_person" and g["args"]["name"] == "김영규"
    assert s["intent"] == "compare_companies"
    assert s["args"]["corp_codes"] == {
        "$from": "g_xstore", "field": "corp_code", "collect": True}
    assert s["args"]["year"] == 2023 and s["depends_on"] == ["g_xstore"]


def test_subsidiary_chain_binds_child_corp_code() -> None:
    """parent corp_code 출발 — list_subsidiaries→compare_companies, child_corp_code 바인딩."""
    plan = _deterministic_cross_store_plan(
        persons=[], targets=["00126380"], q="자회사 중 매출 가장 큰", year_hint=2023)
    g, s = plan
    assert g["intent"] == "list_subsidiaries" and g["args"]["parent_corp_code"] == "00126380"
    assert s["args"]["corp_codes"]["field"] == "child_corp_code"


def test_metric_from_policy_ssot() -> None:
    """metric 은 policy.infer_compare_metric SSOT 를 따른다."""
    assert _deterministic_cross_store_plan(
        persons=["p"], targets=[], q="영업이익이 가장 큰", year_hint=2023)[1]["args"]["metric"] == "operating_income"
    assert _deterministic_cross_store_plan(
        persons=["p"], targets=[], q="당기순이익 1위", year_hint=2023)[1]["args"]["metric"] == "net_income"
    assert _deterministic_cross_store_plan(
        persons=["p"], targets=[], q="매출 순위", year_hint=2023)[1]["args"]["metric"] == "revenue"


def test_rank_direction_min_vs_max() -> None:
    """A-1: 최소 우선 질문→'asc', 그 외→'desc' — compare_companies direction(synth 결정화)."""
    from autonexusgraph.agents.policy import rank_direction
    for q in ("매출이 가장 큰 회사", "매출액 기준 1위", "당기순이익을 큰 순으로", "매출 순위 상위"):
        assert rank_direction(q) == "desc", q
    for q in ("매출이 가장 작은 회사", "매출이 작은 순으로 맨 앞", "영업이익이 가장 낮은", "매출이 가장 적은"):
        assert rank_direction(q) == "asc", q


def test_plan_carries_direction() -> None:
    """B plan 의 compare_companies 가 direction 을 운반(min→asc 로 답이 첫 행)."""
    assert _deterministic_cross_store_plan(
        persons=["p"], targets=[], q="매출 가장 작은", year_hint=2023)[1]["args"]["direction"] == "asc"
    assert _deterministic_cross_store_plan(
        persons=["p"], targets=[], q="매출 가장 큰", year_hint=2023)[1]["args"]["direction"] == "desc"


def test_no_year_or_no_start_falls_back_to_llm() -> None:
    """compare_companies year 필수 + 출발 엔티티 필수 — 부재 시 None(→LLM 폴백)."""
    assert _deterministic_cross_store_plan(
        persons=["김영규"], targets=[], q="매출 가장 큰", year_hint=None) is None
    assert _deterministic_cross_store_plan(
        persons=[], targets=[], q="매출 가장 큰", year_hint=2023) is None
