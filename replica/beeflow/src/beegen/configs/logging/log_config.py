from pathlib import Path
from beegen.configs.yaml_model import YamlModel
from beegen.const import BEEGEN_ROOT
from typing import List, Optional, Dict, Union


class KafkaLogConfig(YamlModel):
    """Configuration settings for Kafka logging.
    
    This class defines the configuration parameters needed to set up Kafka logging,
    including connection details, security settings, and producer configurations.
    
    Attributes:
        kafka_boostrap_servers (List): List of Kafka broker addresses.
        kafka_topic_log (str): The Kafka topic to which logs will be sent.
        kafka_security_protocol (Optional[str]): Security protocol for Kafka connection.
            Defaults to "PLAINTEXT".
        kafka_ssl_ca_file (Optional[str]): Path to SSL CA certificate file.
        kafka_sasl_mechanism (Optional[str]): SASL mechanism for authentication.
        kafka_sasl_username (Optional[str]): SASL username for authentication.
        kafka_sasl_password (Optional[str]): SASL password for authentication.
        kafka_compression_type (Optional[str]): Compression type for messages.
            Options: none, gzip, snappy, lz4. Defaults to 'gzip'.
        kafka_retries (Optional[int]): Number of retry attempts. Defaults to 3.
    """
    
    # Required fields
    kafka_boostrap_servers: List = ["10.1.16.247:9092", "10.1.16.248:9092", "10.1.16.249:9092"]
    kafka_topic_log: str = "LOG_EDP_BIGDATA"
    
    # Security settings
    kafka_security_protocol: Optional[str] = "PLAINTEXT"
    kafka_ssl_ca_file: Optional[str] = None
    kafka_sasl_mechanism: Optional[str] = None
    kafka_sasl_username: Optional[str] = None
    kafka_sasl_password: Optional[str] = None
    
    # Producer configurations
    kafka_compression_type: Optional[str] = 'gzip'
    kafka_retries: Optional[int] = 3


class StdLogConfig(YamlModel):
    """Configuration settings for standard logging.
    
    This class defines the configuration parameters for standard Python logging,
    including file handling, formatting, and additional features.
    
    Attributes:
        log_level (str): Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            Defaults to "INFO".
        log_dir (str): Directory where log files will be stored. Defaults to "logs".
        log_filename_prefix (Optional[str]): Prefix for log filenames.
        max_bytes (Optional[int]): Maximum size of each log file in bytes.
            Defaults to 10MB.
        backup_count (Optional[int]): Number of backup files to keep.
            Defaults to 5.
        log_format (Optional[str]): Format string for log messages.
    """
    
    # Basic settings
    log_level: str = "INFO"
    log_dir: str = "logs"
    
    # File handling
    log_filename_prefix: Optional[str] = 'beegen'
    max_bytes: Optional[int] = 10485760  # 10MB
    backup_count: Optional[int] = 5
    
    # Formatting
    log_format: Optional[str] = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Additional features
    log_host_name: Optional[str] = None
    include_hostname: Optional[bool] = True


class LogConfig(YamlModel):
    """Main configuration class for logging setup.
    
    This class combines both standard and Kafka logging configurations along with
    global settings for the logging system.
    
    Attributes:
        std (StdLogConfig): Standard logging configuration.
        kafka (Optional[KafkaLogConfig]): Kafka logging configuration.
        app_name (str): Name of the application.
        environment (str): Deployment environment (development, staging, production).
        log_filters (Optional[List[str]]): List of modules/loggers to filter out.
        extra_fields (Optional[Dict]): Additional fields to include in log messages.
    
    Raises:
        ValueError: If required fields are missing or invalid environment is specified.
    """
    
    std: StdLogConfig
    kafka: Optional[KafkaLogConfig] = None
    
    # Global settings
    app_name: str = "beegen-core"
    environment: str = "production" # development, staging, production
    log_filters: Optional[List[str]] = []
    extra_fields: Optional[Dict[str, Union[str, int, float, bool]]] = {}
    
    @classmethod
    def default(cls) -> 'LogConfig':
        """Load default config"""

        config_path = BEEGEN_ROOT / "config/logging-beeflow.yaml"
        if config_path.exists():
            data = cls.read_yaml(config_path)
            return cls(**data)
        else:
            return cls(std=StdLogConfig(), kafka=None)


if __name__ == "__main__":
    # log_config.to_yaml_file(Path('log_config.yaml'))
    log_config = LogConfig.default()
    print(log_config)