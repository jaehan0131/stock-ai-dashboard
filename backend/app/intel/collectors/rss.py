"""RSS 수집기. 무료 RSS/Atom 피드 → IntelItem 변환.

룰북 v1.0 §1(인과 사슬 8축)·§3(출처 신뢰도) 동기화.
점수는 정적 기본값 (2,2,2) + 키워드 부스트 — LLM 호출 없이 코드만 처리한다.
키워드 매칭 0개면 합 6 → should_call_llm 게이트에서 자동 거부된다.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Final

import feedparser

from app.llm import IntelItem

logger = logging.getLogger(__name__)


# 출처 ID → (URL, 신뢰도 가중치). 룰북 §3과 동기화.
RSS_SOURCES: Final[dict[str, tuple[str, float]]] = {
    "yahoo_finance_market": ("https://finance.yahoo.com/news/rssindex", 0.6),
    "reuters_business": ("https://feeds.reuters.com/reuters/businessNews", 0.8),
}


# 룰북 §1 인과 사슬 8축 매핑. (impact, time, size) 가산값.
# 변경 시 룰북 §1과 함께 갱신할 것.
KEYWORD_BOOST: Final[dict[str, tuple[int, int, int]]] = {
    "fomc":          (2, 2, 2),
    "fed":           (2, 1, 1),
    "interest rate": (2, 1, 1),
    "cpi":           (2, 2, 1),
    "inflation":     (1, 0, 1),
    "recession":     (2, 0, 2),
    "nvidia":        (2, 1, 2),
    "tsmc":          (2, 1, 2),
    "semiconductor": (2, 0, 2),
    "china pmi":     (2, 1, 1),
    "yuan":          (1, 1, 1),
    "crude oil":     (1, 1, 1),
    "wti":           (1, 1, 1),
    "war":           (1, 0, 2),
    "sanctions":     (1, 0, 1),
}

_BASE_SCORE: Final[tuple[int, int, int]] = (2, 2, 2)
_MAX_PER_AXIS: Final = 5


def score_item(title: str, summary: str) -> tuple[int, int, int]:
    """RSS title+summary 키워드 매칭으로 (impact, time, size) 점수 산정.

    각 축은 max 5로 cap. 매칭 0이면 (2,2,2) 합 6 → should_call_llm 게이트 거부.
    """
    text = f"{title} {summary}".lower()
    impact, time_, size = _BASE_SCORE
    for kw, (i, t, s) in KEYWORD_BOOST.items():
        if kw in text:
            impact += i
            time_ += t
            size += s
    return (
        min(impact, _MAX_PER_AXIS),
        min(time_, _MAX_PER_AXIS),
        min(size, _MAX_PER_AXIS),
    )


def _make_dedup_key(source_id: str, title: str, ts: datetime) -> str:
    """SHA256(source|title|YYYY-MM-DD)의 앞 16자.

    title 기반(URL은 트래킹 파라미터로 변동 가능), 날짜 단위(시·분 미포함)로 안정성 확보.
    """
    date_str = ts.astimezone(timezone.utc).strftime("%Y-%m-%d")
    raw = f"{source_id}|{title}|{date_str}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _parse_timestamp(entry: Any) -> datetime:
    """feedparser entry → tz-aware UTC datetime. 누락 시 현재 시각."""
    tt = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )
    if tt is None:
        return datetime.now(timezone.utc)
    # feedparser의 *_parsed는 time.struct_time(UTC 사양). 6개 필드만 사용.
    return datetime(
        tt.tm_year, tt.tm_mon, tt.tm_mday,
        tt.tm_hour, tt.tm_min, tt.tm_sec,
        tzinfo=timezone.utc,
    )


def fetch_rss(source_id: str, limit: int = 20) -> list[IntelItem]:
    """단일 RSS 피드 → IntelItem 리스트.

    알 수 없는 source_id → ValueError. 네트워크 에러 → RuntimeError(원인 포함).
    entries가 비면 빈 리스트 반환(fail-soft).
    """
    if source_id not in RSS_SOURCES:
        raise ValueError(f"알 수 없는 출처: {source_id}")

    url, weight = RSS_SOURCES[source_id]

    try:
        feed = feedparser.parse(url)
    except Exception as e:
        raise RuntimeError(f"RSS 수집 실패: {source_id}: {e}") from e

    items: list[IntelItem] = []
    for entry in feed.entries[:limit]:
        title = entry.get("title", "")
        summary = entry.get("summary", "")[:500]
        ts = _parse_timestamp(entry)
        si, st, sz = score_item(title, summary)
        items.append(
            IntelItem(
                source=source_id,
                source_weight=weight,
                content_summary=f"{title}\n{summary}",
                score_impact=si,
                score_time=st,
                score_size=sz,
                dedup_key=_make_dedup_key(source_id, title, ts),
                timestamp=ts,
            )
        )
    return items


def fetch_all() -> list[IntelItem]:
    """RSS_SOURCES 전체 순회. 개별 출처 실패는 격리하고 logger.warning만 남긴다."""
    out: list[IntelItem] = []
    for source_id in RSS_SOURCES:
        try:
            out.extend(fetch_rss(source_id))
        except Exception as e:
            logger.warning("RSS 수집 실패(스킵): %s: %s", source_id, e)
    return out
