"""시그널 조회·승인·수집 트리거 API.

CLAUDE.md 절대 룰: 어떤 엔드포인트도 주문을 실행하지 않는다.
approve는 *상태 변경*일 뿐, 실제 매매는 Phase G의 별도 모듈에서만 가능하다.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import IntelRunResult, SignalRead
from app.storage import Signal, get_db

router = APIRouter()


@router.get("/signals/pending", response_model=list[SignalRead])
def list_pending(db: Session = Depends(get_db)) -> list[Signal]:
    """user_status='pending' 시그널을 최근순 50건 반환."""
    stmt = (
        select(Signal)
        .where(Signal.user_status == "pending")
        .order_by(Signal.created_at.desc())
        .limit(50)
    )
    return list(db.scalars(stmt))


@router.get("/signals/{signal_id}", response_model=SignalRead)
def get_signal(signal_id: int, db: Session = Depends(get_db)) -> Signal:
    """단일 시그널 상세 조회. 없으면 404."""
    row = db.get(Signal, signal_id)
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"시그널을 찾을 수 없습니다: id={signal_id}",
        )
    return row


def _transition(db: Session, signal_id: int, new_status: str) -> Signal:
    """pending → approved/rejected 공통 로직.

    이미 결정된 시그널(approved/rejected)은 409로 차단 — 중복 처리 방지.
    """
    row = db.get(Signal, signal_id)
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"시그널을 찾을 수 없습니다: id={signal_id}",
        )
    if row.user_status != "pending":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"이미 처리된 시그널입니다: 현재 상태={row.user_status}",
        )
    row.user_status = new_status
    row.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


@router.post("/signals/{signal_id}/approve", response_model=SignalRead)
def approve_signal(
    signal_id: int, db: Session = Depends(get_db)
) -> Signal:
    """시그널 승인. CLAUDE.md 절대 룰: 승인은 *상태 변경*일 뿐, 주문 트리거가 아니다."""
    return _transition(db, signal_id, "approved")


@router.post("/signals/{signal_id}/reject", response_model=SignalRead)
def reject_signal(
    signal_id: int, db: Session = Depends(get_db)
) -> Signal:
    """시그널 거부."""
    return _transition(db, signal_id, "rejected")


@router.post("/intel/run", response_model=IntelRunResult)
def run_intel_pipeline() -> IntelRunResult:
    """수동 트리거: RSS → 게이트 → 요약 → 시그널 종합 → DB 저장.

    동기 실행 (수십초 소요 가능). 키 미설정 시 500 + 한국어 에러.
    """
    # 지연 import — startup 시점에 LLM·intel 모듈을 로드하지 않아 부팅 가볍게
    from app.intel.collectors import fetch_all
    from app.intel.signals import generate_signals
    from app.intel.signals.aggregate import save_signal
    from app.intel.summarizer import summarize_item
    from app.llm import clear_dedup_cache, should_call_llm

    clear_dedup_cache()
    raw = fetch_all()
    passed = [it for it in raw if should_call_llm(it)[0]]

    try:
        summarized = [
            s for s in (summarize_item(it) for it in passed) if s is not None
        ]
        signals_out = generate_signals(summarized)
        saved_ids = [save_signal(s) for s in signals_out]
    except RuntimeError as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    return IntelRunResult(
        collected=len(raw),
        gate_passed=len(passed),
        summarized=len(summarized),
        signals_generated=len(signals_out),
        saved_ids=saved_ids,
    )
