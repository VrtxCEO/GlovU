from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from .events import DATA_DIR

LOG_FILE = DATA_DIR / "glovu.log"

_configured = False
_original_sys_excepthook = sys.excepthook
_original_threading_excepthook = getattr(threading, "excepthook", None)


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    logger = logging.getLogger("glovu")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=512_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(threadName)s] %(message)s"
        ))
        logger.addHandler(handler)

    sys.excepthook = _sys_excepthook
    if _original_threading_excepthook is not None:
        threading.excepthook = _threading_excepthook

    _configured = True
    logger.info("Logging initialized.")


def get_logger() -> logging.Logger:
    configure_logging()
    return logging.getLogger("glovu")


def log_exception(context: str) -> None:
    get_logger().exception(context)


def _sys_excepthook(exc_type, exc_value, exc_traceback) -> None:
    get_logger().exception(
        "Unhandled exception on main thread.",
        exc_info=(exc_type, exc_value, exc_traceback),
    )
    _original_sys_excepthook(exc_type, exc_value, exc_traceback)


def _threading_excepthook(args: threading.ExceptHookArgs) -> None:
    get_logger().exception(
        "Unhandled exception in thread %s.",
        args.thread.name if args.thread else "unknown",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
    if _original_threading_excepthook is not None:
        _original_threading_excepthook(args)
