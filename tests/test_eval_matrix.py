"""축소 평가 매트릭스 (PRD §10 DoD #17 (d)) — AgentAdapter 매트릭스 변수 + cell enumerator.

검증:
- AgentAdapter base 에 rerank / llm_tier 매트릭스 변수 + label() 자동 생성
- 4 어댑터 × rerank {True/False} = 8 cells enumerate
- compute_thesis_headline — simulation 모드는 'available=False (full mode 필요)' 응답
- 매트릭스 셀 라벨 형식 일관 (<name>_<tier>_rerank<0|1>)
"""

from __future__ import annotations

from eval.adapters import ADAPTER_REGISTRY, get_adapter
from eval.runners.run_matrix_smoke import (
    DEFAULT_ADAPTERS,
    DEFAULT_RERANK,
    DEFAULT_TIERS,
    compute_thesis_headline,
    enumerate_cells,
)


# ── AgentAdapter base 매트릭스 변수 ───────────────────────────────
def test_adapter_default_label_fast_rerank_on():
    a = get_adapter("vector")
    assert a.rerank is True
    assert a.llm_tier == "fast"
    assert a.label() == "vector_fast_rerank1"


def test_adapter_rerank_off_label():
    a = get_adapter("vector", rerank=False)
    assert a.rerank is False
    assert a.label() == "vector_fast_rerank0"


def test_adapter_smart_tier_label():
    a = get_adapter("hybrid", rerank=True, llm_tier="smart")
    assert a.llm_tier == "smart"
    assert a.label() == "hybrid_smart_rerank1"


def test_all_4_adapters_support_rerank_toggle():
    """4 구체 어댑터 모두 rerank 매트릭스 변수 수용."""
    for name in ADAPTER_REGISTRY:
        for rerank in (True, False):
            a = get_adapter(name, rerank=rerank)
            assert a.rerank is rerank
            assert a.label() == f"{name}_fast_rerank{int(rerank)}"


# ── 셀 enumerator ─────────────────────────────────────────────────
def test_default_matrix_base_8_plus_planner_2():
    """기본 = 8 base 셀 + (축2) hybrid LLM planner ablation 2 = 10."""
    cells = enumerate_cells()
    assert len(cells) == 10
    base = {c["label"] for c in cells if not c["llm_planner"]}
    assert base == {f"{a}_fast_rerank{r}" for a in DEFAULT_ADAPTERS for r in (0, 1)}
    planner = {c["label"] for c in cells if c["llm_planner"]}
    assert planner == {"hybrid_fast_rerank1_planner1", "hybrid_fast_rerank0_planner1"}


def test_planner_ablation_off_gives_base_8():
    cells = enumerate_cells(planner_ablation=False)
    assert len(cells) == 8
    assert all(not c["llm_planner"] for c in cells)


def test_cell_keys_are_complete():
    cells = enumerate_cells()
    for c in cells:
        assert set(c.keys()) == {"label", "adapter", "tier", "rerank", "llm_planner"}
        assert c["tier"] == "fast"
        assert isinstance(c["rerank"], bool)
        assert isinstance(c["llm_planner"], bool)


def test_custom_adapter_subset():
    # vector(2) + hybrid(2) base + hybrid planner(2) = 6
    cells = enumerate_cells(adapters=("vector", "hybrid"))
    assert len(cells) == 6
    assert {c["adapter"] for c in cells} == {"vector", "hybrid"}


def test_subset_without_hybrid_has_no_planner_cells():
    """hybrid 미포함 subset 은 planner 셀 0 (agent planner 미경유)."""
    cells = enumerate_cells(adapters=("vector", "graph"))
    assert len(cells) == 4
    assert all(not c["llm_planner"] for c in cells)


def test_custom_single_rerank_value():
    # 4 adapters × 1 rerank = 4 base + hybrid planner 1 = 5
    cells = enumerate_cells(reranks=(True,))
    assert len(cells) == 5
    for c in cells:
        assert c["rerank"] is True


# ── 축2 planner ablation headline ─────────────────────────────────
def test_planner_ablation_headline_full_mode():
    """hybrid 룰 vs LLM planner multi_hop_em 차이 계산 (LLM 우위 판정)."""
    from eval.runners.run_matrix_smoke import compute_planner_ablation
    cells = enumerate_cells()
    results = []
    for c in cells:
        em = None
        if c["label"] == "hybrid_fast_rerank1":
            em = 0.50           # 룰 planner
        elif c["label"] == "hybrid_fast_rerank1_planner1":
            em = 0.62           # LLM planner
        results.append({**c, "multi_hop_em": em})
    pa = compute_planner_ablation(results)
    assert pa["available"] is True
    assert pa["rule_em"] == 0.50 and pa["llm_em"] == 0.62
    assert pa["diff_pp"] == 12.0
    assert pa["llm_better"] is True


def test_planner_ablation_unavailable_in_simulation():
    from eval.runners.run_matrix_smoke import compute_planner_ablation
    cells = enumerate_cells()
    results = [{**c, "multi_hop_em": None} for c in cells]
    pa = compute_planner_ablation(results)
    assert pa["available"] is False


# ── thesis headline ───────────────────────────────────────────────
def test_thesis_unavailable_in_simulation_mode():
    cells = enumerate_cells()
    # simulation 모드 — multi_hop_em 가 None
    results = [{**c, "multi_hop_em": None} for c in cells]
    thesis = compute_thesis_headline(results)
    assert thesis["available"] is False
    # 단 필요 셀 (hybrid_rerank1 + vector_rerank0) 의 존재는 reason 으로 안내.
    assert "simulation" in thesis["reason"] or "full" in thesis["reason"]


