"""APScheduler 4.x AsyncScheduler — 백그라운드 자동화.

CLAUDE.md 절대 룰 매핑
- 장 운영 외 시간(평일 09:00–15:30 KST 밖)에는 KIS 호출 차단
- job 함수는 자체 try/except — 한 job 실패가 스케줄러/서버 전체를 죽이지 않게
- 모든 datetime은 tz-aware. 장 시간 판정은 Asia/Seoul 기준
- 시그널 생성은 절대 자동 주문을 트리거하지 않는다 (signals API와 동일 룰)

스케줄
- RSS 시그널 파이프라인: 30분마다 (항상 실행)
- 시세 캐시 갱신: 5분마다 (장중에만 실행)
- 체결 폴링: 1분마다 (장중에만 실행) — Phase H

향후 개선
- WATCHLIST를 DB 테이블 또는 settings로 이동
- pykrx로 한국 휴장일 검증 추가 (현재는 평일+시간만 체크)
- price_cache를 Redis 등 공유 캐시로 이동 (단일 인스턴스 한정 현황)
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, time as dtime
from typing import Any, AsyncIterator, Final
from zoneinfo import ZoneInfo

from apscheduler import AsyncScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


# Phase ② 명세 — 관심 종목 하드코드. Phase G 진입 시 DB/설정으로 이동.
WATCHLIST: Final[tuple[str, ...]] = ("005930", "000660")

KST: Final[ZoneInfo] = ZoneInfo("Asia/Seoul")
MARKET_OPEN: Final[dtime] = dtime(9, 0)
MARKET_CLOSE: Final[dtime] = dtime(15, 30)

# 단일 프로세스 메모리 캐시. 다중 인스턴스에선 종목별 최종 갱신값이 인스턴스마다 다를 수 있음.
price_cache: dict[str, dict[str, Any]] = {}


def is_market_open(now_kst: datetime | None = None) -> bool:
    """KST 기준 정규장 시간 + 평일 여부를 반환한다.

    한국 휴장일(어린이날 등)은 현재 검증하지 않음 — 호출 시 KIS가 에러 응답을 줄 것이고
    job의 try/except가 이를 격리한다. pykrx 추가 시 정밀화 가능.
    """
    now = now_kst or datetime.now(KST)
    if now.weekday() >= 5:  # 토(5), 일(6)
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


async def _rss_signal_job() -> None:
    """RSS → 게이트 → 요약 → 시그널 종합 → DB 저장 한 사이클."""
    logger.info("scheduler[rss]: 사이클 시작")
    try:
        # /intel/run의 동기 함수를 재사용. 동기 호출이라 이벤트 루프 블록을 막기 위해
        # 별도 스레드에서 실행한다. LLM 호출이 길어도 다른 API가 멈추지 않는다.
        from app.api.signals import run_intel_pipeline

        result = await asyncio.to_thread(run_intel_pipeline)
        logger.info(
            "scheduler[rss]: 사이클 완료 collected=%s passed=%s summarized=%s "
            "signals=%s saved_ids=%s",
            result.collected,
            result.gate_passed,
            result.summarized,
            result.signals_generated,
            result.saved_ids,
        )
    except Exception as e:
        logger.exception("scheduler[rss]: 사이클 실패 — %s", e)


async def _price_cache_job() -> None:
    """관심 종목 현재가 갱신. 장외 시간엔 KIS 호출 자체를 스킵."""
    if not is_market_open():
        logger.debug("scheduler[price]: 장외 — 갱신 스킵")
        return

    logger.info("scheduler[price]: 갱신 시작 watchlist=%s", WATCHLIST)
    from app.market.kis_price import get_current_price

    for code in WATCHLIST:
        try:
            result = await get_current_price(code, dry_run=False)
            if result["success"]:
                price_cache[code] = {
                    **result["data"],
                    "fetched_at": datetime.now(KST).isoformat(),
                }
                logger.info(
                    "scheduler[price]: 갱신 성공 code=%s price=%s",
                    code,
                    result["data"].get("current_price"),
                )
            else:
                logger.warning(
                    "scheduler[price]: KIS 비즈니스 실패 code=%s err=%s",
                    code,
                    result["error"],
                )
        except Exception as e:
            logger.exception("scheduler[price]: 예외 code=%s — %s", code, e)


async def _order_poll_job() -> None:
    """장중에만 — pending + dry_run=False + ODNO 있는 OrderLog 체결조회."""
    if not is_market_open():
        logger.debug("scheduler[poll]: 장외 — 스킵")
        return

    # 지연 import — startup 시점에 trading 모듈 import 회피 + 순환 방지
    from sqlalchemy import select

    from app.storage import SessionLocal
    from app.storage.models import OrderLog
    from app.trading.kis_order import fetch_order_status

    db = SessionLocal()
    try:
        stmt = select(OrderLog.id).where(
            OrderLog.status == "pending",
            OrderLog.dry_run.is_(False),
            OrderLog.kis_order_number.is_not(None),
        )
        pending_ids = list(db.scalars(stmt))
    finally:
        db.close()

    if not pending_ids:
        logger.debug("scheduler[poll]: pending 0건 — 스킵")
        return

    logger.info("scheduler[poll]: %s건 체결조회", len(pending_ids))
    for oid in pending_ids:
        try:
            result = await fetch_order_status(oid)
            if result.get("changed"):
                logger.info("scheduler[poll]: order_log_id=%s 상태 전이", oid)
        except Exception as e:
            logger.exception(
                "scheduler[poll]: order_log_id=%s 실패 — %s", oid, e
            )


@asynccontextmanager
async def scheduler_lifespan() -> AsyncIterator[None]:
    """AsyncScheduler 생성·잡 등록·백그라운드 실행·정리까지 컨텍스트로 묶는다.

    async with AsyncScheduler() 의 __aenter__ 가 start_in_background() 를 호출하고
    __aexit__ 가 stop() 을 호출한다 — 별도로 두 번 호출하면 안 됨.
    """
    async with AsyncScheduler() as sched:
        await sched.add_schedule(
            _rss_signal_job,
            IntervalTrigger(minutes=30),
            id="rss_signal_pipeline",
        )
        await sched.add_schedule(
            _price_cache_job,
            IntervalTrigger(minutes=5),
            id="price_cache_refresh",
        )
        await sched.add_schedule(
            _order_poll_job,
            IntervalTrigger(minutes=1),
            id="order_poll",
        )
        logger.info(
            "scheduler: 시작됨 — rss=30min(항상), price=5min(장중만), poll=1min(장중만)"
        )
        try:
            yield
        finally:
            logger.info("scheduler: 종료 진행")
