"""IRRelationExtractor 단위 테스트 — LLM 모킹.

실제 LLM 호출 없이 prompt 로딩 / chunk 메타 주입 / 결과 매핑 검증.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autograph.extractors.ir_relation_extractor import (
    IRRelationExtractor, load_ir_prompt,
)


def test_load_ir_prompt_returns_required_keys():
    prompt = load_ir_prompt()
    assert prompt
    assert prompt.get("system")
    assert prompt.get("user_template")
    assert prompt.get("json_schema")
    assert "target_relations" in prompt


def test_target_relations_are_ir_specific():
    prompt = load_ir_prompt()
    rels = prompt.get("target_relations") or []
    assert "MANUFACTURED_AT" in rels
    assert "CAPACITY_REPORTED" in rels


def test_extractor_healthcheck_passes():
    ext = IRRelationExtractor()
    assert ext.healthcheck() is True


def test_extractor_name_version():
    ext = IRRelationExtractor()
    assert ext.name == "ir_relation_extractor"
    assert ext.version == "p3-ir-v1"


def test_extract_no_llm_client_returns_empty():
    """ctx.llm_client=None — 빈 결과 + warning."""
    from autonexusgraph.extractors.base import RunContext
    ext = IRRelationExtractor()
    chunk = {"id": 1, "text": "test", "metadata": {"oem": "hyundai"}}
    ctx = RunContext(llm_client=None, prompt_spec=ext.prompt, extra={})
    result = ext.extract(chunk, ctx)
    assert result.relations == ()
    assert "no_llm_client" in (result.warnings or ())


def test_extract_calls_llm_with_ir_specific_context():
    """chunk metadata (oem, section, title, url) 가 user prompt 에 주입."""
    from autonexusgraph.extractors.base import RunContext
    ext = IRRelationExtractor()
    chunk = {
        "id": 42,
        "source": "oem_ir",
        "section": "ir/quarterly_earnings",
        "text": "현대차는 2024년 1분기 HMC 공장에서 100,000대 생산했다.",
        "metadata": {
            "oem": "hyundai",
            "oem_corp_code": "00164742",
            "title": "2024 1Q Earnings",
            "url": "https://www.hyundai.com/.../quarterly-earnings",
            "published_date": "2024-04-25",
        },
    }
    fake_client = MagicMock()
    fake_client.chat_json.return_value = {
        "entities": [{"name": "HMC", "kind": "Plant"}],
        "relations": [{
            "type": "CAPACITY_REPORTED",
            "head": "HMC", "head_kind": "Plant",
            "tail": "현대자동차", "tail_kind": "Manufacturer",
            "evidence": "HMC 공장에서 100,000대 생산",
            "confidence": 0.85,
            "attributes": {"capacity_units": 100000, "snapshot_year": 2024},
        }],
    }
    ctx = RunContext(llm_client=fake_client, prompt_spec=ext.prompt,
                      extra={"oem_names": {"hyundai": "현대자동차"}})
    result = ext.extract(chunk, ctx)

    # LLM 호출 1회
    fake_client.chat_json.assert_called_once()
    args, kwargs = fake_client.chat_json.call_args
    messages = args[0] if args else kwargs.get("messages")
    user_msg = messages[1]["content"]

    # 핵심 컨텍스트 주입 검증
    assert "hyundai" in user_msg
    assert "ir/quarterly_earnings" in user_msg
    assert "https://www.hyundai.com" in user_msg
    assert "2024-04-25" in user_msg
    assert "HMC 공장" in user_msg

    # 결과 메타 보강
    assert len(result.relations) == 1
    rel = result.relations[0]
    assert rel["_extracted_by"] == "ir_relation_extractor"
    assert rel["_chunk_id"] == 42
    assert rel["_oem"] == "hyundai"
    assert rel["_oem_corp_code"] == "00164742"
    assert rel["_snapshot_year"] == 2024


def test_extract_truncates_long_body():
    """6000 chars cap — LLM 비용 가드."""
    from autonexusgraph.extractors.base import RunContext
    ext = IRRelationExtractor()
    long_text = "본문 " * 10_000   # ~40k chars
    chunk = {
        "id": 1, "text": long_text,
        "metadata": {"oem": "hyundai", "title": "t", "url": "u"},
    }
    fake_client = MagicMock()
    fake_client.chat_json.return_value = {"entities": [], "relations": []}
    ctx = RunContext(llm_client=fake_client, prompt_spec=ext.prompt, extra={})
    ext.extract(chunk, ctx)
    messages = fake_client.chat_json.call_args[0][0]
    user_msg = messages[1]["content"]
    # truncated to 6000 chars (+template overhead ~600)
    assert len(user_msg) < 10_000


# ── run_p3_ir CLI 검증 ────────────────────────────────────────
def test_run_p3_ir_dry_run_no_llm_call(monkeypatch):
    """--dry-run-cost — chunk select 후 LLM 호출 없이 estimate 만."""
    from autograph.extractors import run_p3_ir
    fake_chunks = [
        {"id": 1, "text": "a" * 1000, "metadata": {"oem": "hyundai"}},
        {"id": 2, "text": "b" * 2000, "metadata": {"oem": "hyundai"}},
    ]
    monkeypatch.setattr(run_p3_ir, "select_ir_chunks",
                        lambda **kwargs: fake_chunks)

    # LLM client 호출 안 되어야 함
    monkeypatch.setattr(run_p3_ir, "get_llm_client",
                        lambda **kw: pytest.fail("호출 안 됨"))

    out = run_p3_ir.run(
        oems=["hyundai"], sections=None, sources=["oem_ir"],
        limit=10, dry_run_cost=True, hard_limit_usd=None,
    )
    assert out["chunks"] == 2
    assert "estimate" in out


def test_run_p3_ir_empty_chunks_skips(monkeypatch):
    from autograph.extractors import run_p3_ir
    monkeypatch.setattr(run_p3_ir, "select_ir_chunks", lambda **kw: [])
    out = run_p3_ir.run(
        oems=None, sections=None, sources=["oem_ir"], limit=10,
        dry_run_cost=False, hard_limit_usd=None,
    )
    assert out == {"chunks": 0}
