"""Debug logging helpers based on stdlib logging."""

from __future__ import annotations

import logging
import os
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from . import constants as C
from .config import config_path

_LOGGER_NAME = "chroma_monitor.window_layout_debug"
_LOGGER_CONFIG_LOCK = threading.Lock()
_LOGGER_ANNOUNCED_PATHS: set[str] = set()


def _parse_env_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def is_window_layout_debug_enabled() -> bool:
    """Return whether window_layout debug logging is enabled."""
    env_value = _parse_env_bool(os.environ.get(C.DEBUG_WINDOW_LAYOUT_LOG_ENV))
    if env_value is not None:
        return bool(env_value)
    return bool(C.DEBUG_WINDOW_LAYOUT_LOG_ENABLED)


def window_layout_debug_log_path() -> Path:
    """Resolve the output path for window_layout debug logs."""
    override = os.environ.get(C.DEBUG_WINDOW_LAYOUT_LOG_PATH_ENV)
    if override:
        return Path(override).expanduser()
    return config_path().parent / C.DEBUG_WINDOW_LAYOUT_LOG_FILE


def _format_field(value: Any) -> str:
    text = repr(value)
    return text.replace("\n", "\\n")


def _configured_window_layout_logger() -> logging.Logger:
    """Return a configured rotating logger for window layout debug events."""
    path = window_layout_debug_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    abs_path = str(path.resolve())

    logger = logging.getLogger(_LOGGER_NAME)
    with _LOGGER_CONFIG_LOCK:
        configured_path = getattr(logger, "_cm_debug_log_path", None)
        if configured_path != abs_path or not logger.handlers:
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
                try:
                    handler.close()
                except Exception:
                    pass

            handler = RotatingFileHandler(
                abs_path,
                mode="a",
                maxBytes=int(C.DEBUG_WINDOW_LAYOUT_LOG_MAX_BYTES),
                backupCount=int(C.DEBUG_WINDOW_LAYOUT_LOG_BACKUP_COUNT),
                encoding="utf-8",
            )
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s.%(msecs)03d [%(name)s] %(message)s",
                    datefmt="%Y-%m-%dT%H:%M:%S",
                )
            )
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
            logger.propagate = False
            logger._cm_debug_log_path = abs_path
            if abs_path not in _LOGGER_ANNOUNCED_PATHS:
                logger.debug("[debug_logger_ready] path=%r", abs_path)
                _LOGGER_ANNOUNCED_PATHS.add(abs_path)
    return logger


def write_window_layout_debug_log(event: str, **fields: Any) -> None:
    """Append one debug log line when debug mode is enabled."""
    if not is_window_layout_debug_enabled():
        return
    try:
        logger = _configured_window_layout_logger()
        parts = [f"{key}={_format_field(value)}" for key, value in fields.items()]
        tail = " ".join(parts)
        if tail:
            logger.debug("[%s] %s", str(event), tail)
        else:
            logger.debug("[%s]", str(event))
    except Exception:
        # Debug logging must never affect app behavior.
        return
