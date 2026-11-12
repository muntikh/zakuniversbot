from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    # High-concurrency settings for SQLite under 10k users
    connect_args={"check_same_thread": False, "timeout": 30.0} if "sqlite" in settings.database_url else {},
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create all tables and configure SQLite for high concurrency."""
    from bot.db.models import Base  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if "sqlite" in settings.database_url:
        async with AsyncSessionLocal() as session:
            # WAL journal allows unlimited concurrent readers alongside writers
            await session.execute(text("PRAGMA journal_mode=WAL"))
            # 30-second busy timeout prevents 'database is locked' under concurrent load
            await session.execute(text("PRAGMA busy_timeout=30000"))
            # NORMAL synchronous is 5-10x faster and safe with WAL mode
            await session.execute(text("PRAGMA synchronous=NORMAL"))
            # 64MB memory cache for SQLite index/data pages
            await session.execute(text("PRAGMA cache_size=-64000"))

            try:
                await session.execute(text("ALTER TABLE orders ADD COLUMN custom_config_name VARCHAR(64)"))
                await session.commit()
            except Exception:
                await session.rollback()
            await session.commit()


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
