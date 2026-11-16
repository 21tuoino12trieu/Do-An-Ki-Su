"""Fully asynchronous Kafka logging handler."""

import os
import sys
import time
import socket
import atexit
import codecs
import json
import logging
import threading
import queue
from typing import Dict, List, Any, Optional, Callable
from kafka import KafkaProducer
from beegen_v1.configs import LogConfig


def _setup_console_handler(log_level: str, log_format: str) -> logging.Handler:
    """
    Setup and configure console handler with UTF-8 encoding
    """
    formatter = logging.Formatter(log_format)
    console_handler = logging.StreamHandler(
        stream=codecs.getwriter('utf-8')(sys.stdout.buffer)
    )
    console_handler.setLevel(getattr(logging, log_level))
    console_handler.setFormatter(formatter)
    return console_handler


class AsyncKafkaHandler(logging.Handler):
    """Asynchronous Kafka logging handler that never blocks the main thread."""
    
    # Class variable to store the singleton instance
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        # This is called before __init__
        if cls._instance is None:
            cls._instance = super(AsyncKafkaHandler, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(
        self,
        bootstrap_servers: List[str],
        topic: str,
        security_protocol: str = "PLAINTEXT",
        ssl_cafile: Optional[str] = None,
        extra_fields: Optional[Dict[str, Any]] = None,
        batch_size: int = 100,
        flush_interval: float = 2.0,
        producer_config: Optional[Dict[str, Any]] = None,
        log_preprocessor: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
    ):
        """
        Initialize the asynchronous Kafka logging handler.
        """
        # Only initialize once
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        super().__init__()
        
        # Initialize all attributes first to ensure they exist even if initialization fails
        self.topic = topic
        self.extra_fields = extra_fields or {}
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.log_preprocessor = log_preprocessor
        self.closed = False
        self.producer = None
        self.queue = None
        self.shutdown_event = None
        self.worker = None
        
        try:
            # Suppress Kafka connection logs
            logging.getLogger('kafka.conn').setLevel(logging.ERROR)
            
            # Add default extra fields
            hostname = socket.gethostname()
            self.extra_fields.update({
                "host": hostname,
                "host_ip": socket.gethostbyname(hostname)
            })
            
            # Configure Kafka producer
            producer_config = producer_config or {}
            producer_config.setdefault('max_block_ms', 2000)
            producer_config.update({
                'bootstrap_servers': bootstrap_servers,
                'security_protocol': security_protocol,
                'value_serializer': lambda m: json.dumps(m).encode('utf-8'),
            })
            
            if security_protocol == "SSL" and ssl_cafile:
                producer_config['ssl_cafile'] = ssl_cafile
            
            # Initialize producer - this might fail
            self.producer = KafkaProducer(**producer_config)
            
            # Setup message queue and worker thread
            self.queue = queue.Queue()
            self.shutdown_event = threading.Event()
            self.worker = threading.Thread(target=self._worker_thread, daemon=True)
            self.worker.start()
            
            # Register exit handler
            atexit.register(self._at_exit)
            
            # Only set initialized to True if everything succeeded
            self._initialized = True
            
        except Exception as e:
            # If initialization fails, log the error and set up as a no-op handler
            sys.stderr.write(f"Failed to initialize Kafka handler: {e}\n")
            sys.stderr.write("Kafka logging will be disabled, only console logging will work.\n")
            
            # Clean up any partially initialized resources
            if self.producer:
                try:
                    self.producer.close()
                except:
                    pass
                self.producer = None
            
            # Mark as initialized but disabled
            self._initialized = True
            self.closed = True  # Mark as closed so emit() becomes a no-op
    
    def emit(self, record):
        """Add log record to the queue for asynchronous processing."""
        if record.name == "kafka.client" or self.closed or not self.queue:
            return
            
        try:
            # Format and enhance record
            log_dict = self._format_record(record)
            
            # Apply preprocessor if available
            if self.log_preprocessor:
                log_dict = self.log_preprocessor(log_dict)
                
            # Add to queue without blocking
            self.queue.put_nowait(log_dict)
        except Exception:
            self.handleError(record)
    
    def _format_record(self, record):
        """Format log record as dictionary with additional fields."""
        # Format the record
        self.format(record)
        
        # Create base record dict
        log_dict = {
            'timestamp': self._get_timestamp(record),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'process_id': record.process,
            'thread_id': record.thread,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_dict['exception'] = self._format_exception(record)
            
        # Add all extra context from record
        for key, value in record.__dict__.items():
            if key not in ('args', 'asctime', 'created', 'exc_info', 'exc_text', 
                          'filename', 'funcName', 'id', 'levelname', 'levelno',
                          'lineno', 'module', 'msecs', 'message', 'msg', 
                          'name', 'pathname', 'process', 'processName', 
                          'relativeCreated', 'stack_info', 'thread', 'threadName'):
                log_dict[key] = value
                
        # Add extra fields
        log_dict.update(self.extra_fields)
        
        return log_dict
    
    def _get_timestamp(self, record):
        """Convert record creation time to ISO format."""
        from datetime import datetime
        dt = datetime.fromtimestamp(record.created)
        return dt.isoformat() + 'Z'
    
    def _format_exception(self, record):
        """Format exception information as a string."""
        if record.exc_info:
            import traceback
            return '\n'.join(traceback.format_exception(*record.exc_info))
        return None
    
    def _worker_thread(self):
        """Background thread that processes the queue and sends logs to Kafka."""
        batch = []
        last_flush_time = time.time()
                
        while not self.shutdown_event.is_set() or not self.queue.empty():
            try:
                # Get message with timeout to allow checking shutdown event
                try:
                    log_dict = self.queue.get(timeout=0.1)
                    batch.append(log_dict)
                    self.queue.task_done()
                except queue.Empty:
                    pass
                
                current_time = time.time()
                time_since_flush = current_time - last_flush_time
                
                # Send batch if it's full or it's time to flush
                if (len(batch) >= self.batch_size or 
                    (batch and time_since_flush >= self.flush_interval)):
                    self._send_batch(batch)
                    batch = []
                    last_flush_time = current_time
                
                # Final flush before shutdown
                if self.shutdown_event.is_set() and batch:
                    self._send_batch(batch)
                    batch = []
                    
            except Exception:
                # Log the exception but keep the worker thread running
                import traceback
                sys.stderr.write(f"Error in Kafka logging worker: {traceback.format_exc()}\n")
                # Clear the batch to avoid repeated errors
                batch = []
    
    def _send_batch(self, batch):
        """Send a batch of log records to Kafka."""
        if not batch or self.closed or not self.producer:
            return
            
        try:
            for log_dict in batch:
                # Send but don't wait for response
                self.producer.send(self.topic, log_dict)
                
            self._consecutive_errors = 0
            # Optional: producer.flush() is intentionally omitted to avoid blocking
            # The producer will flush in the background
        except Exception as e:
            # If sending fails, track consecutive errors and avoid infinite spam
            self._consecutive_errors = getattr(self, '_consecutive_errors', 0) + 1
            if self._consecutive_errors == 1:
                sys.stderr.write(f"Failed to send logs to Kafka: {e}. Circuit breaking Kafka logger after consecutive failures.\n")
            if self._consecutive_errors >= 3:
                self.closed = True
                sys.stderr.write("Kafka logging disabled due to unreachable broker.\n")
    
    def _at_exit(self):
        """Handle cleanup at exit - called by atexit."""
        try:
            self.close()
        except Exception:
            # If there's an error during close, log it but don't crash
            import traceback
            sys.stderr.write(f"Error during Kafka handler shutdown: {traceback.format_exc()}\n")
    
    def close(self):
        """Clean shutdown of the handler."""
        if self.closed:
            return
            
        self.closed = True  # Mark as closed to prevent further emissions
        
        try:
            # Signal shutdown to worker thread
            if self.shutdown_event:
                self.shutdown_event.set()
            
            # Wait briefly for worker to process remaining items
            if self.worker and self.worker.is_alive():
                self.worker.join(timeout=1.0)
                
            # Process remaining queue items directly if the worker is still running
            if self.queue and not self.queue.empty():
                # Get all remaining items before closing producer
                remaining_logs = []
                try:
                    while True:
                        remaining_logs.append(self.queue.get_nowait())
                        self.queue.task_done()
                except queue.Empty:
                    pass
                    
                # Send the remaining logs only if we have a producer
                if remaining_logs and self.producer and hasattr(self.producer, '_closed') and not self.producer._closed:
                    for log in remaining_logs:
                        try:
                            self.producer.send(self.topic, log)
                        except Exception:
                            pass  # Ignore errors during shutdown
                    try:
                        self.producer.flush(timeout=1)
                    except Exception:
                        pass  # Ignore errors during shutdown
        finally:
            # Always close the producer
            if self.producer:
                try:
                    if hasattr(self.producer, '_closed') and not self.producer._closed:
                        self.producer.close(timeout=1)
                except Exception:
                    pass  # Ignore errors during producer close
            
        super().close()


# Update the setup_logger function to use the new handler
def setup_logger(config: LogConfig, name: str = "beegen-core"):
    """
    Setup logger with console and async Kafka handlers
    """
    # Get configurations
    std = config.std
    kafka = config.kafka
    
    # Create logger
    logger = logging.getLogger(name)
    
    # Check if handlers already exist
    has_console_handler = any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
    has_kafka_handler = any(isinstance(h, AsyncKafkaHandler) for h in logger.handlers)
    
    # Set level
    logger.setLevel(getattr(logging, std.log_level))
    
    # Add console handler if needed
    if not has_console_handler:
        logger.addHandler(_setup_console_handler(
            log_level=std.log_level,
            log_format=std.log_format
        ))
    
    # Add async Kafka handler if needed
    if not has_kafka_handler:
        extra_fields = {
            'app_name': config.app_name,
            'environment': config.environment,
            'host_name': std.log_host_name
        }
        
        # Add additional fields
        if hasattr(config, 'extra_fields') and config.extra_fields:
            extra_fields.update(config.extra_fields)
        if hasattr(kafka, 'extra_fields') and kafka.extra_fields:
            extra_fields.update(kafka.extra_fields)
        
        # Configure producer
        producer_config = {}
        if kafka.kafka_compression_type or kafka.kafka_retries:
            producer_config.update({
                'compression_type': kafka.kafka_compression_type,
                'retries': kafka.kafka_retries
            })
        
        if kafka.kafka_security_protocol not in ['PLAINTEXT', 'SSL']:
            producer_config.update({
                'sasl_mechanism': kafka.kafka_sasl_mechanism,
                'sasl_plain_username': kafka.kafka_sasl_username,
                'sasl_plain_password': kafka.kafka_sasl_password
            })
        
        # Create and add handler
        kafka_handler = AsyncKafkaHandler(
            bootstrap_servers=kafka.kafka_boostrap_servers,
            topic=kafka.kafka_topic_log,
            security_protocol=kafka.kafka_security_protocol,
            ssl_cafile=kafka.kafka_ssl_ca_file,
            extra_fields=extra_fields,
            producer_config=producer_config,
            batch_size=100,  # Adjust based on your needs
            flush_interval=1.0  # Adjust based on your needs
        )
        
        kafka_handler.setLevel(logging.INFO)
        logger.addHandler(kafka_handler)
    
    return logger


LOGGER = setup_logger(config=LogConfig.default(), name="beegen")