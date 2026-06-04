"""PRODUCED_BY (부품→공정) loader 단위 테스트 (DB-free).

system→공정 카테고리 매핑 + candidate 등급 + 외주부품 기본 의장 검증.
"""

from __future__ import annotations

from autograph.loaders.load_produced_by import _proc_for, _build_rows


def test_body_to_press():
    assert _proc_for("STRUCTURE:BODY:FRAME") == "프레스"


def test_chassis_to_machining():
    assert _proc_for("SUSPENSION:FRONT:CONTROL ARM:LOWER ARM") == "가공"
    assert _proc_for("SERVICE BRAKES, HYDRAULIC:DISC:CALIPER") == "가공"
    assert _proc_for("브레이크패드") == "가공"


def test_powertrain():
    assert _proc_for("ENGINE AND ENGINE COOLING:ENGINE:GASOLINE") == "파워트레인"
    assert _proc_for("POWER TRAIN:AUTOMATIC TRANSMISSION") == "파워트레인"
    assert _proc_for("배터리셀") == "파워트레인"
    assert _proc_for("점화플러그") == "파워트레인"


def test_bought_in_defaults_to_assembly():
    # 외주 전장/센서/조명 — OEM 공정이 생산 아님 → 의장(조립) BoP 진입.
    assert _proc_for("AIR BAGS:FRONTAL:DRIVER SIDE:INFLATOR MODULE") == "의장"
    assert _proc_for("후방카메라") == "의장"
    assert _proc_for("ELECTRICAL SYSTEM:ADAS") == "의장"


def test_build_rows_candidate_grade():
    rows = _build_rows([{"id": 1, "name": "SUSPENSION:CONTROL ARM"},
                        {"id": 2, "name": "후방카메라"}])
    assert len(rows) == 2
    for r in rows:
        assert r["validated_status"] == "candidate"   # 카테고리 추론 — B 아님
        assert r["confidence_score"] == 0.5
        assert r["step_id"].startswith("proc_")
    assert rows[0]["process_name"] == "가공"
    assert rows[1]["process_name"] == "의장"


def test_build_skips_null_id():
    assert _build_rows([{"id": None, "name": "x"}]) == []
