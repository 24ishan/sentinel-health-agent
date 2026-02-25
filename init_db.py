import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.backend.models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


async def init_db():
    # 1. Create the async engine
    engine = create_async_engine(DATABASE_URL, echo=True)

    async with engine.begin() as conn:
        print("🚀 Initializing Database...")

        # 2. Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        print("✅ pgvector extension enabled.")

        # 3. Create a test table with a vector column
        await conn.execute(text("""
                                CREATE TABLE IF NOT EXISTS test_vectors
                                (
                                    id
                                    serial
                                    PRIMARY
                                    KEY,
                                    embedding
                                    vector
                                (
                                    3
                                )
                                    );
                                """))
        print("✅ Table 'test_vectors' created.")

        await conn.run_sync(Base.metadata.create_all)
        print("✅ Clinical Alerts table synchronized.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())