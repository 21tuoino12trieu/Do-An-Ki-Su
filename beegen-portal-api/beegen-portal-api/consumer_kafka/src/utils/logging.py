"""
Logging Setup – CUA Consumer Service

Hỗ trợ 2 chế độ output:
  - development: console đẹp, màu sắc, dễ đọc
  - production:  JSON mỗi dòng, dễ ingest vào ELK / Datadog

Cấu hình qua env vars:
  LOG_LEVEL      = DEBUG | INFO | WARNING | ERROR   (default: INFO)
  LOG_FORMAT     = json | console                   (default: json)
  SERVICE_NAME   = tên service                      (default: cua-consumer)
  SERVICE_ENV    = dev | staging | production        (default: development)
"""

import logging
import logging.config
import sys

import structlog
from src.config.settings import settings

def _shared_processors() -> list:
    """
    Các processor dùng chung cho cả structlog và logging stdlib.
    Chạy theo thứ tự: merge context → thêm level → timestamp → caller info.
    """
    return [
        # Merge context vars từ asyncio context (request_id, channel, ...)
        structlog.contextvars.merge_contextvars,
        # Thêm log level vào record
        structlog.processors.add_log_level,
        # Timestamp ISO 8601 UTC
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        # Render stack trace nếu có
        structlog.processors.StackInfoRenderer(),
    ]

def _get_renderer(log_format: str):
    """
    Trả về renderer phù hợp theo LOG_FORMAT.
      - json:    JSONRenderer   → dùng cho production / ELK
      - console: ConsoleRenderer → dùng cho development (có màu)
    """
    if log_format == "console":
        return structlog.dev.ConsoleRenderer(colors=True)
    return structlog.processors.JSONRenderer()

def setup_logging() -> None:
    """
    Khởi tạo logging cho toàn bộ service.
    Gọi một lần duy nhất ở main.py trước khi chạy consumer.
    """
    log_level_str = settings.log_level.upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    log_format = getattr(settings, "log_format", "json").lower()

    renderer = _get_renderer(log_format)

    # ── Cấu hình structlog ───────────────────────────────────────────────────
    structlog.configure(
        processors=_shared_processors() + [
            # Format exception thành string trước khi render
            structlog.processors.format_exc_info,
            # Renderer cuối cùng
            renderer,
        ],
        # Dùng BoundLogger chuẩn của structlog
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # ── Cấu hình stdlib logging (để bắt log từ kafka, pymongo, httpx, ...) ──
    logging.config.dictConfig(
        _stdlib_logging_config(log_level_str, log_format)
    )

    # Log thông báo khởi động
    logger = structlog.get_logger("cua.logging")
    logger.info(
        "logging_initialized",
        log_level=log_level_str,
        log_format=log_format,
        service=getattr(settings, "service_name", "cua-consumer"),
        env=getattr(settings, "service_env", "development"),
    )


def _stdlib_logging_config(log_level: str, log_format: str) -> dict:
    """
    Cấu hình logging stdlib dạng dictConfig.
    Dùng ProcessorFormatter của structlog để stdlib log cũng ra cùng format.
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structured": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    # Trích xuất thông tin từ stdlib record
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.format_exc_info,
                    _get_renderer(log_format),
                ],
                "foreign_pre_chain": _shared_processors(),
            },
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "structured",
            },
        },
        "loggers": {
            # Root logger
            "": {
                "handlers": ["stdout"],
                "level": log_level,
                "propagate": True,
            },
            # Giảm noise từ thư viện bên thứ 3
            "aiokafka":  {"level": "WARNING", "propagate": True},
            "kafka":     {"level": "WARNING", "propagate": True},
            "pymongo":   {"level": "WARNING", "propagate": True},
            "httpx":     {"level": "WARNING", "propagate": True},
            "httpcore":  {"level": "WARNING", "propagate": True},
        },
    }