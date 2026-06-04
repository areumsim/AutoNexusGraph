"""CAUSED_BY_PROCESS (리콜→공정) loader 단위 테스트 (DB-free).

공정키워드+결함지시어 매칭 정밀도 + candidate 등급 + 노이즈('단조'=첨단조향) 차단.
"""

from __future__ import annotations

from autograph.loaders.load_recall_process_map import _build_rows, _PROC


def _row(rid, text):
    return (rid, text)


def test_match_requires_defect_indicator():
    # 공정 키워드만 있고 결함 지시어 없으면 매칭 안 됨.
    rows, n = _build_rows([_row(1, "용접 공정으로 제작되었습니다")])
    assert n == 0 and rows == []
    # 결함 지시어 동반 시 매칭.
    rows, n = _build_rows([_row(2, "차체 용접 불량으로 균열 발생")])
    assert n == 1
    assert rows[0]["process_name"] == "용접"


def test_candidate_grade_and_meta():
    rows, _ = _build_rows([_row(3, "조립 불량으로 부품 이탈")])
    r = rows[0]
    assert r["validated_status"] == "candidate"      # 인과 추론 — 단독 근거 금지
    assert r["confidence_score"] == 0.5
    assert r["source_type"] == "datagokr_recall"
    assert r["extraction_method"] == "deterministic"


def test_단조_substring_noise_blocked():
    # '첨단조향장치'(첨단 조향장치)의 '단조'는 forging 아님 — _PROC 에 단조 없음 → 매칭 0.
    assert "단조" not in _PROC
    rows, n = _build_rows([_row(4, "첨단조향장치 소프트웨어 오류로 문제 발생")])
    assert n == 0


def test_synonym_normalization():
    # 체결→조립, 성형→프레스, 코팅→도장.
    assert _PROC["체결"] == "조립"
    assert _PROC["성형"] == "프레스"
    assert _PROC["코팅"] == "도장"
    rows, _ = _build_rows([_row(5, "고정볼트 체결 누락으로 이탈")])
    assert rows[0]["process_name"] == "조립"


def test_empty():
    assert _build_rows([]) == ([], 0)
