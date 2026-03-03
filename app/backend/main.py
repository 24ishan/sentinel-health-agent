import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.backend.services.history import AlertHistory
from app.backend.schemas import ClinicalAlertResponse
from app.config import DATABASE_URL
import json
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from app.backend.services.process_alerts import ProcessAlerts
from config import KAFKA_CONSUMER_TOPIC, KAFKA_BOOTSTRAP_SERVERS
from typing import List
import logging

logger = logging.getLogger(__name__)

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

kafka_consumer = None
kafka_task = None
MAX_RETRIES = 5
RETRY_DELAY = 5


@asynccontextmanager
async def lifespan(app: FastAPI):
    global kafka_task
    kafka_task = asyncio.create_task(blocking_kafka_loop())
    logger.info("Kafka consumer started")
    yield
    if kafka_task:
        kafka_task.cancel()
        try:
            await asyncio.wait_for(kafka_task, timeout=10)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            logger.warning("Kafka consumer shutdown timeout")
    await engine.dispose()
    logger.info("Application shutdown complete")


async def blocking_kafka_loop():
    global kafka_consumer
    retry_count = 0

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
            logger.info("📡 Kafka connected, monitoring health stream...")

            while True:
                try:
                    message = await asyncio.to_thread(
                        kafka_consumer.poll, timeout_ms=1000, max_records=100
                    )
                    if not message:
                        continue

                    for topic_partition, records in message.items():
                        for record in records:
                            data = record.value
                            if data.get("status") == "CRITICAL":
                                process_alerts = ProcessAlerts(AsyncSessionLocal, logger)
                                await process_alerts.process_critical_alert(data, data.get("heart_rate"))
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Error processing message: {e}")

        except (KafkaError, ConnectionError) as e:
            retry_count += 1
            logger.error(f"Kafka connection failed (attempt {retry_count}/{MAX_RETRIES}): {e}")
            if retry_count < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
        finally:
            if kafka_consumer:
                kafka_consumer.close()
                kafka_consumer = None


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def status():
    return {"status": "Agent Active"}


@app.get("/history", response_model=List[ClinicalAlertResponse])
async def get_alert_history(limit: int = 10, patient_id: str = "PATIENT_001"):
    history_obj = AlertHistory(AsyncSessionLocal)
    return await history_obj.get_alert_history(limit, patient_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.backend.main:app", host="0.0.0.0", port=8000, reload=True)
