from typing import Optional
from pathlib import Path
from beegenerate.configs.yaml_model import YamlModel
from beegenerate.const import BEEGEN_ROOT


class LangfuseConfig(YamlModel):
    """Configuration settings for Langfuse API integration.

    A configuration model that handles connection parameters and authentication
    for interacting with the Langfuse observability platform.

    Attributes:
        secret_key (str): Langfuse secret key for authentication.
        public_key (str): Langfuse public key for authentication.
        host (str): Base URL for the Langfuse API.

    Example:
        ```yaml
        langfuse_config:
          secret_key: "REPLACE_WITH_LOCAL_SECRET"
          public_key: "pk-lf-b62944f2-5726-4334-b050-ae87d7d8eef0"
          host: "http://ai-platform-langfuse.tanzu-dev.mbbank.com.vn"
        ```
    """
    secret_key: str
    public_key: str
    host: str
    no_proxy: str
    debug: bool
    timeout: int

    @classmethod
    def default(cls) -> 'LangfuseConfig':
        """Load default Langfuse config"""
        dict = LangfuseConfig.read_yaml(BEEGEN_ROOT / "config/langfuse.yaml")
        return LangfuseConfig(**dict)


if __name__ == "__main__":
    # Example to create a default config file
    # default_config = LangfuseConfig(
    #     secret_key="REPLACE_WITH_LOCAL_SECRET",
    #     public_key="pk-lf-b62944f2-5726-4334-b050-ae87d7d8eef0",
    #     host="http://ai-platform-langfuse.tanzu-dev.mbbank.com.vn"
    # )
    # default_config.to_yaml_file(Path('langfuse.yaml'))

    # Load config from file
    langfuse_config = LangfuseConfig.default()
    print(langfuse_config)
