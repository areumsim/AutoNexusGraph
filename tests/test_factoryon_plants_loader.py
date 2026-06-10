"""factoryon → :Plant 승격 + PERFORMED_AT 확대 loader 단위 테스트 (DB-free).

등급 정합(공장 A / 추론 공정 candidate) + 업종→공정 매핑 + 비제조 skip 검증.
"""

from __future__ import annotations

from autograph.loaders.process.load_factoryon_plants import _build, _city_of, _processes_for


def test_industry_to_processes_완성차():
    assert _processes_for("내연기관 승용차 및 기타 여객용 자동차 제조업") == [
        "프레스", "차체", "도장", "의장"]


def test_industry_to_processes_부품_특화():
    assert _processes_for("자동차 차체용 신품 부품 제조업") == ["프레스", "차체"]
    assert _processes_for("자동차용 신품 동력전달장치 제조업") == ["파워트레인"]
    assert _processes_for("자동차 엔진용 신품 부품 제조업") == ["파워트레인"]


def test_industry_to_processes_비매칭_빈리스트():
    # 일반부품/제철/이차전지/창고 — 명시 공정 시사 없음 → 빈 리스트.
    assert _processes_for("그 외 자동차용 신품 부품 제조업") == []
    assert _processes_for("제철업") == []
    assert _processes_for("일반 창고업") == []


def test_city_parsing():
    assert _city_of("충청북도 진천군 덕산면 한삼로 69") == "충청북도"
    assert _city_of(None) == ""


def test_build_skips_nonmfr_and_marks_candidate():
    rows = [
        {"factory_no": "1", "company_name": "현대자동차(주)울산",
         "industry_name": "내연기관 승용차 및 기타 여객용 자동차 제조업",
         "address": "울산광역시 북구", "business_no": "x", "products": "승용차"},
        {"factory_no": "2", "company_name": "ABC창고",
         "industry_name": "일반 창고업", "address": "서울", "business_no": None, "products": None},
    ]
    plant_rows, perf_rows, skipped = _build(rows)
    assert skipped == 1                          # 창고 skip
    assert len(plant_rows) == 1                  # 완성차만 승격
    assert plant_rows[0]["code"] == "FCTRY_1"
    assert plant_rows[0]["source_type"] == "factoryon"
    assert len(perf_rows) == 4                   # 4 대 공정
    for r in perf_rows:
        assert r["validated_status"] == "candidate"   # 공정 추론분 = candidate (A 전가 금지)
        assert r["confidence_score"] == 0.6
        assert r["step_id"].startswith("fctry_1_")


def test_build_empty():
    assert _build([]) == ([], [], 0)
