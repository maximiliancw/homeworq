import logging
import sys
from copy import copy
from typing import Optional


class CustomFormatter(logging.Formatter):
    """
    Custom formatter that provides consistent colored output.
    """

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[41m",  # Red background
    }
    RESET = "\033[0m"

    def __init__(self, *args, use_colors=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_colors = use_colors

    def format(self, record):
        record_copy = copy(record)
        levelname = record_copy.levelname

        # Convert uvicorn's levelprefix to our standard levelname if present
        if hasattr(record_copy, "levelprefix"):
            levelname = record_copy.levelprefix.strip()

        # Standardize the length of the level name
        levelname = f"{levelname:<8}"

        if self.use_colors and levelname.strip() in self.COLORS:
            levelname = f"{self.COLORS[levelname.strip()]}{levelname}{self.RESET}"

        record_copy.levelname = levelname

        # Handle uvicorn access logs specially
        if hasattr(record_copy, "client_addr"):
            message = f"{record_copy.request_line} | {record_copy.status_code}"
            record_copy.message = message

        return super().format(record_copy)


class CustomAccessFormatter(CustomFormatter):
    """Custom formatter for Uvicorn access logs."""

    def formatMessage(self, record):
        return self._fmt % record.__dict__


class CustomDefaultFormatter(CustomFormatter):
    """Custom formatter for Uvicorn default logs."""

    def formatMessage(self, record):
        return self._fmt % record.__dict__


def setup_logging(log_path: Optional[str] = None, debug: bool = False) -> None:
    """
    Configure logging for the application.

    Args:
        log_path: Optional path to log file
        debug: Whether to enable debug logging
    """
    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Create formatters
    console_formatter = CustomFormatter(
        fmt="%(levelname)s%(asctime)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        use_colors=True,
    )

    file_formatter = CustomFormatter(
        fmt="%(levelname)s%(asctime)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        use_colors=False,
    )

    # Configure handlers
    if log_path:
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Always add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Set specific log levels for different components
    logging.getLogger("homeworq").setLevel(logging.DEBUG if debug else logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("tortoise").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)


def get_uvicorn_log_config() -> dict:
    """
    Get Uvicorn logging config that matches our standard format.

    Args:
        debug: Whether to enable debug logging

    Returns:
        dict: Uvicorn logging configuration
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": CustomDefaultFormatter,
                "fmt": "%(levelname)s%(asctime)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
                "use_colors": True,
            },
            "access": {
                "()": CustomAccessFormatter,
                "fmt": "%(levelname)s%(asctime)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
                "use_colors": True,
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": logging.StreamHandler,
                "stream": "ext://sys.stdout",
            },
            "access": {
                "formatter": "access",
                "class": logging.StreamHandler,
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"level": "WARNING", "propagate": True},
            "uvicorn.access": {
                "handlers": ["access"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }
