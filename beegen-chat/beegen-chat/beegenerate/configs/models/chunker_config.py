from typing import Optional
from beegenerate.configs.yaml_model import YamlModel
from beegenerate.const import BEEGEN_ROOT
from pathlib import Path


class ChunkerConfig(YamlModel):
    """Configuration for the Chunker service."""

    chunker_base_url: str = "http://localhost:8001" # Default value, will be overwritten by config file

    @classmethod
    def default(cls) -> 'ChunkerConfig':
        """Load default config from config/chunker.yaml"""
        config_path = BEEGEN_ROOT / "config/chunker.yaml"
        if not config_path.exists():
            # Handle case where config file doesn't exist, perhaps create a default one or raise an error
            # For now, let's assume it exists or use a default value
            return ChunkerConfig()
        
        data = ChunkerConfig.read_yaml(config_path)
        return ChunkerConfig(**data)

if __name__ == "__main__":
    config = ChunkerConfig.default()
    print(config)