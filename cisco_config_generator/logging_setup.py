from __future__ import annotations

import logging
from rich.logging import RichHandler

_log: logging.Logger | None = None


def setup_logging(level: str = "INFO") -> logging.Logger:
    global _log
    if _log is not None:
        _log.setLevel(getattr(logging, level.upper(), logging.INFO))
        return _log

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)],
    )
    _log = logging.getLogger("cisco_config_generator")
    return _log


def get_logger() -> logging.Logger:
    global _log
    if _log is None:
        return setup_logging()
    return _log
