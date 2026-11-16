import networkx as nx
from typing import Dict, Set, List, Any, Optional, Callable
import redis
import threading
import json
import time


# Example usage
def create_example_graph():
    G = nx.DiGraph()
    
    # Add edges for the first path
    path1 = ['code0', 'prompt0', 'rewrite_query', 'parser0', 'embedding0', 
             'milvus0', 'code1', 'code2', 'mongo0', 'code3', 'prompt1', 'final_response']
    for i in range(len(path1) - 1):
        G.add_edge(path1[i], path1[i+1])
    
    # Add edges for the second path
    path2 = ['code0', 'log_analytics', 'prompt1', 'final_response']
    for i in range(len(path2) - 1):
        G.add_edge(path2[i], path2[i+1])
        
    # Add edges for the second path
    path3 = ['parser0', 'check_log', 'going_somewhere', 'mongo0']
    for i in range(len(path3) - 1):
        G.add_edge(path3[i], path3[i+1])
        
    # Add edges for the second path
    path4 = ['rewrite_query', 'check_sanity', 'retry_rewrite', 'code3', 'prompt1', 'final_response']
    for i in range(len(path4) - 1):
        G.add_edge(path4[i], path4[i+1])

    return G


def ready_to_process(G: nx.DiGraph, node: str, processed: Set[str]):
    for prev in G.predecessors(node):
        if prev not in processed:
            return False
    return True


def process_graph(G: nx.DiGraph, start: str, end: str):
    processed = set()
    wait_nodes = [start]
    
    while wait_nodes:
        new_wait_nodes = []
        for current in wait_nodes:
            if current == end:
                print("THE END!")
                return
            
            processed.add(current)
            
            G.nodes[current]['count'] += 1
            
            if G.nodes[current]['count'] > 3:
                print("dont found end node!")
                return
            
            for next in G.successors(current):
                print(f"\t{current} -> {next} ({ready_to_process(G, next, processed)})")
                if ready_to_process(G, next, processed):
                    new_wait_nodes.append(next)
                    
        wait_nodes = new_wait_nodes


# Test the implementation
if __name__ == "__main__":
    G = create_example_graph()
    
    # Initialize a count attribute for each node
    nx.set_node_attributes(G, 0, 'count')
    
    # topo_order = list(nx.topological_sort(G))
    # paths = list(nx.all_simple_paths(G, "prompt0", "final_response"))
    # print(list(topo_order))
    # for path in paths:
    #     print(path)     

    # for n in topo_order:
    #     print(n, list(G.predecessors(n)))
    
    process_graph(G, "code0", "final_response")