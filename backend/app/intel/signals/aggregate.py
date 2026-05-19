"""SummarizedItem 리스트 → applied_rule 그룹화 → Sonnet 시그널 종합 → Signal.

CLAUDE.md 절대 룰: Signal은 *추천*일 뿐, 자동 주문 트리거 금지.
LLM 호출은 반드시 call_llm() 경유. 룰북 §1-N 외 즉흥 시그널 거부.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

from app.intel.summarizer import SummarizedItem
from app.llm import Task, call_llm, default_system_blocks
from app.storage import SessionLocal
from app.storage.models import Signal as SignalORM  # 이름 충돌 회피

logger = logging.getLogger(__name__)


Direction = Literal[
    "strong_buy", "buy", "watch", "hold", "sell", "strong_sell"
]
# 런타임 응답 검증용 — Literal은 정적 검증만 함
_VALID_DIRECTIONS: Final[frozenset[str]] = frozenset(
    {"strong_buy", "buy", "watch", "hold", "sell", "strong_sell"}
)

# 룰북 §4 임계 — 그룹 weight_sum 1.0 미만이면 LLM 호출 자체 안 함 (코드 컷)
_WEIGHT_MIN_FOR_LLM: Final = 1.0

# §1-N 인과 사슬만 허용. §0/§2-N 등은 폐기.
_RULE_PREFIX_RE: Final = re.compile(r"^§(\d+)-(\d+)")
_JSON_ARRAY_RE: Final = re.compile(r"\[[\s\S]*\]", re.MULTILINE)


SIGNAL_PROMPT: Final = """아래는 게이트·요약기를 통과한 {n}개 그룹의 정보다.
각 그룹은 같은 룰북 §1 인과 사슬에 매핑된 SummarizedItem들이다.

{groups_json}

각 그룹에 대해 룰북 §4 행동 매핑 기준으로 시그널을 생성한다.
출력은 JSON 배열만, 추가 설명 금지. 스키마:
[
  {{
    "direction": "strong_buy|buy|watch|hold|sell|strong_sell",
    "target": "종목명·섹터명·매크로 대상",
    "applied_rule": "§1-N 인과 사슬",
    "combined_score": 합산 점수 (정수, 0-15),
    "reasoning": "한국어 3~5줄 근거"
  }}
]

