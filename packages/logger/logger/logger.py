import logging
from logging.config import dictConfig
from datetime import datetime
from pathlib import Path


def setup_logging(
    service: str | None = None,
    format: str = '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        file_level: str = "DEBUG", stream_level: str = "INFO"):
    log_dir = Path('logs') / service
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(format)

    # file handler (debug)
    file_handler = logging.FileHandler(
        filename=log_dir / f'{datetime.now():%Y-%m-%d_%H-%M-%S}.log' if service else f'{datetime.now():%Y-%m-%d_%H-%M-%S}.log',
        mode='a',
        encoding='utf-8'
    )
    file_handler.setLevel(getattr(logging, file_level.upper()))
    file_handler.setFormatter(formatter)

    # Console handler (info)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, stream_level.upper()))
    console_handler.setFormatter(formatter)

    # logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

if __name__ == '__main__':
    setup_logging()

    logger = logging.getLogger(__name__)

    logger.debug('test debug log')
    logger.info('test info log')
    logger.warning('test warning log')
    logger.critical('test critical log')


def setup_uvicorn_logging(
        service: str | None = None,
    format: str = '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        file_level: str = "DEBUG", stream_level: str = "INFO"):
    log_dir = Path('logs') / service
    log_dir.mkdir(parents=True, exist_ok=True)

    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": format,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": stream_level,
            },
            "file": {
                "class": "logging.FileHandler",
                "formatter": "default",
                "filename": log_dir / f"{datetime.now():%Y-%m-%d_%H-%M-%S}.log" if service else f"{datetime.now():%Y-%m-%d_%H-%M-%S}.log",
                "mode": "a",
                "level": file_level,
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        },
        "root": {
            "level": "DEBUG",
            "handlers": ["console", "file"]
        }
    }

    dictConfig(log_config)