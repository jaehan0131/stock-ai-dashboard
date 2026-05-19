"""모델 라우터. 모든 LLM 호출의 단일 진입점.

CLAUDE.md 절대 규칙: 다른 모듈에서 `anthropic` SDK를 직접 import 금지.
반드시 `call_llm()`을 통해서만 호출하고, 결과는 자동으로 LLMCallLog에 기록된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from anthropic import Anthropic, APIError

from app.core.config import settings

from .cache import CacheBlock, build_cached_system
from .cost_tracker import (
    MODEL_HAIKU,
    MODEL_OPUS,
    MODEL_SONNET,
    calculate_cost,
    log_llm_call,
)

TaskCategory = Literal["classify", "summarize", "synthesize", "deep", "chat"]


@dataclass(frozen=True, slots=True)
class Task:
    """LLM 호출 1건의 메타. 라우팅 결정과 비용 추적용 메타데이터."""

    category: TaskCategory
    complexity: int  # 1~10
    input_tokens_estimate: int  # 라우팅 결정용 대략값
    cache_eligible: bool = False


def route(task: Task) -> str | None:
    """task → 모델 ID 반환. router-design.md '2. 라우팅 로직' 의사코드 구현.

    None을 반환하면 LLM 호출 없이 코드만으로 처리해야 함을 의미한다.
    """
    if task.category in ("classify", "summarize") and task.complexity < 4:
        return MODEL_HAIKU
    if task.category in ("synthesize", "chat") or task.complexity < 8:
        return MODEL_SONNET
    return MODEL_OPUS  # deep 또는 complexity >= 8


_client: Anthropic | None = None


def _get_client() -> Anthropic:
    """Anthropic 클라이언트 lazy 초기화. 키 미설정 시 한국어 RuntimeError."""
    global _client
    if _client is None:
        if settings.anthropic_api_key is None:
            raise RuntimeError(
                "ANTHROPIC_API_KEY가 .env에 설정되지 않았습니다. .env 파일을 확인하세요."
            )
        _client = Anthropic(
            api_key=settings.anthropic_api_key.get_secret_value()
        )
    return _client


def call_llm(
    task: Task,
    *,
    system: str | list[CacheBlock],
    messages: list[dict[str, Any]],
    max_tokens: int,
) -> dict[str, Any]:
    """task 라우팅 → Anthropic 호출 → LLMCallLog 자동 기록.

    `system`은 str 또는 list[CacheBlock]을 받는다. list 형태면 Prompt Caching의
    cache_control 헤더가 prefix 블록에 자동 부착된다.
    반환: `{text, model, input_tokens, output_tokens, cost_usd, log_id}`.
    호출 실패 시에도 LLMCallLog에 `success=False`로 기록한 뒤 예외를 재-raise한다.
    """
    model = route(task)
    if model is None:
        raise ValueError(
            f"이 task는 LLM 호출이 필요 없습니다: category={task.category}"
        )

    system_arg: str | list[dict[str, Any]] = (
        build_cached_system(system) if isinstance(system, list) else system
    )

    client = _get_client()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_arg,
            messages=messages,
        )
    except APIError as e:
        # 호출 실패도 반드시 기록 — 비용·디버깅 누락 방지
        log_llm_call(
            model=model,
            task_category=task.category,
            input_tokens=0,
            input_tokens_cached=0,
            output_tokens=0,
            request_id=str(getattr(e, "request_id", "unknown") or "unknown")[:64],
            success=False,
            error_message=str(e)[:1024],
        )
        raise

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cached = getattr(response.usage, "cache_read_input_tokens", 0) or 0
    text = response.content[0].text if response.content else ""
    request_id = response.id

    log_id = log_llm_call(
        model=model,
        task_category=task.category,
        input_tokens=input_tokens,
        input_tokens_cached=cached,
        output_tokens=output_tokens,
        request_id=request_id,
        success=True,
        error_message=None,
    )

    cost = calculate_cost(model, input_tokens, cached, output_tokens)

    return {
        "text": text,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost,
        "log_id": log_id,
    }
