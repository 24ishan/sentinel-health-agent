"""
Retry utilities for async operations.

Provides decorators and configuration for retrying operations with exponential
backoff. Especially useful for flaky connections (e.g., WiFi-based Ollama).
"""

import asyncio
import random
from functools import wraps
from typing import Callable, Any, Type, Tuple

from app import setup_logging

logger = setup_logging()


class RetryConfig:
    """
    Configuration for retry behavior.

    Attributes:
        max_attempts: Maximum number of retry attempts
        base_delay: Initial delay in seconds before first retry
        exponential_base: Multiplier for exponential backoff
        max_delay: Maximum delay between retries
        jitter: Whether to add random jitter to delay
        retriable_exceptions: Tuple of exception types to retry on
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        exponential_base: float = 2.0,
        max_delay: float = 60.0,
        jitter: bool = True,
        retriable_exceptions: Tuple[Type[Exception], ...] = (
            ConnectionError,
            TimeoutError,
            OSError,
        ),
    ):
        """
        Initialize retry configuration.

        Args:
            max_attempts: How many times to retry (default 3)
            base_delay: Initial delay between retries in seconds (default 1.0)
            exponential_base: Exponential backoff multiplier (default 2.0)
            max_delay: Maximum delay cap in seconds (default 60.0)
            jitter: Add randomness to prevent thundering herd (default True)
            retriable_exceptions: Which exceptions trigger retry
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.exponential_base = exponential_base
        self.max_delay = max_delay
        self.jitter = jitter
        self.retriable_exceptions = retriable_exceptions


def async_retry(retry_config: RetryConfig):
    """
    Decorator for retrying async functions with exponential backoff.

    Automatically retries on specified exceptions with exponential backoff
    and optional jitter. Perfect for unstable connections like WiFi.

    Args:
        retry_config: RetryConfig instance with retry settings

    Returns:
        Decorator function

    Example:
        # >>> config = RetryConfig(max_attempts=3, base_delay=1.0)
        # >>> @async_retry(config)
        # ... async def call_ollama(llm, prompt):
        # ...     return await llm.ainvoke(prompt)
        # >>> result = await call_ollama(llm_instance, "test")

    Behavior:
        - Attempt 1: Fails, waits 1.0s + jitter, retries
        - Attempt 2: Fails, waits 2.0s + jitter, retries
        - Attempt 3: Fails, raises exception
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(1, retry_config.max_attempts + 1):
                try:
                    logger.debug(
                        f"Attempt {attempt}/{retry_config.max_attempts} "
                        f"for {func.__name__}"
                    )
                    return await func(*args, **kwargs)

                except retry_config.retriable_exceptions as e:
                    last_exception = e

                    # If this was the last attempt, raise
                    if attempt == retry_config.max_attempts:
                        logger.error(
                            f"❌ All {retry_config.max_attempts} attempts failed "
                            f"for {func.__name__}: {e}",
                            exc_info=True,
                        )
                        raise

                    # Calculate exponential backoff with optional jitter
                    delay = min(
                        retry_config.base_delay
                        * (retry_config.exponential_base ** (attempt - 1)),
                        retry_config.max_delay,
                    )

                    if retry_config.jitter:
                        delay += random.uniform(0, 0.1 * delay)

                    logger.warning(
                        f"⚠️  Attempt {attempt} failed for {func.__name__}: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)

                except Exception as e:
                    # Don't retry on non-retriable exceptions
                    logger.error(
                        f"Non-retriable error in {func.__name__}: {e}", exc_info=True
                    )
                    raise

            # Should not reach here, but defensive coding
            raise last_exception or RuntimeError(f"Failed to execute {func.__name__}")

        return wrapper

    return decorator


