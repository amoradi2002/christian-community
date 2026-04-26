import logging
import logging.handlers
import os
from pathlib import Path


def setup_logging(log_level="INFO", log_dir=None):
    """Configure logging for the entire bot."""
    if log_dir is None:
        log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    # Root logger
    root = logging.getLogger("bot")
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Console handler - concise format
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    ))
    root.addHandler(console)

    # File handler - detailed format, rotating 5MB files, keep 5
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "trading_bot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s"
    ))
    root.addHandler(file_handler)

    # Error-only file handler
    error_handler = logging.handlers.RotatingFileHandler(
        log_dir / "errors.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d: %(message)s\n%(exc_info)s"
    ))
    root.addHandler(error_handler)

    # Trade-specific logger
    trade_logger = logging.getLogger("bot.trades")
    trade_handler = logging.handlers.RotatingFileHandler(
        log_dir / "trades.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=10,
    )
    trade_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(message)s"
    ))
    trade_logger.addHandler(trade_handler)

    return root
