"""
Database engine and session-factory configuration.

All other modules that need a DB session should import
`engine` or `AsyncSessionLocal` from here rather than
creating their own engine instances.
"""
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import setup_logging
from app.utils.config import DATABASE_URL

logger = setup_logging()

# ---------------------------------------------------------------------------
# Engine — created once at import time, shared across the whole process.
# Pool settings tuned for a small production deployment:
#   pool_size=20    → max persistent connections held open
#   max_overflow=10 → additional connections allowed under burst load
#   pool_recycle=3600 → recycle connections hourly to avoid stale sockets
#   pool_pre_ping=True → verify connections before use (detects broken pipes)
# ---------------------------------------------------------------------------
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10,
    pool_recycle=3600,
    pool_timeout=30,
    echo_pool=False,
    connect_args={
        "timeout": 10,
        "command_timeout": 10,
        "server_settings": {"application_name": "sentinel_health_agent"},
    },
)

# ---------------------------------------------------------------------------
# Session factory — async_sessionmaker is the SQLAlchemy 2.x equivalent of
# sessionmaker for AsyncEngine. Use as:
#     async with AsyncSessionLocal() as session:
#         ...
# ---------------------------------------------------------------------------
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def validate_env_vars() -> None:
    """
    Validate that all required environment variables are present.

    Raises:
        RuntimeError: If any required variable is missing or DATABASE_URL
                      contains unresolved 'None' placeholders.
    """
    required = ["KAFKA_BOOTSTRAP_SERVERS", "KAFKA_CONSUMER_TOPIC", "OLLAMA_HOST"]
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )
    if not DATABASE_URL or "None" in DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not properly configured")
    logger.info("✅ All environment variables validated")

