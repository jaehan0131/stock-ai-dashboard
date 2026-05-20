"""ORM 모델 정의. 모든 datetime은 tz-aware UTC, 금액은 Decimal(Numeric) 저장."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .types import UtcDateTime


class LLMCallLog(Base):
    """LLM 호출 비용·캐시 적중 추적 로그.

    `backend/app/llm/router-design.md` "4. 비용 추적" 섹션의 컬럼 명세 그대로 구현.
    캐시 적중률 = input_tokens_cached / input_tokens 로 대시보드에서 계산한다.
    """

    __tablename__ = "llm_call_log"

    id: Mapped[int] = mapped_column(primary_key=True)

    timestamp: Mapped[datetime] = mapped_column(
        UtcDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    model_used: Mapped[str] = mapped_column(String(32), nullable=False)
    task_category: Mapped[str] = mapped_column(String(32), nullable=False)

    input_tokens: Mapped[int] = mapped_column(nullable=False)
    input_tokens_cached: Mapped[int] = mapped_column(default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(nullable=False)

    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)

    request_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    success: Mapped[bool] = mapped_column(default=True, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(1024), default=None)


class Signal(Base):
    """시그널 영구 로그. 추천·승인 워크플로우 기반.

    CLAUDE.md 절대 룰: 시그널은 *추천*이지 주문 트리거가 아니다.
    이 테이블에는 주문 관련 컬럼이 하나도 없다 — 주문 도메인은 별도 테이블에서 처리한다.
    """

    __tablename__ = "signal"

    id: Mapped[int] = mapped_column(primary_key=True)

    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    target: Mapped[str] = mapped_column(String(256), nullable=False)
    applied_rule: Mapped[str] = mapped_column(String(64), nullable=False)

    combined_score: Mapped[int] = mapped_column(nullable=False)
    weight_sum: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)

    # supporting_log_ids: list[int] → JSON 문자열로 저장.
    # SQLite JSON 타입은 사실 TEXT 별칭이라 명시 직렬화가 단순하고 Postgres 호환도 유지.
    supporting_log_ids: Mapped[str] = mapped_column(Text, nullable=False)

    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    signal_log_id: Mapped[int] = mapped_column(index=True, nullable=False)

    # 사용자 승인 워크플로우 — default "pending"으로 자동 주문 차단의 DB 레벨 강제
    user_status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime, default=None
    )

    # 종목 매칭 결과 — JSON 배열 문자열. None이면 매크로 시그널(종목 미지정).
    target_stocks: Mapped[str | None] = mapped_column(Text, default=None)
