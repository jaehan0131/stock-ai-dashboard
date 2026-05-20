"""KIS 모의 주문 래퍼 + 체결 폴링.

CLAUDE.md 절대 룰 매핑
- ``dry_run: bool = True`` 기본값 — 호출자가 명시적으로 ``dry_run=False``를
  *키워드 인자*로 박지 않으면 절대 실 API 호출 안 함
- 장 운영 시간 외 *실 주문/체결조회 차단* (dry_run은 로깅 허용)
- 레이트 리밋: KIS 초당 20req — ``asyncio.Semaphore(5)`` + 50ms 간격 강제
- 모든 시도(dry_run 포함) OrderLog 영구 저장 + ODNO 별도 컬럼 저장
- 모의 계좌상품코드 ``"01"`` 모듈 상수 (Phase H 진입 시 환경변수로 승격 검토)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Final, Literal
from zoneinfo import ZoneInfo

import httpx

from app.core.config import settings
from app.core.scheduler import is_market_open
from app.market.kis_auth import get_access_token, get_base_url
from app.market.kis_price import _fail, _ok, _validate_stock_code
from app.storage import SessionLocal
from app.storage.models import OrderLog

logger = logging.getLogger(__name__)


_ORDER_PATH: Final = "/uapi/domestic-stock/v1/trading/order-cash"
# 체결 조회 — 일별 체결 내역 (당일 조회는 INQR_STRT_DT=INQR_END_DT=today)
_INQUIRE_CCLD_PATH: Final = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
# 모의 매수/매도 TR_ID. 실전(TTTC0802U/TTTC0801U)과 다름.
_TR_ID_BUY_PAPER: Final = "VTTC0802U"
_TR_ID_SELL_PAPER: Final = "VTTC0801U"
_TR_ID_CCLD_PAPER: Final = "VTTC8001R"  # 모의 주식주문체결내역
# 모의투자 종합매매 계좌상품코드 — 모의는 모두 "01" 고정.
_PAPER_ACNT_PRDT_CD: Final = "01"

# 레이트 리밋: 동시 5건 + 50ms 간격 → 초당 약 20req 안전 마진.
_RATE_SEMAPHORE: Final = asyncio.Semaphore(5)
_RATE_MIN_INTERVAL_SEC: Final = 0.05
_last_call_ts: float = 0.0

_KST: Final = ZoneInfo("Asia/Seoul")


async def _throttle() -> None:
    """직전 호출과 50ms 이상 간격 보장. 모듈 전역 _last_call_ts 갱신."""
    global _last_call_ts
    now = time.monotonic()
    elapsed = now - _last_call_ts
    if elapsed < _RATE_MIN_INTERVAL_SEC:
        await asyncio.sleep(_RATE_MIN_INTERVAL_SEC - elapsed)
    _last_call_ts = time.monotonic()


def _save_log(
    *,
    signal_id: int | None,
    stock_code: str,
    direction: str,
    quantity: int,
    price: Decimal | None,
    order_type: str,
    dry_run: bool,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any] | None,
    status: str,
    error_message: str | None,
    kis_order_number: str | None = None,
) -> int:
    """OrderLog INSERT. 호출 측은 새 row id로 후속 디버그 가능."""
    db = SessionLocal()
    try:
        row = OrderLog(
            signal_id=signal_id,
            stock_code=stock_code,
            direction=direction,
            quantity=quantity,
            price=price,
            order_type=order_type,
            dry_run=dry_run,
            request_payload=json.dumps(request_payload, ensure_ascii=False),
            response_payload=(
                json.dumps(response_payload, ensure_ascii=False)
                if response_payload is not None
                else None
            ),
            status=status,
            error_message=error_message,
            kis_order_number=kis_order_number,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def _build_request_body(
    cano: str, stock_code: str, order_type: str, quantity: int, price: Decimal | None
) -> dict[str, str]:
    """KIS order-cash 요청 body. 모든 값 문자열 (KIS 규약)."""
    return {
        "CANO": cano,
        "ACNT_PRDT_CD": _PAPER_ACNT_PRDT_CD,
        "PDNO": stock_code,
        "ORD_DVSN": "00" if order_type == "market" else "01",
        "ORD_QTY": str(quantity),
        "ORD_UNPR": str(price) if price is not None else "0",
    }


async def place_order(
    stock_code: str,
    direction: Literal["buy", "sell"],
    quantity: int,
    *,
    price: Decimal | None = None,
    order_type: Literal["market", "limit"] = "market",
    dry_run: bool = True,
    signal_id: int | None = None,
) -> dict[str, Any]:
    """KIS 모의 주문 단일 진입점.

    Parameters
    ----------
    dry_run: True면 KIS API 미호출 + 페이로드만 로깅. **기본 True (절대 룰)**.

    Returns
    -------
    ``{ success, data, error, order_log_id }`` — order_log_id로 OrderLog 조회 가능.
    """
    # 1. 입력 검증
    err = _validate_stock_code(stock_code)
    if err:
        return _fail(err)
    if direction not in ("buy", "sell"):
        return _fail(f"direction은 buy/sell만 허용: {direction}")
    if quantity <= 0:
        return _fail(f"quantity는 양수: {quantity}")
    if order_type == "limit" and price is None:
        return _fail("지정가(limit)는 price 필수")

    creds = settings.active_kis_credentials
    request_body = _build_request_body(
        cano=creds.account,
        stock_code=stock_code,
        order_type=order_type,
        quantity=quantity,
        price=price,
    )

    # 2. dry_run 분기 — KIS 호출 없이 즉시 로깅 + 반환
    if dry_run:
        log_id = _save_log(
            signal_id=signal_id,
            stock_code=stock_code,
            direction=direction,
            quantity=quantity,
            price=price,
            order_type=order_type,
            dry_run=True,
            request_payload=request_body,
            response_payload=None,
            status="dry_run",
            error_message=None,
        )
        logger.info(
            "place_order dry_run=True log_id=%s direction=%s qty=%s",
            log_id,
            direction,
            quantity,
        )
        return {
            **_ok({"dry_run": True, "payload": request_body}),
            "order_log_id": log_id,
        }

    # 3. 실 주문 — 장 운영 시간 강제
    if not is_market_open():
        err_msg = "장 운영 시간(09:00-15:30 KST 평일) 외 — 주문 차단"
        log_id = _save_log(
            signal_id=signal_id,
            stock_code=stock_code,
            direction=direction,
            quantity=quantity,
            price=price,
            order_type=order_type,
            dry_run=False,
            request_payload=request_body,
            response_payload=None,
            status="rejected",
            error_message=err_msg,
        )
        return {**_fail(err_msg), "order_log_id": log_id}

    # 4. 토큰 발급
    try:
        token = await get_access_token()
    except RuntimeError as e:
        log_id = _save_log(
            signal_id=signal_id,
            stock_code=stock_code,
            direction=direction,
            quantity=quantity,
            price=price,
            order_type=order_type,
            dry_run=False,
            request_payload=request_body,
            response_payload=None,
            status="rejected",
            error_message=f"토큰 발급 실패: {e}",
        )
        return {**_fail(f"토큰 발급 실패: {e}"), "order_log_id": log_id}

    # 5. KIS 호출 — throttle + semaphore로 레이트 리밋 가드
    tr_id = _TR_ID_BUY_PAPER if direction == "buy" else _TR_ID_SELL_PAPER
    url = f"{get_base_url()}{_ORDER_PATH}"
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": creds.app_key.get_secret_value(),
        "appsecret": creds.app_secret.get_secret_value(),
        "tr_id": tr_id,
    }

    resp_body: dict[str, Any] | None = None
    await _throttle()
    async with _RATE_SEMAPHORE:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json=request_body)
                resp_body = (
                    resp.json()
                    if resp.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                    else {"raw": resp.text}
                )
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            log_id = _save_log(
                signal_id=signal_id,
                stock_code=stock_code,
                direction=direction,
                quantity=quantity,
                price=price,
                order_type=order_type,
                dry_run=False,
                request_payload=request_body,
                response_payload=resp_body,
                status="rejected",
                error_message=f"HTTP {e.response.status_code}",
            )
            return {
                **_fail(f"KIS HTTP {e.response.status_code}"),
                "order_log_id": log_id,
            }
        except httpx.HTTPError as e:
            log_id = _save_log(
                signal_id=signal_id,
                stock_code=stock_code,
                direction=direction,
                quantity=quantity,
                price=price,
                order_type=order_type,
                dry_run=False,
                request_payload=request_body,
                response_payload=None,
                status="rejected",
                error_message=str(e),
            )
            return {**_fail(f"네트워크 오류: {e}"), "order_log_id": log_id}

    # 6. 응답 분류 — rt_cd '0'만 접수 성공 (체결 확인은 fetch_order_status로)
    assert resp_body is not None
    kis_order_number: str | None = None
    if resp_body.get("rt_cd") == "0":
        status = "pending"
        error_message = None
        # ODNO 추출 — 후속 체결 폴링용 별도 컬럼
        output = (
            resp_body.get("output")
            if isinstance(resp_body.get("output"), dict)
            else {}
        )
        odno = output.get("ODNO") if isinstance(output, dict) else None
        kis_order_number = str(odno) if odno else None
    else:
        status = "rejected"
        error_message = resp_body.get("msg1") or "KIS 비즈니스 오류"

    log_id = _save_log(
        signal_id=signal_id,
        stock_code=stock_code,
        direction=direction,
        quantity=quantity,
        price=price,
        order_type=order_type,
        dry_run=False,
        request_payload=request_body,
        response_payload=resp_body,
        status=status,
        error_message=error_message,
        kis_order_number=kis_order_number,
    )
    if status == "rejected":
        return {**_fail(f"KIS: {error_message}"), "order_log_id": log_id}
    return {**_ok({"kis_response": resp_body}), "order_log_id": log_id}


async def fetch_order_status(order_log_id: int) -> dict[str, Any]:
    """단일 OrderLog의 체결 상태를 KIS 체결조회 API로 갱신.

    Early-return 게이트 (KIS 호출 0건):
    - OrderLog 없음 → 실패
    - dry_run=True → skipped
    - status != "pending" → skipped (이미 결정)
    - kis_order_number is None → skipped (토큰 실패 등으로 ODNO 없음)

    Returns
    -------
    ``{ success, data, error, changed }`` — changed=True면 status 전이됨.
    """
    db = SessionLocal()
    try:
        row = db.get(OrderLog, order_log_id)
        if row is None:
            return {**_fail(f"OrderLog id={order_log_id} 없음"), "changed": False}
        if row.dry_run:
            return {**_ok({"skipped": "dry_run"}), "changed": False}
        if row.status != "pending":
            return {
                **_ok({"skipped": f"status={row.status}"}),
                "changed": False,
            }
        if not row.kis_order_number:
            return {**_ok({"skipped": "no_kis_order_number"}), "changed": False}

        creds = settings.active_kis_credentials
        try:
            token = await get_access_token()
        except RuntimeError as e:
            return {**_fail(f"토큰: {e}"), "changed": False}

        today = datetime.now(_KST).strftime("%Y%m%d")
        params = {
            "CANO": creds.account,
            "ACNT_PRDT_CD": _PAPER_ACNT_PRDT_CD,
            "INQR_STRT_DT": today,
            "INQR_END_DT": today,
            "SLL_BUY_DVSN_CD": "00",
            "INQR_DVSN": "00",
            "PDNO": row.stock_code,
            "CCLD_DVSN": "00",
            "ORD_GNO_BRNO": "",
            "ODNO": row.kis_order_number,
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        headers = {
            "authorization": f"Bearer {token}",
            "appkey": creds.app_key.get_secret_value(),
            "appsecret": creds.app_secret.get_secret_value(),
            "tr_id": _TR_ID_CCLD_PAPER,
        }
        url = f"{get_base_url()}{_INQUIRE_CCLD_PATH}"

        await _throttle()
        async with _RATE_SEMAPHORE:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url, headers=headers, params=params)
                    body = (
                        resp.json()
                        if resp.headers.get("content-type", "").startswith(
                            "application/json"
                        )
                        else {"raw": resp.text}
                    )
                    resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning(
                    "체결조회 실패 order_log_id=%s: %s", order_log_id, e
                )
                return {**_fail(f"네트워크 오류: {e}"), "changed": False}

        if body.get("rt_cd") != "0":
            return {
                **_fail(f"KIS: {body.get('msg1') or '체결조회 실패'}"),
                "changed": False,
            }

        # output1: 체결 내역 배열. KIS는 응답 필드명 소문자 사용.
        items = body.get("output1") or []
        matching = next(
            (it for it in items if it.get("odno") == row.kis_order_number),
            None,
        )
        if matching is None:
            # 응답에 우리 ODNO 없음 — 아직 미체결 또는 시점 차이. pending 유지.
            return {
                **_ok({"status": "pending", "raw_items": len(items)}),
                "changed": False,
            }

        # 체결 상태 분류
        try:
            rmn_qty = int(matching.get("rmn_qty", "0") or "0")
        except (TypeError, ValueError):
            rmn_qty = 0
        cncl_yn = matching.get("cncl_yn", "N")
        if cncl_yn == "Y":
            new_status = "cancelled"
        elif rmn_qty == 0:
            new_status = "filled"
        else:
            # 부분 체결 — pending 유지, 다음 사이클에서 다시 확인
            new_status = "pending"

        changed = new_status != row.status
        if changed:
            row.status = new_status
            db.commit()
            db.refresh(row)
            logger.info(
                "체결조회 갱신 order_log_id=%s ODNO=%s new_status=%s",
                order_log_id,
                row.kis_order_number,
                new_status,
            )

        return {
            **_ok(
                {
                    "status": new_status,
                    "kis_order_number": row.kis_order_number,
                    "rmn_qty": rmn_qty,
                    "cncl_yn": cncl_yn,
                }
            ),
            "changed": changed,
        }
    finally:
        db.close()
