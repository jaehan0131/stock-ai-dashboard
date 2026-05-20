"""KIS 모의투자 현재가 조회.

CLAUDE.md 절대 룰 매핑
- 종목코드는 6자리 문자열만 허용 (int 금지 — 앞 0 손실 방지)
- 외부 호출은 try/except + 구조화 로그 + 응답 표준 포맷 `{ success, data, error }`
- `dry_run=True` 기본값 — 실 API 미호출, 더미 응답 + 페이로드 로깅만

엔드포인트: GET /uapi/domestic-stock/v1/quotations/inquire-price
TR_ID: VTTC8434R (모의)
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Any, Final

import httpx

from app.core.config import settings
from app.market.kis_auth import get_access_token, get_base_url

logger = logging.getLogger(__name__)


# KIS 시세 API. 모의/실전 경로 동일, 베이스 URL만 다름.
_PRICE_PATH: Final[str] = "/uapi/domestic-stock/v1/quotations/inquire-price"

# 시세 조회 TR_ID — 계좌 컨텍스트가 없는 단순 조회라 모의/실전 동일.
# (VTTC8434R은 '모의 주식잔고조회'용 — 이걸 보내면 KIS가 CANO를 요구해 INPUT_FIELD_NAME CANO 에러 발생)
_TR_ID_PAPER: Final[str] = "FHKST01010100"

# 6자리 숫자 문자열 — 정규식 검증으로 코드 단에서 즉시 거부.
_STOCK_CODE_RE: Final[re.Pattern[str]] = re.compile(r"^\d{6}$")


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    """성공 응답 표준 포맷."""
    return {"success": True, "data": data, "error": None}


def _fail(message: str) -> dict[str, Any]:
    """실패 응답 표준 포맷. message는 사용자에게 노출 가능한 한국어 문장."""
    return {"success": False, "data": None, "error": message}


def _validate_stock_code(stock_code: str) -> str | None:
    """6자리 숫자 문자열 검증. 통과 시 None, 실패 시 한국어 에러 메시지."""
    if not isinstance(stock_code, str):
        return "종목코드는 문자열이어야 합니다 (int 금지)."
    if not _STOCK_CODE_RE.match(stock_code):
        return f"종목코드 형식 오류: '{stock_code}' — 6자리 숫자 문자열 필요."
    return None


def _dummy_payload(stock_code: str) -> dict[str, Any]:
    """dry_run 모드용 결정적(deterministic) 더미. 외부 시세 없이도 라우터·UI 테스트 가능.

    가격은 종목코드 해시가 아니라 단순 상수 — 코드 안정성 우선.
    실 API 응답과 동일한 키 셋(`stock_code, name, current_price, change_rate`)을 유지.
    """
    return {
        "stock_code": stock_code,
        "name": f"DRYRUN-{stock_code}",
        "current_price": Decimal("70000"),
        "change_rate": Decimal("0.00"),
        "dry_run": True,
    }


def _parse_output(stock_code: str, output: dict[str, Any]) -> dict[str, Any]:
    """KIS `output` 블록을 표준 data 형태로 변환.

    KIS는 모든 숫자 필드를 문자열로 반환 — `Decimal`로 직접 변환해 금액 정밀도를 보존.
    `float` 변환 금지 (CLAUDE.md 룰).
    """
    # 종목명 후보 — KIS 모의/실전 응답이 다른 키를 쓰는 경우가 있어 다중 시도.
    # 모두 비어있으면 종목코드를 fallback으로 표시 (UI가 빈 문자열로 깨지지 않게).
    name = (
        output.get("hts_kor_isnm")
        or output.get("prdt_abrv_name")
        or output.get("prdt_name")
        or output.get("bstp_kor_isnm")
        or stock_code
    )
    return {
        "stock_code": stock_code,
        "name": name,
        "current_price": Decimal(output.get("stck_prpr", "0")),
        "change_rate": Decimal(output.get("prdy_ctrt", "0")),
    }


async def get_current_price(
    stock_code: str, dry_run: bool = True
) -> dict[str, Any]:
    """현재가 조회.

    Parameters
    ----------
    stock_code: 6자리 숫자 문자열 (예: '005930')
    dry_run: True면 외부 호출 없이 더미 응답. 기본 True.

    Returns
    -------
    `{ success: bool, data: { stock_code, name, current_price, change_rate } | None, error: str | None }`
    """
    err = _validate_stock_code(stock_code)
    if err:
        logger.warning("현재가 조회 입력 검증 실패: %s", err)
        return _fail(err)

    if dry_run:
        logger.info(
            "현재가 조회 dry_run=True stock_code=%s — 외부 API 미호출", stock_code
        )
        return _ok(_dummy_payload(stock_code))

    creds = settings.active_kis_credentials
    try:
        access_token = await get_access_token()
    except RuntimeError as e:
        logger.error("현재가 조회 토큰 발급 실패 stock_code=%s err=%s", stock_code, e)
        return _fail(f"토큰 발급 실패: {e}")

    url = f"{get_base_url()}{_PRICE_PATH}"
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": creds.app_key.get_secret_value(),
        "appsecret": creds.app_secret.get_secret_value(),
        "tr_id": _TR_ID_PAPER,
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",  # J = 주식
        "FID_INPUT_ISCD": stock_code,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error(
            "KIS 시세 호출 실패 stock_code=%s status=%s body=%s",
            stock_code,
            e.response.status_code,
            e.response.text,
        )
        return _fail(f"KIS HTTP {e.response.status_code}: {e.response.text}")
    except httpx.HTTPError as e:
        logger.error("KIS 시세 네트워크 오류 stock_code=%s err=%s", stock_code, e)
        return _fail(f"KIS 네트워크 오류: {e}")

    body = resp.json()
    # 디버그: 모의/실전 응답 키 셋이 달라 종목명 필드 추적용. 필드 확정 후 debug 레벨로 강등.
    output_for_log = body.get("output")
    logger.info(
        "KIS body 구조 stock_code=%s body_keys=%s output_keys=%s",
        stock_code,
        sorted(body.keys()),
        sorted(output_for_log.keys()) if isinstance(output_for_log, dict) else None,
    )
    # KIS 응답 컨벤션: rt_cd '0' == 정상, 그 외는 비즈니스 오류
    if body.get("rt_cd") != "0":
        msg = body.get("msg1") or "알 수 없는 KIS 오류"
        logger.warning(
            "KIS 시세 비즈니스 오류 stock_code=%s rt_cd=%s msg=%s",
            stock_code,
            body.get("rt_cd"),
            msg,
        )
        return _fail(f"KIS: {msg}")

    output = body.get("output")
    if not isinstance(output, dict):
        logger.error("KIS 응답 형식 오류 stock_code=%s body=%s", stock_code, body)
        return _fail("KIS 응답 output 누락")

    return _ok(_parse_output(stock_code, output))
