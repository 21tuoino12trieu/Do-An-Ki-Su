from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import Field

from beegen.configs.yaml_model import YamlModel
from beegen.const import BEEGEN_ROOT
from beegen.tools.schema.param import ParamSet


class KafkaSecurityProtocol(str, Enum):
    PLAINTEXT = "PLAINTEXT"
    SASL_PLAINTEXT = "SASL_PLAINTEXT"
    SASL_SSL = "SASL_SSL"
    SSL = "SSL"
    
class KafkaOperation(str, Enum):
    PRODUCE = "produce"
    CONSUME = "consume"

# --------------------- IO Schemas (ParamSet) ---------------------
KAFKA_OPERATION_INPUTS = {
    KafkaOperation.PRODUCE: (
        ParamSet.new()
            .var("topic: str", "Destination topic", required=True)
            .var("value: str | bytes | dict", "Message payload", required=True)
            .var("key: Optional[str | bytes]", "Optional key for partitioning")
            .var("headers: Optional[dict]", "Optional message headers (str->str)")
            .var("partition: Optional[int]", "Specific partition to send to")
            .build()
    ),
    KafkaOperation.CONSUME: (
        ParamSet.new()
            .var("topics: list[str] | str", "Topic(s) to subscribe", required=True)
            .var("max_messages: int = 1", "Max messages to return")
            .var("timeout_ms: int = 1000", "Poll timeout ms")
            .var("commit: bool = False", "Commit offsets after read")
            .var("decode: bool = True", "Decode key/value to UTF-8 strings")
            .build()
    ),
}

KAFKA_OPERATION_OUTPUTS = {
    KafkaOperation.PRODUCE: (
        ParamSet.new()
            .var("status: str", "success | error", required=True)
            .var("partition_written: int", "Partition written")
            .var("offset: int", "Offset of the record")
            .var("timestamp: Optional[int]", "Kafka timestamp")
            .var("message: str", "Status message if any")
            .build()
    ),
    KafkaOperation.CONSUME: (
        ParamSet.new()
            .var("status: str", "success | error", required=True)
            .var("messages: list[dict]", "List of consumed messages")
            .var("count: int", "Number of messages returned")
            .var("message: str", "Status message")
            .build()
    ),
}


class KafkaConfig(YamlModel):
    """
    Configuration for Kafka connections (producer, consumer, and admin).

    Attributes:
        bootstrap_servers (List[str] | str): Kafka broker addresses.
        client_id (str): Logical identifier for this client.
        group_id (Optional[str]): Consumer group id (required for consumer operations).

        # Security
        security_protocol (KafkaSecurityProtocol): Kafka security protocol.
        sasl_mechanism (Optional[str]): SASL mechanism (e.g., PLAIN, SCRAM-SHA-256, SCRAM-SHA-512, OAUTHBEARER).
        sasl_plain_username (Optional[str]): Username for SASL/PLAIN.
        sasl_plain_password (Optional[str]): Password for SASL/PLAIN.
        ssl_cafile (Optional[str]): Path to CA file if using SSL / SASL_SSL.

        # Producer tuning
        acks (str): Number of acknowledgements the producer requires (all, 1, 0).
        linger_ms (int): Linger time before send.
        compression_type (Optional[str]): Compression codec, e.g., gzip, lz4, snappy, zstd.
        request_timeout_ms (int): Request timeout for produce.

        # Consumer tuning
        auto_offset_reset (str): earliest/latest/none.
        enable_auto_commit (bool): Whether consumer auto-commits offsets.
        session_timeout_ms (int): Consumer session timeout.
        fetch_max_bytes (int): Max bytes per fetch.
    """

    # Core
    bootstrap_servers: List[str] | str
    client_id: str = Field(default="beeflow-client")
    group_id: Optional[str] = Field(default=None)

    # Security
    security_protocol: KafkaSecurityProtocol = Field(default=KafkaSecurityProtocol.PLAINTEXT)
    sasl_mechanism: Optional[str] = None
    sasl_plain_username: Optional[str] = None
    sasl_plain_password: Optional[str] = None
    ssl_cafile: Optional[str] = None

    # Producer
    acks: str = Field(default="all")
    linger_ms: int = Field(default=0)
    compression_type: Optional[str] = None
    request_timeout_ms: int = Field(default=30000)

    # Consumer
    auto_offset_reset: str = Field(default="latest")
    enable_auto_commit: bool = Field(default=True)
    session_timeout_ms: int = Field(default=10000)
    fetch_max_bytes: int = Field(default=50 * 1024 * 1024)

    @classmethod
    def default(cls) -> "KafkaConfig":
        """Load default config from `config/kafka.yaml`."""
        data = cls.read_yaml(BEEGEN_ROOT / "config/kafka.yaml")
        return KafkaConfig(**data)

    def to_aiokafka_common_kwargs(self) -> Dict[str, Any]:
        """Return base kwargs for aiokafka Producer/Consumer/Admin from this config."""
        servers = self.bootstrap_servers
        if isinstance(servers, list):
            servers = ",".join(servers)

        kwargs: Dict[str, Any] = {
            "bootstrap_servers": servers,
            "client_id": self.client_id,
            "security_protocol": self.security_protocol.value,
        }

        if self.security_protocol in {KafkaSecurityProtocol.SASL_PLAINTEXT, KafkaSecurityProtocol.SASL_SSL}:
            if self.sasl_mechanism:
                kwargs["sasl_mechanism"] = self.sasl_mechanism
            if self.sasl_plain_username is not None:
                kwargs["sasl_plain_username"] = self.sasl_plain_username
            if self.sasl_plain_password is not None:
                kwargs["sasl_plain_password"] = self.sasl_plain_password
        if self.security_protocol in {KafkaSecurityProtocol.SSL, KafkaSecurityProtocol.SASL_SSL} and self.ssl_cafile:
            kwargs["ssl_cafile"] = self.ssl_cafile

        return kwargs

    def to_aiokafka_producer_kwargs(self) -> Dict[str, Any]:
        base = self.to_aiokafka_common_kwargs()
        base.update({
            "acks": self.acks,
            "linger_ms": self.linger_ms,
            "compression_type": self.compression_type,
            "request_timeout_ms": self.request_timeout_ms
        })
        return base

    def to_aiokafka_consumer_kwargs(self) -> Dict[str, Any]:
        base = self.to_aiokafka_common_kwargs()
        base.update({
            "group_id": self.group_id,
            "enable_auto_commit": self.enable_auto_commit,
            "auto_offset_reset": self.auto_offset_reset,
            "session_timeout_ms": self.session_timeout_ms,
            "fetch_max_bytes": self.fetch_max_bytes,
        })
        return base