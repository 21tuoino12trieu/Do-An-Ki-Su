from enum import Enum
from typing import Optional, Dict, Any
from beegen.configs.yaml_model import YamlModel
    

class VectorDBType(str, Enum):
    """Types of vectordb"""
    MILVUS = "milvus"


class VectorDBConfig(YamlModel):
    """Base configuration for vector database implementations."""
    db_type: VectorDBType