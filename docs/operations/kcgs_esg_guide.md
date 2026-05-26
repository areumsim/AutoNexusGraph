# KCGS ESG 등급 수집 가이드

KCGS(한국ESG기준원)은 공식 API 가 없고, 등급 풀데이터는 회원만 접근 가능합니다.
본 시스템은 다음 두 트랙으로 KCGS 데이터를 자동/반자동 수집합니다.

## 1) 보도자료 자동 모니터 — `make ingest-kcgs`

KCGS press_list.jsp 의 '등급' 키워드 보도자료를 polling.
ESG 등급 조정·평가 발표 시 새 게시물을 자동 감지하고
`data/raw/kcgs/press/<no>/meta.json + body.html` 에 저장.

```bash
# 보도자료 자동 monitor (최근 3페이지, body 포함)
make ingest-kcgs

# 또는 키워드/페이지 커스텀
python scripts/ingest/download_kcgs.py --svalue 평가 --pages 5 --with-body
```

출력 예시:
```
[KCGS] ⚠️  ESG 등급 관련 보도자료 8건:
  • 2025-08-20 [보도자료] 2025년 2분기 ESG 등급 조정
    https://www.cgs.or.kr/news/press_view.jsp?no=229
```

## 2) 등급표 CSV 적재 — `make load-kcgs`

KCGS 정기 등급(매년 10~11월) 또는 등급 조정 발표의 CSV/엑셀을 사용자가 수동 다운로드.

### 다운로드 경로
1. **회원 가입 시** — KCGS 회원 페이지 → 등급 데이터 다운로드
2. **공개 시점** — 보도자료 첨부 HWP/PDF (위 ingest-kcgs 로 감지)
3. **3rd party 데이터셋** — DBpia/언론사 정리 자료

### CSV 형식
```csv
회사명,종목코드,환경,사회,지배구조,종합
삼성전자,005930,A,A,A,A
SK하이닉스,000660,A+,A,A+,A+
...
```

컬럼명은 자동 감지 (회사명/기업명, 종목코드/코드, 환경/E, 사회/S, 지배구조/G, 종합/통합).

### 저장 위치 + 적재
```bash
# data/raw/kcgs/<year>/ratings.csv 에 두기
mkdir -p data/raw/kcgs/2024
cp ~/Downloads/kcgs_2024.csv data/raw/kcgs/2024/ratings.csv

# 적재 (PG esg.ratings + Neo4j Company.esg_<year>_*)
make load-kcgs                                # 기본 year=2024
python scripts/load/load_kcgs.py --year 2024  # 명시
```

검증:
```bash
# PG
psql $POSTGRES_DSN -c "SELECT total_grade, count(*) FROM esg.ratings WHERE year=2024 GROUP BY 1"

# Neo4j
cypher-shell "MATCH (c:Company) WHERE c.esg_2024_total='A+' RETURN c.corp_code, c.corp_name LIMIT 10"
```

## 3) Sample template — 검증용

`data/raw/kcgs/sample/template.csv` 에 10개 Top 회사의 형식 예시 (실제 등급 아님 — 코드 동작 검증용).

## 한계 + 향후

- KCGS 등급 본 데이터는 자동 다운로드 불가 (회원 + 약관)
- 등급 조정 보도자료의 본문은 자동 수집 OK, 첨부 PDF 는 JS 함수 호출이라 수동 다운로드 필요
- 매년 정기 등급 발표 시 보도자료 monitor 가 알림 → 사용자가 페이지 방문 후 CSV 저장 → load-kcgs 자동 적재
