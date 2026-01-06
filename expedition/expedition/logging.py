from __future__ import annotations

import logging as std_logging
from pathlib import Path


def configure_logging(log_file: Path, level: int = std_logging.INFO) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = std_logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    file_handler = std_logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = std_logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root_logger = std_logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
