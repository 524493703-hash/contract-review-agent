from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {
    "charset": "utf8mb4",
    "connect_timeout": 10,
}
engine_options = {"connect_args": connect_args}
if not is_sqlite:
    engine_options.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_pre_ping=settings.db_pool_pre_ping,
        pool_timeout=15,
        skip_autocommit_rollback=True,
    )
engine = create_engine(settings.database_url, **engine_options)
read_engine = engine if is_sqlite else create_engine(
    settings.database_url,
    isolation_level="AUTOCOMMIT",
    **engine_options,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
ReadSessionLocal = sessionmaker(bind=read_engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_read_db() -> Generator[Session, None, None]:
    """Read-only request session without a remote ROLLBACK round trip."""
    db = ReadSessionLocal()
    try:
        yield db
    finally:
        db.close()
