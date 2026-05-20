"""KIS 시세 조회 smoke test (삼성전자 005930).

dry_run 경로만 검증 — 외부 KIS API 호출 없이 함수·라우터 wiring을 확인.
실 API 통합 테스트는 별도 `test_market_integration.py`로 분리해 CI 기본 제외.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.market.kis_price import get_current_price

SAMSUNG = "005930"


@pytest.mark.asyncio
async def test_get_current_price_dry_run_samsung() -> None:
    """005930 dry_run=True — 외부 호출 없이 success 응답이 와야 한다."""
    result = await get_current_price(SAMSUNG, dry_run=True)

    assert result["success"] is True
    assert result["error"] is None

    data = result["data"]
    assert data["stock_code"] == SAMSUNG
    # current_price/change_rate는 Decimal — float 변환 금지 룰 검증.
    assert isinstance(data["current_price"], Decimal)
    assert isinstance(data["change_rate"], Decimal)
    assert data["dry_run"] is True


@pytest.mark.asyncio
async def test_get_current_price_rejects_int() -> None:
    """종목코드 int 입력은 즉시 거부 (앞 0 손실 방지)."""
    result = await get_current_price(5930, dry_run=True)  # type: ignore[arg-type]
    assert result["success"] is False
    assert "문자열" in result["error"]


@pytest.mark.asyncio
async def test_get_current_price_rejects_bad_format() -> None:
    """6자리 숫자가 아닌 입력은 거부."""
    for bad in ("00593", "0059300", "ABCDEF", ""):
        result = await get_current_price(bad, dry_run=True)
        assert result["success"] is False, f"입력 '{bad}'은 거부되어야 한다"
        assert "형식 오류" in result["error"] or "문자열" in result["error"]


def test_router_price_endpoint_samsung() -> None:
    """GET /market/price/005930 — 라우터·FastAPI 등록·dry_run 기본값 일괄 검증."""
    client = TestClient(app)
    resp = client.get(f"/market/price/{SAMSUNG}")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["success"] is True
    assert body["data"]["stock_code"] == SAMSUNG


def test_router_price_endpoint_bad_code() -> None:
    """잘못된 종목코드는 400으로 거부."""
    client = TestClient(app)
    resp = client.get("/market/price/12345")
    assert resp.status_code == 400
