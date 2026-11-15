from datetime import datetime
from beeflow.utils.streaming import STREAM_SERVICE
from beeflow.configs.edge_config import EdgeConfig, EdgeType
from beeflow.configs.node_config import NodeType
from beeflow.nodes.base_node import BaseNode, END
from beeflow.states.workflow_state import WorkflowState
from beeflow.utils.context import _current_graph
from beeflow.utils.bimap import BiMap
from beegen.tools.schema.param import ParamSet
from beegen.loggings.loggers import LOGGER
from typing import Dict, List, Literal, Any, Optional
from collections import defaultdict, deque
from beegen.utils.common import fake_chunk_from
import asyncio


"""Classify nodes based on connection patterns."""
NodeFlowType = Literal["MERGE", "FORK", "BLOOM", "BRANCH", "NORMAL", "OTHER"]


class GraphNode(BaseNode):
    """
    A node that contains and manages a subgraph of nodes.

    Allows organizing nodes into reusable subgraphs,
    supporting parallel execution of branches and correct flow control.

    Supports both initialization via config and context manager usage.
    """
    
    __slots__ = [
        '_token',
        '_nodes',               # Dict mapping node name -> node object
        'entries',              # List of entry node names
        'exits',                # List of exit node names
        'prevs',                # Dict mapping node -> list of predecessors
        'nexts',                # Dict mapping node -> list of successors
        'ready_count',          # Dict mapping node -> predecessor count
        'flowtype_map',         # Bi-map mapping flow types <-> set of node names
        '_edges',               # Store edges for context manager mode
        '_edges_lookup',        # Fast edge lookup
        '_is_building'          # Flag indicating graph is being built
    ]
    
    type: NodeType = "graph"
    
    def __init__(self, **kwargs):
        """Initialize GraphNode with a name."""
        super().__init__(**kwargs)
        self._token = None
        self._is_building = True
        self._nodes: Dict[str, BaseNode] = {}
        self._edges = []
        self._edges_lookup = {}
        self.entries = []
        self.exits = []
        self.prevs = defaultdict(list)
        self.nexts = defaultdict(list)
        # self.prevs_sets = {}
        self.flowtype_map = BiMap[str, NodeFlowType]()
    
    def __enter__(self):
        """Enter context manager mode."""
        self._token = _current_graph.set(self)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager mode and finalize building."""
        _current_graph.reset(self._token)
        
    # region ===== GRAPH STRUCTURE BUILDING METHODS =====

    def _setup_endpoints(self):
        """
        Initialize entry and exit nodes.

        Automatically detect entry nodes (nodes without predecessors) and
        exit nodes (nodes without successors) if not explicitly set.
        Then validate that the graph has at least one entry and one exit.
        """
        LOGGER.info(f"Graph: '{self.name}': khởi tạo endpoints...")
        
        # Auto-detect entries if not set
        if not self.entries:
            self.entries = [node for node in self._nodes if not self.prevs[node]]
        
        # Auto-detect exits if not set
        if not self.exits:
            self.exits = [node for node in self._nodes if not self.nexts[node]]
        
        # Validate at least one entry and exit
        if not self.entries:
            raise ValueError("Graph phải có ít nhất một entry node.")
        if not self.exits:
            raise ValueError("Graph phải có ít nhất một exit node.")
    
    def _setup_schema(self):
        """Initialize input/output schema."""
        from beeflow.nodes import INPUT, OUTPUT
        
        LOGGER.info(f"Graph '{self.name}': Tạo configs...")
        input_schema = ParamSet.new().build()
        output_schema = ParamSet.new().var("continue_loop: bool = False").var("content: Any = None").build()
        
        for _, node in self._nodes.items():
            # Graph Input Schema = collect variables referencing INPUT
            for var, ref in node.inputs.items():
                if isinstance(ref, dict) and len(ref) > 0:
                    ref_key, ref_var = next(iter(ref.items()))
                    if ref_key == INPUT:
                        input_schema[ref_var] = node.input_schema[var]
            
            # Graph Output Schema = collect variables referencing OUTPUT
            for var, ref in node.outputs.items():
                if isinstance(ref, dict) and len(ref) > 0:
                    ref_key, ref_var = next(iter(ref.items()))
                    if ref_key == OUTPUT:
                        output_schema[ref_var] = node.output_schema[var]
        
        self.input_schema = input_schema
        self.output_schema = output_schema
        
    def _build_flow_type(self):
        """
        Determine the flow type of each node based on connection patterns:
        [MERGE, FORK, BLOOM, BRANCH, NORMAL, OTHER]
        """
        LOGGER.info(f"Graph '{self.name}': xác định flow type của nodes...")
        self.flowtype_map = BiMap[str, NodeFlowType]()
        
        for name, node in self._nodes.items():
            prev_count = len(self.prevs[name])
            next_count = len(self.nexts[name])
            
            flow_type: NodeFlowType = "OTHER"
            
            # Determine node category
            if node.type == "branch":
                flow_type = "BRANCH"
                # Recalculate flow type for branch targets if they have simple connections
                for target in node.candidates:
                    if target in self._nodes and len(self.nexts[target]) == 1:
                        self.flowtype_map[target] = "NORMAL"
            
            elif prev_count > 1 and next_count > 1:
                flow_type = "BLOOM"
            elif prev_count > 1 and next_count == 1:
                flow_type = "MERGE"
            elif prev_count == 1 and next_count > 1:
                flow_type = "FORK"
            elif prev_count == 1 and next_count == 1:
                flow_type = "NORMAL"
                
            # Store node flow type
            self.flowtype_map[name] = flow_type
            
    def build(self):
        """
        Build the graph by building all child nodes first,
        then finalize this graph.
        """
        # First, build child graph nodes still in building state
        for node in self._nodes.values():
            if hasattr(node, 'build'):
                node.build()
                
        # Then build the final graph
        self._setup_schema()
        self._build_flow_type()
        self._setup_endpoints()
        
        # OPTIMIZATION: Precompute ready_count for faster runtime lookup
        # Set intersection O(min(m,n)) vs list comprehension O(m*n)
        self.ready_count = {
            name: len(preds) for name, preds in self.prevs.items()
        }
        
        self._post_init()
        self._is_building = False
        
    # endregion ===== GRAPH STRUCTURE BUILDING METHODS =====
    
    # region ===== UTILITIES =====
    
    @staticmethod
    def get_current_graph() -> Optional['GraphNode']:
        """Get the current graph from context."""
        try:
            return _current_graph.get()
        except LookupError:
            return None
    
    def add_node(self, node: BaseNode) -> BaseNode:
        """Add a node to the graph."""
        from beeflow.nodes import START, END
        
        if not self._is_building:
            raise RuntimeError("Cannot add nodes after the graph is built!")
        
        # Skip adding dummy START and END nodes to the actual graph
        if node in [START, END]:
            return node
        
        self._nodes[node.name] = node
        
        # Auto-detect entries and exits based on node properties
        if hasattr(node, 'start') and node.start:
            if node.name not in self.entries:
                self.entries.append(node.name)
        
        if hasattr(node, 'end') and node.end:
            if node.name not in self.exits:
                self.exits.append(node.name)
                
        return node
    
    def add_edge(self, source: str, target: str, type: EdgeType = "normal"):
        """
        Add an edge between two nodes: source -> target.

        Special handling for START and END dummy nodes:
        - START >> node: mark node as start=True and add to entries
        - node >> END: mark node as end=True and add to exits
        """
        from beeflow.nodes import START, END, INPUT, OUTPUT, CONTINUE
        
        if not self._is_building:
            raise RuntimeError("Cannot add edges after the graph is built!")
        
        # Handle START dummy node
        if source == START.name:
            if target not in self._nodes:
                raise ValueError(f"Target node '{target}' không tìm thấy")
            
            # Đánh dấu target là start node
            target_node = self._nodes[target]
            target_node.start = True
            
            # Thêm vào entries nếu chưa có
            if target not in self.entries:
                self.entries.append(target)
            
            return  # Không tạo edge thực sự tới START
        
        # Handle END dummy node
        if target == END.name:
            if source not in self._nodes:
                raise ValueError(f"Source node '{source}' không tìm thấy")
            
            # Đánh dấu source là end node
            source_node = self._nodes[source]
            source_node.end = True
            
            # Thêm vào exits nếu chưa có
            if source not in self.exits:
                self.exits.append(source)
            
            return  # Không tạo edge thực sự tới END
        
        if target == CONTINUE.name:
            # Đánh dấu source là continue-loop
            source_node = self._nodes[source]
            source_node.continue_loop = True
            return
        
        if target in [INPUT.name, OUTPUT.name]:
            return
        
        # Handle normal edge
        if source not in self._nodes:
            raise ValueError(f"Source node '{source}' không tìm thấy")
        if target not in self._nodes:
            raise ValueError(f"Target node '{target}' không tìm thấy")
        
        if not self._nodes[source].enabled:
            self._nodes[target].enabled = False
        
        new_edge = EdgeConfig(from_node=source, to_node=target, type=type)
        if (source, target) not in self._edges_lookup:
            self._edges.append(new_edge)
            self._edges_lookup[source, target] = new_edge
            self.nexts[source].append(target)
            self.prevs[target].append(source)

    def show(self, indent=0):
        """Display graph structure (debug)."""
        prefix = "  " * indent
        print(f"{prefix}Graph: {self.name}")
        print(f"{prefix}Nodes:", list(self._nodes.keys()))
        print(f"{prefix}Edges:")
        for edge in self._edges:
            print(f"{prefix}  {edge.from_node} -> {edge.to_node}: {edge.type}")
        
        # Display nested graphs
        for node in self._nodes.values():
            if isinstance(node, GraphNode):
                node.show(indent + 1)
                
    # endregion ===== UTILITIES =====
    
    # region ===== WORKFLOW EXECUTION METHODS =====
    
    async def run(
        self,
        state: WorkflowState,
        context_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute the graph by running nodes asynchronously respecting dependency order.

        Algorithm: Synchronizing Merge with Dead Path Elimination (DPE)
        ---------------------------------------------------------------
        This engine ensures that a node only runs when ALL its predecessors have 
        finished (Synchronizing Merge), regardless of whether those predecessors 
        were executed or skipped (Dead Path).

        Execution Logic:
        1. Initialization:
           - Set `ready_count` for each node = number of incoming edges.
           - Entry nodes are marked as `activated` (receive "True Token") and scheduled.

        2. Node Completion (Node N finishes):
           - Determine Successors:
             * If N is a Branch: Only the specific target gets a "True Token" 
               (added to `activated_nodes`).
             * If N is Standard: All successors get a "True Token".
           - Signal Propagation:
             * Decrement `ready_count` for ALL successors (both active and inactive paths).
             * This ensures downstream nodes know a path has completed/skipped.

        3. Node Evaluation (Check successor S):
           - If `ready_count[S] == 0`:
             a. Case RUN: S is in `activated_nodes` -> Schedule S to run.
             b. Case SKIP (DPE): S is NOT in `activated_nodes` -> S is on a Dead Path.
                Add S to `deactivation_queue` to propagate the "False Token".

        4. Dead Path Propagation Loop:
           - Process `deactivation_queue` to recursively decrement `ready_count` 
             for children of skipped nodes, ensuring the entire dead branch is skipped 
             correctly until a merge point is reached or the path ends.

        Args:
            state: WorkflowState containing workflow context and variables
            context_id: Identifier to distinguish different loops/contexts
        
        Returns:
            Dict of graph outputs
        """
        
        parent_name = self.father.full_name if self.father else None
        state.record_execution(self.full_name, parent_name, context_id)
        
        request_id = state.request_id
        start_time = datetime.now()
        _outputs = {}
        
        try:
            _inputs = self.get_inputs(state, context_id=context_id)
            
            # Log inputs (truncated) for debugging
            LOGGER.info("request[%s]: %s, running NODE: %s: %s, inputs = %s", 
                request_id, context_id, self.name, str(self.type).upper(), str(_inputs)[:200])
            
            # Ensure the graph has been finalized
            if self._is_building:
                raise ValueError(
                    f"Graph {self.name} has not been built yet. "
                    "You must call graph.build() before execution!!"
                )

            # Track currently running nodes
            active_tasks: Dict[str, asyncio.Task] = {}
            
            # Track how many predecessors each node is still waiting for
            ready_count: Dict[str, int] = self.ready_count.copy()
            
            # Set to store nodes that have ever received a "true token"
            activated_nodes: set[str] = set()

            # Queue to propagate "false tokens"
            deactivation_nodes = deque()

            # Helper function to check and schedule a node to run
            def schedule_if_ready(node_to_check: str):
                # Check dependency count
                if ready_count.get(node_to_check, 0) == 0:
                    # Case 1: Ready AND Activated -> RUN
                    if node_to_check in activated_nodes:
                        if node_to_check not in active_tasks:
                            new_task = asyncio.create_task(
                                name=node_to_check,
                                coro=self._nodes[node_to_check].run(state, context_id)
                            )
                            active_tasks[node_to_check] = new_task
                    
                    # Case 2: Ready BUT Not Activated -> Dead Path (propagate False token)
                    else:
                        deactivation_nodes.append(node_to_check)
            
            # Start from entry nodes
            for entry in self.entries:
                # Entry nodes are activated by default
                task = asyncio.create_task(
                    name=entry,
                    coro=self._nodes[entry].run(state, context_id)
                )
                active_tasks[entry] = task
            
            # Continue until all tasks are completed
            while active_tasks:
                # Wait for any task to complete
                done_tasks, _ = await asyncio.wait(
                    active_tasks.values(),
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Process each completed task
                for task in done_tasks:
                    node_name = task.get_name()
                    node  = self._nodes[node_name]
                    active_tasks.pop(node_name)
                    
                    nodes_to_activate_now = []
                    # Determine successor nodes and who gets the "True Token"
                    next_nodes = self.nexts[node_name]
                    if node.type == "branch":
                        # Branch node: only activate the selected target
                        branch_target = node.get_target(state, context_id)
                        if branch_target in self._nodes:
                            nodes_to_activate_now = [branch_target]
                        elif branch_target == END.name:
                            state[self.full_name, "continue_loop", context_id] = False
                    else:
                        nodes_to_activate_now = next_nodes
                    activated_nodes.update(nodes_to_activate_now)

                    # Process ALL successors to update ready_count
                    # This step sends both "true tokens" and "false tokens"
                    for next_node in next_nodes:
                        if next_node not in self._nodes: continue
                                                
                        # Decrement ready_count for every successor, regardless of whether it is activated.
                        # This is the key to handling merge nodes correctly.
                        ready_count[next_node] -= 1
                        # Immediately check if the node that just received a signal can run
                        schedule_if_ready(next_node)

                    # Iteratively propagate "false tokens"
                    while deactivation_nodes:
                        deactivation_node = deactivation_nodes.popleft()
                        for next_node_deactivate in self.nexts.get(deactivation_node, []):
                            if next_node_deactivate not in self._nodes: continue
                            ready_count[next_node_deactivate] -= 1
                            schedule_if_ready(next_node_deactivate)
                        
                    # Handle continue_loop flag
                    if node.continue_loop:
                        state[self.full_name, "continue_loop", context_id] = True

            _outputs = self.get_outputs(state, context_id=context_id)

            new_content = _outputs.get("content")
            current_content = _inputs.get("content") # Lấy content cũ từ đầu vào của graph hiện tại
            
            if new_content is not None:
                if current_content is not None:
                    # Tự động nhận diện kiểu dữ liệu để nối cho phù hợp
                    if isinstance(current_content, list):
                        if isinstance(new_content, list):
                            _outputs["content"] = current_content + new_content
                        else:
                            _outputs["content"] = current_content + [new_content]
                    elif isinstance(current_content, str):
                        # Nối chuỗi, có thể tùy chỉnh thêm khoảng trắng hoặc xuống dòng ở đây
                        _outputs["content"] = current_content + "\n" + str(new_content)
                    else:
                        # Fallback ép kiểu
                        _outputs["content"] = str(current_content) + "\n" + str(new_content)
                else:
                    _outputs["content"] = new_content
            else:
                # Nếu chu kỳ graph này không sinh ra content mới, ta giữ nguyên content cũ để pass đi tiếp
                if current_content is not None:
                    _outputs["content"] = current_content

            LOGGER.info(
                f"request: {request_id}, complete NODE: {self.name}: "
                f"{str(self.type).upper()}, outputs = {str(_outputs)[:200]}"
            )
            
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            LOGGER.error(f"Error in node {self.name}: {str(e)}")
            LOGGER.error(error_msg)
            
            # Save error to state
            state[self.full_name, "error", context_id] = error_msg

        finally:            
            await asyncio.sleep(0.000001)
            end_time = datetime.now()
            state.set_by_index(self.metrics['start_time'], start_time, context_id=context_id)
            state.set_by_index(self.metrics['end_time'], end_time, context_id=context_id)
            return _outputs
        
    # endregion ===== WORKFLOW EXECUTION METHODS =====


# region ===== TESTS =====

    
    





# endregion ===== TESTS =====