import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.backend.models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Construct from parts
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER_NAME", "admin")
    password = os.getenv("POSTGRES_PASSWORD", "password123")
    db = os.getenv("POSTGRES_DB", "health_agent")
    DATABASE_URL = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


async def init_db():
    engine = create_async_engine(DATABASE_URL, echo=True)

    async with engine.begin() as conn:
        print("🚀 Initializing Database...")

        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        print("✅ pgvector extension enabled.")

        # Create all tables: patients, medical_history, clinical_alerts
        await conn.run_sync(Base.metadata.create_all)
        print("✅ All tables created:")
        print("   • patients")
        print("   • medical_history")
        print("   • clinical_alerts")
        print()
        print("ℹ️  Note: 'medical_knowledge' (pgvector embeddings table) is NOT created here.")
        print("   It is created automatically by the RAG service (PostgresRAGManager)")
        print("   on the first startup of the FastAPI backend via langchain-postgres.")

    await engine.dispose()
    print("✅ Database initialization complete.")


if __name__ == "__main__":
    asyncio.run(init_db())