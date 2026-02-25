import asyncio
import json
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from kafka import KafkaConsumer
from dotenv import load_dotenv
from app.backend.services.rag_service import rag_agent
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.backend.models import ClinicalAlert
from app.backend.services.history import AlertHistory
from app.backend.schemas import ClinicalAlertResponse
from typing import List

load_dotenv()

engine = create_async_engine(os.getenv("DATABASE_URL"))
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    # Start Kafka Consumer as a background task
    task = asyncio.create_task(asyncio.to_thread(blocking_kafka_loop, loop))
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)


async def consume_vitals():
    await asyncio.to_thread(blocking_kafka_loop)


def blocking_kafka_loop(loop):
    consumer = KafkaConsumer(
        "vitals_stream",
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
    )

    print("📡 Monitoring health stream...")
    for message in consumer:
        data = message.value
        if data.get("status") == "CRITICAL":
            hr = data.get("heart_rate")

            future = asyncio.run_coroutine_threadsafe(
                process_critical_alert(data, hr),
                loop
            )
            # This blocks the background thread until the result is ready
            future.result()

async def process_critical_alert(data, hr):
    # This function is ASYNC and runs on the MAIN event loop
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
@app.get("/")
async def status():
    return {"status": "Agent Active"}

@app.get("/history", response_model=List[ClinicalAlertResponse])
async def get_alert_history(limit: int = 10, patient_id: str = "PATIENT_001"):
    history_obj = AlertHistory(AsyncSessionLocal)
    return await history_obj.get_alert_history(limit, patient_id)

if __name__ == "__main__":
    import uvicorn
    # Use the import string "app.main:app" so that reload works with your new structure
    uvicorn.run("app.backend.main:app", host="0.0.0.0", port=8000, reload=True)