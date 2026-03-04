"""Application constants and configuration values."""

# Kafka Configuration
KAFKA_MAX_RETRIES = 5
KAFKA_RETRY_DELAY_SECONDS = 5
KAFKA_POLL_TIMEOUT_MS = 1000
KAFKA_MAX_POLL_RECORDS = 10

# Kafka Session/Request Timeouts (milliseconds)
KAFKA_SESSION_TIMEOUT_MS = 30000
KAFKA_REQUEST_TIMEOUT_MS = 40000
KAFKA_RECONNECT_BACKOFF_MS = 1000
KAFKA_RECONNECT_BACKOFF_MAX_MS = 10000

# Database Configuration
DB_POOL_SIZE = 20
DB_MAX_OVERFLOW = 0

# RAG Service Configuration
RAG_QUERY_TIMEOUT_SECONDS = 10

# API Configuration
UPLOAD_TEMP_FILE_PREFIX = "temp"

# Kafka Settings
KAFKA_AUTO_OFFSET_RESET = "latest"