"""CPC scheme bulk → anxg_ip.cpc_scheme PG + Neo4j :CPCCode + :SUBCLASS_OF.

CPC = Cooperative Patent Classification (USPTO+EPO 공동). 본 PR 은 section/class/
subclass/main_group/subgroup 전 레벨 적재. 입력: CPCTitleList20YYMM.zip 의 섹션별
tab-separated text 파일 (9개).

타이틀 파일 형식 (tab 분리, 3 필드):
    code <tab> depth <tab> title

예시:
    A                        HUMAN NECESSITIES
    A01                      AGRICULTURE; ...
    A01B                     SOIL WORKING IN AGRICULTURE ...
    A01B1/00     0           Hand tools
    A01B1/02     1           Spades; Shovels
    A01B1/0207   2           {pointed spades}

레벨/parent 결정:
    - 1자 (A) → section, parent=None
    - 3자 (A01) → class, parent=A
    - 4자 (A01B) → subclass, parent=A01
    - X/00 with depth 0 → main_group, parent=subclass (4자 prefix)
    - depth ≥ 1 → subgroup, parent=직전 동일 subclass 의 depth-1 entry

PRD §3.5: CPC = A 등급 → confidence 0.95.

CLI:
    python -m ipgraph.loaders.load_cpc           # PG + Neo4j 전체
    python -m ipgraph.loaders.load_cpc --skip-neo4j
    python -m ipgraph.loaders.load_cpc --sections A,B,H   # 일부만
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data/raw/cpc"

_SCHEMA_VERSION = "v2.2"
_CONF_A = 0.95

_EDGE_META = {
    "source_type":       "cpc_scheme",
    "confidence_score":  _CONF_A,
    "validated_status":  "validated",
    "extraction_method": "deterministic",
    "schema_version":    _SCHEMA_VERSION,
    "snapshot_year":     2026,
}


# ── 1. Parser ────────────────────────────────────────────────

def _classify(code: str, depth_str: str) -> tuple[str, int | None]:
    """code → (level, depth or None)."""
    if "/" in code:
        try:
            d = int(depth_str)
        except (TypeError, ValueError):
            d = None
        if d is not None and d == 0:
            return ("main_group", 0)
        return ("subgroup", d if d is not None else 1)
    n = len(code)
    if n == 1:
        return ("section", None)
    if n == 3:
        return ("class", None)
    if n == 4:
        return ("subclass", None)
    return ("unknown", None)


def _parent_of(code: str, level: str, depth: int | None,
               recent_stack: dict[str, list[tuple[str, int]]]) -> str | None:
    """code 의 parent_code 산정.

    recent_stack[subclass] = [(code, depth), ...]  현재 subclass 내 부모 후보 스택.
    """
    if level == "section":
        return None
    if level == "class":
        return code[0]
    if level == "subclass":
        return code[:3]
    if level == "main_group":
        return code[:4]   # subclass
    if level == "subgroup":
        # 동일 subclass 의 depth-1 entry.
        sc = code.split("/")[0][:4]
        stk = recent_stack.get(sc) or []
        target = (depth or 1) - 1
        # 뒤에서 첫 depth ≤ target 인 항목.
        for c, d in reversed(stk):
            if d <= target:
                return c
        return sc   # fallback to subclass.
    return None


def parse_zip(zip_path: Path, *, sections: list[str] | None = None
              ) -> list[dict]:
    """CPCTitleList zip → list of rows."""
    rows: list[dict] = []
    recent_stack: dict[str, list[tuple[str, int]]] = {}
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if m.endswith(".txt")]
        members.sort()
        for member in members:
            # Filename pattern: cpc-section-X_YYYYMMDD.txt
            m = re.match(r"cpc-section-([A-Y])_\d+\.txt", member)
            if not m:
                continue
            sec = m.group(1)
            if sections and sec not in sections:
                continue
            with zf.open(member) as fh:
                for raw in fh:
                    line = raw.decode("utf-8", errors="replace").rstrip("\n")
                    if not line.strip():
                        continue
                    parts = line.split("\t")
                    code = parts[0].strip()
                    depth_str = parts[1].strip() if len(parts) > 1 else ""
                    title = parts[2].strip() if len(parts) > 2 else (
                        " ".join(parts[1:]).strip())
                    if not code:
                        continue
                    level, depth = _classify(code, depth_str)
                    parent = _parent_of(code, level, depth, recent_stack)
                    rows.append({
                        "code": code, "parent_code": parent,
                        "level": level, "depth": depth,
                        "title": title,
                    })
                    # subclass 의 stack 관리 — main_group/subgroup 후속 parent 탐색 용.
                    if level in ("main_group", "subgroup"):
                        sc = code.split("/")[0][:4]
                        st = recent_stack.setdefault(sc, [])
                        # depth 가 더 깊은 항목 pop.
                        d = depth if depth is not None else 0
                        while st and st[-1][1] >= d:
                            st.pop()
                        st.append((code, d))
    return rows


# ── 2. PG UPSERT ────────────────────────────────────────────

def upsert_pg(rows: list[dict]) -> tuple[int, int, int]:
    import psycopg2
    dsn = os.environ.get("POSTGRES_DSN") or _dsn_from_env()
    conn = psycopg2.connect(dsn)
    ins = upd = skip = 0
    try:
        with conn.cursor() as cur:
            # 우선 SQL slot 적용 (멱등).
            slot = ROOT / "infra/postgres/init/23_ip_cpc.sql"
            if slot.exists():
                cur.execute(slot.read_text(encoding="utf-8"))
            # 배치 UPSERT.
            for i, r in enumerate(rows):
                cur.execute("SAVEPOINT sp_cpc")
                try:
                    cur.execute("""
                        INSERT INTO anxg_ip.cpc_scheme
                          (code, parent_code, level, depth, title, raw)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (code) DO UPDATE SET
                          parent_code = COALESCE(EXCLUDED.parent_code, anxg_ip.cpc_scheme.parent_code),
                          level       = EXCLUDED.level,
                          depth       = EXCLUDED.depth,
                          title       = COALESCE(EXCLUDED.title, anxg_ip.cpc_scheme.title),
                          updated_at  = now()
                        RETURNING (xmax = 0) AS is_new
                    """, (r["code"], r.get("parent_code"), r["level"],
                          r.get("depth"), r.get("title") or None,
                          json.dumps({}, ensure_ascii=False)))
                    is_new = bool(cur.fetchone()[0])
                    if is_new:
                        ins += 1
                    else:
                        upd += 1
                    cur.execute("RELEASE SAVEPOINT sp_cpc")
                    if (i + 1) % 5000 == 0:
                        conn.commit()
                        log.info("[cpc:pg] progress %d", i + 1)
                except Exception as exc:   # noqa: BLE001 — [cpc:pg] CPC row UPSERT 실패 흡수 → SAVEPOINT rollback + skip + 다음 row
                    cur.execute("ROLLBACK TO SAVEPOINT sp_cpc")
                    log.warning("[cpc:pg] %s fail: %s", r.get("code"), exc)
                    skip += 1
        conn.commit()
    finally:
        conn.close()
    return ins, upd, skip


# ── 3. Neo4j MERGE ──────────────────────────────────────────

def load_neo4j(rows: list[dict]) -> dict:
    logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)
    from neo4j import GraphDatabase
    drv = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"]),
    )
    stats = {"nodes_merged": 0, "subclass_of_merged": 0}
    try:
        with drv.session(database=os.environ.get("NEO4J_DATABASE") or None) as s:
            s.run("CREATE CONSTRAINT cpc_code IF NOT EXISTS "
                  "FOR (c:Anxg_CPCCode) REQUIRE c.code IS UNIQUE")
            s.run("CREATE INDEX cpc_level IF NOT EXISTS "
                  "FOR (c:Anxg_CPCCode) ON (c.level)")

            # 노드 — 일괄 UNWIND.
            batch = 1000
            for i in range(0, len(rows), batch):
                chunk = rows[i:i + batch]
                s.run("""
                    UNWIND $rows AS r
                    MERGE (c:Anxg_CPCCode {code: r.code})
                    SET c.level = r.level,
                        c.depth = r.depth,
                        c.title = r.title,
                        c.updated_at = datetime()
                """, rows=chunk)
                stats["nodes_merged"] += len(chunk)

            # 엣지 — SUBCLASS_OF (child → parent).
            for i in range(0, len(rows), batch):
                chunk = [r for r in rows[i:i + batch] if r.get("parent_code")]
                if not chunk:
                    continue
                s.run("""
                    UNWIND $rows AS r
                    MATCH (child:Anxg_CPCCode {code: r.code})
                    WITH child, r
                    MATCH (parent:Anxg_CPCCode {code: r.parent_code})
                    MERGE (child)-[e:SUBCLASS_OF]->(parent)
                    SET e.source_type       = $source_type,
                        e.source_id         = 'cpc_scheme_2026',
                        e.confidence_score  = $confidence_score,
                        e.validated_status  = $validated_status,
                        e.snapshot_year     = $snapshot_year,
                        e.extraction_method = $extraction_method,
                        e.schema_version    = $schema_version,
                        e.updated_at        = datetime()
                """, rows=chunk, **_EDGE_META)
                stats["subclass_of_merged"] += len(chunk)
    finally:
        drv.close()
    return stats


def _dsn_from_env() -> str:
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("POSTGRES_DSN="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("POSTGRES_DSN 미설정")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", type=str,
                    default=str(RAW_DIR / "CPCTitleList202605.zip"))
    ap.add_argument("--sections", type=str, default=None,
                    help="콤마 분리 섹션 (예 A,B,H) — 기본 전체")
    ap.add_argument("--include-subgroups", action="store_true",
                    help="subgroup (~250K row) 포함. 기본 = section/class/subclass/main_group 만")
    ap.add_argument("--skip-neo4j", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    sections = [s.strip() for s in args.sections.split(",")] if args.sections else None
    zp = Path(args.zip)
    if not zp.exists():
        log.error("[cpc] zip 미존재: %s — make ingest-cpc 먼저 실행", zp)
        return 1
    log.info("[cpc] parsing %s", zp.name)
    rows = parse_zip(zp, sections=sections)
    log.info("[cpc] parsed %d rows", len(rows))
    if not args.include_subgroups:
        rows = [r for r in rows if r["level"] != "subgroup"]
        log.info("[cpc] subgroups 제외 → %d rows", len(rows))
    by_level: dict[str, int] = {}
    for r in rows:
        by_level[r["level"]] = by_level.get(r["level"], 0) + 1
    log.info("[cpc] by level: %s", by_level)

    ins, upd, skip = upsert_pg(rows)
    log.info("[cpc:pg] ins=%d upd=%d skip=%d", ins, upd, skip)
    out: dict = {
        "parsed":  len(rows),
        "by_level": by_level,
        "pg":     {"inserted": ins, "updated": upd, "skipped": skip},
    }

    if not args.skip_neo4j:
        out["neo4j"] = load_neo4j(rows)
        log.info("[cpc:neo4j] %s", out["neo4j"])

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["parse_zip", "upsert_pg", "load_neo4j"]
