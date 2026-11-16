from pathlib import Path
from typing import Optional
from pydantic import Field
from beegenerate.configs.yaml_model import YamlModel

class AppConfig(YamlModel):
    """Application configuration model"""
    app_name: str = Field(..., description="Name of the application")
    version: str = Field(..., description="Application version")
    debug_mode: bool = Field(default=False, description="Enable debug mode")
    max_connections: int = Field(default=100, description="Maximum number of connections")
    api_key: Optional[str] = Field(None, description="API key for external service")


def main():
    # Example usage of AppConfig
    config_path = Path("app_config.yaml")
    
    # Create a sample configuration
    sample_config = AppConfig(
        app_name="MyAwesomeApp",
        version="1.0.0",
        debug_mode=True,
        max_connections=200,
        api_key="REPLACE_WITH_LOCAL_SECRET"
    )
    
    # Write the configuration to a YAML file
    sample_config.to_yaml_file(config_path)
    print(f"Sample configuration written to {config_path}")

    # Read the configuration from the YAML file
    loaded_config = AppConfig.from_yaml_file(config_path)
    print("\nLoaded configuration:")
    print(f"App Name: {loaded_config.app_name}")
    print(f"Version: {loaded_config.version}")
    print(f"Debug Mode: {loaded_config.debug_mode}")
    print(f"Max Connections: {loaded_config.max_connections}")
    print(f"API Key: {loaded_config.api_key}")
    

if __name__ == "__main__":
    main()