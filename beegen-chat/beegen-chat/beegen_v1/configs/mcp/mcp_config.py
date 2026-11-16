from enum import Enum
from typing import Optional, Dict
from beegen_v1.configs.yaml_model import YamlModel
from pathlib import Path


class JiraMCPConfig(YamlModel):
    token_enc_key: str
    jira_base_url: str
    jira_mcp_url: str


class HRInfo(YamlModel):
    mcp_url: str


class MCPConfig(YamlModel):
    jira: JiraMCPConfig
    hr_info: HRInfo


class RootMCPConfig(YamlModel):
    mcp_config: MCPConfig

    @classmethod
    def default(cls) -> "RootMCPConfig":
        from beegen_v1.const import BEEGEN_ROOT
        dict_ = cls.read_yaml(BEEGEN_ROOT / "config/mcp_config.yaml")
        return cls(**dict_)


if __name__ == "__main__":
    config = RootMCPConfig.default()
    print(config.model_dump())
