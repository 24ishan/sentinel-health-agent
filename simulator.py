import json
import time
import random
import os
from datetime import datetime, timezone
from kafka import KafkaProducer
from dotenv import load_dotenv

load_dotenv()

# ── Kafka config ──────────────────────────────────────────────────────────────
KAFKA_SERVER = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_NAME = os.getenv("KAFKA_CONSUMER_TOPIC", "vitals_stream")

# ── Patient pool — add / remove patient IDs here freely ──────────────────────
# These must match IDs that exist in your patients table.
# After registering a patient via the dashboard, copy their auto-generated
# ID (e.g. PAT-3F2A1B4C) into this list.
PATIENT_IDS = [
    "PAT-2E20508E"
]

# ── Simulation config ─────────────────────────────────────────────────────────
SEND_INTERVAL_SECONDS = 2     # how often a reading is sent
CRITICAL_CHANCE = 0.10        # 10% chance of CRITICAL alert
WARNING_CHANCE  = 0.15        # 15% chance of WARNING alert
                              # remaining 75% → NORMAL


def json_serializer(data: dict) -> bytes:
    return json.dumps(data).encode("utf-8")


def get_producer() -> KafkaProducer | None:
    try:
        producer = KafkaProducer(
            bootstrap_servers=[KAFKA_SERVER],
            value_serializer=json_serializer,
            acks="all",
        )
        print(f"✅ Connected to Kafka at {KAFKA_SERVER}")
        return producer
    except Exception as e:
        print(f"❌ Could not connect to Kafka: {e}")
        return None


def generate_vitals(patient_id: str) -> dict:
    """
    Generate a single simulated vitals reading for the given patient.

    Probabilities:
      - CRITICAL  (~10%) : HR 121–160 BPM  — tachycardia
      - WARNING   (~15%) : HR 101–120 BPM  — elevated
      - NORMAL    (~75%) : HR  60– 99 BPM  — healthy range
    """
    roll = random.random()

    if roll < CRITICAL_CHANCE:
        heart_rate = random.randint(121, 160)
        status = "CRITICAL"
    elif roll < CRITICAL_CHANCE + WARNING_CHANCE:
        heart_rate = random.randint(101, 120)
        status = "WARNING"
    else:
        heart_rate = random.randint(60, 99)
        status = "NORMAL"

    return {
        "patient_id": patient_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "heart_rate": heart_rate,
        "spo2": random.randint(94, 99),
        "status": status,
    }


def run_simulator():
    if not PATIENT_IDS:
        print("❌ PATIENT_IDS list is empty. Add at least one patient ID and restart.")
        return

    producer = get_producer()
    if not producer:
        return

    print(f"🚀 Simulator started  |  topic: {TOPIC_NAME}  |  patients: {len(PATIENT_IDS)}")
    print(f"   Pool: {PATIENT_IDS}")
    print(f"   Interval: {SEND_INTERVAL_SECONDS}s  |  Ctrl+C to stop\n")

    sent = 0
    try:
        while True:
            # Pick a random patient from the pool on every tick
            patient_id = random.choice(PATIENT_IDS)
            vitals = generate_vitals(patient_id)

            producer.send(TOPIC_NAME, vitals)
            sent += 1

            status_icon = {"CRITICAL": "🔴", "WARNING": "🟡", "NORMAL": "🟢"}.get(vitals["status"], "⚪")
            print(
                f"{status_icon} [{sent:04d}] "
                f"Patient: {patient_id:<14} | "
                f"HR: {vitals['heart_rate']:>3} BPM | "
                f"SpO2: {vitals['spo2']}% | "
                f"{vitals['status']}"
            )

            time.sleep(SEND_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print(f"\n🛑 Simulator stopped. Total readings sent: {sent}")
    finally:
        producer.flush()
        producer.close()


if __name__ == "__main__":
    run_simulator()