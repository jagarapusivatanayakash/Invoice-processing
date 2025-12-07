"""Global Logger Module for Invoice Processing."""

import os
import logging
from contextvars import ContextVar
import uuid
import datetime
import coloredlogs
from dotenv import load_dotenv

load_dotenv()

# Context variable to store tracker_id for the current request
tracker_id_context: ContextVar[str] = ContextVar("tracker_id", default="")


class TrackerLogger:
    """Custom logger wrapper that automatically includes tracker_id in messages."""

    def __init__(self, logger_instance):
        self._logger = logger_instance

    def _format_message(self, msg):
        """Format message with tracker_id if available."""
        tracker_id = tracker_id_context.get("")
        if tracker_id:
            return f"[{tracker_id}] {msg}"
        return str(msg)

    def info(self, msg, *args, **kwargs):
        """Log info message with tracker_id prefix."""
        self._logger.info(self._format_message(msg), *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        """Log error message with tracker_id prefix."""
        self._logger.error(self._format_message(msg), *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        """Log warning message with tracker_id prefix."""
        self._logger.warning(self._format_message(msg), *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        """Log debug message with tracker_id prefix."""
        self._logger.debug(self._format_message(msg), *args, **kwargs)


def set_tracker_id(tracker_id: str):
    """Set the tracker_id for the current context."""
    tracker_id_context.set(tracker_id)


def get_tracker_id() -> str:
    """Get the current tracker_id."""
    return tracker_id_context.get("")


def generate_tracker_id():
    """Generate a tracker ID for invoice processing."""
    current_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    uuid_part = str(uuid.uuid4())[8:13]
    return f"INV-{current_time}_{uuid_part}"


def generate_na_tracker():
    """Generate a 'not available' tracker ID."""
    current_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    uuid_part = str(uuid.uuid4())[8:13]
    return f"N/A-{current_time}_{uuid_part}"


# Configure base logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

base_logger = logging.getLogger(__name__)
coloredlogs.install(
    level="INFO",
    logger=base_logger,
    fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Create the tracker-aware logger
logger = TrackerLogger(base_logger)

logger.info("Logger configured successfully")
