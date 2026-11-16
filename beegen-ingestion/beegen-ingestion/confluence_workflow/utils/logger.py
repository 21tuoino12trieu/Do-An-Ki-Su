"""
Logging utilities for Confluence workflow.

This module provides centralized logging configuration.
"""

import os
import logging
import sys
import io
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Global logger instance
_logger = None


def setup_logging(
    log_level: str = 'INFO',
    log_dir: str = 'logs',
    enable_kafka: bool = True,
    kafka_flush_timeout: float = 30.0,
):
    """
    Setup logging configuration.
    
    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for log files
        enable_kafka: Enable Kafka log forwarding
        kafka_flush_timeout: Kafka flush timeout in seconds
        
    Returns:
        Configured logger instance
    """
    global _logger
    
    # Create log directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)
    
    # Create logger
    logger = logging.getLogger('confluence_workflow')
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_stream = sys.stdout
    if hasattr(sys.stdout, "buffer"):
        console_stream = io.TextIOWrapper(
            sys.stdout.buffer,
            encoding="utf-8",
            errors="backslashreplace",
            line_buffering=True,
        )
    console_handler = logging.StreamHandler(console_stream)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler with rotation
    log_file = os.path.join(log_dir, 'confluence_sync.log')
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Error log file
    error_log_file = os.path.join(log_dir, 'confluence_sync_error.log')
    error_handler = RotatingFileHandler(
        error_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    logger.addHandler(error_handler)
    _logger = logger
    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    Get a named logger instance.
    
    Args:
        name: Logger name (defaults to 'confluence_workflow')
        
    Returns:
        Logger instance
    """
    if name is None:
        return _logger
    return logging.getLogger(f'confluence_workflow.{name}')
