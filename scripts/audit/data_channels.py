#!/usr/bin/env python3
"""제조 공정·생산 데이터 채널 트래픽라이트.

각 채널의 raw 파일 / PG row / Neo4j 엣지 상태를 한눈에:
    🟢 green   — PG/Neo4j 에 데이터 적재됨
    🟡 yellow  — raw 만 있고 PG/Neo4j 미적재 (loader 실행 대기)
    🔴 red     — 아무 데이터 없음 (raw 도 없음, ingest 필요)

대상 채널:
    - 산단공 합성 공정 (15151075) — CSV / auto.processes
    - DART 사업보고서 production — zip / auto.plant_capacity + plant_production
      + Neo4j MANUFACTURED_AT
    - KAMA 매크로 — CSV / auto.macro_production_yearly + macro_industry_monthly
    - 팩토리온 (15087611) — API / (스키마 미정)
    - 한국 리콜 (15089863) — API / auto.events_recalls WHERE source='datagokr_kotsa'

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
    except Exception as exc:   # noqa: BLE001
        return f"?({type(exc).__name__})"


def _try_neo4j_count(cypher: str) -> int | str:
    try:
        from autonexusgraph.db.neo4j import get_driver
        with get_driver().session() as s:
            r = s.run(cypher).single()
            return int(r["n"]) if r else 0
    except Exception as exc:   # noqa: BLE001
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
    sandang_pg = _try_pg_count("SELECT count(*) FROM auto.processes")
    out.append(ChannelStatus(
        name="산단공 합성 공정 (15151075)",
        raw_count=sandang_csvs,
        raw_detail="CSV file(s)",
        pg_count=sandang_pg,
        pg_detail="auto.processes",
        notes="C 등급 (합성), 공정명 taxonomy 사전",
    ))

    # DART production
    dart_corps = ["00164742", "00106641", "00164788", "00161125",
                  "01042775", "00106623"]
    dart_zips = sum(_count_files(raw_root / "dart_bulk" / "corp" / cc / "documents",
                                  "*.zip")
                    for cc in dart_corps)
    dart_capa = _try_pg_count("SELECT count(*) FROM auto.plant_capacity")
    dart_prod = _try_pg_count("SELECT count(*) FROM auto.plant_production")
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
    kama_yearly_pg = _try_pg_count("SELECT count(*) FROM auto.macro_production_yearly")
    kama_monthly_pg = _try_pg_count("SELECT count(*) FROM auto.macro_industry_monthly")
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

    # 팩토리온 (15087611)
    factoryon_dir = raw_root / "auto" / "factoryon"
    factoryon_files = _count_files(factoryon_dir, "**/*.json")
    out.append(ChannelStatus(
        name="팩토리온 공장등록 (15087611)",
        raw_count=factoryon_files,
        raw_detail="JSON pages (key 필요)",
        pg_count="N/A",
        pg_detail="(스키마 미정 — 키 도착 후 정의)",
        notes="DATA_GO_KR_API_KEY 필요",
    ))

    # 한국 리콜 (15089863)
    datagokr_recalls_dir = raw_root / "auto" / "datagokr_recalls"
    datagokr_files = _count_files(datagokr_recalls_dir, "page_*.json")
    datagokr_pg = _try_pg_count(
        "SELECT count(*) FROM auto.events_recalls WHERE source='datagokr_kotsa'"
    )
    out.append(ChannelStatus(
        name="한국 리콜 (15089863, KOTSA)",
        raw_count=datagokr_files,
        raw_detail="page JSON (key 필요)",
        pg_count=datagokr_pg,
        pg_detail="auto.events_recalls",
        notes="DATA_GO_KR_API_KEY 필요",
    ))

    # 한국 수리검사 (15155857)
    inspections_files = _count_files(raw_root / "datagokr",
                                      "*수리검사*.csv")
    inspections_pg = _try_pg_count(
        "SELECT count(*) FROM auto.events_inspections"
    )
    out.append(ChannelStatus(
        name="한국 수리검사 (15155857, KOTSA)",
        raw_count=inspections_files,
        raw_detail="CSV 파일 다운",
        pg_count=inspections_pg,
        pg_detail="auto.events_inspections",
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
    oem_news_pg = _try_pg_count("SELECT count(*) FROM auto.events_oem_news")
    out.append(ChannelStatus(
        name="OEM IR/뉴스룸 (Hyundai+Kia ww)",
        raw_count=n_hyundai_meta + n_kia_ww_meta,
        raw_detail=f"hyundai={n_hyundai_meta} + kia_worldwide={n_kia_ww_meta}",
        pg_count=oem_news_pg,
        pg_detail="auto.events_oem_news",
        notes="B 등급. Kia 한국·Mobis 비활성 (robots Disallow / SPA)",
    ))

    # DART 가동률 (2026-06-01 신규)
    util_pg = _try_pg_count("SELECT count(*) FROM auto.plant_utilization")
    out.append(ChannelStatus(
        name="DART 가동률 (utilization, Hyundai)",
        raw_count="포함",
        raw_detail="(DART zip 재사용)",
        pg_count=util_pg,
        pg_detail="auto.plant_utilization",
        notes="B 등급. Hyundai 사업보고서 III.(3) — explicit utilization_pct",
    ))

    # vec.chunks OEM IR + Wikipedia plants
    chunks_ir = _try_pg_count("SELECT count(*) FROM vec.chunks WHERE source='oem_ir'")
    chunks_plants = _try_pg_count(
        "SELECT count(*) FROM vec.chunks WHERE source='wikipedia_auto' AND metadata->>'kind'='plants'"
    )
    out.append(ChannelStatus(
        name="vec.chunks — OEM IR + Wiki plants",
        raw_count="from PG",
        raw_detail="2 sources",
        pg_count=(chunks_ir if isinstance(chunks_ir, int) else 0)
                  + (chunks_plants if isinstance(chunks_plants, int) else 0),
        pg_detail=f"oem_ir={chunks_ir} + wiki/plants={chunks_plants}",
        notes="P3 LLM 추출 가능 (run_p3_ir.py / IRRelationExtractor)",
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
