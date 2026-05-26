"""Streamlit 렌더링 component — citation expander / cost badge / grounding warning.

설계 메모 (이전 web/ui.py 의 카드 패턴 — namespace selector 같은 BNT 특화는 제외):
- 답변 본문에 citation expander
- 사이드바에 비용 누적 + LLM provider 표시
- grounding warning 이 있으면 노란 박스
"""

from __future__ import annotations

from typing import Any


def render_citations(citations: list[dict]) -> None:
    """답변 아래 출처 expander."""
    import streamlit as st
    if not citations:
        return
    with st.expander(f"출처 {len(citations)}건"):
        for i, c in enumerate(citations, 1):
            corp = c.get("corp_code") or ""
            year = c.get("fiscal_year") or ""
            section = (c.get("section") or "")[:40]
            score = c.get("score")
            rcept = c.get("rcept_no") or ""
            score_s = f" sim={score:.3f}" if score is not None else ""
            st.markdown(
                f"**[{i}]** `corp={corp}` `year={year}` "
                f"`section={section}` `rcept={rcept}`{score_s}"
            )


def render_grounding_warning(grounding: dict | None) -> None:
    """grounding.ok=False 시 노란 박스 + 사유 노출."""
    import streamlit as st
    if not grounding:
        return
    if grounding.get("ok"):
        return
    warnings = grounding.get("warnings") or []
    if not warnings:
        return
    st.warning(
        "⚠️ 답변 근거 검증 경고: "
        + ", ".join(warnings)
        + f" (overlap={grounding.get('overlap_ratio', 0):.2f}, "
        f"cit={grounding.get('citation_count', 0)})"
    )


def render_agent_trace(trace: dict[str, Any]) -> None:
    """agent_trace 요약 — question_kind / targets / tool 호출 수 / 비용."""
    import streamlit as st
    if not trace:
        return
    items: list[str] = []
    if trace.get("question_kind"):
        items.append(f"유형: `{trace['question_kind']}`")
    targets = trace.get("target_companies") or trace.get("targets") or []
    if targets:
        items.append(f"회사: `{', '.join(targets[:3])}`")
    if trace.get("n_tool_results") is not None:
        items.append(f"도구: `{trace['n_tool_results']}`")
    if trace.get("cost_usd") is not None:
        items.append(f"비용: `${trace['cost_usd']:.4f}`")
    if trace.get("aborted_reason"):
        items.append(f"⚠️ aborted: `{trace['aborted_reason']}`")
    if items:
        st.caption(" · ".join(items))


def render_cost_badge(cumulative_usd: float, turn_usd: float = 0.0) -> None:
    """사이드바 — 세션 비용 누적 + 최근 turn 비용."""
    import streamlit as st
    st.metric(
        label="누적 LLM 비용 (USD)",
        value=f"${cumulative_usd:.4f}",
        delta=f"+${turn_usd:.4f}" if turn_usd else None,
    )


def render_provider_info() -> None:
    """사이드바 — 현재 LLM provider / model 표시."""
    import streamlit as st
    from ..config import get_settings
    s = get_settings()
    st.caption(f"LLM: `{s.llm_provider}` / `{s.llm_model}`")
    st.caption(f"임베딩: `{s.embedding_url}` (dim {s.embedding_dim})")


def render_sample_questions() -> str | None:
    """샘플 질문 클릭 시 그 텍스트 반환 (input 으로 전달)."""
    import streamlit as st
    samples = [
        "삼성전자 2024년 매출은?",
        "삼성전자 자회사 중 매출 1조 이상은?",
        "현대자동차의 주요 사업 위험요인은?",
        "이재용이 임원인 회사들은?",
        "삼성그룹 계열사 중 ESG A+ 등급은?",
    ]
    with st.sidebar.expander("샘플 질문"):
        for q in samples:
            if st.button(q, key=f"sample_{q[:20]}"):
                return q
    return None
