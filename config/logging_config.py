"""
Configuração de logging da aplicação
"""

import logging
import sys
from pathlib import Path
from loguru import logger

from config.settings import get_settings


def setup_logging():
    """Configurar sistema de logging"""
    settings = get_settings()

    logger.remove()

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stdout,
        format=log_format,
        level=settings.log_level,
        colorize=True
    )

    logger.add(
        "logs/finance_bot.log",
        format=log_format,
        level=settings.log_level,
        rotation="1 day",
        retention="30 days",
        compression="zip"
    )

    logger.add(
        "logs/errors.log",
        format=log_format,
        level="ERROR",
        rotation="1 week",
        retention="4 weeks"
    )

    class InterceptHandler(logging.Handler):
        def emit(self, record):
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

            frame, depth = logging.currentframe(), 2
            while frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1

            logger.opt(depth=depth, exception=record.exc_info).log(
                level, record.getMessage()
            )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    for logger_name in ["uvicorn", "uvicorn.access", "fastapi"]:
        logging_logger = logging.getLogger(logger_name)
        logging_logger.handlers = [InterceptHandler()]