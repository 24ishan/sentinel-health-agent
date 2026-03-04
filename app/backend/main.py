import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI,UploadFile, File, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app import setup_logging
from app.backend.services.history import AlertHistory
from app.backend.schemas import ClinicalAlertResponse
from utils.config import DATABASE_URL, VECTOR_TABLE_NAME, OLLAMA_HOST
from app.backend.services.rag_service import MedicalRAG
import json
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from app.backend.services.process_alerts import ProcessAlerts
from utils.config import KAFKA_CONSUMER_TOPIC, KAFKA_BOOTSTRAP_SERVERS
from typing import List
import os
import uuid
import shutil
from app.vector_db.ingest_pdf import PostgresRAGManager

logger = setup_logging()

# Validate required environment variables
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

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, pool_size=20, max_overflow=0)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Reusable ProcessAlerts instance
process_alerts_instance = None

# RAG service instance
rag_service = None

kafka_consumer = None
kafka_task = None
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

    # Initialize ProcessAlerts once
    process_alerts_instance = ProcessAlerts(AsyncSessionLocal)

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

    # Cleanup RAG service
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
                auto_offset_reset='latest',
                session_timeout_ms=30000,
                request_timeout_ms=40000,
                reconnect_backoff_ms=1000,
                reconnect_backoff_max_ms=10000,
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
                                if data.get("status") == "CRITICAL":
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
                    await asyncio.sleep(1)  # Brief pause before retry

        except (KafkaError, ConnectionError) as e:
            retry_count += 1
            logger.error(f"⚠️  Kafka connection failed (attempt {retry_count}/{MAX_RETRIES}): {e}")
            if retry_count < MAX_RETRIES:
                logger.info(f"🔄 Retrying in {RETRY_DELAY} seconds...")
                await asyncio.sleep(RETRY_DELAY)
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


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint"""
    return {
        "status": "healthy",
        "kafka_connected": kafka_consumer is not None,
        "kafka_task_running": kafka_task is not None and not kafka_task.done(),
        "timestamp": str(__import__('datetime').datetime.now())
    }


@app.get("/health/rag")
async def rag_health_check():
    """Health check specifically for RAG service"""
    if rag_service is None:
        return {"status": "unhealthy", "error": "RAG service not initialized"}
    return await rag_service.health_check()


@app.get("/")
async def status():
    return {"status": "Agent Active"}


@app.get("/history", response_model=List[ClinicalAlertResponse])
async def get_alert_history(limit: int = 10, patient_id: str = "PATIENT_001"):
    history_obj = AlertHistory(AsyncSessionLocal)
    return await history_obj.get_alert_history(limit, patient_id)


@app.post("/upload")
async def upload_document(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...)
):
    """
    Uploads a PDF and triggers background indexing.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # 2. Save file temporarily
    temp_id = str(uuid.uuid4())
    temp_path = f"temp_{temp_id}_{file.filename}"

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 3. Add indexing to Background Tasks
    # This runs AFTER the response is sent to the user
    async def run_indexing(file_path: str):
        """Worker function to process the file and cleanup."""
        try:

            rag_manager = await PostgresRAGManager.create(engine, VECTOR_TABLE_NAME, OLLAMA_HOST)
            await rag_manager.index_file(file_path)
        finally:
            # 4. Always cleanup the temp file
            if os.path.exists(file_path):
                os.remove(file_path)

    background_tasks.add_task(run_indexing, temp_path)

    return {
        "message": f"File '{file.filename}' uploaded successfully.",
        "status": "Indexing started in background",
        "job_id": temp_id
    }

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.backend.main:app", host="0.0.0.0", port=8000, reload=False)
