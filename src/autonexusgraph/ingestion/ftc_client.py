"""공정거래위원회 대규모기업집단현황 크롤러.

라이선스: 공공누리 제1유형 (출처표시) — 상업·연구 허용.

소스 후보 (우선순위):
1. 공공데이터포털 API — https://www.data.go.kr 검색 "대규모기업집단" / "기업집단지정"
   - 가장 안정적, 키 발급 필요
2. 공정위 공시정보시스템 (opni.ftc.go.kr) — 직접 CSV/HWP 다운로드
   - 키 불필요하지만 URL 매년 변경 가능
3. FTC 보도자료 페이지 HTML — 매년 5월 지정 결과 발표

본 클라이언트는 (1) data.go.kr API 우선, 실패 시 (2) 직접 다운 fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

# data.go.kr — 공정거래위원회 기업집단 (상호출자제한 + 공시대상)
# 무료 키 발급 후 ?serviceKey=... 로 호출
DATA_GO_KR_BASE = "https://api.odcloud.kr/api"
# ⚠️ 아래 odcloud `/15083033/...` 은 **오설정**: dataset 15083033 은 실제로
#   '소상공인 상가(상권)정보' 이고 기업집단이 아니다 (2026-06-10 확인, plus UDDI 도 플레이스홀더).
# 올바른 소스(2026-06-10 data.go.kr 확인): '공정거래위원회_지정된 대규모기업집단 조회 서비스'
#   dataset 15091886, endpoint = https://apis.data.go.kr/1130000/appnGroupSttusList/appnGroupSttusListApi
#   (계열: 15091898 임원현황 / 15091902 참여업종). odcloud 가 아니라 apis.data.go.kr/1130000/ 포맷이라
#   파라미터·응답 파서가 다르다 → 구현 TODO (BACKLOG). + 해당 dataset 별 활용신청 필요
#   (현 DATA_GO_KR_API_KEY 는 1130000 서비스 미등록 → 403 Forbidden).
DEFAULT_ENDPOINT = "/15083033/v1/uddi:8a7e1f59-..."  # FIXME: 위 15091886 로 교체(키 등록 후)


@dataclass(frozen=True)
class GroupCompany:
    """기업집단 계열사 1건."""

    group_code: str | None     # 공정위 부여 코드
    group_name: str            # 삼성, 현대자동차, ...
    company_name: str          # 삼성전자, 현대자동차 ...
    representative: str | None
    sector: str | None
    designated_year: int


class FtcClient:
    """공정거래위원회 기업집단 데이터 클라이언트.

    무료 키 발급: https://www.data.go.kr/data/15083033/openapi.do
    .env 에 FTC_API_KEY 설정 후 사용. 미설정 시 raise.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DATA_GO_KR_BASE,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint
        self._client = httpx.Client(timeout=timeout, headers={
            "Accept": "application/json",
        })

    def __enter__(self) -> FtcClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def fetch_groups(self, year: int, page: int = 1, per_page: int = 1000) -> list[dict]:
        """대규모기업집단 + 계열사 명단 (해당 연도 지정 결과)."""
        if not self.api_key:
            raise ValueError(
                "FTC_API_KEY 미설정 — data.go.kr 에서 무료 키 발급 후 .env 추가.\n"
                "또는 수동: https://www.ftc.go.kr → 대규모기업집단 → 지정현황 CSV/HWP 다운"
            )
        url = f"{self.base_url}{self.endpoint}"
        params: dict[str, Any] = {
            "serviceKey": self.api_key,
            "page": page,
            "perPage": per_page,
            "cond[지정연도::EQ]": year,    # filter 형식 — 실제는 endpoint 마다 다름
        }
        resp = self._client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    def load_manual_csv(self, csv_path: Path, year: int) -> list[GroupCompany]:
        """수동 다운로드 CSV → GroupCompany 리스트.

        예상 컬럼: 그룹명, 회사명, 대표자, 업종 (FTC 표준 양식).
        """
        import pandas as pd
        df = pd.read_csv(csv_path, encoding="utf-8")
        # 컬럼명 매핑 (다양한 표기 흡수)
        col_map: dict[str, str] = {}
        for c in df.columns:
            cc = str(c).strip()
            if "그룹" in cc or "기업집단" in cc:
                col_map["group_name"] = c
            elif "회사" in cc or "계열" in cc:
                col_map["company_name"] = c
            elif "대표" in cc:
                col_map["representative"] = c
            elif "업종" in cc or "산업" in cc:
                col_map["sector"] = c

        results = []
        for _, row in df.iterrows():
            results.append(GroupCompany(
                group_code=None,
                group_name=str(row[col_map.get("group_name", df.columns[0])]).strip(),
                company_name=str(row[col_map.get("company_name", df.columns[1])]).strip(),
                representative=str(row[col_map["representative"]]).strip()
                              if "representative" in col_map else None,
                sector=str(row[col_map["sector"]]).strip()
                       if "sector" in col_map else None,
                designated_year=year,
            ))
        return results
