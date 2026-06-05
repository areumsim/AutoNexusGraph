#!/usr/bin/env python3
"""제조 공정·생산 데이터 채널 트래픽라이트.

각 채널의 raw 파일 / PG row / Neo4j 엣지 상태를 한눈에:
    🟢 green   — PG/Neo4j 에 데이터 적재됨
    🟡 yellow  — raw 만 있고 PG/Neo4j 미적재 (loader 실행 대기)
    🔴 red     — 아무 데이터 없음 (raw 도 없음, ingest 필요)

대상 채널:
    - 산단공 합성 공정 (15151075) — CSV / anxg_auto.processes
    - DART 사업보고서 production — zip / anxg_auto.plant_capacity + plant_production
      + Neo4j MANUFACTURED_AT
    - KAMA 매크로 — CSV / anxg_auto.macro_production_yearly + macro_industry_monthly
    - 팩토리온 (15087611) — API / (스키마 미정)
    - 한국 리콜 (3048950 CSV, 구 15089863 API 폐기) — anxg_auto.events_recalls WHERE source='datagokr_kotsa'

출력:
    eval/reports/data_channels_latest.md (기본)
    --stdout 으로 stdout 출력

DB 미가용 시 PG/Neo4j 항목은 "?" 로 표시 + exit 0 (raw 만 보고).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


@dataclass
class ChannelStatus:
    name: str
    raw_count: int | str = "?"
    raw_detail: str = ""
    pg_count: int | str = "?"
    pg_detail: str = ""
    neo4j_count: int | str = "?"
    neo4j_detail: str = ""
    notes: str = ""

    def light(self) -> str:
        """raw + PG/Neo4j 상태로 트래픽라이트 결정."""
        try:
            pg = int(self.pg_count) if self.pg_count != "?" else None
        except (TypeError, ValueError):
            pg = None
        try:
            raw = int(self.raw_count) if self.raw_count != "?" else None
        except (TypeError, ValueError):
            raw = None
        try:
            ng = int(self.neo4j_count) if self.neo4j_count != "?" else None
        except (TypeError, ValueError):
            ng = None

        if pg is not None and pg > 0:
            return "🟢"
        if raw is not None and raw > 0:
            return "🟡"
        if pg == 0 and (raw is None or raw == 0):
            return "🔴"
        return "⊘"   # 미측정


def _try_pg_count(sql: str) -> int | str:
    try:
        from autonexusgraph.db.postgres import get_pool
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql)
            r = cur.fetchone()
            return int(r[0]) if r else 0
    except Exception as exc:   # noqa: BLE001 — fail-soft 흡수 → 기본값 반환
        return f"?({type(exc).__name__})"


def _try_neo4j_count(cypher: str) -> int | str:
    try:
        from autonexusgraph.db.neo4j import get_session
        with get_session() as s:
            r = s.run(cypher).single()
            return int(r["n"]) if r else 0
    except Exception as exc:   # noqa: BLE001 — fail-soft 흡수 → 기본값 반환
        return f"?({type(exc).__name__})"


def _count_files(root: Path, pattern: str) -> int:
    if not root.exists():
        return 0
    return len(list(root.glob(pattern)))


def collect() -> list[ChannelStatus]:
    raw_root = ROOT / "data" / "raw"

    out: list[ChannelStatus] = []

    # 산단공 합성 공정 (15151075)
    sandang_csvs = _count_files(raw_root / "datagokr", "한국산업단지공단_자동차*.csv")
    sandang_pg = _try_pg_count("SELECT count(*) FROM anxg_auto.processes")
    out.append(ChannelStatus(
        name="산단공 합성 공정 (15151075)",
        raw_count=sandang_csvs,
        raw_detail="CSV file(s)",
        pg_count=sandang_pg,
        pg_detail="anxg_auto.processes",
        notes="C 등급 (합성), 공정명 taxonomy 사전",
    ))

    # DART production
    dart_corps = ["00164742", "00106641", "00164788", "00161125",
                  "01042775", "00106623"]
    dart_zips = sum(_count_files(raw_root / "dart_bulk" / "corp" / cc / "documents",
                                  "*.zip")
                    for cc in dart_corps)
    dart_capa = _try_pg_count("SELECT count(*) FROM anxg_auto.plant_capacity")
    dart_prod = _try_pg_count("SELECT count(*) FROM anxg_auto.plant_production")
    dart_pg = (dart_capa if isinstance(dart_capa, int)
               else 0) + (dart_prod if isinstance(dart_prod, int) else 0)
    dart_edges = _try_neo4j_count(
        "MATCH ()-[r:MANUFACTURED_AT]->() "
        "WHERE r.source_type='dart_business_report' RETURN count(r) AS n"
    )
    out.append(ChannelStatus(
        name="DART 사업보고서 production",
        raw_count=dart_zips,
        raw_detail=f"zip files (6 OEM)",
        pg_count=dart_pg,
        pg_detail=f"capacity={dart_capa} + production={dart_prod}",
        neo4j_count=dart_edges,
        neo4j_detail="MANUFACTURED_AT (source=dart)",
        notes="B 등급 (DART), 6 OEM × 모든 사업보고서",
    ))

    # KAMA macro
    kama_yearly_csvs = _count_files(raw_root / "datagokr",
                                     "산업통상부_국내 및 세계 자동차 생산량*.csv")
    kama_monthly_csvs = _count_files(raw_root / "datagokr",
                                      "산업통상부_전체 자동차 산업 현황*.csv")
    kama_yearly_pg = _try_pg_count("SELECT count(*) FROM anxg_auto.macro_production_yearly")
    kama_monthly_pg = _try_pg_count("SELECT count(*) FROM anxg_auto.macro_industry_monthly")
    kama_pg = (kama_yearly_pg if isinstance(kama_yearly_pg, int) else 0) + \
              (kama_monthly_pg if isinstance(kama_monthly_pg, int) else 0)
    out.append(ChannelStatus(
        name="KAMA 매크로 통계 (15051116+15051118)",
        raw_count=kama_yearly_csvs + kama_monthly_csvs,
        raw_detail=f"yearly={kama_yearly_csvs} + monthly={kama_monthly_csvs}",
        pg_count=kama_pg,
        pg_detail=f"yearly={kama_yearly_pg} + monthly={kama_monthly_pg}",
        notes="A 등급 (KAMA), 매크로 시계열 (key 불필요!)",
    ))

    # 팩토리온 (15087611) — M-11 단계에서 PG 스키마 + loader 완성.
    factoryon_dir = raw_root / "auto" / "factoryon"
    factoryon_files = _count_files(factoryon_dir, "**/*.json")
    factoryon_pg = _try_pg_count("SELECT count(*) FROM anxg_auto.factoryon_registry")
    out.append(ChannelStatus(
        name="팩토리온 공장등록 (15087611)",
        raw_count=factoryon_files,
        raw_detail="JSON pages (key 필요)",
        pg_count=factoryon_pg,
        pg_detail="anxg_auto.factoryon_registry (24_auto_factoryon.sql)",
        notes="DATA_GO_KR_API_KEY 필요. wire 완료 (load_factoryon.py)",
    ))

    # 한국 리콜 (3048950 CSV — 구 15089863 오픈API 폐기, 무인증 파일데이터)
    datagokr_recall_csvs = _count_files(raw_root / "datagokr",
                                         "*자동차결함 리콜현황*.csv")
    datagokr_pg = _try_pg_count(
        "SELECT count(*) FROM anxg_auto.events_recalls WHERE source='datagokr_kotsa'"
    )
    out.append(ChannelStatus(
        name="한국 리콜 (3048950, KOTSA)",
        raw_count=datagokr_recall_csvs,
        raw_detail="CSV 파일 다운",
        pg_count=datagokr_pg,
        pg_detail="anxg_auto.events_recalls",
        notes="키 불필요 (파일 다운로드)",
    ))

    # 한국 수리검사 (15155857)
    inspections_files = _count_files(raw_root / "datagokr",
                                      "*수리검사*.csv")
    inspections_pg = _try_pg_count(
        "SELECT count(*) FROM anxg_auto.events_inspections"
    )
    out.append(ChannelStatus(
        name="한국 수리검사 (15155857, KOTSA)",
        raw_count=inspections_files,
        raw_detail="CSV 파일 다운",
        pg_count=inspections_pg,
        pg_detail="anxg_auto.events_inspections",
        notes="키 불필요 (파일 다운로드)",
    ))

    # OEM IR / 뉴스룸 — Hyundai 활성, Kia worldwide 활성, Mobis/Kia 한국 비활성
    oem_ir_root = raw_root / "auto" / "oem_ir"
    def _meta_n(oem):
        p = oem_ir_root / oem / "_meta.jsonl"
        if not p.exists():
            return 0
        return sum(1 for line in p.read_text().splitlines() if line.strip())
    n_hyundai_meta = _meta_n("hyundai")
    n_kia_ww_meta  = _meta_n("kia_worldwide")
    oem_news_pg = _try_pg_count("SELECT count(*) FROM anxg_auto.events_oem_news")
    out.append(ChannelStatus(
        name="OEM IR/뉴스룸 (Hyundai+Kia ww)",
        raw_count=n_hyundai_meta + n_kia_ww_meta,
        raw_detail=f"hyundai={n_hyundai_meta} + kia_worldwide={n_kia_ww_meta}",
        pg_count=oem_news_pg,
        pg_detail="anxg_auto.events_oem_news",
        notes="B 등급. Kia 한국·Mobis 비활성 (robots Disallow / SPA)",
    ))

    # DART 가동률 (2026-06-01 신규)
    util_pg = _try_pg_count("SELECT count(*) FROM anxg_auto.plant_utilization")
    out.append(ChannelStatus(
        name="DART 가동률 (utilization, Hyundai)",
        raw_count="포함",
        raw_detail="(DART zip 재사용)",
        pg_count=util_pg,
        pg_detail="anxg_auto.plant_utilization",
        notes="B 등급. Hyundai 사업보고서 III.(3) — explicit utilization_pct",
    ))

    # anxg_vec.chunks OEM IR + Wikipedia plants + DART narrative (LLM P3 가능)
    chunks_ir = _try_pg_count("SELECT count(*) FROM anxg_vec.chunks WHERE source='oem_ir'")
    chunks_plants = _try_pg_count(
        "SELECT count(*) FROM anxg_vec.chunks WHERE source='wikipedia_auto' AND metadata->>'kind'='plants'"
    )
    chunks_narrative = _try_pg_count(
        "SELECT count(*) FROM anxg_vec.chunks WHERE source='dart_narrative'"
    )
    total_ir_p3 = sum(
        v if isinstance(v, int) else 0
        for v in (chunks_ir, chunks_plants, chunks_narrative)
    )
    out.append(ChannelStatus(
        name="anxg_vec.chunks — IR + Wiki plants + DART narrative",
        raw_count="from PG",
        raw_detail="3 sources",
        pg_count=total_ir_p3,
        pg_detail=f"oem_ir={chunks_ir} + wiki/plants={chunks_plants} + dart_narrative={chunks_narrative}",
        notes="P3 LLM 추출 가능 (run_p3_ir.py / IRRelationExtractor)",
    ))

    # ── 신규 4 오픈데이터 채널 (opendata_patch.md) ────────────────────
    # 1) USGS MCS — 핵심광물 L6.
    usgs_raw = _count_files(ROOT / "data/raw/usgs_mcs", "mcs*.pdf")
    out.append(ChannelStatus(
        name="USGS MCS — 핵심광물 L6 (Li/Ni/Co/Mn/Graphite)",
        raw_count=usgs_raw, raw_detail="MCS PDF 5+ files",
        pg_count=_try_pg_count("SELECT count(*) FROM anxg_auto.master_minerals"),
        pg_detail="anxg_auto.master_minerals",
        neo4j_count=_try_neo4j_count(
            "MATCH ()-[r:DERIVED_FROM]->() RETURN count(r)"),
        neo4j_detail="DERIVED_FROM 엣지 (Material→Mineral, 7-key 100%)",
        notes="A 등급 (USGS, 무인증). materials_seed.yaml = 6 cathode chem",
    ))
    # 2) GLEIF KR enrich — bridge 품질 보강.
    gleif_pages = _count_files(ROOT / "data/raw/gleif/kr", "gleif_kr_p*.json")
    out.append(ChannelStatus(
        name="GLEIF KR enrich — Bridge 품질 (LEI↔corp_code)",
        raw_count=gleif_pages, raw_detail="raw JSON pages (KR 2,704 LEI)",
        pg_count=_try_pg_count(
            "SELECT count(*) FROM anxg_master.entity_map WHERE id_type='lei'"),
        pg_detail="anxg_master.entity_map(id_type='lei')",
        neo4j_count="N/A", neo4j_detail="PG-only",
        notes="A 등급 (GLEIF API CC BY 4.0, 무인증). registeredAs → business_no/jurir_no 매칭",
    ))
    # 3) OpenAlex Work/Institution.
    oa_inst = _count_files(ROOT / "data/raw/openalex", "institution_*.json")
    out.append(ChannelStatus(
        name="OpenAlex — Work / Institution / AUTHORED_AT",
        raw_count=oa_inst, raw_detail="institution JSON snapshots",
        pg_count=_try_pg_count("SELECT count(*) FROM anxg_ip.works"),
        pg_detail="anxg_ip.works (+anxg_ip.institution +anxg_ip.work_institution)",
        neo4j_count=_try_neo4j_count(
            "MATCH ()-[r:AUTHORED_AT]->() RETURN count(r)"),
        neo4j_detail="AUTHORED_AT (7-key 100%) + IS_ENTITY (→Company)",
        notes="A 등급 (OpenAlex CC0). OPENALEX_API_KEY 사용. abstract→anxg_vec.chunks",
    ))
    # 4) data.go.kr EV chargers — 본 PR 보류 (사용자 결정).
    out.append(ChannelStatus(
        name="EV 충전소 (data.go.kr B552584/B553530)",
        raw_count=0, raw_detail="(보류 — 사용자 결정)",
        pg_count="N/A", pg_detail="SQL 슬롯만 존재",
        neo4j_count="N/A", neo4j_detail="—",
        notes="DATA_GO_KR_API_KEY 발급 + 활용신청 필요. 본 PR 미진행",
    ))

    # ── M-13/M-14 (제조 데이터 끝까지) 추가 채널 ───────────────────────
    # KOSIS 산업 통계 — kosis.kr/openapi
    kosis_files = _count_files(ROOT / "data/raw/kosis", "**/*.json")
    out.append(ChannelStatus(
        name="KOSIS 산업 통계 (kosis.kr)",
        raw_count=kosis_files, raw_detail="raw JSON (stat_code/period)",
        pg_count=_try_pg_count("SELECT count(*) FROM anxg_macro.kosis_series"),
        pg_detail="anxg_macro.kosis_series (04_external_data.sql)",
        neo4j_count="N/A", neo4j_detail="—",
        notes="A 등급 (공공). KOSIS_API_KEY 필요. wire 완료 (load_kosis_industry.py)",
    ))

    # Wikidata cathode chemistry — CC0 무인증.
    cell_chem_files = _count_files(ROOT / "data/raw/auto/wikidata_cell_chem", "*.json")
    out.append(ChannelStatus(
        name="Wikidata 배터리 셀 chem (cathode)",
        raw_count=cell_chem_files, raw_detail="cathode_chem_YYYY.json",
        pg_count="N/A", pg_detail="materials_seed.yaml manual seed 활용",
        neo4j_count=_try_neo4j_count(
            "MATCH (m:Anxg_Material) WHERE m.source='wikidata' RETURN count(m)"),
        neo4j_detail=":Material (Wikidata 보강)",
        notes="B 등급 (Wikidata CC0). 회사단위 셀↔OEM 소싱은 grade C candidate (PRD §2.3)",
    ))

    return out


def render_md(statuses: list[ChannelStatus]) -> str:
    lines = [
        "# 제조 공정·생산 데이터 채널 — 트래픽라이트",
        f"\n측정일: {date.today().isoformat()}\n",
        "| 상태 | 채널 | raw | PG | Neo4j | 비고 |",
        "|:---:|---|---:|---:|---:|---|",
    ]
    for s in statuses:
        lines.append(
            f"| {s.light()} | {s.name} | "
            f"{s.raw_count} ({s.raw_detail}) | "
            f"{s.pg_count} ({s.pg_detail}) | "
            f"{s.neo4j_count} ({s.neo4j_detail}) | "
            f"{s.notes} |"
        )
    lines.append("\n## 범례")
    lines.append("- 🟢 적재 완료 (PG 또는 Neo4j 에 row 존재)")
    lines.append("- 🟡 raw 만 있고 적재 대기 (loader 실행 필요)")
    lines.append("- 🔴 raw 도 없음 (ingest/다운로드 필요)")
    lines.append("- ⊘ 측정 불가 (DB 미가용 등)")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(prog="data_channels",
                                  description=__doc__.split("\n")[0])
    ap.add_argument("--stdout", action="store_true",
                    help="파일 저장 대신 stdout 출력")
    ap.add_argument("--out", type=Path, default=None,
                    help="md 저장 경로 (기본 eval/reports/data_channels_latest.md)")
    args = ap.parse_args()

    statuses = collect()
    md = render_md(statuses)

    if args.stdout:
        print(md)
        return 0

    out = args.out or (ROOT / "eval" / "reports" / "data_channels_latest.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md + "\n", encoding="utf-8")
    print(f"[data_channels] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
