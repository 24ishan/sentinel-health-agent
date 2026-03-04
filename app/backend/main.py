from typing import List, Optional
import asyncio
from datetime import datetime, timezone
import json
import os
import shutil
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, File, FastAPI, HTTPException, UploadFile
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app import setup_logging
from app.backend.schemas import ClinicalAlertResponse
from app.backend.services.history import AlertHistory
from app.backend.services.process_alerts import ProcessAlerts
from app.backend.services.rag_service import MedicalRAG
from app.backend.routers import patients as patients_router
from app.backend.routers import chatbot as chatbot_router
from app.utils.config import (
    DATABASE_URL,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_CONSUMER_TOPIC,
    OLLAMA_HOST,
    VECTOR_TABLE_NAME,
)
from app.backend.constants import (
    KAFKA_AUTO_OFFSET_RESET,
    KAFKA_RECONNECT_BACKOFF_MAX_MS,
    KAFKA_RECONNECT_BACKOFF_MS,
    KAFKA_REQUEST_TIMEOUT_MS,
    KAFKA_RETRY_DELAY_SECONDS,
    KAFKA_SESSION_TIMEOUT_MS,
)
from app.vector_db.ingest_pdf import PostgresRAGManager
from app.backend.schemas import UploadResponse

logger = setup_logging()


def validate_env_vars():
    required_vars = ["DATABASE_URL", "KAFKA_BOOTSTRAP_SERVERS", "KAFKA_CONSUMER_TOPIC", "OLLAMA_HOST"]
    missing = [var for var in required_vars if not os.getenv(var) and var != "DATABASE_URL"]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    if not DATABASE_URL or "None" in DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not properly configured")
    logger.info("✅ All environment variables validated")

try:
    validate_env_vars()
except RuntimeError as e:
    logger.critical(f"Configuration Error: {e}")
    raise

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
        "server_settings": {
            "application_name": "sentinel_health_agent"
        }
    }
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

process_alerts_instance: Optional[ProcessAlerts] = None
rag_service: Optional[MedicalRAG] = None
kafka_consumer = None
kafka_task: Optional[asyncio.Task] = None
MAX_RETRIES = 5
RETRY_DELAY = 5
KAFKA_POLL_TIMEOUT = 1000
MAX_POLL_RECORDS = 10


@asynccontextmanager
async def lifespan(app: FastAPI):
    global kafka_task, process_alerts_instance, rag_service
    logger.info("🚀 Starting Sentinel Health Agent...")

    # Initialize RAG service
    try:
        rag_service = MedicalRAG()
        await rag_service.initialize()
        logger.info("✅ RAG service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize RAG service: {e}", exc_info=True)
        raise

    # Initialize ProcessAlerts with RAG service injected
    process_alerts_instance = ProcessAlerts(AsyncSessionLocal, rag_service)

    # Expose shared resources on app.state for routers to access
    app.state.session_factory = AsyncSessionLocal
    app.state.rag_service = rag_service
    app.state.chatbot_graphs = {}           # session_id → compiled LangGraph

    kafka_task = asyncio.create_task(blocking_kafka_loop())
    logger.info("✅ Kafka consumer task created")
    yield

    logger.info("🛑 Shutting down application...")
    if kafka_task:
        kafka_task.cancel()
        try:
            await asyncio.wait_for(kafka_task, timeout=10)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            logger.warning("⚠️  Kafka consumer shutdown timeout exceeded")

    if rag_service:
        await rag_service.close()

    await engine.dispose()
    logger.info("✅ Application shutdown complete")


