#!/usr/bin/env python3
"""PRD §10 DoD #15/#16 — IPGraph 도메인 wire-up audit.

검증 항목 (LLM/DB 무관 — wire-up only):
  1. ``ipgraph`` 패키지 import — handler/policy/ontology/tools 모두 loadable
  2. ``register_handler('ip')`` + ``register_router(route_domain_ip)`` 부작용 확인
  3. ontology/ip/{entities,relations}.yaml pydantic strict validate
  4. ``ip_*`` Cypher 템플릿 25개 등록 확인
  5. gold_qa_ip_v0.jsonl 30 row + gold_qa_cross_v0.jsonl 의 ip 결합 8 row

종료 코드: 0 (PASS) | 1 (FAIL)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)


def _check_handler() -> dict:
    try:
        import ipgraph    # noqa: F401
        from ipgraph.agent_handler import IPGraphHandler, IP_GRAPH_ALLOWED
        from autonexusgraph.agents._domain_handler import get_handler
    except Exception as e:   # noqa: BLE001 — 호출 실패 흡수 → {"passed": False, "reason":... 반환
        return {"passed": False, "reason": f"ipgraph import 실패: {e}"}
    h = get_handler("ip")
    if h is None or not isinstance(h, IPGraphHandler):
        return {"passed": False,
                "reason": f"register_handler('ip') 부작용 미발생 (got {h!r})"}
    return {
        "passed":            True,
        "domain":            h.domain,
        "graph_allowed":     len(IP_GRAPH_ALLOWED),
        "sql_allowed":       len(h.allowed_intents("sql")),
        "research_intents":  len(h.allowed_intents("research")),
    }


def _check_router() -> dict:
    try:
        from autonexusgraph.agents._domain_handler import _ROUTERS    # type: ignore[attr-defined]
        from ipgraph.policy import route_domain_ip
    except Exception as e:   # noqa: BLE001 — 호출 실패 흡수 → {"passed": False, "reason":... 반환
        return {"passed": False, "reason": f"router import 실패: {e}"}
    if route_domain_ip not in _ROUTERS:
        return {"passed": False, "reason": "route_domain_ip 미등록"}
    # 동작 검증.
    out_ip = route_domain_ip("삼성SDI 특허 출원 추세", None)
    out_cross = route_domain_ip("삼성SDI 특허 영업이익", None)
    return {
        "passed":   out_ip == "ip" and out_cross is None,
        "ip_only":  out_ip,
        "cross_yielded": out_cross,
    }


def _check_ontology() -> dict:
    try:
        from autonexusgraph.ontology import load_and_validate, OntologyValidationError
    except Exception as e:   # noqa: BLE001 — 호출 실패 흡수 → {"passed": False, "reason":... 반환
        return {"passed": False, "reason": f"ontology 모듈 import 실패: {e}"}
    out: dict = {"passed": True, "files": []}
    for fname in ("ontology/ip/entities.yaml", "ontology/ip/relations.yaml"):
        path = ROOT / fname
        if not path.exists():
            out["passed"] = False
            out["files"].append({"file": fname, "passed": False, "reason": "missing"})
            continue
        try:
            ont = load_and_validate(path)
        except OntologyValidationError as e:
            out["passed"] = False
            out["files"].append({"file": fname, "passed": False,
                                  "reason": str(e.cause)[:200]})
            continue
        out["files"].append({
            "file":            fname,
            "passed":          True,
            "schema_version":  ont.schema_version,
            "n_entities":      len(ont.entities or {}),
            "n_relations":     len(ont.relations or {}),
        })
    return out


def _check_cypher_templates() -> dict:
    try:
        from ipgraph.cypher_templates_ip import IP_TEMPLATES
        from ipgraph import tools          # noqa: F401  부작용: register_templates(_IP_TEMPLATES)
        from autonexusgraph.tools.cypher_templates import TEMPLATES
    except Exception as e:   # noqa: BLE001 — 호출 실패 흡수 → {"passed": False, "reason":... 반환
        return {"passed": False, "reason": f"cypher_templates import 실패: {e}"}
    ip_count = len(IP_TEMPLATES)
    registered = [k for k in TEMPLATES if k.startswith("ip_")]
    return {
        "passed":     ip_count >= 25 and len(registered) >= 25,
        "ip_templates_defined":   ip_count,
        "ip_templates_registered": len(registered),
    }


def _check_gold() -> dict:
    ip_gold = ROOT / "eval" / "qa_gold" / "gold_qa_ip_v0.jsonl"
    cross_gold = ROOT / "eval" / "qa_gold" / "gold_qa_cross_v0.jsonl"
    if not ip_gold.exists():
        return {"passed": False, "reason": "gold_qa_ip_v0.jsonl 없음"}
    n_ip = sum(1 for line in ip_gold.read_text(encoding="utf-8").splitlines() if line.strip())
    if not cross_gold.exists():
        return {"passed": False, "reason": "gold_qa_cross_v0.jsonl 없음"}
    n_cross_total = 0
    n_cross_ip = 0
    for line in cross_gold.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        n_cross_total += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        qid = row.get("qid") or ""
        tags = row.get("tags") or []
        if "-IP-" in qid or "ip" in tags:
            n_cross_ip += 1
    return {
        "passed":          n_ip >= 30 and n_cross_ip >= 8,
        "n_ip":            n_ip,
        "n_cross_total":   n_cross_total,
        "n_cross_ip":      n_cross_ip,
    }


def main() -> int:
    p = argparse.ArgumentParser(prog="audit-ipgraph", description=__doc__.split("\n")[0])
    p.add_argument("--out-dir", type=Path,
                   default=ROOT / "data" / "reports",
                   help="JSON 리포트 저장 디렉토리")
    p.add_argument("--log-level", default="WARNING")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out_dir / f"audit_ipgraph_{ts}.json"

    checks = {
        "handler":          _check_handler(),
        "router":           _check_router(),
        "ontology":         _check_ontology(),
        "cypher_templates": _check_cypher_templates(),
        "gold":             _check_gold(),
    }
    failed = [name for name, r in checks.items() if not r.get("passed")]
    payload = {
        "passed":   len(failed) == 0,
        "n_total":  len(checks),
        "n_pass":   sum(1 for r in checks.values() if r.get("passed")),
        "n_fail":   len(failed),
        "failed":   failed,
        "checks":   checks,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    if payload["passed"]:
        ip_count = checks["cypher_templates"].get("ip_templates_registered", 0)
        n_ip = checks["gold"].get("n_ip", 0)
        n_cross = checks["gold"].get("n_cross_ip", 0)
        print(f"[audit-ipgraph] PASS — handler+router+ontology+{ip_count} cypher+gold(ip={n_ip}, cross_ip={n_cross})  ({out_path})")
        return 0
    print(f"[audit-ipgraph] FAIL — {failed}  ({out_path})")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
