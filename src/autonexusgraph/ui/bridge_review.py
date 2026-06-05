"""Bridge candidate 검토 UI (Q-1) — name match candidate 를 ✓/✗ 라벨.

기동 (chat UI 와 별도 — core 무변경):
    streamlit run src/autonexusgraph/ui/bridge_review.py

데이터 계층은 ``autonexusgraph.bridge_review`` (사전 정의 함수). 본 파일은 표시만.
"""

from __future__ import annotations

import streamlit as st

from autonexusgraph.bridge_review import (
    auto_expire_stale,
    list_candidates,
    review_progress_kpi,
    set_review_status,
)

st.set_page_config(page_title="Bridge 검토 — AutoNexusGraph", layout="wide")
st.title("Bridge candidate 검토 (Q-1)")
st.caption("`anxg_bridge.corp_entity` 자동 매칭 후보를 사람이 ✓ 승급 / ✗ 거부. "
           "검토자 id 와 시각이 기록됩니다.")

reviewer = st.sidebar.text_input("검토자 id", value="reviewer")
st.sidebar.markdown("---")

# ── 진행률 KPI ──────────────────────────────────────────────────────
try:
    kpi = review_progress_kpi()
except Exception as e:   # noqa: BLE001 — 호출 실패 흡수 → 다음 단계 진행
    st.error(f"KPI 조회 실패 (DB 연결 확인): {e}")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("전체", kpi["total"])
c2.metric("검토 완료율", f"{kpi['reviewed_pct']}%")
c3.metric("대기(candidate)", kpi["pending"])
c4.metric("최장 대기(일)", kpi["oldest_pending_age_days"] or 0)

if kpi["by_entity_type"]:
    with st.expander("유형별 분포"):
        st.dataframe(kpi["by_entity_type"], use_container_width=True)

# ── 자동 만료 ────────────────────────────────────────────────────────
with st.sidebar.expander("자동 만료 (N일 미검토 → 거부)"):
    days = st.number_input("기준 일수", min_value=1, value=180, step=30)
    if st.button("dry-run (대상 수)"):
        st.info(auto_expire_stale(days=int(days), apply=False))
    if st.button("실제 거부 적용", type="primary"):
        st.warning(auto_expire_stale(days=int(days), apply=True))
        st.rerun()

# ── 후보 필터 ────────────────────────────────────────────────────────
st.markdown("### 검토 대상")
f1, f2, f3 = st.columns(3)
entity_type = f1.selectbox("entity_type",
                           ["(전체)", "manufacturer", "supplier", "vehicle_model", "variant"])
match_method = f2.selectbox("match_method",
                            ["(전체)", "name_exact", "name_fuzzy", "wikidata_qid",
                             "lei", "cik", "business_no", "manual"])
limit = f3.slider("표시 수", 5, 100, 25)

rows = list_candidates(
    entity_type=None if entity_type == "(전체)" else entity_type,
    match_method=None if match_method == "(전체)" else match_method,
    limit=limit,
)

if not rows:
    st.success("검토 대기 후보 없음 (해당 필터).")
    st.stop()

st.caption(f"{len(rows)}건 — confidence 낮은 / 오래된 후보 우선. ✓ 승급 · ✗ 거부.")

# ── 후보 라벨링 ──────────────────────────────────────────────────────
for r in rows:
    cols = st.columns([4, 1.2, 1.2, 1.2, 1])
    with cols[0]:
        st.markdown(
            f"**{r.get('name') or '(이름없음)'}**  ·  `{r['entity_type']}`  ·  "
            f"corp={r.get('corp_code') or '—'}  ·  entity={r['entity_id']}  \n"
            f"match=`{r['match_method']}`  conf=**{r['confidence_score']}**  "
            f"qid={r.get('wikidata_qid') or '—'}  대기 {r['age_days']}일"
        )
    if cols[1].button("✓ 승급", key=f"ok-{r['id']}"):
        set_review_status(r["id"], "reviewed", reviewer=reviewer)
        st.rerun()
    if cols[2].button("✗ 거부", key=f"no-{r['id']}"):
        set_review_status(r["id"], "rejected", reviewer=reviewer)
        st.rerun()
    cols[3].caption(f"id={r['id']}")
    st.divider()
