import logging
import os
import sys

from dotenv import load_dotenv


load_dotenv()


def setup_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO")
    logger = logging.getLogger("sentinel_health_agent")
    logger.setLevel(log_level)

    # Console handler only
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(console_handler)

    return logger