행동 결정 기준 (룰북 §4):
- weight_sum >= 1.5 + combined_score >= 13 → strong_buy/strong_sell
- weight_sum >= 1.0 + combined_score >= 12 → buy/sell 또는 watch
- 그 외 → hold
"""


@dataclass(frozen=True, slots=True)
class Signal:
    """시그널 생성 결과. *추천*일 뿐 자동 주문 금지 (CLAUDE.md 절대 룰)."""

    direction: Direction
    target: str
    applied_rule: str
    combined_score: int
    weight_sum: float
    supporting_log_ids: list[int]
    reasoning: str
    signal_log_id: int


def _rule_prefix(rule: str) -> str | None:
    """'§1-3 미국 금리' → '§1-3'. §0이거나 §2-N 등 §1 외 섹션이면 None."""
    m = _RULE_PREFIX_RE.match(rule)
    if not m:
        return None
    section, idx = m.groups()
    if section != "1":
        return None
    return f"§{section}-{idx}"


def _serialize_groups(grouped: dict[str, list[SummarizedItem]]) -> str:
    """그룹별 최소 정보 JSON. 토큰 절감: 원본 IntelItem 전체 X, 필요 필드만."""
    out: dict[str, dict] = {}
    for rule_key, items in grouped.items():
        out[rule_key] = {
            "weight_sum": round(
                sum(it.original.source_weight for it in items), 2
            ),
            "items": [
                {
                    "source": it.original.source,
                    "summary_ko": it.summary_ko,
                    "refined_scores": list(it.refined_scores),
                }
                for it in items
            ],
        }
    return json.dumps(out, ensure_ascii=False, indent=2)


def _try_parse_array(text: str) -> list[dict] | None:
    """배열 JSON 파싱. 직접 파싱 → 정규식 폴백 → None."""
    try:
        v = json.loads(text)
        return v if isinstance(v, list) else None
    except json.JSONDecodeError:
        pass
    m = _JSON_ARRAY_RE.search(text)
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
        return v if isinstance(v, list) else None
    except json.JSONDecodeError:
        return None


def generate_signals(items: list[SummarizedItem]) -> list[Signal]:
    """SummarizedItem 리스트 → 룰북 §4 시그널 리스트.

    흐름:
        1. is_relevant=True 필터 (false positive 컷)
        2. applied_rule §1-N으로 그룹화 (§0/§2-N 등 폐기)
        3. weight_sum >= 1.0 그룹만 통과 (LLM 호출 비용 절감)
        4. Sonnet 호출 1회로 다중 그룹 처리
        5. 응답 검증·그룹 매칭 후 Signal 리스트 반환
    실패 시 빈 리스트 + logger.warning. RuntimeError(키 미설정)는 그대로 raise.
    """
    if not items:
        return []

    grouped: dict[str, list[SummarizedItem]] = defaultdict(list)
    for it in items:
        if not it.is_relevant:
            continue
        key = _rule_prefix(it.applied_rule)
        if key is None:
            continue
        grouped[key].append(it)

    # weight_sum 컷 — LLM 호출 전 코드 레벨에서 약그룹 폐기
    eligible: dict[str, list[SummarizedItem]] = {
        k: lst
        for k, lst in grouped.items()
        if sum(it.original.source_weight for it in lst) >= _WEIGHT_MIN_FOR_LLM
    }
    if not eligible:
        return []

    groups_json = _serialize_groups(eligible)
    user_msg = SIGNAL_PROMPT.format(n=len(eligible), groups_json=groups_json)

    task = Task(
        category="synthesize",
        complexity=6,
        input_tokens_estimate=len(user_msg) // 3,
    )

    try:
        result = call_llm(
            task,
            system=default_system_blocks(),
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=1500,
        )
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning("generate_signals LLM 호출 실패: %s", e)
        return []

    parsed = _try_parse_array(result["text"])
    if parsed is None:
        logger.warning(
            "generate_signals JSON 파싱 실패: %r", result["text"][:200]
        )
        return []

    signals: list[Signal] = []
    for entry in parsed:
        try:
            rule_key = _rule_prefix(str(entry["applied_rule"]))
            if rule_key is None or rule_key not in eligible:
                logger.warning(
                    "그룹 매칭 실패 — applied_rule=%r", entry.get("applied_rule")
                )
                continue
            direction = entry["direction"]
            if direction not in _VALID_DIRECTIONS:
                logger.warning("잘못된 direction: %r", direction)
                continue
            group = eligible[rule_key]
            signals.append(
                Signal(
                    direction=direction,
                    target=str(entry["target"]),
                    applied_rule=str(entry["applied_rule"]),
                    combined_score=int(entry["combined_score"]),
                    weight_sum=round(
                        sum(it.original.source_weight for it in group), 2
                    ),
                    supporting_log_ids=[
                        it.llm_call_log_id for it in group
                    ],
                    reasoning=str(entry["reasoning"]),
                    signal_log_id=int(result["log_id"]),
                )
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(
                "Signal 스키마 검증 실패: %s, entry=%r", e, entry
            )
            continue

    return signals


def _signal_to_orm(signal: Signal) -> SignalORM:
    """Signal dataclass → ORM 모델 변환. supporting_log_ids는 JSON 문자열로.

    weight_sum은 float → Decimal 변환 시 반드시 `str()` 경유 — 직접 `Decimal(float)`은
    부동소수점 오차로 1.4가 1.39999...로 저장될 위험.
    """
    return SignalORM(
        direction=signal.direction,
        target=signal.target,
        applied_rule=signal.applied_rule,
        combined_score=signal.combined_score,
        weight_sum=Decimal(str(signal.weight_sum)),
        supporting_log_ids=json.dumps(signal.supporting_log_ids),
        reasoning=signal.reasoning,
        signal_log_id=signal.signal_log_id,
    )


def save_signal(signal_obj: Signal) -> int:
    """Signal dataclass → DB INSERT. 새 row id 반환.

    generate_signals()와 분리(느슨한 결합): 호출자가 명시적으로 save 호출해야 영구화된다.
    검증·dry-run 시 save 없이도 동작 가능.
    """
    db = SessionLocal()
    try:
        row = _signal_to_orm(signal_obj)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    except Exception as e:
        db.rollback()
        logger.error("save_signal 실패: %s", e)
        raise
    finally:
        db.close()
