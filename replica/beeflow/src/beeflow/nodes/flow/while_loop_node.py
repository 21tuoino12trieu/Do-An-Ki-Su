from typing import Callable, Dict, Any, List, Optional
from beeflow.nodes.base_node import BaseNode
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.configs import NodeType
from beeflow.states.workflow_state import WorkflowState
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.utils.context import _current_graph
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.tools.schema.param import Param
from beegen.utils.common import fake_chunk_from
from beegen.loggings import LOGGER
import asyncio
import traceback
from datetime import datetime



class WhileLoopNode(BaseNode):
    """A node that iterates over a condition"""
    
    type: NodeType = "while"
    
    def __init__(self, **kwargs):
        """Initialize a GraphNode with a name"""
        super().__init__(**kwargs)
        self._graph: GraphNode = GraphNode(name=BaseNode.INNER_PROCESS)
        self._graph.father = self
        self._token = None
    
    def __enter__(self):
        """Enter context manager mode - set ForLoopNode as current context"""
        self._token = _current_graph.set(self._graph)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager and delegate to inner graph"""
        _current_graph.reset(self._token)
        # Build the inner graph
                        
    def build(self):
        self._graph.build()

        self.input_schema = self._graph.input_schema
        self.output_schema = self._graph.output_schema
        
        for key in self.inputs:
            if key not in self.input_schema:
                self.input_schema.params[key] = Param(type="Any", required=True)

        self._post_init()
        
    def add_node(self, node: BaseNode) -> BaseNode:
        """Delegate node addition to inner graph"""
        return self._graph.add_node(node)
    
    def add_edge(self, source: str, target: str, type=None):
        """Delegate edge addition to inner graph"""
        return self._graph.add_edge(source, target, type)
    
    async def run(
        self,
        state: WorkflowState,
        context_id: Optional[str] = None
    ) -> Dict[str, Any]:
        
        parent_name = self.father.full_name if self.father else None
        state.record_execution(self.full_name, parent_name, context_id)
        
        request_id = state.request_id
        
        start_time = datetime.now()
        
        _outputs = {}
        
        try:
            _inputs = self.get_inputs(state, context_id=context_id)
            
            # Log truncated inputs for debugging
            LOGGER.info("request[%s]: %s, running NODE: %s: %s, inputs = %s", 
                request_id, context_id, self.name, str(self.type).upper(), str(_inputs)[:200])
            
            _continue = True
            step_count = 0
            
            step_inputs = _inputs
            
            while _continue:
                step_name = f"{context_id}_while[{step_count}]" if context_id else f"while[{step_count}]"
            
                state.inject_inputs(
                    node=self._graph.full_name,
                    inputs=step_inputs,
                    context_id=step_name
                )
                
                _outputs = await self._graph.run(state, context_id=step_name)
                
                step_inputs = self._graph.get_inputs(state, context_id=step_name)
                step_count += 1
                
                _continue = _outputs.get("continue_loop", False)
            
        except Exception as e:
            error_msg = traceback.format_exc()
            LOGGER.error(f"Error in node {self.name}: {str(e)}")
            LOGGER.error(error_msg)
            # Propagate the error but ensure metrics are recorded
            state[self.full_name, "error", context_id] = error_msg
            
            if self.stream:
                asyncio.create_task(STREAM_SERVICE.push(
                    request_id=request_id,
                    channel_name=self.identity(context_id),
                    data=fake_chunk_from(
                        content='Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại sau.',
                        model="error"
                    )
                ))
        finally:
            # Always record timing metrics            
            await asyncio.sleep(0.000001)
            end_time = datetime.now()
            state.set_by_index(self.metrics['start_time'], start_time, context_id=context_id)
            state.set_by_index(self.metrics['end_time'], end_time, context_id=context_id)
            self.store_result(state, _outputs, context_id=context_id)
            if self.stream:
                asyncio.create_task(STREAM_SERVICE.end(request_id, self.identity(context_id)))
            return _outputs
        
        
    

