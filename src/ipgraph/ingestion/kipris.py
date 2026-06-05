"""KIPRIS Open API — 한국 특허 검색·서지 수집 + XML 파서. docs/ipgraph.md §5.

라이선스: KIPRIS Open API (공공데이터포털) — 검색·서지 무료, 본문/대량은 KIPRISPLUS
회원·일부 비공개. ``LICENSE_POLICY['kipris'] = 'kogl_type1'`` (메타 저장 OK).

우선 출원인: 현대차 / 기아 / 삼성SDI / LG에너지솔루션 / 현대모비스 (docs/ipgraph.md §5).

API 인증:
    ``KIPRIS_API_KEY`` env 필요. 미설정 시 graceful skip + 0 row. raw XML 이
    ``data/raw/ip/kipris/*.xml`` 에 미리 있으면 키 없이도 parse + collect 가능
    (오프라인 적재 / 키 발급 전 smoke).

CLI:
    python -m ipgraph.ingestion.kipris
    python -m ipgraph.ingestion.kipris --applicants 한국조폐공사,삼성SDI --year 2024
    python -m ipgraph.ingestion.kipris --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "raw" / "ip" / "kipris"

log = logging.getLogger(__name__)


# KIPRIS Open API endpoint — 공공데이터포털.
# https://www.data.go.kr/data/15077221/openapi.do
KIPRIS_SEARCH_URL = (
    "http://plus.kipris.or.kr/openapi/rest/patUtiModInfoSearchSevice/"
    "advancedSearch"
)

# 우선 출원인 (docs/ipgraph.md §5).
PRIORITY_APPLICANTS = (
    "현대자동차", "기아", "삼성SDI", "LG에너지솔루션", "현대모비스",
)


def _api_key() -> str | None:
    """KIPRIS_API_KEY env — 미설정 시 None (graceful skip)."""
    key = os.getenv("KIPRIS_API_KEY", "").strip()
    return key or None


def _ensure_raw_dir() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    return RAW_DIR


def _fetch_one_applicant(applicant: str, *, year: int | None,
                         api_key: str, max_pages: int = 5) -> list[dict]:
    """단일 출원인 advanced search — 페이지네이션. fail-soft."""
    rows: list[dict] = []
    for page in range(1, max_pages + 1):
        params = {
            "ServiceKey":  api_key,
            "applicant":   applicant,
            "numOfRows":   "100",
            "pageNo":      str(page),
            "patent":      "true",
        }
        if year:
            params["applicationDate"] = f"{year}0101~{year}1231"
        url = f"{KIPRIS_SEARCH_URL}?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "AutoNexusGraph/IPG"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = resp.read().decode("utf-8")
        except Exception as e:   # noqa: BLE001 — [kipris] fetch 실패 (네트워크/auth) 흡수 → log + break (남은 page 포기)
            log.warning("[kipris] fetch 실패 (%s page=%d): %s",
                        applicant, page, e)
            break
        # KIPRIS 응답이 XML 일 수 있음 — wire-up 단계는 raw 저장만.
        raw_path = RAW_DIR / f"{applicant}_y{year or 'all'}_p{page}.txt"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(payload, encoding="utf-8")
        # 본 단계는 parse 미구현 (XML schema 인증 후) — rows 빈 list 반환.
        # 후속 PR 에서 lxml 파싱 추가.
        if "<item>" not in payload and "<patentInfo>" not in payload:
            break
    return rows


def parse_xml(xml_text: str, *, snapshot_year: int | None = None
              ) -> dict[str, list[dict]]:
    """KIPRIS XML 응답 → 정규화된 7-list dict.

    KIPRIS Open API ``advancedSearch`` 응답 구조:
        <response>
          <body>
            <items>
              <item>
                <applicationNumber>1020230012345</applicationNumber>
                <applicationDate>20230101</applicationDate>
                <registerNumber>1012345670000</registerNumber>
                <registerDate>20231220</registerDate>
                <inventionTitle>발명의명칭</inventionTitle>
                <astrtCont>요약</astrtCont>
                <applicantName>삼성SDI주식회사</applicantName>
                <inventorName>홍길동;김영수</inventorName>
                <ipcNumber>H01M 10/052</ipcNumber>
                ...
              </item>
            </items>
          </body>
        </response>

    multi-applicant / multi-inventor 는 ``;`` 또는 ``,`` 로 구분 — 분리 후 patent_assignees
    / patent_inventors 다대다 link 생성.
    """
    sy = snapshot_year if snapshot_year is not None else datetime.now(timezone.utc).year
    out = {
        "patents":          [],
        "assignees":        [],
        "inventors":        [],
        "patent_assignees": [],
        "patent_inventors": [],
        "patent_cpc":       [],
    }
    seen_assignees: dict[str, dict] = {}
    seen_inventors: dict[str, dict] = {}
    try:
        from lxml import etree
        root = etree.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ImportError:
        import xml.etree.ElementTree as etree
        root = etree.fromstring(xml_text)
    except Exception as e:   # noqa: BLE001 — [kipris] XML parse 실패 흡수 → out 반환
        log.warning("[kipris] XML parse 실패: %s", e)
        return out

    # 응답 구조 — XPath 두 단계 (body/items/item).
    items = root.findall(".//item") or root.findall(".//patentInfo")
    for item in items:
        app_no = _txt(item, "applicationNumber")
        reg_no = _txt(item, "registerNumber")
        # 등록번호 우선 (등록특허), 없으면 출원번호 (공개).
        pub_no = f"KR{reg_no}" if reg_no else f"KR{app_no}" if app_no else None
        if not pub_no:
            continue

        out["patents"].append({
            "pub_no":         pub_no,
            "app_no":         app_no,
            "title":          _txt(item, "inventionTitle"),
            "abstract":       _txt(item, "astrtCont"),
            "filing_date":    _normalize_date(_txt(item, "applicationDate")),
            "grant_date":     _normalize_date(_txt(item, "registerDate")),
            "kind":           "B1" if reg_no else "A",
            "jurisdiction":   "KR",
            "source":         "kipris",
            "snapshot_year":  sy,
            "schema_version": "v2.2",
        })

        # Applicant — ; 또는 , 로 multi.
        applicants_raw = _txt(item, "applicantName") or ""
        for seq, name in enumerate(_split_multi(applicants_raw)):
            aid = f"KR-ASN:{name}"
            if aid not in seen_assignees:
                seen_assignees[aid] = {
                    "assignee_id":    aid,
                    "name":           name,
                    "name_norm":      name.lower().strip(),
                    "country":        "KR",
                    "type":           _guess_assignee_type(name),
                    "wikidata_qid":   None,
                    "snapshot_year":  sy,
                    "schema_version": "v2.2",
                }
            out["patent_assignees"].append({
                "pub_no": pub_no, "assignee_id": aid, "sequence": seq,
            })

        # Inventor.
        inventors_raw = _txt(item, "inventorName") or ""
        for seq, name in enumerate(_split_multi(inventors_raw)):
            iid = f"KR-INV:{name}"
            if iid not in seen_inventors:
                seen_inventors[iid] = {
                    "inventor_id":    iid,
                    "name":           name,
                    "name_norm":      name.lower().strip(),
                    "country":        "KR",
                    "schema_version": "v2.2",
                }
            out["patent_inventors"].append({
                "pub_no": pub_no, "inventor_id": iid, "sequence": seq,
            })

        # IPC → CPC fallback. KIPRIS 는 ``ipcNumber`` (IPC) 가 primary.
        # IPC 와 CPC 는 동일 영역 코드가 호환 → load_cpc 의 :CPCCode 매칭 시도.
        ipc = _txt(item, "ipcNumber") or _txt(item, "cpcNumber")
        if ipc:
            # 여러 IPC ; 분리.
            for raw_code in _split_multi(ipc):
                # KIPRIS 응답 'H01M 10/052' → CPC scheme 'H01M10/052' 정규화 (공백 제거).
                # 이래야 PG FK + Neo4j MATCH 가 적중.
                code = raw_code.replace(" ", "").strip()
                if code:
                    out["patent_cpc"].append({
                        "pub_no":       pub_no,
                        "cpc_code":     code,
                        "primary_flag": False,
                    })

    out["assignees"] = list(seen_assignees.values())
    out["inventors"] = list(seen_inventors.values())
    return out


def _txt(elem: Any, tag: str) -> str | None:
    """ElementTree first matching child text — None if missing/empty."""
    c = elem.find(tag) if hasattr(elem, "find") else None
    if c is None:
        return None
    t = (c.text or "").strip()
    return t or None


def _split_multi(s: str) -> list[str]:
    """multi-value 문자열 (; 또는 , 구분) → list — 공백 정규화."""
    if not s:
        return []
    out: list[str] = []
    for part in s.replace(",", ";").split(";"):
        v = part.strip()
        if v:
            out.append(v)
    return out


def _normalize_date(s: str | None) -> str | None:
    """KIPRIS 'YYYYMMDD' → ISO 'YYYY-MM-DD'."""
    if not s:
        return None
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


def _guess_assignee_type(name: str) -> str:
    """이름 패턴으로 assignee type 추정."""
    n = (name or "").lower()
    if any(k in n for k in ("대학교", "university")):
        return "university"
    if any(k in n for k in ("정부", "공사", "원", "ministry", "government")):
        return "gov"
    if any(k in n for k in ("주식회사", "(주)", "co.", "ltd", "inc", "corp", "솔루션")):
        return "company"
    return "company"


def collect(*, applicants: list[str] | None = None,
            year: int | None = None,
            dry_run: bool = False) -> dict[str, Any]:
    """KIPRIS 수집 진입점.

    ``KIPRIS_API_KEY`` 미설정 시 + raw XML 도 없으면 graceful skip + 0 row.
    raw XML 이 ``data/raw/ip/kipris/*.xml`` 에 있으면 key 없이도 parse + collect.
    """
    raw_dir = _ensure_raw_dir()
    apps = applicants or list(PRIORITY_APPLICANTS)
    snapshot_year = datetime.now(timezone.utc).year

    # 1. 키 있으면 fetch — raw_dir 에 응답 XML 저장.
    key = _api_key()
    if key:
        for applicant in apps:
            if dry_run:
                log.info("[kipris] dry-run %s year=%s", applicant, year)
                continue
            _fetch_one_applicant(applicant, year=year, api_key=key)
    else:
        log.warning("[kipris] KIPRIS_API_KEY 미설정 — fetch skip, raw 파일이 있으면 parse 만")

    # 2. raw_dir 의 모든 *.xml + *.txt parse → 합산.
    aggregate = {k: [] for k in ("patents", "assignees", "inventors",
                                   "patent_assignees", "patent_inventors", "patent_cpc")}
    seen_pat = set()
    seen_asn = set()
    seen_inv = set()
    for fp in sorted(list(raw_dir.glob("*.xml")) + list(raw_dir.glob("*.txt"))):
        try:
            xml_text = fp.read_text(encoding="utf-8")
        except Exception as e:   # noqa: BLE001 — [kipris] 1 unit 실패 흡수 → log + continue (부분 성공 보존)
            log.warning("[kipris] read 실패 %s: %s", fp.name, e)
            continue
        parsed = parse_xml(xml_text, snapshot_year=snapshot_year)
        # 중복 제거.
        for p in parsed["patents"]:
            if p["pub_no"] in seen_pat:
                continue
            seen_pat.add(p["pub_no"])
            aggregate["patents"].append(p)
        for a in parsed["assignees"]:
            if a["assignee_id"] in seen_asn:
                continue
            seen_asn.add(a["assignee_id"])
            aggregate["assignees"].append(a)
        for inv in parsed["inventors"]:
            if inv["inventor_id"] in seen_inv:
                continue
            seen_inv.add(inv["inventor_id"])
            aggregate["inventors"].append(inv)
        for k in ("patent_assignees", "patent_inventors", "patent_cpc"):
            aggregate[k].extend(parsed[k])

    return {
        "n_patents":          len(aggregate["patents"]),
        "n_assignees":        len(aggregate["assignees"]),
        "n_inventors":        len(aggregate["inventors"]),
        "n_patent_assignees": len(aggregate["patent_assignees"]),
        "n_patent_inventors": len(aggregate["patent_inventors"]),
        "n_patent_cpc":       len(aggregate["patent_cpc"]),
        "raw_dir":            str(raw_dir),
        "snapshot_year":      snapshot_year,
        "key_present":        bool(key),
        "_data":              aggregate,
    }


def main() -> int:
    p = argparse.ArgumentParser(prog="ipgraph.ingestion.kipris",
                                 description=__doc__.split("\n")[0])
    p.add_argument("--applicants", default=None,
                   help="csv — 미지정 시 priority 5사")
    p.add_argument("--year", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(message)s")

    apps: list[str] | None = None
    if args.applicants:
        apps = [a.strip() for a in args.applicants.split(",") if a.strip()]
    result = collect(applicants=apps, year=args.year, dry_run=args.dry_run)
    print(f"[kipris] {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
