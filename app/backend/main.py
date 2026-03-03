import asyncio
import json
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from kafka import KafkaConsumer
from app.backend.services.rag_service import rag_agent
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.backend.models import ClinicalAlert
from app.backend.services.history import AlertHistory
from app.backend.schemas import ClinicalAlertResponse
from app.config import DATABASE_URL,KAFKA_CONSUMER_TOPIC,KAFKA_BOOTSTRAP_SERVERS
from typing import List
import logging

logger = logging.getLogger(__name__)

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

kafka_consumer = None
kafka_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global kafka_task
    loop = asyncio.get_running_loop()
    kafka_task = asyncio.create_task(blocking_kafka_loop())
    logger.info("Kafka consumer started")
    yield
    if kafka_task:
        kafka_task.cancel()
        try:
            await kafka_task
        except asyncio.CancelledError:
            pass
    if kafka_consumer:
        kafka_consumer.close()
    await engine.dispose()
    logger.info("Kafka consumer and engine disposed")


async def blocking_kafka_loop():
    global kafka_consumer
    try:
        kafka_consumer = KafkaConsumer(
            KAFKA_CONSUMER_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            auto_offset_reset='latest',
        )
        print("📡 Monitoring health stream...")

        for message in kafka_consumer:
            try:
                data = message.value
                if data.get("status") == "CRITICAL":
                    hr = data.get("heart_rate")
                    await process_critical_alert(data, hr)
            except Exception as e:
                logger.error(f"Error processing message: {e}")
    except Exception as e:
        logger.error(f"Kafka consumer error: {e}")
    finally:
        if kafka_consumer:
            kafka_consumer.close()


async def process_critical_alert(data, hr):
    try:
        advice = await rag_agent.get_clinical_advice(hr)
        print(f"🚨 CRITICAL ALERT: HR {hr} | {advice}")

        async with AsyncSessionLocal() as session:
            async with session.begin():
                new_alert = ClinicalAlert(
                    patient_id=data.get("patient_id"),
                    heart_rate=hr,
                    status="CRITICAL",
                    ai_advice=advice
                )
                session.add(new_alert)
        print(f"💾 Alert Saved to DB for HR: {hr}")
    except Exception as e:
        logger.error(f"Error processing critical alert: {e}")

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