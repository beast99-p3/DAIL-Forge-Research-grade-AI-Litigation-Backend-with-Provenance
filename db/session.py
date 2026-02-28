"""Async and sync SQLAlchemy engine / session factories."""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from api.config import get_settings

settings = get_settings()

# ── Async (used by FastAPI) ──────────────────────────────────────────
async_engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def get_async_session() -> AsyncSession:  # type: ignore[misc]
    async with AsyncSessionLocal() as session:
        yield session


# ── Sync (used by pipeline / Alembic) ───────────────────────────────
sync_engine = create_engine(settings.DATABASE_URL_SYNC, echo=False, future=True)
SyncSessionLocal = sessionmaker(sync_engine, class_=Session, expire_on_commit=False)


def get_sync_session() -> Session:  # type: ignore[misc]
    with SyncSessionLocal() as session:
        yield session
