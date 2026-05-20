"""시그널 텍스트 → 관련 종목코드 매칭.

Haiku 1회 호출로 사전 정의 카테고리 추출 → 매핑 테이블로 종목코드 lookup.
실패해도 빈 리스트 반환 — 시그널 저장은 계속 (매칭은 보조 정보).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Final

from app.llm import Task, call_llm

logger = logging.getLogger(__name__)

# MVP — 카테고리 → 종목코드 매핑 하드코딩. Phase G 진입 시 DB 테이블로.
_CATEGORY_TO_STOCKS: Final[dict[str, list[str]]] = {
    "반도체": ["005930", "000660"],
    "삼성": ["005930"],
    "하이닉스": ["000660"],
    "카카오": ["035720"],
    "네이버": ["035420"],
}

_SYSTEM_PROMPT = """당신은 한국 주식 시그널 → 관련 카테고리 추출기다.
다음 카테고리 중 시그널 텍스트와 관련 있는 것만 JSON 배열로 반환한다:
- 반도체
- 삼성
- 하이닉스
- 카카오
- 네이버

매칭이 없으면 빈 배열. 사전 정의 외 카테고리 추가 금지.
출력 형식 (JSON만, 추가 설명 X): {"categories": ["반도체"]}"""

_JSON_RE: Final = re.compile(r"\{[\s\S]*\}")


def match_stocks(text: str) -> list[str]:
    """시그널 텍스트 → 관련 종목코드 리스트. 실패 시 빈 리스트.

    Haiku 1회 호출 (Task('classify', 2, len/3)) — 비용 약 $0.0001.
    """
    if not text.strip():
        return []

    task = Task(
        category="classify",
        complexity=2,
        input_tokens_estimate=len(text) // 3,
    )
    try:
        result = call_llm(
            task,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
            max_tokens=100,
        )
    except Exception as e:
        # 키 미설정(RuntimeError) + Anthropic 부하/네트워크 에러 모두 빈 리스트로 처리.
        # 매칭은 보조 정보라 시그널 파이프라인을 멈출 이유가 안 됨.
        logger.warning("stock_matcher: LLM 호출 실패 — %s", e)
        return []

    raw = result["text"]
    m = _JSON_RE.search(raw)
    if not m:
        logger.warning("stock_matcher: JSON 미발견 raw=%r", raw[:80])
        return []

    try:
        parsed = json.loads(m.group(0))
    except json.JSONDecodeError:
        logger.warning("stock_matcher: JSON 파싱 실패 raw=%r", raw[:80])
        return []

    cats = parsed.get("categories")
    if not isinstance(cats, list):
        return []

    # 카테고리 → 종목코드 (set으로 중복 제거 후 정렬)
    stocks: set[str] = set()
    for cat in cats:
        if isinstance(cat, str):
            stocks.update(_CATEGORY_TO_STOCKS.get(cat, []))
    return sorted(stocks)
