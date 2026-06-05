"""feedback_stats — DB 없이 _summarize / _up_rate / _format_table 검증."""

from __future__ import annotations

import pytest

from autonexusgraph import feedback_stats as fs


# ── _up_rate ───────────────────────────────────────────────────────
@pytest.mark.parametrize("up,down,expected", [
    (10, 0, 100.0),
    (0, 10, 0.0),
    (5, 5, 50.0),
    (3, 1, 75.0),
    (0, 0, 0.0),       # 분모 0 — 의견 없음 → 0.0
    (1, 0, 100.0),
])
def test_up_rate(up, down, expected):
    assert fs._up_rate(up, down) == expected


def test_up_rate_excludes_comment_only():
    """comment(rating=0) 은 분모/분자 어디에도 포함되지 않음 — 무방향 의견."""
    # comment 만 100건 있어도 up_rate 는 up+down 으로만 계산.
    # _up_rate 시그니처가 (up, down) 만 받으니 자연 보장 — 회귀 가드.
    import inspect
    sig = inspect.signature(fs._up_rate)
    assert set(sig.parameters) == {"up", "down"}, \
        f"_up_rate 시그니처 변경 — comment 누락 가드: {sig}"


# ── _summarize ─────────────────────────────────────────────────────
def test_summarize_shape_and_fields():
    out = fs._summarize(
        overall={"total": 100, "up": 60, "down": 30, "comment": 10},
        recent={"total":  20, "up": 15, "down":  3, "comment":  2},
        top_negative=[
            {"message_id": 42, "content_preview": "답변이 부정확합니다",
             "n_down": 3, "last_at": "2026-06-05T00:00:00Z"},
            {"message_id": 17, "content_preview": "출처 누락",
             "n_down": 2, "last_at": "2026-06-04T00:00:00Z"},
        ],
        days=7,
    )
    # overall
    assert out["overall"]["total"] == 100
    assert out["overall"]["up"] == 60
    assert out["overall"]["down"] == 30
    assert out["overall"]["comment"] == 10
    assert out["overall"]["up_rate"] == round(100.0 * 60 / 90, 1)
    # recent
    assert out["recent"]["days"] == 7
    assert out["recent"]["total"] == 20
    assert out["recent"]["up_rate"] == round(100.0 * 15 / 18, 1)
    # top_negative
    assert len(out["top_negative"]) == 2
    assert out["top_negative"][0]["message_id"] == 42
    assert out["top_negative"][0]["n_down"] == 3


def test_summarize_handles_zero_feedback():
    """피드백 0건 — up_rate 0.0, top_negative 빈 list, total 0."""
    out = fs._summarize(
        overall={"total": 0, "up": 0, "down": 0, "comment": 0},
        recent={"total":  0, "up": 0, "down": 0, "comment": 0},
        top_negative=[],
        days=7,
    )
    assert out["overall"]["total"] == 0
    assert out["overall"]["up_rate"] == 0.0
    assert out["recent"]["up_rate"] == 0.0
    assert out["top_negative"] == []


def test_summarize_truncates_preview_160():
    """content_preview 가 160자 초과 시 truncate."""
    long = "X" * 300
    out = fs._summarize(
        overall={"total": 1, "up": 0, "down": 1, "comment": 0},
        recent={"total": 1, "up": 0, "down": 1, "comment": 0},
        top_negative=[{
            "message_id": 1, "content_preview": long,
            "n_down": 1, "last_at": "2026-06-05",
        }],
        days=7,
    )
    assert len(out["top_negative"][0]["content_preview"]) == 160


# ── _format_table ──────────────────────────────────────────────────
def test_format_table_renders_overall_and_recent():
    out = fs._summarize(
        overall={"total": 50, "up": 30, "down": 15, "comment": 5},
        recent={"total":  10, "up":  8, "down":  1, "comment": 1},
        top_negative=[{"message_id": 99, "content_preview": "부정 답변 예시",
                       "n_down": 4, "last_at": "2026-06-05"}],
        days=14,
    )
    text = fs._format_table(out)
    assert "anxg_chat.feedback" in text
    assert "👍" in text and "👎" in text and "📝" in text
    assert "최근 14일" in text
    # 부정 누적 표시
    assert "99" in text and "4x" in text


def test_format_table_empty_negative_shows_friendly_message():
    """부정 0건 시 친화적 메시지 표시 (빈 표 회피)."""
    out = fs._summarize(
        overall={"total": 5, "up": 5, "down": 0, "comment": 0},
        recent={"total":  5, "up": 5, "down": 0, "comment": 0},
        top_negative=[],
        days=7,
    )
    text = fs._format_table(out)
    assert "부정(-1) 누적 0건" in text or "feedback 부족" in text


# ── SQL 회귀 가드 — namespace 정합 ────────────────────────────────
def test_sql_uses_anxg_chat_schema():
    """모든 SQL 이 anxg_chat 프리픽스 사용 (namespace 격리 회귀 가드)."""
    for sql_const in (fs._SQL_OVERALL, fs._SQL_RECENT, fs._SQL_TOP_NEGATIVE):
        assert "anxg_chat.feedback" in sql_const, \
            f"anxg_chat.feedback 미사용: {sql_const[:80]}"
        # bare 'chat.feedback' 잔재 0
        import re
        assert not re.search(r"(?<!anxg_)chat\.feedback", sql_const), \
            f"bare 'chat.feedback' 발견: {sql_const[:80]}"


def test_sql_top_negative_joins_messages():
    """top_negative 가 messages 와 JOIN — content_preview 확보 회귀 가드."""
    assert "anxg_chat.messages" in fs._SQL_TOP_NEGATIVE
    assert "JOIN" in fs._SQL_TOP_NEGATIVE
    assert "rating = -1" in fs._SQL_TOP_NEGATIVE
