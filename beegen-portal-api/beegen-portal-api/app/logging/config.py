import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class KafkaLogConfig:
    kafka_boostrap_servers: str
    kafka_topic_log: str
    kafka_security_protocol: str
    kafka_ssl_ca_file: Optional[str]
    kafka_sasl_mechanism: Optional[str]
    kafka_sasl_username: Optional[str]
    kafka_sasl_password: Optional[str]
    kafka_compression_type: Optional[str]
    kafka_retries: Optional[int]


@dataclass
class HttpLogConfig:
    app_name: str
    environment: str
    type_system: str
    destination_app_ip: str
    destination_app_port: str
    ip_server: str
    sys_code: str
    cmp_code: str
    instrumentation_scope: str


@dataclass
class LogConfig:
    kafka: KafkaLogConfig
    http: HttpLogConfig


def _get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def load_log_config() -> LogConfig:
    kafka = KafkaLogConfig(
        kafka_boostrap_servers=_get_env("KAFKA_BOOTSTRAP_SERVERS"),
        kafka_topic_log=_get_env("KAFKA_TOPIC_LOG"),
        kafka_security_protocol=_get_env("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
        kafka_ssl_ca_file=_get_env("KAFKA_SSL_CA_FILE") or None,
        kafka_sasl_mechanism=_get_env("KAFKA_SASL_MECHANISM") or None,
        kafka_sasl_username=_get_env("KAFKA_SASL_USERNAME") or None,
        kafka_sasl_password=_get_env("KAFKA_SASL_PASSWORD") or None,
        kafka_compression_type=_get_env("KAFKA_COMPRESSION_TYPE") or None,
        kafka_retries=int(_get_env("KAFKA_RETRIES", "3")),
    )

    http = HttpLogConfig(
        app_name=_get_env("LOG_APP_NAME"),
        environment=_get_env("LOG_ENVIRONMENT"),
        type_system=_get_env("LOG_TYPE_SYSTEM", "tanzu-prod-multidc-dc01-ai-cls"),
        destination_app_ip=_get_env("LOG_DESTINATION_APP_IP"),
        destination_app_port=_get_env("LOG_DESTINATION_APP_PORT"),
        ip_server=_get_env("LOG_IP_SERVER"),
        sys_code=_get_env("LOG_SYS_CODE"),
        cmp_code=_get_env("LOG_CMP_CODE"),
        instrumentation_scope=_get_env("LOG_INSTRUMENTATION_SCOPE"),
    )

    return LogConfig(kafka=kafka, http=http)
