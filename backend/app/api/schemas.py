"""API 응답 Pydantic 모델.

ORM ↔ HTTP 경계의 변환을 모두 여기서 처리한다.
- supporting_log_ids: DB에는 JSON 문자열, 응답에는 list[int]
- weight_sum: Decimal → str (프론트의 부동소수점 오차 회피)
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator


class SignalRead(BaseModel):
    """Signal ORM → API 응답 변환 모델."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    direction: str
    target: str
    applied_rule: str
    combined_score: int
    weight_sum: Decimal
    supporting_log_ids: list[int]
    target_stocks: list[str]
    reasoning: str
    signal_log_id: int
    user_status: str
    reviewed_at: datetime | None

    @field_validator("supporting_log_ids", mode="before")
    @classmethod
    def _parse_log_ids(cls, v: Any) -> Any:
        """ORM의 JSON 문자열을 list[int]로 파싱. 이미 list면 그대로."""
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("target_stocks", mode="before")
    @classmethod
    def _parse_stocks(cls, v: Any) -> Any:
        """ORM의 JSON 문자열 또는 None → list[str]. None은 빈 리스트로 정규화."""
        if v is None:
            return []
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_serializer("weight_sum")
    def _ser_decimal(self, v: Decimal) -> str:
        """Decimal → 문자열. JSON 부동소수점 오차 회피."""
        return str(v)


class IntelRunResult(BaseModel):
    """/intel/run 응답."""

    collected: int
    gate_passed: int
    summarized: int
    signals_generated: int
    saved_ids: list[int]
