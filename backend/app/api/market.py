"""한국 시장 시세 API 라우터.

CLAUDE.md 절대 룰: 시세 조회는 *읽기 전용*이며 주문을 트리거하지 않는다.
모든 경로는 `dry_run=True` 기본 — 쿼리스트링 `?dry_run=false`로만 실 API 호출.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from app.core.scheduler import price_cache
from app.market.kis_price import get_current_price

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/price/{stock_code}")
async def fetch_price(
    stock_code: str,
    dry_run: bool = Query(
        default=True,
        description="True면 외부 KIS API 호출 없이 더미 응답 (기본). false 명시 시에만 실 호출.",
    ),
) -> dict:
    """현재가 조회. `{ success, data, error }` 표준 포맷.

    실패 시 4xx — 입력 형식 오류는 400, 외부 API 오류는 502.
    """
    result = await get_current_price(stock_code, dry_run=dry_run)

    if result["success"]:
        return result

    # 입력 검증 실패는 클라이언트 오류, 외부 API 실패는 게이트웨이 오류로 구분.
    err = result["error"] or ""
    if "형식 오류" in err or "문자열이어야" in err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=err)
    raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=err)


@router.get("/prices")
async def list_cached_prices() -> dict:
    """캐시된 모든 종목 현재가. APScheduler가 장중 5분마다 채움.

    빈 dict면 아직 1회도 갱신 안 됨 (서버 막 시작했거나 장외 시간).
    """
    return {"success": True, "data": price_cache, "error": None}


@router.get("/prices/{stock_code}")
async def get_cached_price(stock_code: str) -> dict:
    """단일 종목 캐시 조회. KIS 직접 호출 안 함 — 스케줄러가 채운 결과만 읽기.

    캐시 미스 시 404 (서버 막 시작 / 장외 / 종목 미등록).
    """
    data = price_cache.get(stock_code)
    if data is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"캐시에 없습니다: stock_code={stock_code}. 5분 내 갱신 또는 장외 시간.",
        )
    return {"success": True, "data": data, "error": None}
