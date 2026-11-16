from typing import Literal, Tuple
from beegen.configs.yaml_model import YamlModel
from pydantic import Field


EdgeType = Literal["normal", "lookback", "condition"]


class EdgeConfig(YamlModel):
    """Configuration for edges between nodes in a workflow graph."""
    
    from_node: str
    to_node: str 
    type: EdgeType = "normal"
    
    
if __name__ == "__main__":
    edge = EdgeConfig(from_node="node1", to_node="node2")
    print(edge)