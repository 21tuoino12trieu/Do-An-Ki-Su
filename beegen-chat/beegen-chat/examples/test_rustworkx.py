import time
import random
import networkx as nx
import rustworkx as rx

def create_graphs_with_path(path_length=100):
    """
    Create identical graphs for both NetworkX and rustworkx with 
    a guaranteed path from node 0 to node path_length-1
    """
    # Create the path nodes 0 → 1 → 2 → ... → path_length-1
    edges = [(i, i+1) for i in range(path_length-1)]
    
    # Create NetworkX graph
    nx_graph = nx.DiGraph()
    nx_graph.add_nodes_from(range(path_length))
    nx_graph.add_edges_from(edges)
    
    # Create rustworkx graph
    rx_graph = rx.PyDiGraph()
    for i in range(path_length):
        rx_graph.add_node(i)
    for i, j in edges:
        rx_graph.add_edge(i, j, None)
    
    # The path is simply [0, 1, 2, ..., path_length-1]
    path = list(range(path_length))
    
    return nx_graph, rx_graph, path

def traverse_path_networkx(graph, path):
    """Traverse a path in NetworkX and verify edges exist"""
    # This simulates following a known path through the graph
    for i in range(len(path)-1):
        # Check if edge exists and get any edge data
        if not graph.has_edge(path[i], path[i+1]):
            return False
    return True

def traverse_path_rustworkx(graph, path):
    """Traverse a path in rustworkx and verify edges exist"""
    # This simulates following a known path through the graph
    for i in range(len(path)-1):
        # Check if edge exists 
        # We have to manually search because rustworkx doesn't have has_edge
        found = False
        for edge in graph.out_edges(path[i]):
            if edge[1] == path[i+1]:
                found = True
                break
        if not found:
            return False
    return True

def benchmark_path_traversal(path_lengths=[100, 1000, 10000], num_trials=5):
    """Benchmark traversing a known path for both libraries"""
    
    for path_length in path_lengths:
        print(f"\nBenchmarking path traversal with path length: {path_length}")
        print("=" * 60)
        
        # Results storage
        nx_times = []
        rx_times = []
        
        for trial in range(num_trials):
            print(f"Trial {trial+1}/{num_trials}")
            
            # Create graphs with the guaranteed path
            nx_graph, rx_graph, path = create_graphs_with_path(path_length)
            
            # Do a warm-up run
            _ = traverse_path_networkx(nx_graph, path)
            _ = traverse_path_rustworkx(rx_graph, path)
            
            # Number of iterations for accurate timing
            iterations = 1000 if path_length <= 1000 else 100
            
            # Benchmark NetworkX path traversal
            start_time = time.time()
            for _ in range(iterations):
                success = traverse_path_networkx(nx_graph, path)
            nx_time = (time.time() - start_time) / iterations
            nx_times.append(nx_time)
            
            print(f"  NetworkX traversal: {nx_time:.8f} seconds (avg of {iterations} runs)")
            
            # Benchmark rustworkx path traversal
            start_time = time.time()
            for _ in range(iterations):
                success = traverse_path_rustworkx(rx_graph, path)
            rx_time = (time.time() - start_time) / iterations
            rx_times.append(rx_time)
            
            print(f"  rustworkx traversal: {rx_time:.8f} seconds (avg of {iterations} runs)")
            
            # Calculate speed ratio
            faster_lib = "rustworkx" if rx_time < nx_time else "NetworkX"
            ratio = nx_time/rx_time if rx_time < nx_time else rx_time/nx_time
            print(f"  {faster_lib} is {ratio:.2f}x faster for path length {path_length}")
        
        # Calculate average times
        avg_nx = sum(nx_times) / len(nx_times)
        avg_rx = sum(rx_times) / len(rx_times)
        
        print(f"\nAverage results for path length {path_length}:")
        print(f"  NetworkX traversal: {avg_nx:.8f} seconds")
        print(f"  rustworkx traversal: {avg_rx:.8f} seconds")
        faster_lib = "rustworkx" if avg_rx < avg_nx else "NetworkX"
        ratio = avg_nx/avg_rx if avg_rx < avg_nx else avg_rx/avg_nx
        print(f"  {faster_lib} is {ratio:.2f}x faster on average")


if __name__ == "__main__":
    # Run benchmark with different path lengths
    benchmark_path_traversal(path_lengths=[100, 1000, 10000], num_trials=3)