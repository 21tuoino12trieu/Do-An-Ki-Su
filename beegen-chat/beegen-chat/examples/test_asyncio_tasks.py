import asyncio
from typing import Dict, List, Set, Callable, Any


class Node:
    def __init__(self, id: str, func: Callable):
        self.id = id
        self.func = func
        self.dependencies: Set[str] = set()
        self.dependents: Set[str] = set()
        
class Graph:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.state: Dict[str, Any] = {}
        
    def add_node(self, id: str, func: Callable) -> Node:
        node = Node(id, func)
        self.nodes[id] = node
        return node
        
    def add_edge(self, from_id: str, to_id: str):
        # Add dependency relationship
        self.nodes[to_id].dependencies.add(from_id)
        self.nodes[from_id].dependents.add(to_id)
        
    async def execute(self, start_id: str, end_id: str):
        # Find start node
        if start_id not in self.nodes:
            raise ValueError(f"Start node {start_id} not found")
        if end_id not in self.nodes:
            raise ValueError(f"End node {end_id} not found")
            
        # Create a future for the end node that we'll wait on
        end_future = asyncio.Future()
        
        # Track all running tasks
        running_tasks = set()
        
        async def execute_node(node_id: str):
            node = self.nodes[node_id]
            
            # Get input data from dependencies
            inputs = {dep_id: self.state.get(dep_id) for dep_id in node.dependencies}
            
            # Execute the node function
            result = await node.func(inputs)
            
            # Store result in state
            self.state[node_id] = result
            
            # Check if this is the end node
            if node_id == end_id:
                end_future.set_result(result)
                
            # Schedule dependent nodes that are ready
            for dep_id in node.dependents:
                dep_node = self.nodes[dep_id]
                # Check if all dependencies are in state (completed)
                if all(d in self.state for d in dep_node.dependencies):
                    # Create task for this node
                    task = asyncio.create_task(execute_node(dep_id))
                    running_tasks.add(task)
                    task.add_done_callback(running_tasks.discard)
        
        # Start the workflow by scheduling the start node
        start_task = asyncio.create_task(execute_node(start_id))
        running_tasks.add(start_task)
        start_task.add_done_callback(running_tasks.discard)
        
        # Wait for the end node to complete
        result = await end_future
        
        # Wait for any remaining tasks to finish (optional cleanup)
        if running_tasks:
            await asyncio.gather(*running_tasks)
            
        return result
    

async def main():
    import cProfile
    
    profiler = cProfile.Profile()
    
    profiler.enable()
    
    # Create a workflow graph
    graph = Graph()
    
    # Define some asynchronous node functions
    async def start_node(_):
        print("Starting workflow")
        await asyncio.sleep(1)  # Simulate work
        return "start data"
    
    async def process_a(inputs):
        data = inputs["start"]
        print(f"Process A using {data}")
        await asyncio.sleep(2)  # Simulate work
        return "result A"
    
    async def process_b(inputs):
        data = inputs["start"]
        print(f"Process B using {data}")
        await asyncio.sleep(3)  # Simulate work
        return "result B"
    
    async def combine(inputs):
        a_result = inputs["process_a"]
        b_result = inputs["process_b"]
        print(f"Combining {a_result} and {b_result}")
        await asyncio.sleep(1)  # Simulate work
        return f"{a_result} + {b_result}"
    
    # Add nodes
    graph.add_node("start", start_node)
    graph.add_node("process_a", process_a)
    graph.add_node("process_b", process_b)
    graph.add_node("combine", combine)
    
    # Add edges (dependencies)
    graph.add_edge("start", "process_a")
    graph.add_edge("start", "process_b")
    graph.add_edge("process_a", "combine")
    graph.add_edge("process_b", "combine")
    
    # Execute workflow from start to end
    result = await graph.execute("start", "combine")
    print(f"Final result: {result}")
    
    profiler.disable()
    
    profiler.print_stats()

# Run the example
asyncio.run(main())