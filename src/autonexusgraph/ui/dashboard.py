"""AutoNexusGraph 현황 대시보드 — DB 적재 / DoD §10 / thesis 실측 / 최근 audit.

채팅 UI 와 별도. core 무변경, 표시만(데이터 계층은 DB 직접 조회 + data/reports/ 리포트 파일).
기동:
    streamlit run src/autonexusgraph/ui/dashboard.py
    # 또는 make serve-dashboard

표기 규약: 상태는 데이터에서 파생한 텍스트(달성/미달/미측정)로만 — 장식 이모지 미사용.
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="AutoNexusGraph 현황", layout="wide")
st.title("AutoNexusGraph 현황 대시보드")
st.caption("DB 적재량 · DoD §10 충족 · thesis 실측 · 최근 audit/eval 결과. "
           "수치는 live DB 조회 + data/reports/ 리포트에서 읽는다.")

_REPORTS = Path("data/reports")


# ─────────────────────────── 데이터 헬퍼 ───────────────────────────
@st.cache_data(ttl=60)
def _pg_counts() -> list[tuple[str, str, object]]:
    """주요 PG 테이블 row 수 — (도메인, 테이블, count|에러)."""
    rows: list[tuple[str, str, object]] = []
    try:
        import sys
        sys.path.insert(0, "src")
        from autonexusgraph.db.postgres import get_connection
        conn = get_connection()
        targets = [
            ("finance", "anxg_master.companies"),
            ("finance", "anxg_fin.financials"),
            ("finance", "anxg_fin.filings"),
            ("finance", "anxg_master.persons"),
            ("vector", "anxg_vec.chunks"),
            ("auto", "anxg_auto.master_manufacturers"),
            ("auto", "anxg_auto.master_vehicle_models"),
            ("auto", "anxg_auto.events_recalls"),
            ("auto", "anxg_auto.processes"),
            ("bridge", "anxg_bridge.corp_entity"),
            ("ip", "anxg_ip.cpc_scheme"),
            ("ip", "anxg_ip.works"),
        ]
        for dom, tbl in targets:
            cur = conn.cursor()
            try:
                cur.execute(f"SELECT count(*) FROM {tbl}")  # noqa: S608 — 정적 테이블명
                rows.append((dom, tbl, cur.fetchone()[0]))
            except Exception as e:  # noqa: BLE001 — 테이블 부재 등은 셀별 에러로 표시
                conn.rollback()
                rows.append((dom, tbl, f"(에러: {str(e)[:40]})"))
    except Exception as e:  # noqa: BLE001 — DB 연결 실패는 전체 에러 행으로 표시
        rows.append(("-", "PG 연결", f"(실패: {str(e)[:60]})"))
    return rows


@st.cache_data(ttl=60)
def _neo4j_counts() -> list[tuple[str, object]]:
    """주요 Neo4j 라벨/관계 수 — (이름, count|에러)."""
    out: list[tuple[str, object]] = []
    queries = [
        ("Company 노드", "MATCH (c:Anxg_Company) RETURN count(c) AS n"),
        ("Person 노드", "MATCH (p:Anxg_Person) RETURN count(p) AS n"),
        ("Person distinct(name,by)",
         "MATCH (p:Anxg_Person) RETURN count(DISTINCT [p.name, p.birth_year]) AS n"),
        ("SUBSIDIARY_OF", "MATCH ()-[r:SUBSIDIARY_OF]->() RETURN count(r) AS n"),
        ("EXECUTIVE_OF", "MATCH ()-[r:EXECUTIVE_OF]->() RETURN count(r) AS n"),
        ("Patent CPCCode", "MATCH (c:Anxg_CPCCode) RETURN count(c) AS n"),
        ("vec chunks(Neo4j 미러 없음)", None),
    ]
    try:
        import sys
        sys.path.insert(0, "src")
        from autonexusgraph.db.neo4j import get_session
        with get_session() as s:
            for name, q in queries:
                if q is None:
                    continue
                try:
                    out.append((name, s.run(q).single()["n"]))
                except Exception as e:  # noqa: BLE001 — 개별 쿼리 실패는 셀별 에러로 표시
                    out.append((name, f"(에러: {str(e)[:40]})"))
    except Exception as e:  # noqa: BLE001 — Neo4j 연결 실패는 전체 에러 행으로 표시
        out.append(("Neo4j 연결", f"(실패: {str(e)[:60]})"))
    return out


def _latest(pattern: str) -> Path | None:
    files = sorted(glob.glob(str(_REPORTS / pattern)), key=os.path.getmtime, reverse=True)
    return Path(files[0]) if files else None


# ─────────────────────────── 1. DB 적재 현황 ───────────────────────────
st.header("1. DB 적재 현황")
col_pg, col_neo = st.columns(2)
with col_pg:
    st.subheader("PostgreSQL")
    st.table([{"도메인": d, "테이블": t, "row": c} for d, t, c in _pg_counts()])
with col_neo:
    st.subheader("Neo4j")
    st.table([{"항목": n, "수": c} for n, c in _neo4j_counts()])
    dups = next((c for n, c in _neo4j_counts() if n == "Person 노드"), None)
    dist = next((c for n, c in _neo4j_counts() if n == "Person distinct(name,by)"), None)
    if isinstance(dups, int) and isinstance(dist, int) and dups > dist:
        st.warning(f"Person 중복 노드 {dups - dist}개 (dedup 미적용 — "
                   "scripts/migrate/dedup_persons_neo4j.py).")


# ─────────────────────────── 2. DoD §10 현황 ───────────────────────────
st.header("2. DoD §10 충족 현황")
dod_md = Path("eval/reports/prd_dashboard_latest.md")
if dod_md.exists():
    st.caption(f"출처: {dod_md} (생성: `make audit-dod`)")
    st.markdown(dod_md.read_text(encoding="utf-8"))
else:
    st.info("DoD dashboard 미생성 — `make audit-dod` 실행 후 갱신.")


# ─────────────────────────── 3. thesis 실측 ───────────────────────────
st.header("3. thesis 실측 (Hybrid vs Vector)")
matrix = _latest("audit_eval_matrix_*.json")
if matrix:
    data = json.loads(matrix.read_text(encoding="utf-8"))
    t = data.get("thesis", {})
    st.caption(f"출처: {matrix.name} (mode={data.get('mode')}, cells={data.get('n_cells')})")
    c1, c2, c3 = st.columns(3)
    c1.metric("vector hits@k", t.get("vector_hits"))
    c2.metric("hybrid hits@k", t.get("hybrid_hits"))
    diff = t.get("hits_diff_pp")
    c3.metric("hybrid − vector", f"{diff}%p" if diff is not None else "n/a",
              help="목표 +30%p. 음수면 thesis 미달(가설 반증).")
    target_met = t.get("target_met")
    st.write(f"목표(+30%p) 충족: **{'달성' if target_met else '미달(반증)'}** · "
             f"EM 상태: `{t.get('em_status')}` (scorable {t.get('em_scorable_n')})")
    dod14 = data.get("dod_14", {})
    if dod14.get("available"):
        st.write(f"§10.14 latency internal pass-rate: "
                 f"**{dod14.get('internal_pass_rate')}** (목표 {dod14.get('target_internal')})")
else:
    st.info("eval matrix 리포트 없음 — `make audit-eval-matrix --full` (LLM 키 필요).")


# ─────────────────────────── 4. 최근 audit/eval ───────────────────────────
st.header("4. 최근 audit / eval 리포트")
recent = sorted(glob.glob(str(_REPORTS / "audit_*.json")),
                key=os.path.getmtime, reverse=True)[:10]
table = []
for f in recent:
    p = Path(f)
    kind = p.name.split("_")[1] if "_" in p.name else p.name
    table.append({
        "리포트": p.name,
        "종류": kind,
        "수정시각(UTC)": __import__("datetime").datetime.utcfromtimestamp(
            os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M"),
    })
if table:
    st.table(table)
else:
    st.info("audit 리포트 없음 — `make audit-*` 실행 후 갱신.")

st.divider()
st.caption("본 페이지는 표시 전용. 실 측정/적재는 `make audit-*` / `make load-*` / "
           "`make ingest-*`. 데이터 계층 무변경.")
