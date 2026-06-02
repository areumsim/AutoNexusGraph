"""AutoGraph SQL tool — 차종 식별·제원 조회·비교 (사전 정의 함수 풀).

자유 SQL 금지. LLM 은 함수명 + 파라미터만 결정. READ-ONLY.

모든 함수는 dict / list[dict] 반환 → JSON serializable.
정량 수치는 본 함수 결과만 인용 (LLM 생성 금지).
"""

from __future__ import annotations

from ._db import query_dicts, query_one_dict


DEFAULT_LIMIT = 10
HARD_LIMIT = 200


def _cap(n: int | None, default: int = DEFAULT_LIMIT) -> int:
    if n is None or n <= 0:
        return default
    return min(int(n), HARD_LIMIT)


# ── 식별 ────────────────────────────────────────────────────
def lookup_vehicle(query: str, *,
                   year: int | None = None,
                   limit: int = 5) -> list[dict]:
    """차종 식별 — manufacturer + model + variant (year 옵션).

    매칭 우선순위: model.name 정확 > prefix > substr. year 가 있으면 variant 까지 필터.
    """
    q = (query or "").strip()
    if not q:
        return []
    lim = _cap(limit, 5)
    return query_dicts("""
        SELECT v.variant_id, m.model_id, m.name AS model_name,
               mm.manufacturer_id, mm.name AS mfr_name,
               v.model_year, v.trim, v.fuel_type, v.body_class,
               CASE WHEN m.name ILIKE %(q)s THEN 100
                    WHEN m.name ILIKE %(q)s || '%%' THEN 80
                    WHEN m.name ILIKE '%%' || %(q)s || '%%' THEN 60
                    WHEN mm.name ILIKE '%%' || %(q)s || '%%' THEN 40
                    ELSE 0 END AS score
          FROM auto.master_vehicle_variants v
          JOIN auto.master_vehicle_models m ON v.model_id = m.model_id
          JOIN auto.master_manufacturers mm ON m.manufacturer_id = mm.manufacturer_id
         WHERE (m.name ILIKE '%%' || %(q)s || '%%'
                OR mm.name ILIKE '%%' || %(q)s || '%%')
           AND (%(year)s::int IS NULL OR v.model_year = %(year)s::int)
         ORDER BY score DESC, v.model_year DESC, m.name
         LIMIT %(lim)s
    """, {"q": q, "year": year, "lim": lim})


def get_vehicle_info(variant_id: int) -> dict | None:
    return query_one_dict("""
        SELECT v.variant_id, v.model_year, v.trim, v.fuel_type, v.body_class,
               v.drive_type, v.transmission,
               m.model_id, m.name AS model_name, m.market, m.wikidata_qid,
               mm.manufacturer_id, mm.name AS mfr_name,
               mm.country, mm.wikidata_qid AS mfr_wikidata_qid
          FROM auto.master_vehicle_variants v
          JOIN auto.master_vehicle_models m ON v.model_id = m.model_id
          JOIN auto.master_manufacturers mm ON m.manufacturer_id = mm.manufacturer_id
         WHERE v.variant_id = %s
    """, (variant_id,))


# ── 제원 ────────────────────────────────────────────────────
def get_spec(variant_id: int, measure_key: str | None = None) -> list[dict]:
    """차량 제원 측정값. measure_key 생략 시 모든 키.

    리턴: [{"measure_key", "value_num", "value_text", "unit", "source",
            "confidence", "validated_status", "snapshot_year"}]
    """
    if measure_key:
        return query_dicts("""
            SELECT measure_key, value_num, value_text, unit, source,
                   confidence, validated_status, snapshot_year
              FROM auto.spec_measurements
             WHERE variant_id = %s AND measure_key = %s
             ORDER BY confidence DESC, snapshot_year DESC NULLS LAST
        """, (variant_id, measure_key))
    return query_dicts("""
        SELECT measure_key, value_num, value_text, unit, source,
               confidence, validated_status, snapshot_year
          FROM auto.spec_measurements
         WHERE variant_id = %s
         ORDER BY measure_key, confidence DESC
    """, (variant_id,))


