"""환경변수 로딩 단일 진입점. KIS 모의/실전 키 분리·시크릿 마스킹·기본 모드 paper 강제."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

TradingMode = Literal["paper", "live"]

_live_warned: bool = False


@dataclass(frozen=True, slots=True)
class KisCredentials:
    """KIS OpenAPI 인증 정보 묶음 (모드 1종만 담는 불변 컨테이너)."""

    mode: TradingMode
    app_key: SecretStr
    app_secret: SecretStr
    account: str


class Settings(BaseSettings):
    """프로젝트 전역 설정. `.env` 파일에서 환경변수를 읽어 검증한다.

    호출 측은 모듈 하단 `settings` 싱글톤을 사용하고, KIS 키는
    반드시 `active_kis_credentials` property를 통해서만 접근한다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    kis_paper_app_key: SecretStr | None = None
    kis_paper_app_secret: SecretStr | None = None
    kis_paper_account: str | None = None

    kis_live_app_key: SecretStr | None = None
    kis_live_app_secret: SecretStr | None = None
    kis_live_account: str | None = None

    trading_mode: TradingMode = "paper"

    dart_api_key: SecretStr | None = None
    fred_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None

    database_url: str = "sqlite:///./local.db"

    @property
    def active_kis_credentials(self) -> KisCredentials:
        """현재 `trading_mode`에 해당하는 KIS 키 3종을 반환한다.

        - `paper` 모드: `KIS_PAPER_*` 키 3종을 묶어 반환
        - `live` 모드: `KIS_LIVE_*` 키 3종을 묶어 반환 + 프로세스 1회 경고 로그
        - 해당 모드의 키 중 하나라도 누락되면 한국어 ValueError 발생
        """
        global _live_warned

        if self.trading_mode == "live":
            if not _live_warned:
                logger.warning(
                    "KIS 실거래 모드로 진입했습니다. TRADING_MODE=live"
                )
                _live_warned = True
            return self._build_credentials(
                mode="live",
                app_key=self.kis_live_app_key,
                app_secret=self.kis_live_app_secret,
                account=self.kis_live_account,
            )

        return self._build_credentials(
            mode="paper",
            app_key=self.kis_paper_app_key,
            app_secret=self.kis_paper_app_secret,
            account=self.kis_paper_account,
        )

    @staticmethod
    def _build_credentials(
        *,
        mode: TradingMode,
        app_key: SecretStr | None,
        app_secret: SecretStr | None,
        account: str | None,
    ) -> KisCredentials:
        """모드별 키 3종을 검증해 `KisCredentials`로 묶는다. 누락 시 한국어 에러."""
        missing: list[str] = []
        prefix = "KIS_PAPER" if mode == "paper" else "KIS_LIVE"

        if app_key is None or not app_key.get_secret_value():
            missing.append(f"{prefix}_APP_KEY")
        if app_secret is None or not app_secret.get_secret_value():
            missing.append(f"{prefix}_APP_SECRET")
        if not account:
            missing.append(f"{prefix}_ACCOUNT")

        if missing:
            raise ValueError(
                f"{'/'.join(missing)} 중 누락된 키가 있습니다: {missing}. "
                ".env 파일을 확인하세요."
            )

        assert app_key is not None and app_secret is not None and account is not None
        return KisCredentials(
            mode=mode,
            app_key=app_key,
            app_secret=app_secret,
            account=account,
        )


settings = Settings()
