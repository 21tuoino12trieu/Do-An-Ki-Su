from .context import _current_graph


class Node:
    def __init__(self, task_id):
        from .graph import Graph
        
        self.task_id = task_id
        self.graph = Graph.get_current()  # Đây chính là `g`
        self.graph.add_node(self)

    def __rshift__(self, other):
        if isinstance(other, list):
            # n1 >> [n2, n3] - connect this node to multiple nodes
            for node in other:
                self.graph.add_edge(self, node)
            return other
        elif hasattr(other, 'graph'):  # Check if it's a Node
            # n1 >> n2 - connect this node to another node
            self.graph.add_edge(self, other)
            return other
        else:
            # Return NotImplemented for unsupported types
            return NotImplemented

    def __lshift__(self, other):
        if isinstance(other, list):
            # [n2, n3] >> n4 becomes n4 << [n2, n3]
            for node in other:
                self.graph.add_edge(node, self)
            return self
        elif hasattr(other, 'graph'):  # Check if it's a Node
            # n2 << n1 - connect another node to this node
            self.graph.add_edge(other, self)
            return self
        else:
            # Return NotImplemented for unsupported types
            return NotImplemented
    
    def __rrshift__(self, other):
        """Called for [n1, n2] >> self because lists don't have __rshift__"""
        return self.__lshift__(other)
    
    def __rlshift__(self, other):
        """Called for [n1, n2] << self because lists don't have __lshift__"""
        return self.__rshift__(other)