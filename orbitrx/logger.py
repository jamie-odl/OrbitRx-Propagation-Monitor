"""Structured logging: rotating file under logs/ plus stderr."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s"


def setup_logging(log_dir: Path | None = None, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("orbitrx")
    if logger.handlers:
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter(LOG_FORMAT)
    if log_dir is None:
        from orbitrx.paths import project_root
        log_dir = project_root() / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(log_dir / "orbitrx.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        pass  # read-only install dir: fall back to stderr only
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger
