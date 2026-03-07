"""
Sentinel Health Agent — FastAPI application entry point.

Responsibilities (only):
  1. Run startup / shutdown lifecycle via `lifespan`
  2. Create the FastAPI `app` instance
  3. Register all routers with `app.include_router`

All business logic lives in dedicated modules:
  - app.backend.database        → engine & session factory
  - app.backend.services.*      → business services
  - app.backend.routers.*       → HTTP route handlers
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import setup_logging
from app.backend.database import AsyncSessionLocal, engine, validate_env_vars
from app.backend.services.kafka_consumer import KafkaConsumerService
from app.backend.services.process_alerts import ProcessAlerts
from app.backend.services.rag_service import MedicalRAG
from app.backend.routers import core as core_router
from app.backend.routers import patients as patients_router
from app.backend.routers import chatbot as chatbot_router

logger = setup_logging()

# Validate required environment variables at startup (fail fast)
try:
    validate_env_vars()
except RuntimeError as exc:
    logger.critical(f"Configuration error: {exc}")
    raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    Startup:
      - Initialise the RAG (vector store + LLM) service
      - Start the Kafka consumer background task
      - Expose shared resources on app.state for routers

    Shutdown:
      - Stop the Kafka consumer gracefully
      - Close the RAG engine connection pool
      - Dispose the SQLAlchemy engine
    """
    logger.info("🚀 Starting Sentinel Health Agent...")

    # ── RAG service ──────────────────────────────────────────────────────
    rag_service = MedicalRAG()
    try:
        await rag_service.initialize()
        logger.info("✅ RAG service initialised")
    except Exception as exc:
        logger.error(f"Failed to initialise RAG service: {exc}", exc_info=True)
        raise

    # ── Alert processor (injected with RAG to avoid double-init) ────────
    process_alerts = ProcessAlerts(AsyncSessionLocal, rag_service)

    # ── Kafka consumer ───────────────────────────────────────────────────
    kafka_service = KafkaConsumerService(process_alerts)
    await kafka_service.start()

    # ── Expose shared state for routers ─────────────────────────────────
    app.state.session_factory = AsyncSessionLocal
    app.state.rag_service = rag_service
    app.state.kafka_service = kafka_service
    app.state.engine = engine
    app.state.chatbot_graphs = {}   # session_id → compiled LangGraph

    yield  # Application is running

    # ── Graceful shutdown ────────────────────────────────────────────────
    logger.info("🛑 Shutting down Sentinel Health Agent...")
    await kafka_service.stop()
    await rag_service.close()
    await engine.dispose()
    logger.info("✅ Shutdown complete")


# ---------------------------------------------------------------------------
# Application instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Sentinel Health Agent",
    description=(
        "AI-powered real-time clinical alert monitoring "
        "with RAG + LangGraph nurse chatbot."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Router registration — each domain owns its own router file
# ---------------------------------------------------------------------------
app.include_router(core_router.router)
app.include_router(patients_router.router)
app.include_router(chatbot_router.router)



if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.backend.main:app", host="0.0.0.0", port=8000, reload=False)
