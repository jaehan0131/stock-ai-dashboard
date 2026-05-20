"""KIS OpenAPI OAuth 토큰 발급·메모리 캐시.

CLAUDE.md 절대 룰 매핑
- 키는 `settings.active_kis_credentials`에서만 read (하드코딩 금지)
- 모의/실전 베이스 URL을 `mode`로 분기 → 한 모듈에 두 환경 공존 금지
- 토큰 만료 60초 전 사전 갱신 → race 윈도우 차단

토큰 캐시는 단일 프로세스 메모리 한정 (인스턴스 여러 개면 각자 발급).
정식 운영 단계에 들어가면 Redis 등 공유 캐시로 교체.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Final

import httpx

from app.core.config import KisCredentials, TradingMode, settings

logger = logging.getLogger(__name__)


# KIS REST 베이스 URL — 모드별 호스트가 다르다. 모의/실전 키 분리와 짝을 맞춤.
_KIS_BASE_URLS: Final[dict[TradingMode, str]] = {
    "paper": "https://openapivts.koreainvestment.com:29443",
    "live": "https://openapi.koreainvestment.com:9443",
}

_TOKEN_PATH: Final[str] = "/oauth2/tokenP"

# 만료 임박 판정 마진. 응답 expires_in 보다 N초 일찍 갱신 → 호출 도중 만료 방지.
_TOKEN_RENEW_MARGIN_SEC: Final[int] = 60


@dataclass(frozen=True, slots=True)
class _CachedToken:
    """발급된 access_token + 만료 시각 묶음 (불변)."""

    access_token: str
    expires_at: datetime  # tz-aware UTC. naive 저장 금지.
    mode: TradingMode  # 모의/실전 캐시 충돌 방지용 키.


class KisTokenCache:
    """KIS OAuth 토큰 캐시. 모드별로 1슬롯씩.

    동시 호출 안전성: `asyncio.Lock`으로 동시 갱신 직렬화 → 같은 만료 토큰을
    여러 코루틴이 동시에 재발급하는 낭비를 막는다.
    """

    def __init__(self) -> None:
        self._tokens: dict[TradingMode, _CachedToken] = {}
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        """현재 trading_mode의 유효 access_token을 반환. 만료 임박이면 자동 재발급."""
        creds = settings.active_kis_credentials
        async with self._lock:
            cached = self._tokens.get(creds.mode)
            if cached is not None and not self._is_expiring_soon(cached.expires_at):
                return cached.access_token

            new_token = await self._issue_token(creds)
            self._tokens[creds.mode] = new_token
            logger.info(
                "KIS 토큰 발급 완료 mode=%s expires_at=%s",
                creds.mode,
                new_token.expires_at.isoformat(),
            )
            return new_token.access_token

    def clear(self) -> None:
        """강제 캐시 비우기. 401 응답을 받았을 때 호출자가 직접 비우고 재시도."""
        self._tokens.clear()

    @staticmethod
    def _is_expiring_soon(expires_at: datetime) -> bool:
        """만료까지 `_TOKEN_RENEW_MARGIN_SEC` 이하면 만료 임박으로 판정."""
        now = datetime.now(timezone.utc)
        return (expires_at - now).total_seconds() <= _TOKEN_RENEW_MARGIN_SEC

    @staticmethod
    async def _issue_token(creds: KisCredentials) -> _CachedToken:
        """KIS `/oauth2/tokenP` POST → access_token, expires_in 파싱."""
        base = _KIS_BASE_URLS[creds.mode]
        url = f"{base}{_TOKEN_PATH}"
        payload = {
            "grant_type": "client_credentials",
            "appkey": creds.app_key.get_secret_value(),
            "appsecret": creds.app_secret.get_secret_value(),
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            # 응답 body가 시크릿을 포함하지 않으므로 그대로 노출 OK.
            logger.error(
                "KIS 토큰 발급 실패 status=%s body=%s",
                e.response.status_code,
                e.response.text,
            )
            raise RuntimeError(
                f"KIS 토큰 발급 실패: HTTP {e.response.status_code} — {e.response.text}"
            ) from e
        except httpx.HTTPError as e:
            logger.error("KIS 토큰 발급 네트워크 오류: %s", e)
            raise RuntimeError(f"KIS 토큰 발급 네트워크 오류: {e}") from e

        body = resp.json()
        access_token = body.get("access_token")
        expires_in = body.get("expires_in")
        if not access_token or not isinstance(expires_in, int):
            raise RuntimeError(
                f"KIS 토큰 응답 형식 오류: access_token/expires_in 누락 — {body}"
            )

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        return _CachedToken(
            access_token=access_token,
            expires_at=expires_at,
            mode=creds.mode,
        )


# 프로세스 단일 인스턴스. 라우터·시그널 생성기 등에서 모두 이 캐시를 공유한다.
token_cache = KisTokenCache()


async def get_access_token() -> str:
    """간편 호출용 헬퍼. 호출자가 `KisTokenCache` 인스턴스를 신경 쓸 필요 없게 한다."""
    return await token_cache.get_token()


def get_base_url() -> str:
    """현재 trading_mode에 맞는 KIS REST 베이스 URL."""
    return _KIS_BASE_URLS[settings.active_kis_credentials.mode]