def compare_vehicles(variant_ids: list[int],
                     measure_keys: list[str]) -> list[dict]:
    """여러 차량 × 여러 measure_key 비교. 각 (variant_id, measure_key) 마다 best confidence 값."""
    if not variant_ids or not measure_keys:
        return []
    variant_ids = [int(v) for v in variant_ids][:20]
    measure_keys = [str(k) for k in measure_keys][:20]
    return query_dicts("""
        SELECT DISTINCT ON (variant_id, measure_key)
               variant_id, measure_key, value_num, value_text, unit,
               source, confidence
          FROM auto.spec_measurements
         WHERE variant_id = ANY(%s) AND measure_key = ANY(%s)
         ORDER BY variant_id, measure_key, confidence DESC, snapshot_year DESC NULLS LAST
    """, (variant_ids, measure_keys))


# ── 안전 등급 ────────────────────────────────────────────────
def get_safety_rating(variant_id: int) -> dict | None:
    """NCAP / IIHS 안전 등급.

    ``auto.spec_measurements`` 의 'safety.*' 키를 모두 반환. NHTSA NCAP 은
    `load_auto_safety` 가 'safety.ncap.*' / 'safety.feature.*' 로 채운다.
    KNCAP / Euro NCAP / IIHS 는 별도 ingest 모듈이 추가되면 같은 prefix 로 합류.
    """
    rows = query_dicts("""
        SELECT measure_key, value_num, value_text, unit, source, confidence
          FROM auto.spec_measurements
         WHERE variant_id = %s AND measure_key LIKE 'safety.%%'
         ORDER BY measure_key
    """, (variant_id,))
    if not rows:
        return None
    return {"variant_id": variant_id, "ratings": rows}


# ── 생산 & 공정 (DART 사업보고서 / 산단공 합성) ─────────────
def get_plant_capacity(corp_code: str,
                       plant_code: str | None = None,
                       year: int | None = None) -> list[dict]:
    """auto.plant_capacity 조회 — 모든 인자 optional 결합.

    원천: DART 사업보고서 "III. 생산 및 설비 — (1) 생산능력" 표.
    confidence 0.80 (B 등급 — DART 공식 공시).

    Returns:
        [{"capacity_id", "corp_code", "business_division", "plant_code",
          "plant_region", "snapshot_year", "capacity_units", "unit",
          "source_rcept_no", "confidence_score", "validated_status"}]
    """
    cc = (corp_code or "").strip()
    if not cc:
        return []
    return query_dicts("""
        SELECT capacity_id, corp_code, business_division, plant_code, plant_region,
               snapshot_year, capacity_units, unit, source_rcept_no,
               confidence_score, validated_status
          FROM auto.plant_capacity
         WHERE corp_code = %(cc)s
           AND (%(plant)s::text IS NULL OR plant_code = %(plant)s)
           AND (%(year)s::int  IS NULL OR snapshot_year = %(year)s::int)
         ORDER BY snapshot_year DESC NULLS LAST, plant_code
         LIMIT 200
    """, {"cc": cc, "plant": plant_code, "year": year})


def get_oem_production(corp_code: str,
                       year: int | None = None) -> list[dict]:
    """auto.plant_production — OEM 의 모든 공장 실적, optional year.

    원천: DART 사업보고서 "III. 생산 및 설비 — (2) 생산실적" 표.
    """
    cc = (corp_code or "").strip()
    if not cc:
        return []
    return query_dicts("""
        SELECT production_id, corp_code, business_division, plant_code, plant_region,
               snapshot_year, actual_units, unit, source_rcept_no,
               confidence_score, validated_status
          FROM auto.plant_production
         WHERE corp_code = %(cc)s
           AND (%(year)s::int IS NULL OR snapshot_year = %(year)s::int)
         ORDER BY snapshot_year DESC NULLS LAST, plant_code
         LIMIT 200
    """, {"cc": cc, "year": year})


