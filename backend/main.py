import asyncio
import json
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from kafka import KafkaConsumer
from dotenv import load_dotenv

load_dotenv()

# Config
KAFKA_SERVER = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_NAME = "vitals_stream"


async def consume_vitals():
    """Background task to consume Kafka messages."""
    consumer = KafkaConsumer(
        TOPIC_NAME,
        bootstrap_servers=[KAFKA_SERVER],
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        auto_offset_reset='latest'
    )

    print(f"📡 Consumer listening on {TOPIC_NAME}...")
    try:
        for message in consumer:
            data = message.value
            patient_id = data.get("patient_id")
            hr = data.get("heart_rate")
            status = data.get("status")

            if status == "CRITICAL":
                print(f"🚨 ALERT! Patient {patient_id} has HR: {hr}. Triggering RAG...")
                # This is where we will call our RAG function later!
            else:
                print(f"✅ Normal vitals received for {patient_id}")

            # Small sleep to yield control back to the event loop
            await asyncio.sleep(0.01)
    except Exception as e:
        print(f"❌ Consumer Error: {e}")
    finally:
        consumer.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start the Kafka consumer in the background
    task = asyncio.create_task(consume_vitals())
    yield
    # Shutdown: Clean up if needed
    task.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "Health Agent API is running."}