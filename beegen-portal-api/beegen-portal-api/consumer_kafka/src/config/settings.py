from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import pathlib
from dotenv import load_dotenv
import os

# Project Directories
ROOT = pathlib.Path(__file__).resolve().parent.parent
if os.path.isfile("/deployment/config/config.env"):
    config_file_path = "/deployment/config/config.env"
else:
    config_file_path = os.path.join("config.env")

load_dotenv(config_file_path, override=True)
load_dotenv("/deployment/sc/config-sc-common.env", override=True)

class Settings(BaseSettings):
    ai_aes_key: str = Field("GuPR4nWYk4QIyCj89VkOLyRC5haRT3zp")
    # Kafka
    kafka_bootstrap_servers: str = Field(default="localhost:9092")
    kafka_input_topic: str = Field(default="APP_AI_CUA_IN")
    kafka_output_topic: str = Field(default="APP_AI_CUA_OUT")
    kafka_group_id: str = Field(default="cua-consumer-group")
    kafka_auto_offset_reset: str = Field(default="earliest")
    kafka_max_poll_interval_ms: int = Field(default=30000)   # 10 phút
    kafka_session_timeout_ms: int = Field(default=60000)       # 1 phút
    kafka_heartbeat_interval_ms: int = Field(default=10000)    # 10 giây (= 1/3 session)
    kafka_max_poll_records: int = Field(default=10)            # Số message xử lý mỗi batch
    kafka_max_concurrent_tasks: int = Field(default=5)         # Số message xử lý đồng thời
    kafka_user: str = Field(default="kafka_user")
    kafka_password: str = Field(default="kafka_password")
    kafka_consumer_batch_size: int = Field(default=20)
    kafka_sasl_mechanism: str = Field(default="SCRAM-SHA-512")
    kafka_security_protocol: str = Field(default="SASL_PLAINTEXT")

    # MongoDB
    mongo_host: str = Field(default="10.215.107.53:27017")
    mongo_port: int = Field(default=27017)
    ai_mongodb_cua_username: str = Field(default="cua_ai")
    ai_mongodb_cua_password: str = Field(default="")
    ai_mongodb_cua_url_suffix: str
    mongo_db: str = Field(default="cua_ai")
    mongo_collection_logs: str = Field(default="consumer_logs")
    mongo_db_uri_suffix: str = Field(default="readPreference=primary&ssl=false&directConnection=true")

    # Airflow
    airflow_host: str = Field(default="https://ai-platform-airflow.tanzu-dev.mbbank.com.vn")
    airflow_username: str = Field(default="")
    airflow_password: str = Field(default="")
    airflow_auth: str = Field(default="")
    airflow_api_timeout: int = Field(default=30)
    airflow_retry_max_attempts: int = Field(default=3)
    airflow_retry_wait_min: int = Field(default=1)
    airflow_retry_wait_max: int = Field(default=10)

    # App
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")        # json | console
    service_name: str = Field(default="cua-consumer")
    service_env: str = Field(default="development")

settings = Settings()