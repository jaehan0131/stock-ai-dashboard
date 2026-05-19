"""DB 엔진·세션·Base 정의. settings.database_url에서만 URL 로드."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# SQLite는 멀티스레드(FastAPI thread pool) 환경에서 check_same_thread=False 필요.
# 다른 DB(Postgres 등)는 connect_args 비워둠.
_connect_args: dict[str, object] = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    future=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
)


class Base(DeclarativeBase):
    """모든 ORM 모델의 공통 상위. SQLAlchemy 2.x DeclarativeBase 상속."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI 의존성 주입용 세션 제너레이터. 요청 종료 시 자동 close."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
