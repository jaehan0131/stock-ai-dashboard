"""IntelItem → Haiku 요약·점수 정제 → SummarizedItem.

JSON 출력 강제 + 코드블록 감싸기 폴백.
LLM 호출은 반드시 `call_llm()` 경유 (CLAUDE.md 절대 룰).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Final

from app.llm import (
    IntelItem,
    Task,
    call_llm,
    default_system_blocks,
)

logger = logging.getLogger(__name__)


SUMMARY_PROMPT: Final = """다음 뉴스 항목을 분석한다.
출처: {source} (신뢰도 {weight})
원본 (제목+요약): {content_summary}

아래 JSON 스키마로만 응답한다. 추가 설명 금지.
{{
  "summary_ko": "한국어 3~5줄 요약",
  "scores": {{"impact": 0-5 정수, "time": 0-5 정수, "size": 0-5 정수}},
  "applied_rule": "룰북 §1-N 인과 사슬 명 (해당 없으면 §0 무관)",
  "is_relevant": true/false
}}
점수 기준: 룰북 §2 (영향 경로/시간 우위/영향 크기).
is_relevant=false면 후속 시그널 생성 단계 스킵 (false positive 컷).
"""

# 응답이 코드블록·서론 등으로 감싸진 경우의 폴백 추출용.
_JSON_BLOCK_RE: Final = re.compile(r"\{[\s\S]*\}", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class SummarizedItem:
    """LLM 요약·점수 정제 결과. 원본 IntelItem은 보존한다."""

    original: IntelItem
    summary_ko: str
    refined_scores: tuple[int, int, int]  # (impact, time, size), 각 0~5
    applied_rule: str  # 예: "§1-3 미국 금리"
    is_relevant: bool
    llm_call_log_id: int  # LLMCallLog 적재 id, 사후 비용 분석용


def _try_parse_json(text: str) -> dict | None:
    """직접 파싱 → 실패 시 정규식으로 {...} 추출해 재시도. 모두 실패면 None."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = _JSON_BLOCK_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def summarize_item(item: IntelItem) -> SummarizedItem | None:
    """IntelItem → Haiku 호출 → SummarizedItem.

    실패(LLM 호출 에러·JSON 파싱·스키마 검증) 시 None + logger.warning.
    환경 설정 문제(키 미설정 RuntimeError)는 silent 처리 부적절하므로 그대로 raise.
    """
    task = Task(
        category="summarize",
        complexity=2,
        input_tokens_estimate=len(item.content_summary) // 3,
    )
    user_msg = SUMMARY_PROMPT.format(
        source=item.source,
        weight=item.source_weight,
        content_summary=item.content_summary,
    )

    try:
        result = call_llm(
            task,
            system=default_system_blocks(),
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=500,
        )
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning("summarize_item LLM 호출 실패: %s", e)
        return None

    parsed = _try_parse_json(result["text"])
    if parsed is None:
        logger.warning(
            "summarize_item JSON 파싱 실패: text=%r", result["text"][:200]
        )
        return None

    try:
        scores = parsed["scores"]
        return SummarizedItem(
            original=item,
            summary_ko=str(parsed["summary_ko"]),
            refined_scores=(
                int(scores["impact"]),
                int(scores["time"]),
                int(scores["size"]),
            ),
            applied_rule=str(parsed["applied_rule"]),
            is_relevant=bool(parsed["is_relevant"]),
            llm_call_log_id=int(result["log_id"]),
        )
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(
            "summarize_item 스키마 검증 실패: %s, parsed=%r", e, parsed
        )
        return None