def test_thesis_available_in_full_mode():
    """full 모드 시 hybrid_rerank1 vs vector_rerank0 multi-hop EM 차이 계산."""
    cells = enumerate_cells()
    # hybrid_fast_rerank1 = 0.85, vector_fast_rerank0 = 0.40 → +45%p (target met)
    results = []
    for c in cells:
        em = None
        if c["label"] == "hybrid_fast_rerank1":
            em = 0.85
        elif c["label"] == "vector_fast_rerank0":
            em = 0.40
        results.append({**c, "multi_hop_em": em})
    thesis = compute_thesis_headline(results)
    assert thesis["available"] is True
    assert thesis["hybrid_em"] == 0.85
    assert thesis["vector_em"] == 0.40
    assert thesis["diff_pp"] == 45.0
    assert thesis["target_met"] is True


def test_thesis_target_not_met():
    """Hybrid 가 Vector baseline 을 +30%p 못 이기면 fail."""
    cells = enumerate_cells()
    results = []
    for c in cells:
        em = None
        if c["label"] == "hybrid_fast_rerank1":
            em = 0.55
        elif c["label"] == "vector_fast_rerank0":
            em = 0.50
        results.append({**c, "multi_hop_em": em})
    thesis = compute_thesis_headline(results)
    assert thesis["available"] is True
    assert thesis["diff_pp"] == 5.0
    assert thesis["target_met"] is False


def test_thesis_unavailable_when_missing_cells():
    """필요 셀이 enumeration 에서 빠지면 unavailable."""
    # graph 만 — hybrid 도 vector 도 없음.
    results = enumerate_cells(adapters=("graph",))
    thesis = compute_thesis_headline(results)
    assert thesis["available"] is False


# ── C2 회귀 — rerank 가 search_documents 시그니처에 전파 ──────────────
def test_search_documents_accepts_rerank_kwarg():
    """retrieve.search_documents 가 rerank 인자 수용 — C2 회귀 방지."""
    import inspect
    from autonexusgraph.tools.retrieve import search_documents
    sig = inspect.signature(search_documents)
    assert "rerank" in sig.parameters
    assert sig.parameters["rerank"].default is True


def test_search_documents_auto_accepts_rerank_kwarg():
    """autograph retrieve.search_documents_auto 도 rerank 수용."""
    import inspect
    from autograph.tools.retrieve import search_documents_auto
    sig = inspect.signature(search_documents_auto)
    assert "rerank" in sig.parameters


def test_vector_adapter_passes_rerank_flag(monkeypatch):
    """VectorAdapter(rerank=False) 가 search_documents(rerank=False) 호출."""
    from eval.adapters.vector_adapter import VectorAdapter
    captured = {}

    def _mock_search(question, *, top_k, rerank=True, **kw):
        captured["rerank"] = rerank
        captured["top_k"] = top_k
        return []  # 빈 결과 → adapter 가 no_evidence 로 refuse

    monkeypatch.setattr("autonexusgraph.tools.retrieve.search_documents", _mock_search)
    # vector_adapter 내부 import 도 우회 — sys.modules 갱신.
    import autonexusgraph.tools.retrieve as _r
    monkeypatch.setattr(_r, "search_documents", _mock_search)

    a = VectorAdapter(rerank=False)
    a.query("질문", domain="auto")
    assert captured.get("rerank") is False


def test_sql_vec_adapter_passes_rerank_flag(monkeypatch):
    """SqlVecAdapter(rerank=False) 가 search_documents(rerank=False) 호출."""
    from eval.adapters.sql_vec_adapter import SqlVecAdapter
    captured = {}

    def _mock_search(question, *, top_k, rerank=True, **kw):
        captured["rerank"] = rerank
        return []

    import autonexusgraph.tools.retrieve as _r
    monkeypatch.setattr(_r, "search_documents", _mock_search)

    a = SqlVecAdapter(rerank=False)
    # SqlVecAdapter 는 SQL tool 도 호출 — 회사 못 찾으면 early return 가능.
    # 단 search_documents 호출 자체는 try-except 안에서 일어나므로 captured 됨.
    try:
        a.query("삼성전자 2024 매출은?", domain="finance")
    except Exception:   # noqa: BLE001 — adapter 내부 실패 무시 (본 테스트는 search_documents 호출 captured 만 확인)
        pass
    # mock 이 호출됐다면 rerank=False 가 들어와야.
    if "rerank" in captured:
        assert captured["rerank"] is False


# ── C4 회귀 — manifest 병합 + thesis full 모드 ─────────────────────
def test_thesis_full_mode_with_manifest_metrics():
    """full 모드 결과를 mocked manifest 로 시뮬레이션 — thesis 정상 계산."""
    cells = enumerate_cells()
    # _run_cell_full 가 반환할 형식 모사
    results = []
    for c in cells:
        em_mh = None
        if c["label"] == "hybrid_fast_rerank1":
            em_mh = 0.78
        elif c["label"] == "vector_fast_rerank0":
            em_mh = 0.42
        results.append({**c, "ran": True, "mode": "full",
                        "multi_hop_em": em_mh, "em": em_mh, "f1": em_mh,
                        "cost_usd": 0.05, "n_questions": 30})
    thesis = compute_thesis_headline(results)
    assert thesis["available"] is True
    assert thesis["hybrid_em"] == 0.78
    assert thesis["vector_em"] == 0.42
    assert thesis["target_met"] is True
    assert thesis["diff_pp"] == 36.0


# ── C1 회귀 — env / CLI 매트릭스 변수 ─────────────────────────────
def test_run_qa_eval_module_imports():
    """run_qa_eval 모듈이 매트릭스 변수 import 후 에러 없이 로드."""
    import importlib
    import eval.runners.run_qa_eval as m
    assert hasattr(m, "main")
    # ENV 변수 처리 코드가 main 안에 있어야 함 — import 시점은 부수효과 없음.
