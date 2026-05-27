from __future__ import annotations
import sys
import logging


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("gossip_engine")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-5s | %(message)s",
            datefmt="%H:%M:%S",
        ))
        logger.addHandler(handler)
    return logger
