"""USES_EQUIPMENT / CONSUMES_MATERIAL (G-3) loader 단위 테스트 (DB-free).

공정→설비 매핑 + validated 등급 + 7키 메타 검증.
"""

from __future__ import annotations

from autograph.loaders.process.load_process_resources import _EQUIPMENT, _build_equipment_rows


def test_every_process_has_equipment():
    # 9 공정유형 모두 설비 1개 이상.
    assert set(_EQUIPMENT) >= {"프레스", "차체", "도장", "의장", "파워트레인", "가공", "사출", "용접"}
    for _proc, eqs in _EQUIPMENT.items():
        assert len(eqs) >= 1


def test_equipment_rows_validated_grade():
    rows = _build_equipment_rows()
    assert len(rows) == sum(len(v) for v in _EQUIPMENT.values())
    for r in rows:
        assert r["validated_status"] == "validated"      # textbook 표준 설비
        assert r["confidence_score"] == 0.5
        assert r["source_type"] == "manual_seed"
        assert r["step_id"] == f"proc_{r['process_name_norm']}"


def test_press_equipment_mapping():
    rows = _build_equipment_rows()
    press = {r["equipment"] for r in rows if r["process_name"] == "프레스"}
    assert "프레스기" in press


def test_step_id_links_to_proc_representative():
    rows = _build_equipment_rows()
    # proc_* 대표 스텝 사용 (plant 비귀속) — G-2 와 동일 네임스페이스.
    assert all(r["step_id"].startswith("proc_") for r in rows)