async def blocking_kafka_loop():
    global kafka_consumer, process_alerts_instance
    retry_count = 0
    messages_processed = 0

    while retry_count < MAX_RETRIES:
        try:
            kafka_consumer = KafkaConsumer(
                KAFKA_CONSUMER_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                auto_offset_reset=KAFKA_AUTO_OFFSET_RESET,
                session_timeout_ms=KAFKA_SESSION_TIMEOUT_MS,
                request_timeout_ms=KAFKA_REQUEST_TIMEOUT_MS,
                reconnect_backoff_ms=KAFKA_RECONNECT_BACKOFF_MS,
                reconnect_backoff_max_ms=KAFKA_RECONNECT_BACKOFF_MAX_MS,
            )
            retry_count = 0
            logger.info(f"📡 Kafka connected, monitoring topic: {KAFKA_CONSUMER_TOPIC}")

            while True:
                try:
                    message = await asyncio.to_thread(
                        kafka_consumer.poll, timeout_ms=KAFKA_POLL_TIMEOUT, max_records=MAX_POLL_RECORDS
                    )
                    if not message:
                        continue

                    for topic_partition, records in message.items():
                        for record in records:
                            try:
                                data = record.value
                                alert_status = data.get("status")
                                if alert_status in ["CRITICAL", "WARNING"]:
                                    assert process_alerts_instance is not None
                                    await process_alerts_instance.process_critical_alert(data, data.get("heart_rate"))
                                    messages_processed += 1
                                    logger.debug(f"✅ Processed {messages_processed} critical alerts")
                            except Exception as e:
                                logger.error(f"❌ Error processing individual message: {e}", exc_info=True)

                except asyncio.CancelledError:
                    logger.info(f"📊 Kafka consumer cancelled after processing {messages_processed} alerts")
                    raise
                except Exception as e:
                    logger.error(f"❌ Error polling Kafka: {e}", exc_info=True)
                    await asyncio.sleep(1)

        except (KafkaError, ConnectionError) as e:
            retry_count += 1
            logger.error(f"⚠️  Kafka connection failed (attempt {retry_count}/{MAX_RETRIES}): {e}")
            if retry_count < MAX_RETRIES:
                logger.info(f"🔄 Retrying in {KAFKA_RETRY_DELAY_SECONDS} seconds...")
                await asyncio.sleep(KAFKA_RETRY_DELAY_SECONDS)
            else:
                logger.critical(f"🔴 Max Kafka retries ({MAX_RETRIES}) exceeded. Shutting down.")
        finally:
            if kafka_consumer:
                try:
                    kafka_consumer.close()
                    logger.info("🔌 Kafka consumer closed")
                except Exception as e:
                    logger.warning(f"⚠️  Error closing Kafka consumer: {e}")
                kafka_consumer = None


app = FastAPI(
    title="Sentinel Health Agent",
    description="AI-powered real-time clinical alert monitoring with RAG + LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Register routers ──────────────────────────────────────────────────────────
app.include_router(patients_router.router)
app.include_router(chatbot_router.router)


# ── Core endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint."""
    task_running = kafka_task is not None and not kafka_task.done()
    return {
        "status": "healthy",
        "kafka_connected": kafka_consumer is not None,
        "kafka_task_running": task_running,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/health/rag")
async def rag_health_check():
    """Health check specifically for RAG service."""
    if rag_service is None:
        return {"status": "unhealthy", "error": "RAG service not initialized"}
    assert rag_service is not None
    return await rag_service.health_check()


@app.get("/")
async def status():
    return {"status": "Agent Active", "version": "1.0.0"}


@app.get("/history", response_model=List[ClinicalAlertResponse])
async def get_alert_history(limit: int = 10, patient_id: str = "PATIENT_001"):
    history_obj = AlertHistory(AsyncSessionLocal)
    return await history_obj.get_alert_history(limit, patient_id)


@app.post("/upload", response_model=UploadResponse)
async def upload_document(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...)
) -> UploadResponse:
    """Upload a PDF file for medical knowledge indexing."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    temp_id = str(uuid.uuid4())
    temp_path = f"temp_{temp_id}_{file.filename}"

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    async def run_indexing(file_path: str):
        try:
            rag_manager = await PostgresRAGManager.create(engine, VECTOR_TABLE_NAME, OLLAMA_HOST)
            await rag_manager.index_file(file_path)
        except Exception as e:
            logger.error(f"Background indexing failed for {file_path}: {e}", exc_info=True)
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    background_tasks.add_task(run_indexing, temp_path)

    return UploadResponse(
        message=f"File '{file.filename}' uploaded successfully.",
        status="Indexing started in background",
        job_id=temp_id
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.backend.main:app", host="0.0.0.0", port=8000, reload=False)
