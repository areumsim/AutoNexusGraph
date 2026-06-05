"""_number_patterns — SSOT 단위 테스트.

validator + number_guard 가 같은 헬퍼를 거치는지 검증한다. 정규식 자체 검증은
test_validator/test_number_guard 에 이미 있으므로 여기는 state-level 헬퍼만.
"""

from __future__ import annotations

from autonexusgraph.agents._number_patterns import (
    collect_numbers_from_state,
    extract_big_numbers,
    numbers_from_evidence_chunks,
    numbers_from_strings,
    numbers_from_tool_results,
)


# ── extract_big_numbers ─────────────────────────────────────
def test_extract_handles_empty():
    assert extract_big_numbers("") == set()
    assert extract_big_numbers(None) == set()  # type: ignore[arg-type]


def test_extract_strips_commas():
    assert extract_big_numbers("매출 258,935,500,000,000원") == {"258935500000000"}


# ── numbers_from_strings ────────────────────────────────────
def test_numbers_from_strings_mixed_iterable():
    nums = numbers_from_strings([
        "1,234,567,890",
        None,
        12345678,         # int — str 화
        {"a": "9,876,543,210"},   # dict — str(dict) 안에 콤마 패턴 존재 → 추출됨
    ])
    assert "1234567890" in nums
    assert "12345678" in nums
    assert "9876543210" in nums


# ── numbers_from_tool_results ───────────────────────────────
def test_tool_results_picks_result_field():
    tr = [
        {"tool": "get_revenue", "result": {"value": "258,935,500,000,000"}},
        {"tool": "get_op", "result": "영업이익 9,876,543,210원"},
    ]
    nums = numbers_from_tool_results(tr)
    assert "258935500000000" in nums
    assert "9876543210" in nums


def test_tool_results_ignores_non_dict_entries():
    tr = ["not-a-dict", {"result": "1,234,567,890"}, None]
    nums = numbers_from_tool_results(tr)
    assert nums == {"1234567890"}


def test_tool_results_handles_non_list_input():
    assert numbers_from_tool_results(None) == set()
    assert numbers_from_tool_results({}) == set()
    assert numbers_from_tool_results("not a list") == set()


# ── numbers_from_evidence_chunks ────────────────────────────
def test_evidence_chunks_picks_text_field():
    chunks = [
        {"text": "매출은 258,935,500,000,000원이다."},
        {"corp_code": "00126380"},   # text 없음 — skip
    ]
    nums = numbers_from_evidence_chunks(chunks)
    assert nums == {"258935500000000"}


# ── collect_numbers_from_state ──────────────────────────────
def test_collect_state_is_union():
    state = {
        "tool_results": [{"result": "1,234,567,890"}],
        "evidence_chunks": [{"text": "9,876,543,210 원 추가 매출"}],
    }
    nums = collect_numbers_from_state(state)
    assert nums == {"1234567890", "9876543210"}


def test_collect_state_missing_keys():
    """state 에 키가 빠져도 안전 (빈 집합)."""
    assert collect_numbers_from_state({}) == set()
    assert collect_numbers_from_state({"tool_results": None}) == set()
    assert collect_numbers_from_state(None) == set()  # type: ignore[arg-type]


# ── SSOT 정합성 — validator/number_guard 가 같은 결과를 내는지 ───
def test_validator_and_number_guard_agree():
    """동일 state 에 대해 validator 의 helper 와 number_guard 의 helper 가 같은
    집합을 반환해야 한다 — drift 시 환각 가드 우회 가능.
    """
    from autonexusgraph.agents.number_guard import collect_approved_numbers

    state = {
        "tool_results": [
            {"result": {"value": "258,935,500,000,000"}},
            {"result": "9,876,543,210"},
        ],
        "evidence_chunks": [{"text": "추가 매출 12,345,678,000원"}],
    }
    assert collect_approved_numbers(state) == collect_numbers_from_state(state)
