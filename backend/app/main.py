"""FastAPI 엔트리. CORS·헬스체크·라우터 include만 담당.

CLAUDE.md 절대 룰: 어떤 엔드포인트도 주문 실행을 트리거하지 않는다.
api/signals.py의 approve는 *상태 변경*일 뿐, 실제 매매는 Phase G 별도 모듈에서만.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import signals as signals_router
from app.storage import get_db

app = FastAPI(title="주식 AI 대시보드 API", version="0.1.0")

# 학습 단계 — 모든 origin 허용. production 진입 전 좁힐 것.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(signals_router.router)


@app.get("/healthz")
def healthz(db: Session = Depends(get_db)) -> dict[str, str]:
    """헬스체크. DB 연결까지 검증한다. 실패 시 503."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"DB 연결 실패: {e}",
        )
    return {"status": "ok", "db": "connected"}
