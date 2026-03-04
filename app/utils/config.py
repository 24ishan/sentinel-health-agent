"""Application configuration from environment variables."""

import os
from typing import Optional


def _get_env(
        key: str,
        default: Optional[str] = None,
        required: bool = True
) -> str:
    """
    Get environment variable with validation.

    Args:
        key: Environment variable name
        default: Default value if not set
        required: If True, raise error if not set

    Returns:
        Environment variable value

    Raises:
        ValueError: If required variable not set
    """
    value = os.getenv(key, default)
    if required and not value:
        raise ValueError(f"Required environment variable '{key}' not set")
    return value


# Database Configuration
POSTGRES_HOST = _get_env("POSTGRES_HOST", required=True)
POSTGRES_PORT = _get_env("POSTGRES_PORT", "5432", required=False)
POSTGRES_USER_NAME = _get_env("POSTGRES_USER_NAME", required=True)
POSTGRES_PASSWORD = _get_env("POSTGRES_PASSWORD", required=True)
POSTGRES_DB = _get_env("POSTGRES_DB", required=True)
POSTGRES_CLINICAL_ALERTS_TABLE = _get_env(
    "POSTGRES_CLINICAL_ALERTS_TABLE",
    required=True
)
VECTOR_TABLE_NAME = _get_env("VECTOR_TABLE_NAME", required=True)

# Construct DATABASE_URL
DATABASE_URL = (
    f"postgresql+asyncpg://"
    f"{POSTGRES_USER_NAME}:{POSTGRES_PASSWORD}@"
    f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = _get_env("KAFKA_BOOTSTRAP_SERVERS", required=True)
KAFKA_CONSUMER_TOPIC = _get_env("KAFKA_CONSUMER_TOPIC", required=True)

# Ollama Configuration
OLLAMA_HOST = _get_env("OLLAMA_HOST", required=True)
NO_PROXY = _get_env("NO_PROXY", default="localhost,127.0.0.1", required=False)
MEDICAL_EMBEDDING_MODEL = _get_env("MEDICAL_EMBEDDING_MODEL", required=True)
LLM_MODEL = _get_env("LLM_MODEL", required=True)

# Logging Configuration
LOG_LEVEL = _get_env("LOG_LEVEL", default="INFO", required=False)
