"""주문 API 라우터 — 단일 진입점 POST /trading/order + 조회 GET /trading/orders.

CLAUDE.md 절대 룰: dry_run 기본 True. 사용자 클릭 트리거만, 스케줄러 호출 0.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.storage import SessionLocal
from app.storage.models import OrderLog
from app.trading.kis_order import place_order

router = APIRouter(prefix="/trading", tags=["trading"])


class OrderRequest(BaseModel):
    """주문 요청. dry_run 기본 True — CLAUDE.md 절대 룰 (API 층 방어)."""

    signal_id: int | None = None
    stock_code: str = Field(min_length=6, max_length=6)
    direction: Literal["buy", "sell"]
    quantity: int = Field(gt=0)
    price: str | None = None  # Decimal 직렬화 회피 — TS에서 문자열
    order_type: Literal["market", "limit"] = "market"
    dry_run: bool = True


class OrderResponse(BaseModel):
    """주문 응답. order_log_id로 후속 추적 가능."""

    success: bool
    order_log_id: int | None = None
    data: dict | None = None
    error: str | None = None


@router.post("/order", response_model=OrderResponse)
async def submit_order(req: OrderRequest) -> OrderResponse:
    """주문 제출. dry_run=True 기본. 응답에 order_log_id 포함."""
    price_dec = Decimal(req.price) if req.price else None
    result = await place_order(
        stock_code=req.stock_code,
        direction=req.direction,
        quantity=req.quantity,
        price=price_dec,
        order_type=req.order_type,
        dry_run=req.dry_run,
        signal_id=req.signal_id,
    )
    return OrderResponse(**result)


@router.get("/orders")
async def list_orders() -> list[dict]:
    """주문 로그 최근 20건. 가장 최신순."""
    db = SessionLocal()
    try:
        stmt = select(OrderLog).order_by(OrderLog.created_at.desc()).limit(20)
        rows = list(db.scalars(stmt))
        return [
            {
                "id": r.id,
                "signal_id": r.signal_id,
                "stock_code": r.stock_code,
                "direction": r.direction,
                "quantity": r.quantity,
                "price": str(r.price) if r.price is not None else None,
                "order_type": r.order_type,
                "dry_run": r.dry_run,
                "status": r.status,
                "error_message": r.error_message,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    finally:
        db.close()
