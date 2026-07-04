"""
utils/logger.py
----------------
Centralized logger factory. Every module calls `get_logger(__name__)`
instead of configuring logging ad-hoc, so log formatting and log level
stay consistent across the whole application.
"""

from __future__ import annotations
import logging
import sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    """
    Return a configured logger instance.

    Args:
        name: Usually `__name__` of the calling module.

    Returns:
        A logging.Logger writing to both stdout and a rotating app.log file.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        # Logger already configured (avoids duplicate handlers on Streamlit reruns)
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # File system might be read-only in some deployment environments;
        # fall back silently to stdout-only logging.
        pass

    logger.propagate = False
    return logger
