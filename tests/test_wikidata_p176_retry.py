"""Wikidata P176 ingester 의 429 견딤성 단위 테스트.

실제 SPARQL endpoint 호출 없이 retry-after 파싱 + 백오프 결정 + chunked
디스패치 로직만 검증. ``data_inventory.md`` B7 의 429 누적 결손에 대한 회귀
가드.
"""

from __future__ import annotations

import json
from unittest import mock

import httpx
import pytest

from autograph.ingestion import wikidata_auto as W


# ── Retry-After 파싱 ─────────────────────────────────────────────
def _make_response(status: int, retry_after: str | None = None) -> httpx.Response:
    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return httpx.Response(status_code=status, headers=headers)


def test_parse_retry_after_seconds():
    r = _make_response(429, "60")
    assert W._parse_retry_after(r) == 60.0


def test_parse_retry_after_float_string():
    r = _make_response(429, "12.5")
    assert W._parse_retry_after(r) == 12.5


def test_parse_retry_after_missing_returns_none():
    r = _make_response(429)
    assert W._parse_retry_after(r) is None


def test_parse_retry_after_invalid_returns_none():
    r = _make_response(429, "not-a-number")
    assert W._parse_retry_after(r) is None


# ── _sleep_for_429 결정 로직 ─────────────────────────────────────
def test_sleep_for_429_honors_retry_after():
    """Retry-After 값이 있으면 그것을 우선 사용 (cap 적용)."""
    assert W._sleep_for_429(attempt=1, retry_after=30.0) == 30.0
    assert W._sleep_for_429(attempt=3, retry_after=45.0) == 45.0


def test_sleep_for_429_caps_retry_after():
    """매우 큰 Retry-After 값도 cap 으로 제한."""
    assert W._sleep_for_429(attempt=1, retry_after=9999.0) == W._RATE_LIMIT_CAP


def test_sleep_for_429_falls_back_to_exponential():
    """Retry-After 없으면 base*2^(attempt-1) 백오프."""
    assert W._sleep_for_429(attempt=1, retry_after=None) == W._RATE_LIMIT_BASE
    assert W._sleep_for_429(attempt=2, retry_after=None) == W._RATE_LIMIT_BASE * 2
    # cap 적용
    assert W._sleep_for_429(attempt=10, retry_after=None) == W._RATE_LIMIT_CAP


# ── _run_sparql — 429 후 성공 ────────────────────────────────────
def test_run_sparql_recovers_after_429(monkeypatch):
    """첫 호출 429 → Retry-After 대기 → 두 번째 호출 성공."""
    monkeypatch.setattr(W.time, "sleep", lambda _: None)
    monkeypatch.setattr(W._LIMITER, "acquire", lambda: None)

    # 첫 호출만 429, 두 번째부터 성공 응답
    success_payload = {"results": {"bindings": [{"x": {"value": "ok"}}]}}
    call_count = {"n": 0}
    fake_request = httpx.Request("GET", "https://example.org/sparql")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                resp = httpx.Response(status_code=429,
                                      headers={"Retry-After": "1"},
                                      request=fake_request)
                raise httpx.HTTPStatusError("rate limited",
                                            request=fake_request,
                                            response=resp)
            return httpx.Response(
                status_code=200,
                json=success_payload,
                request=fake_request,
            )

    monkeypatch.setattr(W.httpx, "Client", FakeClient)
    out = W._run_sparql("SELECT *", label="test")
    assert out == [{"x": {"value": "ok"}}]
    assert call_count["n"] == 2


def test_run_sparql_gives_up_after_max_retries(monkeypatch):
    """모든 시도가 429 → 최종 HTTPStatusError raise."""
    monkeypatch.setattr(W.time, "sleep", lambda _: None)
    monkeypatch.setattr(W._LIMITER, "acquire", lambda: None)
    monkeypatch.setattr(W, "_RATE_LIMIT_MAX_TRIES", 2)

    fake_request = httpx.Request("GET", "https://example.org/sparql")

    class AlwaysRateLimited:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            resp = httpx.Response(status_code=429,
                                  headers={"Retry-After": "1"},
                                  request=fake_request)
            raise httpx.HTTPStatusError("rate limited",
                                        request=fake_request,
                                        response=resp)

    monkeypatch.setattr(W.httpx, "Client", AlwaysRateLimited)
    with pytest.raises(httpx.HTTPStatusError):
        W._run_sparql("SELECT *", label="test")


