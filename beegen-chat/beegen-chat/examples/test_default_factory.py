from  beegenerate.configs.yaml_model import YamlModel
from typing import List

class NodeConfig(YamlModel):
    upstream_nodes: List = []  # Direct assignment
    

node1 = NodeConfig()
node2 = NodeConfig()
node1.upstream_nodes.append("node_x")

print(node2.upstream_nodes)  # Will show ["node_x"] - shared list!