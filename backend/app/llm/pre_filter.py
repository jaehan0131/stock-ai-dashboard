"""LLM 호출 전 코드 레벨 필터링.

룰북 v1.0 동기화 — 룰북 버전 올라가면 이 모듈 임계값도 검토할 것.
- 점수 3축(impact/time/size): 각 0~5점, 룰북 §2.
- 출처 신뢰도: 0.1~1.0, 룰북 §3.

단일 프로세스 가정의 인메모리 dedup. 멀티프로세스 공유는 후속(Redis 등).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Final

# 룰북 v1.0 임계값 — 변경 시 룰북도 함께 갱신할 것.
SOURCE_WEIGHT_MIN: Final = 0.3  # 룰북 §3: 분석 플랫폼·검증 KOL 이상
SCORE_SUM_MIN: Final = 9  # router-design.md §5: 3축 합산 9/15 이상
DEDUP_HOURS: Final = 24


@dataclass(frozen=True, slots=True)
class IntelItem:
    """intel/ 수집기가 만드는 외부 정보의 통일 진입점."""

    source: str
    source_weight: float
    content_summary: str
    score_impact: int  # 0~5
    score_time: int  # 0~5
    score_size: int  # 0~5
    dedup_key: str
    timestamp: datetime

    def __post_init__(self) -> None:
        # tz-aware UTC 강제 (CLAUDE.md 절대 룰)
        if self.timestamp.tzinfo is None:
            raise ValueError(
                "IntelItem.timestamp는 tz-aware datetime이어야 합니다. "
                "예: datetime.now(timezone.utc)"
            )

    def score_sum(self) -> int:
        """3축 합산. 0~15."""
        return self.score_impact + self.score_time + self.score_size


class _DedupCache:
    """{dedup_key: registered_at} 인메모리 캐시. 만료 항목은 lazy 정리."""

    def __init__(self) -> None:
        self._store: dict[str, datetime] = {}

    def has_recent(self, key: str, hours: int = DEDUP_HOURS) -> bool:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=hours)
        self._store = {k: t for k, t in self._store.items() if t > cutoff}
        return key in self._store

    def add(self, key: str) -> None:
        self._store[key] = datetime.now(timezone.utc)

    def clear(self) -> None:
        self._store.clear()


_dedup_cache = _DedupCache()


def should_call_llm(item: IntelItem) -> tuple[bool, str]:
    """룰북 기준 필터링. 반환: (호출 가능 여부, 사유 한국어 문자열).

    통과한 경우에만 dedup 캐시에 등록한다 — 거부된 항목은 정보 보강 후 재시도 가능.
    """
    if item.source_weight < SOURCE_WEIGHT_MIN:
        return False, f"출처 신뢰도 미달: {item.source_weight}"

    total = item.score_sum()
    if total < SCORE_SUM_MIN:
        return False, f"합산점수 미달: {total}/15"

    if _dedup_cache.has_recent(item.dedup_key):
        return False, f"중복: {DEDUP_HOURS}h 이내 처리 이력"

    _dedup_cache.add(item.dedup_key)
    return True, "통과"


def clear_dedup_cache() -> None:
    """dedup 캐시 초기화. 테스트·수동 리셋용."""
    _dedup_cache.clear()
