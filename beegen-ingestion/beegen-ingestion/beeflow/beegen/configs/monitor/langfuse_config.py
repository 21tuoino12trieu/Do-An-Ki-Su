from typing import Optional
from beegen.configs.yaml_model import YamlModel
from beegen.const import BEEGEN_ROOT


class LangfuseConfig(YamlModel):
    """Configuration for Langfuse connection settings.

    This class defines the parameters needed to establish and maintain
    a connection with a Langfuse server for observability and monitoring.

    Attributes:
        public_key (str): The public key for authenticating with Langfuse.
        secret_key (str): The secret key for authenticating with Langfuse.
        host (str): The hostname or URL of the Langfuse server.
    """
    public_key: str
    secret_key: str
    host: str
    
    @classmethod
    def default(cls) -> 'LangfuseConfig':
        """Load default config from YAML file."""
        config_dict = LangfuseConfig.read_yaml(BEEGEN_ROOT / "config/langfuse.yaml")
        return LangfuseConfig(**config_dict)
    
    
if __name__ == "__main__":
    langfuse_config = LangfuseConfig.default()
    print(langfuse_config)