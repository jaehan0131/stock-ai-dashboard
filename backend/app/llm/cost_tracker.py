"""LLM 호출 비용 계산 + LLMCallLog 적재. 모든 LLM 호출 비용은 이 모듈을 거쳐 DB로."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from app.storage import LLMCallLog, SessionLocal

# 모델 ID 상수 (alias 형식). production 핀팅 시 -YYYYMMDD 접미사로 고정 권장.
MODEL_HAIKU: Final = "claude-haiku-4-5"
MODEL_SONNET: Final = "claude-sonnet-4-6"
MODEL_OPUS: Final = "claude-opus-4-7"


@dataclass(frozen=True, slots=True)
class _Price:
    """1M tokens당 단가(USD). 캐시 read는 input의 10%로 가정."""

    input: Decimal
    output: Decimal


# 2026-05 기준 단가. production 전 재확인 필요.
MODEL_PRICING: Final[dict[str, _Price]] = {
    MODEL_HAIKU: _Price(Decimal("0.80"), Decimal("4.00")),
    MODEL_SONNET: _Price(Decimal("3.00"), Decimal("15.00")),
    MODEL_OPUS: _Price(Decimal("15.00"), Decimal("75.00")),
}

_ONE_M: Final = Decimal("1000000")
_CACHE_RATIO: Final = Decimal("0.1")
_QUANT: Final = Decimal("0.000001")  # 6자리 소수 quantize


def calculate_cost(
    model: str,
    input_tokens: int,
    input_tokens_cached: int,
    output_tokens: int,
) -> Decimal:
    """모델별 단가 × 토큰 수 → USD Decimal(소수 6자리). float 산술 금지.

    - 비캐시 input: input_tokens - cached
    - 캐시 read: cached × (input_price × 10%)
    - output: output_tokens × output_price
    """
    price = MODEL_PRICING.get(model)
    if price is None:
        raise ValueError(f"단가 정의가 없는 모델입니다: {model}")

    uncached = max(0, input_tokens - input_tokens_cached)
    cost = (
        Decimal(uncached) * price.input / _ONE_M
        + Decimal(input_tokens_cached) * price.input * _CACHE_RATIO / _ONE_M
        + Decimal(output_tokens) * price.output / _ONE_M
    )
    return cost.quantize(_QUANT)


def log_llm_call(
    *,
    model: str,
    task_category: str,
    input_tokens: int,
    input_tokens_cached: int,
    output_tokens: int,
    request_id: str,
    success: bool,
    error_message: str | None = None,
) -> int:
    """LLMCallLog row INSERT. 성공·실패 모두 호출. 반환: 새 row id."""
    cost = (
        calculate_cost(model, input_tokens, input_tokens_cached, output_tokens)
        if success
        else Decimal("0.000000")
    )

    db = SessionLocal()
    try:
        log = LLMCallLog(
            model_used=model,
            task_category=task_category,
            input_tokens=input_tokens,
            input_tokens_cached=input_tokens_cached,
            output_tokens=output_tokens,
            cost_usd=cost,
            request_id=request_id,
            success=success,
            error_message=error_message,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log.id
    finally:
        db.close()
