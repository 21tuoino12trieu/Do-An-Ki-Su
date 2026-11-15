from typing import Dict, Any
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.nodes.base_node import BaseNode
from beeflow.states.workflow_state import WorkflowState
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.registry.resource_hub import ResourceHub
from beegen.loggings import LOGGER
import uuid
import asyncio

from beegen.utils.common import verify_data



class WorkflowEngine:

    def __init__(self,
                 name: str,
                 description: str = "",
                 langfuse: str = "beegen",
                 **kwargs):
        self.name = f"{name}:workflow"
        self.graph_name = name
        self._graph = GraphNode(
            name=self.graph_name,
            description=description,
            **kwargs
        )
        self.LANGFUSE_CLIENT = ResourceHub.self().langfuse(langfuse)
        self.indexer = None
        
    def __enter__(self):
        self._graph.__enter__()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._graph.__exit__(exc_type, exc_val, exc_tb)
        
    def compile(self):
        
        from beeflow.nodes import INPUT
        
        self._graph.build()
        
        for var in self._graph.get_input_variables():
            self._graph.inputs[var] = {INPUT: var}
                    
        self.indexer = WorkflowIndexer(name=self.name).add_node(self._graph).build()
                
    def _create_node_trace(self, parent, node: BaseNode, data: Dict[str, Any]):
        """
        Create appropriate Langfuse trace primitive based on node characteristics.
        
        This helper method determines whether to create a generation (for LLM nodes)
        or a span (for all other node types) based on the node's capabilities.
        
        Args:
            parent: The parent Langfuse trace object
            node: The workflow node to create a trace for
            data (Dict[str, Any]): Metadata and metrics for the trace
            
        Returns:
            Langfuse trace object (either generation or span)
            
        Note:
            - Nodes with contain_generation=True are LLM nodes that generate text
            - All other nodes (retrievers, code blocks, etc.) are treated as spans
        """
        if node.contain_generation:
            # LLM nodes: Create generation trace for token usage and model metrics
            return parent.generation(**data)
        else:
            # Non-LLM nodes: Create span trace for execution time and general metrics
            return parent.span(**data)
        
    async def run(self,
                  inputs: Dict[str, Any],
                  user_id: str = None,
                  session_id: str = None,
                  request_id: str = None) -> Dict[str, Any]:
        
        if not request_id: request_id = str(uuid.uuid4())
        state = WorkflowState(
            indexer=self.indexer,
            inputs=inputs,
            user_id=user_id or str(uuid.uuid4()),  # Generate UUID if not provided
            request_id=request_id,
            session_id=session_id or str(uuid.uuid4())
        )
        
        result = await self._graph.run(state)
        await STREAM_SERVICE.end_request(request_id)
        
        # Fire-and-forget background task
        asyncio.create_task(self.flush(state=state))
        
        return result
    
    async def flush(self, state: WorkflowState) -> None:
        """Flush traces to Langfuse asynchronously with error handling."""
        try:
            # Extract execution context for logging and tracing
            req_id = state.request_id
            user_id = state.user_id
            session_id = state.session_id
            
            LOGGER.info("Workflow: %s, Request ID: %s, Creating Langfuse trace hierarchy...", 
                    self.name, req_id)

            langfuse_objects = {}
            parent_object = self.LANGFUSE_CLIENT
            node_context_map = {}
            
            for execution in state.execution_order:
                node_name = execution["node"]
                parent_name = execution["parent"]
                context_id = execution["context_id"]
                node = state._indexer._nodes[node_name]
                trace_data = node.trace_data(state, context_id)
                
                verify_data(trace_data)

                if context_id:
                    node_id = f"{node_name}:{context_id}"
                else:
                    node_id = node_name

                # Save node's context so children can resolve parent later
                node_context_map[node_name] = context_id
                                        
                if parent_name is None:
                    # Root node: Create the main trace
                    trace_data.pop("name", None)
                    
                    langfuse_objects[node_id] = parent_object.trace(
                        id=req_id,
                        name=self.name,
                        user_id=user_id,
                        session_id=session_id,
                        **trace_data
                    )
                else:
                    parent_trace = None

                    # Priority 1: Try finding parent in the same context
                    if context_id:
                        parent_trace = langfuse_objects.get(f"{parent_name}:{context_id}")

                    # Priority 2: Fallback to map lookup if parent not found in current context
                    if parent_trace is None:
                        last_seen_parent_context = node_context_map.get(parent_name)

                        if last_seen_parent_context:
                            parent_id = f"{parent_name}:{last_seen_parent_context}"
                        else:
                            parent_id = parent_name        
                        parent_trace = langfuse_objects[parent_id]

                    if parent_trace:
                        langfuse_objects[node_id] = self._create_node_trace(
                            parent=parent_trace,
                            node=node,
                            data=trace_data
                        )
                    else:
                        LOGGER.warning(f"Parent {parent_name} not found for {node_id}")
            
            # non-blocking flush with timeout        
            await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(None, self.LANGFUSE_CLIENT.flush),
                timeout=60
            )

            LOGGER.info("Workflow: %s, Request ID: %s, Langfuse trace hierarchy created successfully", 
                    self.name, req_id)
            
        except Exception as e:
            import traceback
            LOGGER.error(
                "Workflow: %s, Request ID: %s, Failed to flush traces: %s\nTraceback:\n%s",
                self.name,
                state.request_id,
                str(e),
                traceback.format_exc()
            )
    
    
    # print(result)
    

