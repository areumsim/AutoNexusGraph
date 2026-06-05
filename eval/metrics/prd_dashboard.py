"""PRD §10 17개 success criteria 자동 측정 + 요약 대시보드.

상태 코드:
    ✅ 충족 / ❌ 미달 / ⚠️ 부분 / ⊘ 측정 불가 (LLM 또는 운영 데이터 필요)

CLI:
    python -m eval.metrics.prd_dashboard            # stdout 출력
    python -m eval.metrics.prd_dashboard --json     # JSON
    python -m eval.metrics.prd_dashboard -o path.md # 파일 저장
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any


log = logging.getLogger(__name__)


# 17개 success criteria (v2.1 14 항 + v2.2 IPGraph/상용신호 #15~#17 흡수).
CRITERIA = [
    ("10.1",  "AutoNexusGraph docker compose up", "infra"),
    ("10.2",  "Streamlit UI 도메인 토글 3종 동작", "infra"),
    ("10.3",  "LLM Provider 환경변수 전환", "config"),
    ("10.4",  "MVP 범위 (OEM 5~8 × 모델 30~50 × 2022~2024)", "data"),
    ("10.5",  "BOM Level 0~3 안정 + Level 4 coverage ≥ 60%", "data"),
    ("10.6",  "anxg_bridge.corp_entity QID/LEI 강매칭 confidence ≥0.9 비율 80%+", "bridge"),
    ("10.7",  "Hybrid vs Vector Multi-hop +30%p", "eval-llm"),
    ("10.8",  "Cross-Domain QA 4단계 (CD-L1 80%+/L2 70%+/L3 50%+/L4 40%+)", "eval-llm"),
    ("10.9",  "제원 수치 EM 95%+", "eval-llm"),
    ("10.10", "Faithfulness 90%+", "eval-llm"),
    ("10.11", "SUPPLIED_BY 엣지 confidence/provenance/snapshot_year 100%", "graph"),
    ("10.12", "AutoNexusGraph 코어 코드 변경 < 5%", "git"),
    ("10.13", "메인 홉 효율: 노드 탐색 -30%", "trace"),
    ("10.14", "평균 latency: 도메인 내 < 8s, Cross-Domain < 12s", "trace"),
    # v2.2 — IPGraph (도메인3) 흡수.
    ("10.15", "ip 도메인 추가 후 코어 변경 < 5% 재측정 (baseline reset)", "ipgraph"),
    ("10.16", "ip gold seed (IP-L1/L2/L3) + CD-L3/L4 ip 결합 8 문항", "ipgraph"),
    # v2.2 — DoD #17 상용 신호 (subdivisions).
    ("10.17.a", "MCP 래퍼로 외부 에이전트 호출 가능", "service"),
    ("10.17.b", "Langfuse 실측 ON (turn별 token/cost/replan)", "trace-audit"),
    ("10.17.c", "온톨로지 SHACL/pydantic 검증", "service"),
    ("10.17.d", "축소 평가 매트릭스 (4 어댑터 × FAST × rerank ablation)", "eval-llm"),
]

# 각 카테고리 별 어떻게 처리되는지.
CATEGORY_HOW = {
    "infra":      "docker compose 실측 — 본 dashboard 는 미측정",
    "config":     "ENV 확인 — 본 dashboard 는 미측정",
    "data":       "자동 측정 가능",
    "bridge":     "자동 측정 가능",
    "graph":      "자동 측정 가능 (Neo4j)",
    "eval-llm":   "LLM_API_KEY 필요",
    "git":        "git diff 자동 계산 가능",
    "trace":      "manifest.json 의 main_hop_efficiency / latency 키 자동 흡수",
    "service":    "(예정) 상용 신호 항목",
    "trace-audit":"make audit-trace 의 최신 리포트 기반 자동 측정",
    "ipgraph":    "make audit-ipgraph 의 최신 리포트 기반 자동 측정 (wire-up/gold 분리)",
}


def _find_latest_manifest() -> dict[str, Any] | None:
    """eval/reports/<run>/manifest.json 중 mtime 최신 한 건. (path, payload) 반환."""
    from pathlib import Path as _P
    root = _P(__file__).resolve().parents[2]
    manifests = sorted((root / "eval" / "reports").glob("*/manifest.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    if not manifests:
        return None
    try:
        with manifests[0].open() as f:
            return {"path": manifests[0], "payload": json.load(f)}
    except Exception:   # noqa: BLE001
        return None


def _read_latest_ipgraph_audit() -> tuple[dict, str] | None:
    """data/reports/audit_ipgraph_*.json 중 가장 최신 한 건. (payload, filename)."""
    from pathlib import Path as _P
    root = _P(__file__).resolve().parents[2]
    reports = sorted((root / "data" / "reports").glob("audit_ipgraph_*.json"))
    if not reports:
        return None
    latest = reports[-1]
    try:
        with latest.open() as f:
            return json.load(f), latest.name
    except Exception:   # noqa: BLE001
        return None


def _collect_thesis_audit() -> dict[str, Any]:
    """DoD §10.7 — Hybrid vs Vector multi-hop +30%p 자동 측정.

    우선순위:
      1. data/reports/audit_eval_matrix_*.json 의 ``thesis`` (run_matrix_smoke --full)
      2. eval/reports/<latest>/manifest.json 의 ``hybrid_vs_vector`` (run_qa_eval)
    """
    from pathlib import Path as _P
    root = _P(__file__).resolve().parents[2]

    # 1순위 — audit_eval_matrix_*.json.
    matrices = sorted((root / "data" / "reports").glob("audit_eval_matrix_*.json"))
    for matrix_path in reversed(matrices):
        try:
            with matrix_path.open() as f:
                payload = json.load(f)
        except Exception:   # noqa: BLE001
            continue
        thesis = payload.get("thesis") or {}
        if not thesis.get("available"):
            continue
        diff = thesis.get("diff_pp")
        if thesis.get("target_met"):
            return {"status": "pass",
                    "detail": f"Hybrid−Vector multi-hop = {diff:+.1f}%p ≥ +30%p ({matrix_path.name})"}
        return {"status": "fail",
                "detail": f"Hybrid−Vector multi-hop = {diff:+.1f}%p < +30%p ({matrix_path.name})"}

    # 2순위 — manifest.json.
    info = _find_latest_manifest()
    if info:
        hvv = (info["payload"].get("hybrid_vs_vector") or {})
        if hvv.get("available"):
            em_diff = hvv.get("em_diff_pp", 0.0)
            f1_diff = hvv.get("f1_diff_pp", 0.0)
            status = "pass" if hvv.get("target_met") else "fail"
            return {"status": status,
                    "detail": f"hybrid−vector EM={em_diff:+.1f}%p F1={f1_diff:+.1f}%p ({info['path'].name})"}

    return {"status": "blocked",
            "detail": "LLM_API_KEY 필요 — make eval-full && make audit-eval-matrix 후 자동 측정"}


def _collect_hop_audit() -> dict[str, Any]:
    """DoD §10.13 — Main-Hop Efficiency: hybrid/vector ev_avg ratio ≤ 0.7."""
    info = _find_latest_manifest()
    if not info:
        return {"status": "blocked",
                "detail": "eval/reports/*/manifest.json 없음 — make eval-full 실행 후 자동 측정"}
    mhe = info["payload"].get("main_hop_efficiency") or {}
    hvv = mhe.get("hybrid_vs_vector")
    if not hvv:
        return {"status": "blocked",
                "detail": f"main_hop_efficiency.hybrid_vs_vector 없음 (vector+hybrid 어댑터 모두 필요) ({info['path'].name})"}
    ratio = hvv.get("ratio")
    if hvv.get("target_met"):
        return {"status": "pass",
                "detail": f"hybrid/vector ev_avg ratio = {ratio} ≤ 0.7 ({info['path'].name})"}
    return {"status": "fail",
            "detail": f"hybrid/vector ev_avg ratio = {ratio} > 0.7 ({info['path'].name})"}


def _collect_latency_audit() -> dict[str, Any]:
    """DoD §10.14 — 도메인 내 <8s / Cross <12s pass rate.

    임계: 어댑터 평균 pass rate ≥ 0.9 → pass, ≥ 0.5 → partial, 미만 → fail.
    """
    info = _find_latest_manifest()
    if not info:
        return {"status": "blocked",
                "detail": "eval/reports/*/manifest.json 없음 — make eval-full 실행 후 자동 측정"}
    lat = info["payload"].get("latency") or {}

    int_rates: list[float] = []
    cross_rates: list[float] = []
    for adapter, rec in lat.items():
        if not isinstance(rec, dict) or "p95" not in rec:
            continue
        r_int = rec.get("target_internal_pass_rate")
        r_cross = rec.get("target_cross_pass_rate")
        if r_int is not None:
            int_rates.append(float(r_int))
        if r_cross is not None:
            cross_rates.append(float(r_cross))

    rates = [sum(xs) / len(xs) for xs in (int_rates, cross_rates) if xs]
    if not rates:
        return {"status": "blocked",
                "detail": f"latency pass rate 미산정 ({info['path'].name})"}

    parts = []
    if int_rates:
        parts.append(f"internal pass={sum(int_rates) / len(int_rates):.0%}")
    if cross_rates:
        parts.append(f"cross pass={sum(cross_rates) / len(cross_rates):.0%}")
    detail = ", ".join(parts) + f" ({info['path'].name})"

    min_rate = min(rates)
    if min_rate >= 0.9:
        return {"status": "pass", "detail": detail}
    if min_rate >= 0.5:
        return {"status": "partial", "detail": detail}
    return {"status": "fail", "detail": detail}


def _collect_ipgraph_wireup() -> dict[str, Any]:
    """DoD §10.15 — IPGraph wire-up (handler/router/ontology/cypher_templates).

    gold check 는 §10.16 으로 분리. 본 함수는 코어 plug-in 4 check 만 본다.
    """
    pair = _read_latest_ipgraph_audit()
    if not pair:
        return {"status": "blocked",
                "detail": "(예정) make audit-ipgraph 미실행"}
    payload, name = pair
    checks = payload.get("checks", {})
    wireup_keys = ("handler", "router", "ontology", "cypher_templates")
    failed = [k for k in wireup_keys if not checks.get(k, {}).get("passed")]
    if not failed:
        cy = checks.get("cypher_templates", {}).get("ip_templates_registered", 0)
        return {"status": "pass",
                "detail": f"handler+router+ontology+{cy} cypher ({name})"}
    return {"status": "fail",
            "detail": f"FAIL — wire-up failed: {failed} ({name})"}


def _collect_ipgraph_gold() -> dict[str, Any]:
    """DoD §10.16 — IPGraph gold seed (gold_qa_ip ≥30 + cross_ip ≥8)."""
    pair = _read_latest_ipgraph_audit()
    if not pair:
        return {"status": "blocked",
                "detail": "(예정) make audit-ipgraph 미실행"}
    payload, name = pair
    gold = payload.get("checks", {}).get("gold", {})
    n_ip = gold.get("n_ip", 0)
    n_cross = gold.get("n_cross_ip", 0)
    if gold.get("passed"):
        return {"status": "pass",
                "detail": f"gold_qa_ip={n_ip} + cross_ip={n_cross} ≥ 8 ({name})"}
    return {"status": "fail",
            "detail": f"gold_qa_ip={n_ip}/30, cross_ip={n_cross}/8 ({name})"}


def _collect_mcp_audit() -> dict[str, Any]:
    """DoD #17 (a) — make audit-mcp 의 최신 리포트.

    상태:
      pass    — SDK 설치 + server boot OK
      partial — SDK 미설치, tool discovery 만 검증 (wire-up)
      fail    — tool 0 건 또는 server boot 실패
      blocked — 리포트 없음
    """
    from pathlib import Path as _P
    root = _P(__file__).resolve().parents[2]
    reports = sorted((root / "data" / "reports").glob("audit_mcp_*.json"))
    if not reports:
        return {
            "id": "10.17.a", "status": "blocked",
            "detail": "(예정) make audit-mcp 미실행",
        }
    latest = reports[-1]
    try:
        with latest.open() as f:
            payload = json.load(f)
    except Exception as e:   # noqa: BLE001
        return {"id": "10.17.a", "status": "fail",
                "detail": f"리포트 파싱 실패: {e} ({latest.name})"}
    if payload.get("skipped"):
        n_tools = payload.get("n_tools", 0)
        return {"id": "10.17.a", "status": "partial",
                "detail": f"SDK 미설치 — wire-up only ({n_tools} tools discovered). pip install mcp 후 PASS ({latest.name})"}
    if payload.get("passed"):
        n_tools = payload.get("n_tools", 0)
        return {"id": "10.17.a", "status": "pass",
                "detail": f"{n_tools} tools + server boot OK ({latest.name})"}
    return {"id": "10.17.a", "status": "fail",
            "detail": f"FAIL — {payload.get('reason', '?')} ({latest.name})"}


def _collect_eval_matrix_audit() -> dict[str, Any]:
    """DoD #17 (d) — make audit-eval-matrix 의 최신 리포트.

    상태:
      pass   — 최신 리포트 passed=True (8 cells enumerate 성공)
               full 모드에서 thesis.target_met 까지 통과면 pass + thesis 표기
      partial— simulation 모드 (wire-up 만 — full LLM 측정 필요)
      fail   — passed=False
      blocked— 리포트 없음
    """
    from pathlib import Path as _P
    root = _P(__file__).resolve().parents[2]
    reports = sorted((root / "data" / "reports").glob("audit_eval_matrix_*.json"))
    if not reports:
        return {
            "id": "10.17.d", "status": "blocked",
            "detail": "(예정) make audit-eval-matrix 미실행",
        }
    latest = reports[-1]
    try:
        with latest.open() as f:
            payload = json.load(f)
    except Exception as e:   # noqa: BLE001
        return {"id": "10.17.d", "status": "fail",
                "detail": f"리포트 파싱 실패: {e} ({latest.name})"}
    if not payload.get("passed"):
        return {"id": "10.17.d", "status": "fail",
                "detail": f"FAIL — {payload.get('n_cells', 0)} cells ({latest.name})"}
    mode = payload.get("mode", "simulation")
    n_cells = payload.get("n_cells", 0)
    thesis = payload.get("thesis", {})
    if mode == "simulation":
        return {"id": "10.17.d", "status": "partial",
                "detail": f"wire-up only ({n_cells} cells enumerate) — full 측정은 LLM 키 필요 ({latest.name})"}
    # full 모드 — thesis.target_met 까지 검사.
    if thesis.get("available") and thesis.get("target_met"):
        return {"id": "10.17.d", "status": "pass",
                "detail": f"{n_cells} cells full · thesis Hybrid−Vector = {thesis.get('diff_pp')}%p ≥ +30%p ✓ ({latest.name})"}
    if thesis.get("available"):
        return {"id": "10.17.d", "status": "fail",
                "detail": f"thesis FAIL — Hybrid−Vector = {thesis.get('diff_pp')}%p < +30%p ({latest.name})"}
    return {"id": "10.17.d", "status": "partial",
            "detail": f"full mode but thesis 측정 불가: {thesis.get('reason', '?')} ({latest.name})"}


def _collect_ontology_audit() -> dict[str, Any]:
    """DoD #17 (c) — make audit-ontology 의 최신 리포트 (data/reports/audit_ontology_*.json).

    상태:
      pass — 최신 리포트 passed=True (모든 yaml 파일 pydantic strict-validate 통과)
      fail — passed=False
      blocked — 리포트 자체가 없음 (audit-ontology 미실행)
    """
    from pathlib import Path as _P
    root = _P(__file__).resolve().parents[2]
    reports = sorted((root / "data" / "reports").glob("audit_ontology_*.json"))
    if not reports:
        return {
            "id": "10.17.c", "status": "blocked",
            "detail": "(예정) make audit-ontology 미실행 — data/reports/audit_ontology_*.json 없음",
        }
    latest = reports[-1]
    try:
        with latest.open() as f:
            payload = json.load(f)
    except Exception as e:   # noqa: BLE001
        return {
            "id": "10.17.c", "status": "fail",
            "detail": f"리포트 파싱 실패: {e} ({latest.name})",
        }
    if payload.get("passed"):
        n_pass = payload.get("n_pass", 0)
        n_total = payload.get("n_total", 0)
        # cypher↔yaml cross-check 결과의 정보성 마커 (cross_domain_refs / unused_in_cypher)
        # 도 detail 에 노출 — DoD #17 (c) 'pass' 이지만 도메인 간 참조 패턴은 가시화.
        results = payload.get("results", [])
        cross_info: list[str] = []
        for r in results:
            if not r.get("label", "").endswith(".cypher-vs-yaml"):
                continue
            label = r["label"]
            cd_refs = r.get("cross_domain_refs") or []
            unused = r.get("unused_in_cypher") or []
            if cd_refs:
                cross_info.append(f"{label} cross-domain={len(cd_refs)}")
            if unused:
                cross_info.append(f"{label} unused yaml={len(unused)}")
        cross_str = f" · {' · '.join(cross_info)}" if cross_info else ""
        return {
            "id": "10.17.c", "status": "pass",
            "detail": f"{n_pass}/{n_total} ontology files validated{cross_str} ({latest.name})",
        }
    # FAIL 분기 — cypher cross-check 의 true_missing 정보가 있으면 그것을 우선 노출.
    failed = [r for r in payload.get("results", []) if not r.get("passed")]
    reasons: list[str] = []
    for r in failed[:5]:
        if r.get("true_missing"):
            reasons.append(f"{r['label']}: cypher uses but yaml missing={r['true_missing']}")
        else:
            reasons.append(f"{r['label']}: {r['reason']}")
    return {
        "id": "10.17.c", "status": "fail",
        "detail": f"FAIL — {'; '.join(reasons)} ({latest.name})",
    }


def _collect_trace_audit() -> dict[str, Any]:
    """DoD #17 (b) — make audit-trace 의 최신 리포트 (data/reports/audit_trace_*.json).

    상태:
      pass   — 최신 리포트 passed=True
      partial— skipped (langfuse 미설정)
      fail   — passed=False
      blocked— 리포트 자체가 없음 (audit-trace 미실행)
    """
    from pathlib import Path as _P
    root = _P(__file__).resolve().parents[2]
    reports = sorted((root / "data" / "reports").glob("audit_trace_*.json"))
    if not reports:
        return {
            "id": "10.17.b", "status": "blocked",
            "detail": "(예정) make audit-trace 미실행 — data/reports/audit_trace_*.json 없음",
        }
    latest = reports[-1]
    try:
        with latest.open() as f:
            payload = json.load(f)
    except Exception as e:   # noqa: BLE001
        return {
            "id": "10.17.b", "status": "fail",
            "detail": f"리포트 파싱 실패: {e} ({latest.name})",
        }
    if payload.get("skipped"):
        return {
            "id": "10.17.b", "status": "partial",
            "detail": f"SKIPPED — {payload.get('reason', '')} ({latest.name})",
        }
    if payload.get("passed"):
        return {
            "id": "10.17.b", "status": "pass",
            "detail": f"{payload.get('summary', '')} ({latest.name})",
        }
    return {
        "id": "10.17.b", "status": "fail",
        "detail": f"FAIL — {payload.get('reason', '')} ({latest.name})",
    }


def collect_dashboard() -> dict[str, Any]:
    """17개 criteria 측정 결과 한 곳에 집계."""
    out: dict[str, Any] = {"items": []}

    # 10.4 — data coverage.
    try:
        from eval.metrics.data_coverage import collect_data_coverage
        c10_4 = collect_data_coverage()
        oem_ok = c10_4.get("oem_target_met", False)
        model_ok = c10_4.get("model_target_met", False)
        year_ok = c10_4.get("year_coverage_target", False)
        if oem_ok and model_ok and year_ok:
            status, detail = "pass", f"OEM={c10_4['n_oems']} models={c10_4['n_models']} years={c10_4.get('year_range')}"
        else:
            partial = oem_ok or model_ok or year_ok
            status = "partial" if partial else "fail"
            misses = []
            if not oem_ok: misses.append(f"OEM={c10_4['n_oems']}<5")
            if not model_ok: misses.append(f"models={c10_4['n_models']}<30")
            if not year_ok: misses.append("year≠2022~2024")
            detail = f"{', '.join(misses)} (n_var={c10_4['n_variants']})"
    except Exception as e:   # noqa: BLE001
        log.warning("[dashboard] §10.4 측정 실패: %s", e)
        status, detail = "skip", f"err: {e}"
    out["items"].append({"id": "10.4", "status": status, "detail": detail})

    # 10.5 — BOM coverage.
    try:
        from eval.metrics.bom_coverage import collect_bom_coverage
        c10_5 = collect_bom_coverage()
        l0l3 = c10_5.get("l0_l3_stable", False)
        l4 = c10_5.get("l4_coverage") or {}
        l4_ok = l4.get("target_met", False)
        if l0l3 and l4_ok:
            status, detail = "pass", f"L0~L3 stable, L4={l4.get('ratio', 0) * 100:.1f}%"
        elif l0l3:
            status = "partial"
            detail = (f"L0~L3 ✅, L4={l4.get('with_module', 0)}/"
                      f"{l4.get('denominator', 0)} = {l4.get('ratio', 0) * 100:.1f}% < 60%")
        else:
            status, detail = "fail", "L0~L3 unstable"
    except Exception as e:   # noqa: BLE001
        log.warning("[dashboard] §10.5 측정 실패: %s", e)
        status, detail = "skip", f"err: {e}"
    out["items"].append({"id": "10.5", "status": status, "detail": detail})

    # 10.6 — bridge.
    try:
        from eval.metrics.bridge_quality import collect_bridge_quality
        bq = collect_bridge_quality()
        sm = (bq.get("bridge") or {}).get("strong_match") or {}
        if sm.get("target_met") is True:
            status = "pass"
        elif sm.get("total"):
            status = "fail"
        else:
            status = "skip"
        ratio = sm.get("high_confidence_ratio")
        detail = (f"strong_match {sm.get('high_confidence', 0)}/"
                  f"{sm.get('total', 0)} = "
                  + (f"{ratio * 100:.1f}%" if ratio is not None else "?"))
    except Exception as e:   # noqa: BLE001
        log.warning("[dashboard] §10.6 측정 실패: %s", e)
        status, detail = "skip", f"err: {e}"
    out["items"].append({"id": "10.6", "status": status, "detail": detail})

    # 10.11 — SUPPLIED_BY 메타 100%.
    try:
        from eval.metrics.edge_meta_completeness import collect_edge_meta_completeness
        em = collect_edge_meta_completeness()
        ok = em.get("overall", {}).get("prd_required_compliant", False)
        sb = (em.get("rels") or {}).get("SUPPLIED_BY") or {}
        n_total = sb.get("total", 0)
        if ok and n_total > 0:
            status, detail = "pass", f"SUPPLIED_BY {n_total} edges, 100% meta"
        elif n_total > 0:
            status, detail = "fail", f"SUPPLIED_BY {n_total} edges, miss={sb.get('missing')}"
        else:
            status, detail = "skip", "no SUPPLIED_BY edges"
    except Exception as e:   # noqa: BLE001
        log.warning("[dashboard] §10.11 측정 실패: %s", e)
        status, detail = "skip", f"err: {e}"
    out["items"].append({"id": "10.11", "status": status, "detail": detail})

    # 10.12 — 코어 코드 변경 < 5% (git diff baseline 자동 측정).
    try:
        from eval.metrics.core_diff import collect_core_diff
        cd = collect_core_diff()
        if not cd.get("available"):
            status, detail = "skip", "git 미가용 또는 baseline 미발견"
        else:
            pct = cd["change_ratio"] * 100
            base = (cd["baseline_commit"] or "")[:10]
            label = (f"baseline `{base}` → {cd['changed_loc']:,}/{cd['baseline_loc']:,} "
                     f"LOC = {pct:.2f}%")
            status = "pass" if cd["target_met"] else "fail"
            detail = label
    except Exception as e:   # noqa: BLE001
        log.warning("[dashboard] §10.12 측정 실패: %s", e)
        status, detail = "skip", f"err: {e}"
    out["items"].append({"id": "10.12", "status": status, "detail": detail})

    # 10.7 — Hybrid vs Vector multi-hop +30%p (audit_eval_matrix 또는 manifest 흡수).
    out["items"].append({"id": "10.7", **_collect_thesis_audit()})

    # LLM judge 필요 — ⊘ (10.8 difficulty 층화 / 10.9 EM / 10.10 Faithfulness).
    for cid in ("10.8", "10.9", "10.10"):
        out["items"].append({
            "id": cid, "status": "blocked",
            "detail": "LLM_API_KEY 필요 — make eval-auto / eval-cross 실행 후 자동 측정",
        })

    # 10.17.d — 축소 평가 매트릭스 (simulation 모드는 wire-up 만, full 모드는 LLM 비용).
    out["items"].append(_collect_eval_matrix_audit())

    # 10.17.b — Langfuse 실측 audit 의 최신 리포트 기반.
    out["items"].append(_collect_trace_audit())

    # 10.17.a — MCP 래퍼 wire-up (audit-mcp 의 최신 리포트 기반).
    out["items"].append(_collect_mcp_audit())
    # 10.17.c — 온톨로지 pydantic 검증 — make audit-ontology 의 최신 리포트.
    out["items"].append(_collect_ontology_audit())

    # 인프라/설정.
    _CID_TO_CAT = {cid: cat for cid, _, cat in CRITERIA}
    for cid in ("10.1", "10.2", "10.3"):
        out["items"].append({
            "id": cid, "status": "n/a",
            "detail": CATEGORY_HOW[_CID_TO_CAT[cid]],
        })

    # 10.13 — Main-Hop Efficiency (manifest.main_hop_efficiency).
    out["items"].append({"id": "10.13", **_collect_hop_audit()})

    # 10.14 — Latency p50/p95 (manifest.latency).
    out["items"].append({"id": "10.14", **_collect_latency_audit()})

    # 10.15 — IPGraph wire-up (handler/router/ontology/cypher).
    out["items"].append({"id": "10.15", **_collect_ipgraph_wireup()})

    # 10.16 — IPGraph gold seed (ip 30 + cross_ip 8).
    out["items"].append({"id": "10.16", **_collect_ipgraph_gold()})

    # 정렬.
    order = [c[0] for c in CRITERIA]
    out["items"].sort(key=lambda it: order.index(it["id"]) if it["id"] in order else 99)

    # 집계.
    counts = {"pass": 0, "fail": 0, "partial": 0, "blocked": 0, "n/a": 0, "skip": 0}
    for it in out["items"]:
        counts[it["status"]] = counts.get(it["status"], 0) + 1
    out["counts"] = counts
    out["measurable_total"] = sum(counts[k] for k in ("pass", "fail", "partial"))
    out["measurable_passed"] = counts["pass"]
    return out


_STATUS_MARK = {
    "pass":    "✅",
    "fail":    "❌",
    "partial": "⚠️",
    "blocked": "⊘",
    "n/a":     "·",
    "skip":    "?",
}


def format_summary_md(dash: dict[str, Any]) -> str:
    lines = ["# PRD §10 Success Criteria — Dashboard"]
    items = dash.get("items") or []

    counts = dash.get("counts", {})
    n_mes = dash.get("measurable_total", 0)
    n_pass = dash.get("measurable_passed", 0)

    lines.append(
        f"\n**측정 가능 항목**: {n_pass} pass / {n_mes} measurable "
        f"(⊘ {counts.get('blocked', 0)} LLM 필요, "
        f"· {counts.get('n/a', 0)} 외부 측정, "
        f"⚠️ {counts.get('partial', 0)} 부분, ❌ {counts.get('fail', 0)} 미달)"
    )

    lines.append("\n| ID | 기준 | 상태 | 상세 |")
    lines.append("|---|---|:---:|---|")
    title_map = {cid: title for cid, title, _ in CRITERIA}
    for it in items:
        cid = it["id"]
        mark = _STATUS_MARK.get(it["status"], "?")
        lines.append(
            f"| §{cid} | {title_map.get(cid, '?')} | {mark} | {it['detail']} |"
        )

    lines.append("\n## 범례")
    lines.append("- ✅ 자동 측정으로 통과")
    lines.append("- ❌ 자동 측정으로 미달")
    lines.append("- ⚠️ 부분 충족")
    lines.append("- ⊘ LLM_API_KEY 또는 운영 trace 필요 (본 dashboard 범위 밖)")
    lines.append("- · 외부 측정 (docker / git / ENV)")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(prog="eval.metrics.prd_dashboard")
    ap.add_argument("-o", "--out", help="md 저장 경로 (생략 시 stdout)")
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    ap.add_argument("--log-level", default="WARNING")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level)

    dash = collect_dashboard()
    if args.json:
        text = json.dumps(dash, ensure_ascii=False, indent=2)
    else:
        text = format_summary_md(dash)

    if args.out:
        from pathlib import Path
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        log.info("저장: %s", args.out)
    else:
        print(text)


if __name__ == "__main__":
    main()


__all__ = ["CRITERIA", "collect_dashboard", "format_summary_md"]