# ── chunked part_supplies ───────────────────────────────────────
def test_part_classes_list_is_well_formed():
    """_PART_CLASSES 가 (QID, label) 튜플 list 이고 QID 가 Wikidata 형식."""
    assert len(W._PART_CLASSES) >= 5
    for qid, label in W._PART_CLASSES:
        assert qid.startswith("Q"), f"{qid} not a Wikidata QID"
        assert qid[1:].isdigit(), f"{qid} not a valid Q-id"
        assert label and isinstance(label, str)


def test_sparql_part_supplies_for_class_contains_qid():
    """class QID 가 쿼리에 포함됨."""
    q = W._sparql_part_supplies_for_class("Q12888")
    assert "wd:Q12888" in q
    assert "wdt:P176" in q
    assert "LIMIT" in q


def test_ingest_part_supplies_chunked_partial_success(monkeypatch, tmp_path):
    """일부 chunk 가 429 로 실패해도 나머지 chunk 는 보존 + merged jsonl 생성."""
    # raw 디렉토리 격리
    monkeypatch.setattr(W, "raw_dir", lambda src: tmp_path)
    # CheckpointStore — 메모리 fake
    state = {"done": set(), "failed": set()}

    class FakeCkpt:
        def __init__(self, source):
            pass

        def is_done(self, key):
            return key in state["done"]

        def mark_done(self, key, payload=None):
            state["done"].add(key)

        def mark_failed(self, key, msg):
            state["failed"].add((key, msg))

    monkeypatch.setattr(W, "CheckpointStore", FakeCkpt)

    # _run_sparql — Q12888 (battery) 만 실패, 나머지는 성공
    def fake_run_sparql(query, *, label=""):
        if "Q12888" in query:
            raise RuntimeError("simulated 429 exhaustion")
        return [{"part": {"value": "http://www.wikidata.org/entity/Q1"},
                 "partLabel": {"value": "Part1"},
                 "supplier": {"value": "http://www.wikidata.org/entity/Q2"},
                 "supplierLabel": {"value": "Supplier1"}}]

    monkeypatch.setattr(W, "_run_sparql", fake_run_sparql)

    result = W._ingest_part_supplies_chunked()
    expected_succeeded = len(W._PART_CLASSES) - 1
    assert result["chunks_succeeded"] == expected_succeeded
    assert result["chunks_failed"] == 1
    assert "Q12888" in result["failed_classes"]
    # 부분 성공이라도 row 가 있으면 merged jsonl 생성
    merged = tmp_path / "part_supplies.jsonl"
    assert merged.exists()
    rows = [json.loads(line) for line in merged.read_text().splitlines() if line.strip()]
    assert len(rows) == expected_succeeded
    # part_supplies 전체 done 마킹 안 됨 (부분 실패)
    assert "part_supplies" not in state["done"]


def test_ingest_part_supplies_chunked_full_success(monkeypatch, tmp_path):
    """모든 chunk 성공 → 'part_supplies' kind 전체 done 마킹."""
    monkeypatch.setattr(W, "raw_dir", lambda src: tmp_path)
    state = {"done": set()}

    class FakeCkpt:
        def __init__(self, source): pass
        def is_done(self, key): return key in state["done"]
        def mark_done(self, key, payload=None): state["done"].add(key)
        def mark_failed(self, key, msg): pass

    monkeypatch.setattr(W, "CheckpointStore", FakeCkpt)
    monkeypatch.setattr(W, "_run_sparql",
                        lambda q, *, label="": [
                            {"part": {"value": "http://www.wikidata.org/entity/Q1"},
                             "partLabel": {"value": "P"},
                             "supplier": {"value": "http://www.wikidata.org/entity/Q2"},
                             "supplierLabel": {"value": "S"}}
                        ])

    result = W._ingest_part_supplies_chunked()
    assert result["chunks_succeeded"] == len(W._PART_CLASSES)
    assert result["chunks_failed"] == 0
    # 전체 done 마킹 — 재실행 시 skip
    assert "part_supplies" in state["done"]


def test_ingest_kind_routes_part_supplies_to_chunked(monkeypatch):
    """ingest_kind('part_supplies') 가 chunked 경로로 분기."""
    called = {"chunked": False}

    def fake_chunked():
        called["chunked"] = True
        return {"kind": "part_supplies", "rows": 0,
                "chunks_succeeded": 0, "chunks_failed": 0,
                "failed_classes": []}

    monkeypatch.setattr(W, "_ingest_part_supplies_chunked", fake_chunked)
    W.ingest_kind("part_supplies")
    assert called["chunked"] is True
