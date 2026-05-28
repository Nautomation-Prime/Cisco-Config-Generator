"""Logging bootstrap for Cisco Config Generator."""

from __future__ import annotations

import logging
import logging.config
import os
from pathlib import Path

from rich.logging import RichHandler

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_LOGGING_CONF = _ROOT / "assets" / "config_files" / "logging.conf"

_log: logging.Logger | None = None


def configure_logging(level: str = "INFO") -> None:
    """Configure logging using the INI file if available; otherwise fall back
    to a dual-handler setup (RichHandler console + plain file).

    The LOGGING_CONFIG environment variable can override the default path.
    The logs/ directory is created automatically if it does not yet exist.

    Args:
        level: Console log level when falling back to basic setup.
    """
    global _log

    cfg_env = os.getenv("LOGGING_CONFIG", "").strip()
    cfg_path = Path(cfg_env) if cfg_env else _DEFAULT_LOGGING_CONF

    # Ensure logs/ exists before any FileHandler tries to open the file
    Path("logs").mkdir(exist_ok=True)

    if cfg_path.exists():
        logging.config.fileConfig(str(cfg_path), disable_existing_loggers=False)
        _log = logging.getLogger("cisco_config_generator")
        return

    # Fallback: dual-handler setup (Rich console + plain file)
    root = logging.getLogger()
    if root.handlers:
        _log = logging.getLogger("cisco_config_generator")
        return  # Already configured — don't add duplicate handlers

    root.setLevel(logging.DEBUG)

    console_handler = RichHandler(
        level=getattr(logging, level.upper(), logging.INFO),
        rich_tracebacks=True,
        markup=True,
    )

    file_fmt = logging.Formatter(
        "%(asctime)s - %(levelname)-8s  %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler("logs/debug.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_fmt)

    root.addHandler(console_handler)
    root.addHandler(file_handler)

    _log = logging.getLogger("cisco_config_generator")


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure logging and return the package logger.

    This is a compatibility shim — prefer calling configure_logging() at the
    entry point and then using logging.getLogger(__name__) in each module.
    """
    configure_logging(level)
    return get_logger()


def get_logger() -> logging.Logger:
    """Return the package-level logger, initialising logging if needed."""
    global _log
    if _log is None:
        configure_logging()
    return _log  # type: ignore[return-value]