def list_plants_by_oem(corp_code: str) -> list[dict]:
    """corp_code 가 보유한 공장 distinct 목록 — capacity ∪ production union.

    각 plant 의 latest_year + peak_capacity + latest_actual 동봉. peak 기준 정렬.
    """
    cc = (corp_code or "").strip()
    if not cc:
        return []
    return query_dicts("""
        WITH cap AS (
            SELECT plant_code, plant_region,
                   MAX(snapshot_year)  AS latest_year,
                   MAX(capacity_units) AS peak_capacity
              FROM auto.plant_capacity
             WHERE corp_code = %(cc)s AND plant_code <> ''
             GROUP BY plant_code, plant_region
        ),
        prod AS (
            SELECT plant_code, plant_region,
                   MAX(snapshot_year) AS latest_year,
                   MAX(actual_units)  AS peak_actual
              FROM auto.plant_production
             WHERE corp_code = %(cc)s AND plant_code <> ''
             GROUP BY plant_code, plant_region
        )
        SELECT COALESCE(c.plant_code,  p.plant_code)  AS plant_code,
               COALESCE(c.plant_region, p.plant_region) AS plant_region,
               GREATEST(COALESCE(c.latest_year, 0), COALESCE(p.latest_year, 0))
                   AS latest_year,
               c.peak_capacity,
               p.peak_actual
          FROM cap c
          FULL OUTER JOIN prod p
                  ON c.plant_code = p.plant_code
                 AND c.plant_region IS NOT DISTINCT FROM p.plant_region
         ORDER BY c.peak_capacity DESC NULLS LAST,
                  p.peak_actual   DESC NULLS LAST
         LIMIT 50
    """, {"cc": cc})


def search_processes(query: str, limit: int = 20) -> list[dict]:
    """auto.processes 의 process_name_norm ILIKE 검색 (산단공 합성) — **row 단위**.

    동일 공정명이 여러 factory_manage_no / process_order 조합에 반복되면 row 모두 반환
    (≈550 행 상한). cf. ``autograph.tools.process.lookup_process`` 는 distinct
    ``process_name_norm`` 단위 (GROUP BY, ``:Process`` taxonomy 노드 매칭에 적합).

    빈 query → 빈 list short-circuit. confidence 0.50 (C 등급 — 합성 데이터).
    """
    q = (query or "").strip()
    if not q:
        return []
    lim = _cap(limit, 20)
    return query_dicts("""
        SELECT process_id, factory_manage_no, industry_code,
               process_map_name, process_order, process_name,
               LEFT(process_desc, 200) AS process_desc_preview,
               confidence_score, validated_status
          FROM auto.processes
         WHERE process_name_norm ILIKE '%%' || %(q)s || '%%'
            OR process_map_name  ILIKE '%%' || %(q)s || '%%'
         ORDER BY process_order, process_name
         LIMIT %(lim)s
    """, {"q": q.lower(), "lim": lim})


def get_macro_industry(year: int | None = None,
                       month: int | None = None) -> list[dict]:
    """auto.macro_industry_monthly — 월 단위 내수·수출 매크로 (KAMA 15051118).

    인자 모두 optional. 둘 다 미지정 시 최근 24 개월. confidence 0.95 (A 등급).
    """
    if year is None and month is None:
        return query_dicts("""
            SELECT snapshot_year, snapshot_month,
                   domestic_sales, export_units, export_value_usd_k,
                   source, confidence_score
              FROM auto.macro_industry_monthly
             ORDER BY snapshot_year DESC, snapshot_month DESC
             LIMIT 24
        """)
    return query_dicts("""
        SELECT snapshot_year, snapshot_month,
               domestic_sales, export_units, export_value_usd_k,
               source, confidence_score
          FROM auto.macro_industry_monthly
         WHERE (%(year)s::int  IS NULL OR snapshot_year  = %(year)s::int)
           AND (%(month)s::int IS NULL OR snapshot_month = %(month)s::int)
         ORDER BY snapshot_year DESC, snapshot_month DESC
         LIMIT 36
    """, {"year": year, "month": month})


def get_macro_production(year: int | None = None) -> list[dict]:
    """auto.macro_production_yearly — 연 단위 한국·세계 생산량 (KAMA 15051116).

    year 미지정 시 전체 (21 행). confidence 0.95 (A 등급).
    """
    if year is None:
        return query_dicts("""
            SELECT snapshot_year, domestic_units_k, global_units_k,
                   domestic_share_pct, source, confidence_score
              FROM auto.macro_production_yearly
             ORDER BY snapshot_year DESC
        """)
    return query_dicts("""
        SELECT snapshot_year, domestic_units_k, global_units_k,
               domestic_share_pct, source, confidence_score
          FROM auto.macro_production_yearly
         WHERE snapshot_year = %(year)s::int
    """, {"year": year})


__all__ = [
    "lookup_vehicle",
    "get_vehicle_info",
    "get_spec",
    "compare_vehicles",
    "get_safety_rating",
    # 생산 & 공정 (DART + 산단공 + KAMA)
    "get_plant_capacity",
    "get_oem_production",
    "list_plants_by_oem",
    "search_processes",
    "get_macro_industry",
    "get_macro_production",
]
