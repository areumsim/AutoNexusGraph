"""IRRelationExtractor — OEM IR/뉴스룸 본문에서 plant/모델 관계 추출.

대상 vec.chunks (source='oem_ir') 의 본문을 LLM 에 보내, prompt 'relation_extract_ir.yaml'
가 정의한 두 관계만 추출:

    MANUFACTURED_AT  : (VehicleModel) ↔ (Plant)
    CAPACITY_REPORTED: (Plant) ↔ (Manufacturer) + attributes(capacity_units, snapshot_year)

설계: auto_relation_extractor.AutoRelationExtractor 동일 패턴. metadata 에서 oem /
section / title / url 추출하여 user_template 에 주입. 추출 결과는 staging_writer 가
auto.staging_relations 에 적재 — 이후 cross_validate (P4) 가 DART production 표와
정합 검사 후 Neo4j MANUFACTURED_AT 보강.

실제 LLM 호출은 run_p3_ir.py 가 budget_aware_client 경유. 본 클래스는 BaseExtractor
인터페이스만 구현 — engine 이 retry/safe_extract 처리.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from autonexusgraph.extractors.base import (
    BaseExtractor,
    ExtractorResult,
    RunContext,
)


log = logging.getLogger(__name__)


_PROMPT_PATH = Path(__file__).parent / "prompts" / "relation_extract_ir.yaml"


def load_ir_prompt() -> dict[str, Any]:
    return yaml.safe_load(_PROMPT_PATH.read_text(encoding="utf-8"))


class IRRelationExtractor(BaseExtractor):
    """vec.chunks (source='oem_ir') → MANUFACTURED_AT / CAPACITY_REPORTED 후보."""

    name = "ir_relation_extractor"
    version = "p3-ir-v1"
    timeout_ms = 90_000   # IR 본문은 길어 latency 여유
    deterministic = False

    def __init__(self, *, purpose: str = "ir_p3") -> None:
        self.purpose = purpose
        self.prompt = load_ir_prompt()

    def healthcheck(self) -> bool:
        return bool(
            self.prompt
            and self.prompt.get("system")
            and self.prompt.get("user_template")
            and self.prompt.get("json_schema")
        )

    def extract(self, chunk: dict, ctx: RunContext) -> ExtractorResult:
        client = ctx.llm_client
        if client is None:
            return ExtractorResult.empty(
                self.name, self.version, warnings=("no_llm_client",))

        meta = chunk.get("metadata") or {}
        oem = meta.get("oem") or ""
        oem_name_resolver = ctx.extra.get("oem_names", {})
        oem_name = oem_name_resolver.get(oem, "")

        text = (chunk.get("text") or "")[:6000]   # IR 본문은 더 큼 (Hyundai 80KB 가능)
        # DART narrative chunk 는 title/url 대신 corp_code/rcept_no 보유 — title
        # 자리에 DART 메타 표기.
        if chunk.get("source") == "dart_narrative":
            title_repr = (
                f"DART 사업보고서 (corp_code={meta.get('oem_corp_code', '')}, "
                f"rcept_no={meta.get('rcept_no', '')})"
            )
            url_repr = ""
            published_repr = ""
        else:
            title_repr = meta.get("title") or ""
            url_repr = meta.get("url") or ""
            published_repr = meta.get("published_date") or ""

        user = self.prompt["user_template"].format(
            oem=oem,
            oem_name=oem_name,
            section=chunk.get("section") or meta.get("section") or "",
            title=title_repr,
            url=url_repr,
            published_date=published_repr,
            chunk_text=text,
        )

        messages = [
            {"role": "system", "content": self.prompt["system"]},
            {"role": "user",   "content": user},
        ]
        out = client.chat_json(messages, schema=self.prompt["json_schema"],
                                temperature=0.0, purpose=self.purpose)

        rels = out.get("relations") or []
        # 다운스트림 메타 보강
        for r in rels:
            r["_extracted_by"] = self.name
            r["_chunk_id"] = chunk.get("id")
            r["_oem"] = oem
            r["_oem_corp_code"] = meta.get("oem_corp_code")
            r["_source"] = chunk.get("source") or "oem_ir"
            r["_snapshot_year"] = (
                (r.get("attributes") or {}).get("snapshot_year")
                or (meta.get("published_date") or "")[:4] or None
            )
            r["_url"] = meta.get("url")
        return ExtractorResult(
            relations=tuple(rels),
            extractor_name=self.name,
            extractor_version=self.version,
        )


__all__ = ["IRRelationExtractor", "load_ir_prompt"]
