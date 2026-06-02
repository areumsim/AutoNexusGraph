"""O-1 API 인증 + rate limit + thread 소유권 바인딩 테스트.

DB·LLM 없이 동작 — get_pool / run_agent / 소유권 조회는 monkeypatch.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from autonexusgraph.api import auth as auth_mod
from autonexusgraph.api import main as api_main
from autonexusgraph.config import get_settings


# ── parse_api_keys ──────────────────────────────────────────
def test_parse_api_keys_explicit_and_bare():
    keys = auth_mod.parse_api_keys("tokA:alice, tokB , , tokC:bob")
    assert keys["tokA"] == "alice"
    assert keys["tokC"] == "bob"
    # bare 토큰 → 해시 도출 (평문 누설 안 함)
    assert keys["tokB"].startswith("u_") and keys["tokB"] != "tokB"


def test_parse_api_keys_empty():
    assert auth_mod.parse_api_keys("") == {}
    assert auth_mod.parse_api_keys("   ,  ") == {}


# ── RateLimiter ─────────────────────────────────────────────
def test_rate_limiter_sliding_window():
    rl = auth_mod.RateLimiter(per_min=2)
    assert rl.allow("u", now=0.0)
    assert rl.allow("u", now=1.0)
    assert not rl.allow("u", now=2.0)          # 3번째 = 초과
    assert rl.allow("u", now=61.0)             # 60s 경과 → window 비움
    assert rl.allow("v", now=2.0)              # 다른 identity 독립


def test_rate_limiter_disabled():
    rl = auth_mod.RateLimiter(per_min=0)
    for i in range(100):
        assert rl.allow("u", now=float(i))


# ── 인증 fixture ────────────────────────────────────────────
@pytest.fixture()
def client(monkeypatch):
    """소유권 조회·적재·agent 를 mock 한 TestClient. settings 는 매 테스트 초기화."""
    store: dict[str, str | None] = {}   # thread_id -> owner user_id

    def fake_owner(thread_id):
        if thread_id not in store:
            return (False, None)
        return (True, store[thread_id])

    def fake_persist(thread_id, role, content, citations, trace, user_id=None):
        store.setdefault(thread_id, user_id)

    def fake_load(thread_id, limit=20):
        return []

    def fake_run_agent(message, thread_id, history, domain=None):
        return {"answer": "ok", "citations": []}

    monkeypatch.setattr(api_main, "_fetch_conv_owner", fake_owner)
    monkeypatch.setattr(api_main, "_persist_turn", fake_persist)
    monkeypatch.setattr(api_main, "_load_history", fake_load)
    monkeypatch.setattr(api_main, "run_agent", fake_run_agent)

    get_settings.cache_clear()
    auth_mod.reset_state_for_test()
    yield TestClient(api_main.app), store, monkeypatch
    get_settings.cache_clear()
    auth_mod.reset_state_for_test()


def _set_env(monkeypatch, **kw):
    for k, v in kw.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    auth_mod.reset_state_for_test()


# ── open 모드 (키 미설정) ───────────────────────────────────
def test_open_mode_allows_without_key(client, monkeypatch):
    tc, store, _ = client
    _set_env(monkeypatch, API_KEYS="", API_RATE_LIMIT_PER_MIN="0")
    r = tc.post("/chat", json={"message": "hi", "thread_id": "t1"})
    assert r.status_code == 200
    assert r.json()["answer"] == "ok"
    assert store["t1"] == auth_mod.ANONYMOUS


# ── 키 설정 시 인증 강제 ────────────────────────────────────
def test_missing_key_rejected_401(client, monkeypatch):
    tc, _, _ = client
    _set_env(monkeypatch, API_KEYS="secret:alice", API_RATE_LIMIT_PER_MIN="0")
    r = tc.post("/chat", json={"message": "hi", "thread_id": "t1"})
    assert r.status_code == 401


def test_wrong_key_rejected_401(client, monkeypatch):
    tc, _, _ = client
    _set_env(monkeypatch, API_KEYS="secret:alice", API_RATE_LIMIT_PER_MIN="0")
    r = tc.post("/chat", json={"message": "hi", "thread_id": "t1"},
                headers={"X-API-Key": "nope"})
    assert r.status_code == 401


def test_valid_key_accepted(client, monkeypatch):
    tc, store, _ = client
    _set_env(monkeypatch, API_KEYS="secret:alice", API_RATE_LIMIT_PER_MIN="0")
    r = tc.post("/chat", json={"message": "hi", "thread_id": "t1"},
                headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert store["t1"] == "alice"


def test_bearer_token_accepted(client, monkeypatch):
    tc, _, _ = client
    _set_env(monkeypatch, API_KEYS="secret:alice", API_RATE_LIMIT_PER_MIN="0")
    r = tc.post("/chat", json={"message": "hi", "thread_id": "t1"},
                headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200


# ── thread 소유권 바인딩 ────────────────────────────────────
def test_thread_ownership_enforced_403(client, monkeypatch):
    tc, store, _ = client
    _set_env(monkeypatch, API_KEYS="ka:alice,kb:bob", API_RATE_LIMIT_PER_MIN="0")
    # alice 가 t1 생성
    assert tc.post("/chat", json={"message": "hi", "thread_id": "t1"},
                   headers={"X-API-Key": "ka"}).status_code == 200
    assert store["t1"] == "alice"
    # bob 이 t1 조회 시도 → 403
    r = tc.get("/threads/t1", headers={"X-API-Key": "kb"})
    assert r.status_code == 403
    # alice 본인은 OK
    assert tc.get("/threads/t1", headers={"X-API-Key": "ka"}).status_code == 200


# ── rate limit ──────────────────────────────────────────────
def test_rate_limit_429(client, monkeypatch):
    tc, _, _ = client
    _set_env(monkeypatch, API_KEYS="secret:alice", API_RATE_LIMIT_PER_MIN="2")
    h = {"X-API-Key": "secret"}
    assert tc.post("/chat", json={"message": "1", "thread_id": "t1"}, headers=h).status_code == 200
    assert tc.post("/chat", json={"message": "2", "thread_id": "t1"}, headers=h).status_code == 200
    r = tc.post("/chat", json={"message": "3", "thread_id": "t1"}, headers=h)
    assert r.status_code == 429


# ── /health 는 인증 없음 ────────────────────────────────────
def test_health_open(client, monkeypatch):
    tc, _, _ = client
    _set_env(monkeypatch, API_KEYS="secret:alice", API_RATE_LIMIT_PER_MIN="0")
    # health 는 get_pool/neo4j 접근 — DB 없으면 error 문자열이지만 200 + 인증 불요
    r = tc.get("/health")
    assert r.status_code == 200
    assert r.json()["api"] == "ok"
