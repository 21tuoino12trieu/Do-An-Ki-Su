from .node import Node
from .context import _current_graph


class Graph(Node):
    def __init__(self, name="default"):
        self.name = name
        self.nodes = {}
        self.edges = []
        self._token = None
        
        # Only register as a node if we're inside another graph context
        try:
            parent_graph = _current_graph.get()
            # Call Node.__init__ to register this graph as a node in the parent
            super().__init__(name)
        except LookupError:
            # We're the root graph, no parent to register with
            self.task_id = name
            self.graph = None
    
    def __enter__(self):
        self._token = _current_graph.set(self)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        _current_graph.reset(self._token)
        
    @classmethod
    def get_current(cls):
        try:
            return _current_graph.get()
        except LookupError:
            raise RuntimeError("You must use 'with Graph(...) as g:' before defining nodes.")
        
    def add_node(self, node):
        self.nodes[node.task_id] = node

    def add_edge(self, src, dst):
        self.edges.append((src.task_id, dst.task_id))

    def show(self, indent=0):
        prefix = "  " * indent
        print(f"{prefix}Graph: {self.name}")
        print(f"{prefix}Nodes:", list(self.nodes.keys()))
        print(f"{prefix}Edges:")
        for src, dst in self.edges:
            print(f"{prefix}  {src} -> {dst}")
        
        # Show nested graphs
        for node in self.nodes.values():
            if isinstance(node, Graph):
                node.show(indent + 1)
    
    
if __name__ == "__main__":
    with Graph("MyFlow") as root:
        n1 = Node("n1")
        n2 = Node("n2")
        
        # Create a nested subgraph
        with Graph("g1") as g1:
            s1 = Node("s1") 
            s2 = Node("s2")
            s1 >> s2
            
        with Graph("g2") as g2:
            a1 = Node("a1")
            a2 = Node("a2") 
            a1 >> a2
        
        # Connect regular nodes to subgraphs
        n1 >> g1 >> n2 >> g2
        
        # Even connect subgraphs to each other
        # g1 >> g2 would also work!

    root.show()