"""
Sentinel Health Agent — application package.

Exposes setup_logging() so every sub-module can obtain the same
named logger without duplicating handlers on repeated imports.
"""
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def setup_logging() -> logging.Logger:
    """
    Return the application-wide logger, configuring it only once.

    Uses a named logger ('sentinel_health_agent') so all modules share
    the same instance.  A duplicate-handler guard prevents multiple
    StreamHandlers from being attached when the module is imported more
    than once (e.g. during testing or hot-reloading).
    """
    log_level = os.getenv("LOG_LEVEL", "INFO")
    logger = logging.getLogger("sentinel_health_agent")
    logger.setLevel(log_level)

    # Only add the console handler once — guard against repeated imports
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(handler)

    return logger
