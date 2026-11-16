from enum import Enum
from typing import Dict, Any
from pydantic import Field
from beegen.configs.yaml_model import YamlModel
from beegen.const import BEEGEN_ROOT


class MemoryType(str, Enum):
    MEM0 = "mem0"


class MemoryConfig(YamlModel):
    """Base configuration for Memory modules."""
    api_type: MemoryType

    def dict(self, **kwargs):
        return self.model_dump(**kwargs)