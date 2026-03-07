"""
Kafka consumer service — polls vitals_stream and processes clinical alerts.
Encapsulates the blocking Kafka poll loop, retry logic, and graceful
shutdown into a single class used by the FastAPI lifespan.
"""
import asyncio
import json
from typing import Optional
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from app import setup_logging
from app.backend.constants import (
    KAFKA_AUTO_OFFSET_RESET,
    KAFKA_MAX_POLL_RECORDS,
    KAFKA_MAX_RETRIES,
    KAFKA_POLL_TIMEOUT_MS,
    KAFKA_RECONNECT_BACKOFF_MAX_MS,
    KAFKA_RECONNECT_BACKOFF_MS,
    KAFKA_REQUEST_TIMEOUT_MS,
    KAFKA_RETRY_DELAY_SECONDS,
    KAFKA_SESSION_TIMEOUT_MS,
)
from app.backend.services.process_alerts import ProcessAlerts
from app.utils.config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_CONSUMER_TOPIC
logger = setup_logging()
class KafkaConsumerService:
    """Manages the Kafka consumer lifecycle and alert-processing loop."""
    def __init__(self, process_alerts: ProcessAlerts) -> None:
        self._process_alerts = process_alerts
        self._consumer: Optional[KafkaConsumer] = None
        self._task: Optional[asyncio.Task] = None
        self._messages_processed: int = 0
    # ── Public API ────────────────────────────────────────────────────────
    async def start(self) -> None:
        """Spawn the background Kafka polling task."""
        self._task = asyncio.create_task(self._consume_loop())
        logger.info("✅ Kafka consumer task created")
    async def stop(self) -> None:
        """Cancel the polling task and close the consumer gracefully."""
        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                logger.warning("⚠️  Kafka consumer shutdown timeout exceeded")
    @property
    def is_connected(self) -> bool:
        return self._consumer is not None
    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()
    # ── Internal loop ─────────────────────────────────────────────────────
    async def _consume_loop(self) -> None:
        """Connect to Kafka with retries and poll for alert messages."""
        retry_count = 0
        while retry_count < KAFKA_MAX_RETRIES:
            try:
                self._consumer = KafkaConsumer(
                    KAFKA_CONSUMER_TOPIC,
                    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                    value_deserializer=lambda x: json.loads(x.decode("utf-8")),
                    auto_offset_reset=KAFKA_AUTO_OFFSET_RESET,
                    session_timeout_ms=KAFKA_SESSION_TIMEOUT_MS,
                    request_timeout_ms=KAFKA_REQUEST_TIMEOUT_MS,
                    reconnect_backoff_ms=KAFKA_RECONNECT_BACKOFF_MS,
                    reconnect_backoff_max_ms=KAFKA_RECONNECT_BACKOFF_MAX_MS,
                )
                retry_count = 0
                logger.info(f"📡 Kafka connected, monitoring topic: {KAFKA_CONSUMER_TOPIC}")
                while True:
                    await self._poll_once()
            except asyncio.CancelledError:
                logger.info(
                    f"📊 Kafka consumer cancelled after processing "
                    f"{self._messages_processed} alerts"
                )
                raise
            except (KafkaError, ConnectionError) as exc:
                retry_count += 1
                logger.error(
                    f"⚠️  Kafka connection failed "
                    f"(attempt {retry_count}/{KAFKA_MAX_RETRIES}): {exc}"
                )
                if retry_count < KAFKA_MAX_RETRIES:
                    logger.info(f"🔄 Retrying in {KAFKA_RETRY_DELAY_SECONDS}s...")
                    await asyncio.sleep(KAFKA_RETRY_DELAY_SECONDS)
                else:
                    logger.critical(
                        f"🔴 Max Kafka retries ({KAFKA_MAX_RETRIES}) exceeded."
                    )
            finally:
                self._close_consumer()
    async def _poll_once(self) -> None:
        """Single poll iteration — process any CRITICAL/WARNING messages."""
        try:
            message = await asyncio.to_thread(
                self._consumer.poll,
                timeout_ms=KAFKA_POLL_TIMEOUT_MS,
                max_records=KAFKA_MAX_POLL_RECORDS,
            )
            if not message:
                return
            for _topic_partition, records in message.items():
                for record in records:
                    await self._handle_record(record.value)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"❌ Error polling Kafka: {exc}", exc_info=True)
            await asyncio.sleep(1)
    async def _handle_record(self, data: dict) -> None:
        """Route a single Kafka record to the alert processor."""
        try:
            if data.get("status") in ("CRITICAL", "WARNING"):
                await self._process_alerts.process_critical_alert(
                    data, data.get("heart_rate")
                )
                self._messages_processed += 1
                logger.debug(
                    f"✅ Processed {self._messages_processed} critical alerts"
                )
        except Exception as exc:
            logger.error(f"❌ Error processing message: {exc}", exc_info=True)
    def _close_consumer(self) -> None:
        """Safely close the underlying KafkaConsumer."""
        if self._consumer:
            try:
                self._consumer.close()
                logger.info("🔌 Kafka consumer closed")
            except Exception as exc:
                logger.warning(f"⚠️  Error closing Kafka consumer: {exc}")
            self._consumer = None
