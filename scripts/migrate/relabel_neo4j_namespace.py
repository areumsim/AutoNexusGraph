#!/usr/bin/env python3
"""Neo4j 라벨 namespace 마이그레이션 — 기존 노드 라벨에 프로젝트 프리픽스 부여.

공유 Neo4j 서버에서 AutoNexusGraph 데이터를 타 프로젝트와 격리하기 위해, 모든 노드
라벨을 ``<App>`` → ``Anxg_<App>`` (config ``app_namespace`` 기반) 로 relabel 한다.
**관계 타입은 변경하지 않는다** (라벨만 namespace 대상). 코드(Cypher 템플릿/로더)는 이미
프리픽스 라벨을 쓰므로, 기존 적재된 DB 도 본 스크립트로 한 번 옮겨야 일치한다.

특징:
- **멱등**: bare 라벨 노드가 없으면 no-op. 재실행 안전.
- apoc 있으면 ``apoc.periodic.iterate`` 로 배치, 없으면 단일 트랜잭션.
- ``NEO4J_DATABASE`` (config ``neo4j_database``) 격리 db 대상.
- bare 라벨 대상 orphan constraint/index 는 drop (프리픽스 라벨용은 로더가 IF NOT EXISTS 재생성).

사용:
    python scripts/migrate/relabel_neo4j_namespace.py            # 실제 실행
    python scripts/migrate/relabel_neo4j_namespace.py --dry-run  # 카운트만
    python scripts/migrate/relabel_neo4j_namespace.py --drop-old-constraints
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from autonexusgraph.config import get_settings  # noqa: E402
from autonexusgraph.db.neo4j import get_session  # noqa: E402
from autonexusgraph.ontology.domain import _DOMAIN_MAP  # noqa: E402

log = logging.getLogger("relabel_neo4j_namespace")

# 노드 라벨(관계 타입 제외)의 **권위 SSOT = `ontology/domain.py` `_DOMAIN_MAP`** — 하드코딩 대신
# 레지스트리에서 파생해 드리프트 방지(과거 Component/FailureMode 누락 사고 재발 방지).
# `Sector` 는 `scripts/migrate_neo4j_schema.py` 가 → Industry 로 폐기(0 노드)하므로 제외.
# 레지스트리 밖 템플릿 전용 라벨(Cell/Product 등)도 포함 — DB 에 0 노드면 무해 no-op.
_TEMPLATE_ONLY_LABELS = {"Cell", "Product"}
NODE_LABELS = sorted((set(_DOMAIN_MAP) | _TEMPLATE_ONLY_LABELS) - {"Sector"})


def _prefixed(label: str) -> str:
    return get_settings().neo4j_label(label)


def _has_apoc(session) -> bool:
    try:
        session.run("RETURN apoc.version() AS v").single()
        return True
    except Exception:
        return False


def relabel(dry_run: bool = False, drop_old_constraints: bool = False) -> dict:
    stats: dict[str, int] = {}
    with get_session() as s:
        apoc = _has_apoc(s)
        for label in NODE_LABELS:
            new = _prefixed(label)
            n = s.run(f"MATCH (n:`{label}`) RETURN count(n) AS c").single()["c"]
            stats[label] = n
            if not n:
                continue
            log.info("relabel :%s → :%s (%d nodes)%s", label, new, n,
                     " [dry-run]" if dry_run else "")
            if dry_run:
                continue
            if apoc:
                s.run(
                    "CALL apoc.periodic.iterate($m, $u, {batchSize:10000, parallel:false})",
                    m=f"MATCH (n:`{label}`) RETURN n",
                    u=f"SET n:`{new}` REMOVE n:`{label}`",
                )
            else:
                s.run(f"MATCH (n:`{label}`) SET n:`{new}` REMOVE n:`{label}`")

        if drop_old_constraints and not dry_run:
            # bare 라벨 대상 orphan constraint/index drop (프리픽스용은 로더가 재생성).
            try:
                for rec in list(s.run("SHOW CONSTRAINTS YIELD name, labelsOrTypes")):
                    labels = rec.get("labelsOrTypes") or []
                    if any(lbl in NODE_LABELS for lbl in labels):
                        s.run(f"DROP CONSTRAINT `{rec['name']}` IF EXISTS")
                        log.info("dropped orphan constraint %s (%s)", rec["name"], labels)
            except Exception as e:  # noqa: BLE001
                log.warning("constraint cleanup skipped: %s", e)

    moved = sum(v for v in stats.values())
    log.info("done — %d nodes across %d labels %s",
             moved, len([k for k, v in stats.items() if v]),
             "(dry-run, nothing changed)" if dry_run else "relabeled")
    return stats


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="카운트만 출력, 변경 없음")
    ap.add_argument("--drop-old-constraints", action="store_true",
                    help="bare 라벨 대상 orphan constraint/index drop")
    a = ap.parse_args()
    s = get_settings()
    log.info("namespace=%s, neo4j_database=%r", s.app_namespace, s.neo4j_database or "(default)")
    relabel(dry_run=a.dry_run, drop_old_constraints=a.drop_old_constraints)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
