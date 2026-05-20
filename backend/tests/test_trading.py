"""KIS 주문 래퍼 단위 테스트.

dry_run=True 경로만 외부 API 미호출로 검증. 실 API 통합 테스트는 별도(향후).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.trading.kis_order import place_order


@pytest.mark.asyncio
async def test_dry_run_smoke() -> None:
    """dry_run=True 호출 — KIS API 미호출 + OrderLog 기록."""
    result = await place_order("005930", "buy", 1, dry_run=True)
    assert result["success"] is True
    assert result["data"]["dry_run"] is True
    assert "payload" in result["data"]
    assert "order_log_id" in result and result["order_log_id"] > 0
    # 요청 body 핵심 필드 검증
    payload = result["data"]["payload"]
    assert payload["PDNO"] == "005930"
    assert payload["ORD_QTY"] == "1"
    assert payload["ORD_DVSN"] == "00"  # 시장가


@pytest.mark.asyncio
async def test_market_hours_block(monkeypatch: pytest.MonkeyPatch) -> None:
    """장외 시간엔 실 주문(dry_run=False) 차단."""
    from app.trading import kis_order

    monkeypatch.setattr(kis_order, "is_market_open", lambda: False)
    result = await place_order("005930", "buy", 1, dry_run=False)
    assert result["success"] is False
    assert "장 운영 시간" in result["error"]
    assert result["order_log_id"] > 0  # rejected도 로그 남음


@pytest.mark.asyncio
async def test_validation_stock_code() -> None:
    """잘못된 종목코드 — 6자리 문자열 외 거부."""
    result = await place_order("12345", "buy", 1, dry_run=True)
    assert result["success"] is False


@pytest.mark.asyncio
async def test_validation_quantity_zero() -> None:
    """수량 0 거부."""
    result = await place_order("005930", "buy", 0, dry_run=True)
    assert result["success"] is False


@pytest.mark.asyncio
async def test_validation_limit_without_price() -> None:
    """지정가인데 가격 누락 거부."""
    result = await place_order(
        "005930", "buy", 1, order_type="limit", dry_run=True
    )
    assert result["success"] is False


@pytest.mark.asyncio
async def test_limit_with_price() -> None:
    """지정가 + 가격 명시 — dry_run 통과."""
    result = await place_order(
        "005930",
        "buy",
        1,
        price=Decimal("82000"),
        order_type="limit",
        dry_run=True,
    )
    assert result["success"] is True
    payload = result["data"]["payload"]
    assert payload["ORD_DVSN"] == "01"  # 지정가
    assert payload["ORD_UNPR"] == "82000"


@pytest.mark.asyncio
async def test_poll_skips_dry_run() -> None:
    """dry_run 행은 폴링 시 KIS 호출 없이 skipped 반환."""
    from app.trading.kis_order import fetch_order_status

    r1 = await place_order("005930", "buy", 1, dry_run=True)
    result = await fetch_order_status(r1["order_log_id"])
    assert result["success"] is True
    assert result["data"]["skipped"] == "dry_run"
    assert result["changed"] is False


@pytest.mark.asyncio
async def test_poll_not_found() -> None:
    """존재하지 않는 OrderLog id."""
    from app.trading.kis_order import fetch_order_status

    result = await fetch_order_status(99999999)
    assert result["success"] is False
    assert result["changed"] is False


@pytest.mark.asyncio
async def test_poll_skips_non_pending() -> None:
    """이미 결정된(filled 등) 행은 폴링 시 skipped — KIS 호출 0."""
    from app.storage import SessionLocal
    from app.storage.models import OrderLog
    from app.trading.kis_order import fetch_order_status

    r1 = await place_order("005930", "buy", 1, dry_run=True)
    # 모의: dry_run 행을 filled 상태로 강제 변환
    db = SessionLocal()
    try:
        row = db.get(OrderLog, r1["order_log_id"])
        assert row is not None
        row.dry_run = False
        row.status = "filled"
        row.kis_order_number = "FAKE12345"
        db.commit()
    finally:
        db.close()

    result = await fetch_order_status(r1["order_log_id"])
    assert result["success"] is True
    assert "skipped" in result["data"]
    assert result["data"]["skipped"].startswith("status=")
    assert result["changed"] is False
