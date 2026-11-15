from beegen.configs.yaml_model import YamlModel
from beegen.const import BEEGEN_ROOT
from beegen.tools.schema.param import ParamSet
from typing import Optional
from enum import Enum
from botocore.client import Config as BotoConfig
from pydantic import Field


class S3Operation(str, Enum):
    LIST_PATHS = "list_paths"
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    DOWNLOAD_FILE = "download_file"
    UPLOAD_FILE = "upload_file"


# Define the input parameter sets for each S3 operation
S3_OPERATION_INPUTS = {
    S3Operation.LIST_PATHS: (
        ParamSet.new()
            .var("bucket: Optional[str]", "S3 bucket name")
            .var("prefix: Optional[str] = ''", "Path prefix to filter results")
            .var("recursive: bool = False", "List objects recursively if True")
            .var("max_keys: Optional[int] = None", "Maximum number of paths to return")
            .build()
    ),
    S3Operation.READ: (
        ParamSet.new()
            .var("bucket: Optional[str]", "S3 bucket name")
            .var("key: str", "Full path to the object to read", required=True)
            .var("as_bytes: bool = True", "Return content as bytes if True, otherwise str")
            .build()
    ),
    S3Operation.WRITE: (
        ParamSet.new()
            .var("bucket: Optional[str]", "S3 bucket name")
            .var("key: str", "Full path to write the object to", required=True)
            .var("content: Union[str, bytes]", "Content to write to S3", required=True)
            .var("content_type: Optional[str]", "MIME type of the content (e.g., 'text/plain', 'application/json')")
            .var("overwrite: bool = True", "Overwrite the file if it exists")
            .build()
    ),
    S3Operation.DELETE: (
        ParamSet.new()
            .var("bucket: Optional[str]", "S3 bucket name")
            .var("key: str", "Full path of the object to delete", required=True)
            .build()
    ),
    S3Operation.DOWNLOAD_FILE: (
        ParamSet.new()
            .var("bucket: Optional[str]", "S3 bucket name")
            .var("key: str", "S3 object key to download", required=True)
            .var("local_dir: Optional[str]", "Local directory to download to (defaults to temp)")
            .build()
    ),
    S3Operation.UPLOAD_FILE: (
        ParamSet.new()
            .var("bucket: Optional[str]", "S3 bucket name")
            .var("local_file_path: str", "Local file path to upload", required=True)
            .var("key: str", "S3 object key to upload", required=True)
            .var("content_type: Optional[str | None] = None", "MIME type of the file")
            .build()
    ),
}

# Define the output parameter sets for each S3 operation
S3_OPERATION_OUTPUTS = {
    S3Operation.LIST_PATHS: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("paths: List[str]", "List of file paths")
            .var("count: int", "Number of paths returned")
            .var("message: str", "Error message if status != 'success'")
            .build()
    ),
    S3Operation.READ: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("document_bytes: Union[str, bytes]", "Raw content read from the S3 object")
            .var("document_path: str", "Full S3 path of the object (e.g., s3://bucket/key)")
            .var("content_type: str", "MIME type of the object (e.g., 'application/pdf')")
            .var("message: str", "Error message if status != 'success'")
            .build()
    ),
    S3Operation.WRITE: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("document_path: str", "Full S3 path of the object (e.g., s3://bucket/key)")
            .var("message: str", "Error message if status != 'success'")
            .build()
    ),
    S3Operation.DELETE: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("document_path: str", "Full S3 path of the object (e.g., s3://bucket/key)")
            .var("message: str", "Error message if status != 'success'")
            .build()
    ),
    S3Operation.DOWNLOAD_FILE: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("local_file_path: str", "Local path where file was downloaded")
            .var("document_path: str", "Full S3 path of the object")
            .var("message: str", "Error message if status != 'success'")
            .build()
    ),
    S3Operation.UPLOAD_FILE: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("document_path: str", "Full S3 path of the uploaded object")
            .var("message: str", "Error message if status != 'success'")
            .build()
    ),
}
    

class S3Config(YamlModel):
    """
    Configuration class for S3-compatible storage with boto3 configuration.

    Attributes:
        bucket (str): Bucket name or prefix path.
        region (str): Region name (e.g., ap-southeast-1).
        access_key (str): Access key for S3.
        secret_key (str): Secret key for S3.
        endpoint_url (Optional[str]): Custom endpoint for S3-compatible storage.
        
        # Boto3 Configuration
        signature_version (str): AWS signature version.
        connect_timeout (int): Connection timeout in seconds.
        read_timeout (int): Read timeout in seconds.
        max_attempts (int): Maximum retry attempts.
        payload_signing_enabled (bool): Whether to enable payload signing.
        addressing_style (str): S3 addressing style ('path' or 'virtual').
        use_accelerate_endpoint (bool): Whether to use S3 transfer acceleration.
        use_dualstack_endpoint (bool): Whether to use dualstack endpoint.
    """
    # Core S3 settings
    bucket: str = None
    region: str
    access_key: str
    secret_key: str
    endpoint_url: Optional[str] = None
    
    # Boto3 configuration settings
    signature_version: str = Field(default="s3v4", description="AWS signature version")
    connect_timeout: int = Field(default=10, description="Connection timeout in seconds")
    read_timeout: int = Field(default=30, description="Read timeout in seconds")
    max_attempts: int = Field(default=3, description="Maximum retry attempts")
    payload_signing_enabled: bool = Field(default=False, description="Enable payload signing")
    addressing_style: str = Field(default="path", description="S3 addressing style")
    use_accelerate_endpoint: bool = Field(default=False, description="Use S3 transfer acceleration")
    use_dualstack_endpoint: bool = Field(default=False, description="Use dualstack endpoint")

    @classmethod
    def default(cls) -> 'S3Config':
        """Load default config"""
        dict = S3Config.read_yaml(BEEGEN_ROOT / "config/s3.yaml")
        return S3Config(**dict)

    def get_boto_config(self) -> BotoConfig:
        """Generate BotoConfig from the current settings."""
        s3_cfg = {
            "payload_signing_enabled": self.payload_signing_enabled,
            "addressing_style": self.addressing_style,
            "use_accelerate_endpoint": self.use_accelerate_endpoint,
            "use_expect_header": False, 
        }

        return BotoConfig(
            signature_version=self.signature_version,
            s3=s3_cfg,
            connect_timeout=self.connect_timeout,
            read_timeout=self.read_timeout,
            retries={"max_attempts": self.max_attempts},
            use_dualstack_endpoint=self.use_dualstack_endpoint,
        )


if __name__ == "__main__":
    print(S3_OPERATION_OUTPUTS[S3Operation.LIST_PATHS])
    
    # Test config loading
    try:
        config = S3Config.default()
        boto_config = config.get_boto_config()
        print(f"Config loaded: bucket={config.bucket}, region={config.region}")
        print(f"Boto config: {boto_config}")
    except Exception as e:
        print(f"Error loading config: {e}")