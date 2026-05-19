"""Anthropic Prompt Caching 헤더 부착 모듈.

핵심 규칙 (CLAUDE.md 절대 룰):
- 룰북·시스템 프롬프트는 prefix 위치(앞쪽 블록)에 둔다. 변동 콘텐츠 뒤에 두면 캐시 적중률 0.
- TTL 기본은 "1h", "5m"는 명시적 단기 캐시 필요 시만.
- 캐시 최소 단위 미달 블록은 자동으로 cache_control 생략 (fail-soft).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Literal

SYSTEM_PROMPT: Final = (
    "당신은 한국 주식 시장 분석 보조 AI다. "
    "모든 시그널 출력은 룰북 기준을 따른다. "
    "{사실, 룰, 점수, 출처} 구조로 응답한다."
)

# 캐시 자격 휴리스틱: 정확한 토큰 카운트는 SDK 호출 필요 → 문자수 근사 사용.
# 한글 위주 텍스트에서 1 token ≈ 2.5 chars 어림. Sonnet/Opus 최소 1024 tokens × 2.5 = 2560.
# 주의: Haiku는 최소 2048 tokens(약 5120 chars) 필요 — 이 임계는 Sonnet/Opus 기준.
# 룰북을 Haiku에 넘기는 경로가 생기면 호출자 측에서 cache 미사용 처리 필요.
_CACHE_MIN_CHARS: Final = 2560

# 룰북 파일 경로 — cache.py의 상위 2단계(app/llm → app)에서 intel/rulebook.md
_RULEBOOK_PATH: Final = (
    Path(__file__).resolve().parent.parent / "intel" / "rulebook.md"
)


@dataclass(frozen=True, slots=True)
class CacheBlock:
    """캐시 가능한 시스템 프롬프트 블록 1개."""

    text: str
    ttl: Literal["5m", "1h"] = "1h"


def build_cached_system(blocks: list[CacheBlock]) -> list[dict[str, Any]]:
    """CacheBlock 리스트 → Anthropic SDK용 system 메시지 블록(list[dict]).

    `_CACHE_MIN_CHARS` 미만 블록은 cache_control 생략 (캐시 최소 단위 미달 시 API 거부 회피).
    """
    out: list[dict[str, Any]] = []
    for b in blocks:
        block: dict[str, Any] = {"type": "text", "text": b.text}
        if len(b.text) >= _CACHE_MIN_CHARS:
            block["cache_control"] = {"type": "ephemeral", "ttl": b.ttl}
        out.append(block)
    return out


@lru_cache(maxsize=1)
def read_rulebook() -> str:
    """룰북 파일을 1회 읽어 메모리 캐시. 변경 시 `read_rulebook.cache_clear()` 호출."""
    return _RULEBOOK_PATH.read_text(encoding="utf-8")


def default_system_blocks() -> list[CacheBlock]:
    """기본 시스템 프롬프트 + 룰북을 캐시 대상 블록 리스트로 반환.

    `SYSTEM_PROMPT`는 짧아 cache_control 미부착, 룰북 블록만 캐시된다.
    """
    return [
        CacheBlock(SYSTEM_PROMPT, ttl="1h"),
        CacheBlock(read_rulebook(), ttl="1h"),
    ]
