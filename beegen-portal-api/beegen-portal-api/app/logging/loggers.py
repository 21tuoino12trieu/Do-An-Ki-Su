import json
import socket
import sys
from dataclasses import asdict
from typing import Any, Dict, Optional

from kafka import KafkaProducer

from app.logging.config import LogConfig, load_log_config


class KafkaHTTPLogger:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        config: LogConfig,
        producer_config: Optional[Dict[str, Any]] = None,
        servicename: str = "beegen-portal-api",
    ):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.config = config
        self.producer = None
        self.closed = False
        self.servicename = servicename

        try:
            kafka = config.kafka
            producer_config = producer_config or {}
            producer_config.update({
                "bootstrap_servers": kafka.kafka_boostrap_servers.split(",") if kafka.kafka_boostrap_servers else [],
                "security_protocol": kafka.kafka_security_protocol,
                "value_serializer": lambda m: json.dumps(m).encode("utf-8"),
            })

            if kafka.kafka_ssl_ca_file and kafka.kafka_security_protocol == "SSL":
                producer_config["ssl_cafile"] = kafka.kafka_ssl_ca_file

            if kafka.kafka_security_protocol not in ["PLAINTEXT", "SSL"]:
                producer_config.update({
                    "sasl_mechanism": kafka.kafka_sasl_mechanism,
                    "sasl_plain_username": kafka.kafka_sasl_username,
                    "sasl_plain_password": kafka.kafka_sasl_password,
                })

            if kafka.kafka_compression_type or kafka.kafka_retries:
                producer_config.update({
                    "compression_type": kafka.kafka_compression_type,
                    "retries": kafka.kafka_retries,
                })

            self.producer = KafkaProducer(**producer_config)
            self._initialized = True
        except Exception as e:
            sys.stderr.write(f"Failed to initialize Kafka HTTP logger: {e}\n")
            sys.stderr.write("HTTP logging to Kafka will be disabled.\n")
            self.closed = True

    def _get_timestamp(self) -> str:
        from datetime import datetime, timezone, timedelta
        tz = timezone(timedelta(hours=7))
        return datetime.now(tz).isoformat(timespec="milliseconds")

    def _get_severity_text(self, responsecode: int) -> str:
        return "INFO" if 200 <= responsecode < 300 else "ERROR"

    def _truncate_body(self, content: str, max_size: int = 10240) -> str:
        if content and len(content) > max_size:
            return content[:max_size]
        return content or ""

    def _build_log_structure(
        self,
        log_type: str,
        method: str,
        url: str,
        path: str,
        status: str,
        response_code: int = 0,
        response_msg: str = "",
        response_content: str = "",
        duration_ms: float = 0,
        request_id: str = "",
        request_body: str = "",
        source_ip: str = "",
        source_app: str = "",
        user_agent: str = "",
        origin: str = "",
        content_type: str = "",
        content_length: str = "",
        user_request: str = "",
        session_id: str = "",
        correlation_id: str = "",
        authorization: str = "",
        error_type: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        response_code_str = str(response_code) if response_code else ""

        body_parts = []
        if request_body:
            body_parts.append(f"Request: {self._truncate_body(request_body)}")
        if response_content:
            body_parts.append(f"Response: {self._truncate_body(response_content)}")
        if response_msg:
            body_parts.append(f"Message: {response_msg}")
        body = " | ".join(body_parts) if body_parts else ""

        http = self.config.http
        log_data = {
            "timestamp": self._get_timestamp(),
            "severityText": self._get_severity_text(response_code),
            "body": body,
            "instrumentationScope": http.instrumentation_scope or self.servicename,
            "contextMap": {
                "logType": log_type,
                "sourceApp": source_app,
                "sourceIpAddress": source_ip,
                "ipServer": http.ip_server,
                "application": http.app_name,
                "destinationAppIP": http.destination_app_ip,
                "destinationAppPort": http.destination_app_port,
                "clientMessageID": request_id,
                "urlPath": url,
                "servicePath": path,
                "method": method,
                "status": status,
                "typeSystem": http.type_system,
                "responseCode": response_code_str,
                "responseMessage": response_msg,
                "durationTime": int(duration_ms) if duration_ms else 0,
                "host": socket.gethostname(),
                "operatingSystem": "",
                "deviceModel": "",
                "deviceId": "",
                "SysCode": http.sys_code,
                "CmpCode": http.cmp_code,
                "ErrorType": error_type,
                "servicename": self.servicename,
                "responseContent": self._truncate_body(response_content),
            },
        }

        for key, value in kwargs.items():
            if value and key not in log_data["contextMap"]:
                log_data["contextMap"][key] = value

        return log_data

    def log_request(
        self,
        request_id: str,
        method: str,
        url: str,
        path: str,
        source_ip: str = "",
        source_app: str = "",
        user_agent: str = "",
        origin: str = "",
        content_type: str = "",
        content_length: str = "",
        user_request: str = "",
        session_id: str = "",
        correlation_id: str = "",
        authorization: str = "",
        request_body: str = "",
    ) -> None:
        if self.closed or not self.producer:
            return

        log_data = self._build_log_structure(
            log_type="request",
            method=method,
            url=url,
            path=path,
            status="ON",
            response_code=200,
            request_id=request_id,
            request_body=request_body,
            source_ip=source_ip,
            source_app=source_app,
            user_agent=user_agent,
            origin=origin,
            content_type=content_type,
            content_length=content_length,
            user_request=user_request,
            session_id=session_id,
            correlation_id=correlation_id,
            authorization=authorization,
        )

        try:
            self.producer.send(self.config.kafka.kafka_topic_log, log_data)
        except Exception as e:
            sys.stderr.write(f"Failed to log request to Kafka: {e}\n")

    def log_response(
        self,
        request_id: str,
        method: str,
        url: str,
        path: str,
        responsecode: int,
        duration_ms: float,
        response_msg: str = "",
        response_content: str = "",
        status: str = None,
        source_ip: str = "",
        source_app: str = "",
        user_agent: str = "",
        origin: str = "",
        content_type: str = "",
        content_length: str = "",
        user_request: str = "",
        session_id: str = "",
        correlation_id: str = "",
        authorization: str = "",
        error_type: str = "",
    ) -> None:
        if self.closed or not self.producer:
            return

        if status is None:
            status = "ON"

        log_data = self._build_log_structure(
            log_type="response",
            method=method,
            url=url,
            path=path,
            status=status,
            response_code=responsecode,
            response_msg=response_msg,
            response_content=response_content,
            duration_ms=duration_ms,
            request_id=request_id,
            source_ip=source_ip,
            source_app=source_app,
            user_agent=user_agent,
            origin=origin,
            content_type=content_type,
            content_length=content_length,
            user_request=user_request,
            session_id=session_id,
            correlation_id=correlation_id,
            authorization=authorization,
            error_type=error_type,
        )

        try:
            self.producer.send(self.config.kafka.kafka_topic_log, log_data)
        except Exception as e:
            sys.stderr.write(f"Failed to log response to Kafka: {e}\n")

    def log_error(
        self,
        request_id: str,
        method: str,
        url: str,
        path: str,
        responsecode: int,
        error_msg: str,
        duration_ms: float,
        source_ip: str = "",
        source_app: str = "",
        user_agent: str = "",
        origin: str = "",
        user_request: str = "",
        session_id: str = "",
        correlation_id: str = "",
        authorization: str = "",
        error_type: str = "",
    ) -> None:
        self.log_response(
            request_id=request_id,
            method=method,
            url=url,
            path=path,
            responsecode=responsecode,
            duration_ms=duration_ms,
            response_msg=error_msg,
            status="ON",
            source_ip=source_ip,
            source_app=source_app,
            user_agent=user_agent,
            origin=origin,
            user_request=user_request,
            session_id=session_id,
            correlation_id=correlation_id,
            authorization=authorization,
            error_type=error_type,
        )


HTTP_LOGGER = KafkaHTTPLogger(config=load_log_config())
