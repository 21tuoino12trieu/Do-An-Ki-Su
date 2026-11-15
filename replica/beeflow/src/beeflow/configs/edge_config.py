from typing import Literal, Tuple
from beegen.configs.yaml_model import YamlModel
from pydantic import Field


EdgeType = Literal["normal", "lookback", "condition"]


class EdgeConfig(YamlModel):
    """Configuration for edges between nodes in a workflow graph."""
    
    from_node: str
    to_node: str 
    type: EdgeType = "normal"
    
    
