from dataclasses import dataclass, field
from typing import Dict, Any, Callable, List, Set
from enum import Enum
import time
import json
from collections import deque


def tokenize(raw_text: str) -> List[str]:
    return raw_text.lower().split()


def count_words(tokens: List[str]) -> Dict[str, int]:
    word_count = {}
    for token in tokens:
        word_count[token] = word_count.get(token, 0) + 1
    return word_count


def calculate_stats(word_count: Dict[str, int]) -> Dict:
    return {
        'total_words': sum(word_count.values()),
        'unique_words': len(word_count),
        'most_common': max(word_count.items(), key=lambda x: x[1])
    }


class NodeStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class State:
    data: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict] = field(default_factory=list)
    
    def update(self, node_id: str, data: Any):
        self.data[node_id] = data
        self.history.append({
            'node': node_id,
            'timestamp': time.time(),
            'data': data
        })
    
    def get(self, node_id: str) -> Any:
        return self.data.get(node_id)


@dataclass
class Node:
    node_id: str
    process_fn: Callable
    required_inputs: List[str] = field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    conditions: List[Callable] = field(default_factory=list)
    
    def execute(self, state: State) -> Any:
        if not self._check_conditions(state):
            self.status = NodeStatus.SKIPPED
            return None

        self.status = NodeStatus.RUNNING
        inputs = {input_id: state.get(input_id) for input_id in self.required_inputs}
        
        try:
            result = self.process_fn(**inputs)
            state.update(self.node_id, result)
            self.status = NodeStatus.COMPLETED
            return result
        except Exception as e:
            self.status = NodeStatus.FAILED
            raise e
    
    def _check_conditions(self, state: State) -> bool:
        return all(condition(state) for condition in self.conditions)


class Graph:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: Dict[str, Set[str]] = {}
        self.state = State()
    
    def add_node(self, node: Node):
        self.nodes[node.node_id] = node
        self.edges[node.node_id] = set()
    
    def add_edge(self, from_node: str, to_node: str):
        if from_node not in self.nodes or to_node not in self.nodes:
            raise ValueError("Both nodes must exist in the graph")
        self.edges[from_node].add(to_node)
        if to_node not in self.nodes[to_node].required_inputs:
            self.nodes[to_node].required_inputs.append(from_node)
    
    def get_execution_order(self) -> List[str]:
        in_degree = {node: 0 for node in self.nodes}
        for node in self.nodes:
            for neighbor in self.edges[node]:
                in_degree[neighbor] += 1
        
        queue = deque([node for node, degree in in_degree.items() if degree == 0])
        execution_order = []
        
        while queue:
            node = queue.popleft()
            execution_order.append(node)
            
            for neighbor in self.edges[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        if len(execution_order) != len(self.nodes):
            raise ValueError("Graph contains a cycle")
        
        return execution_order
    
    def execute(self, initial_data: Dict[str, Any] = None):
        if initial_data:
            for key, value in initial_data.items():
                self.state.update(key, value)
        
        execution_order = self.get_execution_order()
        for node_id in execution_order:
            self.nodes[node_id].execute(self.state)
        
        return self.state


def main():
    # Example usage with complex graph
    graph = Graph()
    
    # Data processing nodes
    graph.add_node(Node(
        node_id="tokens",
        process_fn=tokenize,
        required_inputs=["raw_text"]
    ))
    
    graph.add_node(Node(
        node_id="word_count",
        process_fn=count_words,
        required_inputs=["tokens"]
    ))
    
    # Conditional node that only executes if word count > 10
    def check_word_count(state: State) -> bool:
        word_count = state.get("word_count")
        return sum(word_count.values()) > 10
    
    graph.add_node(Node(
        node_id="stats",
        process_fn=calculate_stats,
        required_inputs=["word_count"],
        conditions=[check_word_count]
    ))
    
    # Add edges
    graph.add_edge("tokens", "word_count")
    graph.add_edge("word_count", "stats")
    
    initial_data = {
        "raw_text": "The quick brown fox jumps over the lazy dog. The dog sleeps."
    }
    
    final_state = graph.execute(initial_data)
    print(json.dumps(final_state.data, indent=2))


if __name__ == "__main__":
    main()