import logging
from typing import AsyncGenerator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    if url.startswith("postgresql+asyncpg") and "localhost" not in url and "127.0.0.1" not in url:
        return {"ssl": True}  # Neon / managed Postgres require TLS
    return {}


engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args=_connect_args(settings.DATABASE_URL),
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    from app import models  # noqa: F401  (register tables)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)
    logger.info("Database ready.")


def _add_missing_columns(sync_conn) -> None:
    """create_all never alters existing tables; add new nullable columns so deploys need no manual SQL.

    shortcut: additive nullable columns only; switch to Alembic for renames, drops or constraints.
    """
    inspector = inspect(sync_conn)
    for table in Base.metadata.sorted_tables:
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in existing and column.nullable:
                col_type = column.type.compile(dialect=sync_conn.dialect)
                sync_conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {col_type}'))
                logger.info("Added column %s.%s", table.name, column.name)


async def db_alive() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database ping failed")
        return False


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
