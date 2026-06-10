"""USES_PROCESS (모듈→공정, G-6) loader 단위 테스트 (DB-free).

system_code→공정 매핑 + candidate 등급 + 외주 모듈 기본 의장 검증.
"""

from __future__ import annotations

from autograph.loaders.process.load_uses_process import _build_rows, _proc_for


def test_body_chassis_to_press():
    assert _proc_for("BODY") == "프레스"
    assert _proc_for("CHASSIS") == "프레스"


def test_powertrain_battery():
    assert _proc_for("POWERTRAIN") == "파워트레인"
    assert _proc_for("BATTERY") == "파워트레인"


def test_chassis_systems_to_machining():
    assert _proc_for("SUSPENSION") == "가공"
    assert _proc_for("BRAKE") == "가공"
    assert _proc_for("STEERING") == "가공"


def test_tires_to_injection():
    assert _proc_for("TIRES_WHEELS") == "사출"


def test_electronics_default_assembly():
    # LIGHTING/ELECTRICAL/ADAS/INFOTAINMENT/SAFETY/UNKNOWN → 의장.
    for sc in ("LIGHTING", "ELECTRICAL", "ADAS", "INFOTAINMENT", "SAFETY", "UNKNOWN", ""):
        assert _proc_for(sc) == "의장"


def test_build_rows_candidate_grade():
    rows = _build_rows([{"id": 1, "system_code": "BODY"},
                        {"id": 2, "system_code": "ADAS"},
                        {"id": None, "system_code": "BODY"}])
    assert len(rows) == 2                        # null id skip
    for r in rows:
        assert r["validated_status"] == "candidate"
        assert r["confidence_score"] == 0.5
    assert rows[0]["process_name"] == "프레스"
    assert rows[1]["process_name"] == "의장"
