"""SQLAlchemy 커스텀 타입. SQLite에서도 tz-aware UTC를 강제한다."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """tz-aware UTC datetime을 모든 DB에서 보장하는 커스텀 타입.

    - 입력 검증: naive datetime은 거부 (CLAUDE.md 절대 룰).
    - 저장: tz-aware → UTC로 변환 후 naive로 떨궈서 저장
      (SQLite의 timezone 미지원 한계 대응. Postgres에서는 timezone=True와 동일하게 동작).
    - 읽기: naive로 돌아온 값에 UTC tzinfo를 부착해 반환.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                "naive datetime은 저장할 수 없습니다. tz-aware로 변환해서 전달하세요. "
                "예: datetime.now(timezone.utc)"
            )
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(
        self, value: Any, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
