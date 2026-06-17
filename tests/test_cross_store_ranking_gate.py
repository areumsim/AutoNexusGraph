"""Cross-store 수치 랭킹 게이트 일반화 회귀 가드 (thesis §1 V5 잔여 과제).

배경: V5 cross-store 우위(+78.6pp)는 flat 최상급 키워드 게이트에 의존하는
"좁고 깨지기 쉬운 win". 패러프레이즈("매출 1위"·"순위가 가장 높은"·"매출이 더 많은")엔
발화 안 돼 0.062 로 추락. 본 가드는 structural 게이트(비교·서열 구조 ∧ 수치 metric)가
(a) 패러프레이즈 재현율 회복 + (b) main 비-랭킹 multi-hop 비발화(정밀도)를 보장한다.

핵심 불변식:
- structural 은 legacy 키워드 case 를 모두 포함(상위집합) — 후방호환.
- structural 은 패러프레이즈에 발화하나 legacy 는 놓친다(일반화 실증).
- 둘 다 비-수치 multi-hop(모회사/임원 체인)엔 비발화 — main 비회귀의 정밀도 근거.
- main-62 gold 실파일에서 structural 발화 0 (pre-reg T-G2 비회귀 보증).
- env `ANXG_RANK_GATE` 3-mode(off/keyword/structural) 디스패치.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from autonexusgraph.agents.policy import (
    _RANK_KEYWORD_LEGACY,
    detect_cross_store_ranking,
    is_cross_store_ranking,
    rank_gate_mode,
)

ROOT = Path(__file__).resolve().parents[1]

# legacy 키워드가 박혀 있어 keyword·structural 둘 다 발화해야 하는 질문.
_LEGACY_FIRE = (
    "김영규이 임원으로 재직하는 회사 중 2023년 매출이 가장 큰 회사는?",
    "2023년 매출이 가장 작은 회사는?",
    "영업이익이 가장 높은 자회사는?",
)
# legacy 키워드는 없지만 의미상 cross-store 수치 랭킹인 패러프레이즈 — structural 만 발화.
# metric 은 모두 compare_companies 지원(revenue/operating_income/net_income)이어야 한다 —
# 미지원 metric(시가총액 등)은 _UNSUPPORTED_METRIC_NO_FIRE 로 분리(게이트=다운스트림 능력).
_PARAPHRASE_FIRE = (
    "매출액 기준 1위인 회사는?",                  # 서수 'N위' (revenue)
    "영업이익이 더 많은 회사는?",                  # 비교급 '더 많은' (operating_income)
    "매출 순위가 상위인 회사는?",                  # 서열 '순위/상위' (revenue)
    "당기순이익을 큰 순으로 정렬했을 때 첫 회사는?",   # '큰 순' + net_income(지원 metric)
)

# Signal A(구조)는 있으나 metric 이 compare_companies 미지원(시가총액·자산·직원·부채 등)
# → 비발화. 게이트가 발화하면 _infer_compare_metric 이 revenue 로 조용히 치환해 오답이
# 되던 seam 차단(게이트=다운스트림 능력 일치). 확장하려면 financials._METRIC_ACCOUNTS +
# policy._METRIC_TRIGGERS 를 동시 확장해야 본 가드가 통과한다.
_UNSUPPORTED_METRIC_NO_FIRE = (
    "시가총액이 더 높은 회사는?",
    "자산이 가장 많은 회사는?",
    "직원 수가 가장 많은 회사는?",
    "부채가 가장 적은 회사는?",
)
# 비-랭킹 / 비-수치 multi-hop — 어느 모드에서도 발화 금지(main 비회귀 정밀도 근거).
_NEVER_FIRE = (
    "기아의 모회사 회사명은 무엇인가?",
    "이재용이 임원으로 재직하는 회사를 모두 답하라.",
    "삼성전자의 자회사는 무엇인가?",
    "현대자동차가 제조한 차종 중 리콜 대상이 된 모델명을 모두 답하라.",  # 서수 아님·metric 없음
    "삼성전자의 주요 주주는 누구인가?",
)


def test_structural_superset_of_legacy() -> None:
    """structural 은 legacy 키워드 case 를 모두 포함(상위집합) — 후방호환."""
    for q in _LEGACY_FIRE:
        assert detect_cross_store_ranking(q), f"structural 미발화: {q}"
        assert any(k in q for k in _RANK_KEYWORD_LEGACY), f"legacy 키워드 부재: {q}"


def test_structural_recovers_paraphrases_legacy_misses() -> None:
    """일반화 실증 — legacy 가 놓치는 패러프레이즈를 structural 이 포착."""
    for q in _PARAPHRASE_FIRE:
        assert detect_cross_store_ranking(q), f"structural 패러프레이즈 미발화: {q}"
        # legacy 키워드 게이트는 이 패러프레이즈를 놓쳐야 한다(브리틀 입증).
        legacy = any(k in q for k in _RANK_KEYWORD_LEGACY)
        assert not legacy, f"패러프레이즈가 legacy 에 잡힘(설정 오류): {q}"


def test_no_fire_on_non_numeric_multihop() -> None:
    """비-수치 multi-hop 은 Signal B(metric) 부재 → 비발화. main 비회귀 정밀도 근거."""
    for q in _NEVER_FIRE:
        assert not detect_cross_store_ranking(q), f"오발화(정밀도 위반): {q}"


def test_metric_requirement_is_necessary() -> None:
    """Signal A(구조)만 있고 metric 없으면 비발화 — 정밀도 핵심 가드."""
    assert not detect_cross_store_ranking("가장 큰 회사는 어디인가?")        # metric 없음
    assert not detect_cross_store_ranking("리콜이 가장 많이 발생한 모델은?")  # metric 없음
    # metric 추가 시 발화로 전환.
    assert detect_cross_store_ranking("매출이 가장 큰 회사는 어디인가?")


def test_unsupported_metric_does_not_fire() -> None:
    """미지원 metric(시가총액·자산·직원·부채…)은 Signal A 가 있어도 비발화.

    게이트가 compare_companies 능력 밖 metric 에 over-fire → _infer_compare_metric 이
    revenue 로 조용히 치환 → 매출로 랭킹한 오답이 되던 seam 차단(다운스트림 능력 일치).
    """
    for q in _UNSUPPORTED_METRIC_NO_FIRE:
        assert not detect_cross_store_ranking(q), f"미지원 metric over-fire(seam): {q}"


def test_metric_triggers_subset_of_supported() -> None:
    """SSOT 정합 — policy._METRIC_TRIGGERS 의 metric 은 모두 compare_companies 지원 ⊆."""
    from autonexusgraph.agents.policy import _METRIC_TRIGGERS
    from autonexusgraph.tools.financials import _METRIC_ACCOUNTS
    for _word, metric in _METRIC_TRIGGERS:
        assert metric in _METRIC_ACCOUNTS, f"게이트 trigger 가 미지원 metric: {metric}"


def test_gate_fire_implies_supported_metric_seam() -> None:
    """통합 seam 가드 — 게이트가 발화하는 모든 질문은 compare_companies 가 실제
    랭킹 가능한 metric 으로 귀결돼야 한다(두 단위 테스트[게이트 발화·metric ValueError]가
    각자 통과하지만 놓치던 통합 불변식).

    - policy.infer_compare_metric ≠ None ∧ financials._METRIC_ACCOUNTS 키
    - nodes._infer_compare_metric(rule-plan glue)도 동일 metric 반환(조용한 revenue 치환 없음)
    """
    from autonexusgraph.agents.nodes import _infer_compare_metric
    from autonexusgraph.agents.policy import infer_compare_metric
    from autonexusgraph.tools.financials import _METRIC_ACCOUNTS

    for q in _LEGACY_FIRE + _PARAPHRASE_FIRE:
        m = infer_compare_metric(q)
        assert m is not None, f"발화 질문인데 metric None: {q}"
        assert m in _METRIC_ACCOUNTS, f"게이트 metric 이 compare_companies 미지원: {q}→{m}"
        assert _infer_compare_metric(q) == m, f"rule-plan glue 가 게이트와 불일치: {q}"


@pytest.mark.parametrize("mode,q,expected", [
    ("off",        "매출이 가장 큰 회사는?",   False),
    ("off",        "매출액 1위인 회사는?",      False),
    ("keyword",    "매출이 가장 큰 회사는?",   True),
    ("keyword",    "매출액 1위인 회사는?",      False),   # legacy 는 패러프레이즈 놓침
    ("structural", "매출이 가장 큰 회사는?",   True),
    ("structural", "매출액 1위인 회사는?",      True),    # structural 회복
    ("structural", "기아의 모회사는?",          False),
])
def test_env_mode_dispatch(monkeypatch, mode, q, expected) -> None:
    """env `ANXG_RANK_GATE` 3-mode 디스패치."""
    monkeypatch.setenv("ANXG_RANK_GATE", mode)
    assert rank_gate_mode() == mode
    assert is_cross_store_ranking(q) is expected


def test_default_mode_is_structural(monkeypatch) -> None:
    """env 미설정 시 default=structural — T-G1/T-G2 통과 후 keyword→structural 플립."""
    monkeypatch.delenv("ANXG_RANK_GATE", raising=False)
    assert rank_gate_mode() == "structural"
    # 알 수 없는 값도 structural 로 안전 폴백.
    monkeypatch.setenv("ANXG_RANK_GATE", "bogus")
    assert rank_gate_mode() == "structural"


def test_main62_gold_zero_false_fire() -> None:
    """pre-reg T-G2 비회귀 보증 — main multi-hop 62 gold 에서 structural 발화 0."""
    gold = ROOT / "eval" / "qa_gold" / "gold_qa_graph_multihop_v0.jsonl"
    if not gold.exists():
        pytest.skip("main gold 부재")
    fired = [
        json.loads(ln)["question"]
        for ln in gold.read_text(encoding="utf-8").splitlines()
        if ln.strip() and detect_cross_store_ranking(json.loads(ln).get("question", ""))
    ]
    assert fired == [], f"main-62 오발화 {len(fired)}건 → main 회귀 위험: {fired[:3]}"
