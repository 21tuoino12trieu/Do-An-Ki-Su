from typing import Dict, Any, List, Optional
from beeflow.nodes.base_node import BaseNode
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.configs import NodeType
from beeflow.states.workflow_state import WorkflowState
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.utils.context import _current_graph
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.tools.schema.param import ParamSet
from beegen.utils.common import fake_chunk_from
from beegen.loggings import LOGGER
import asyncio
import traceback
from datetime import datetime



class ForLoopNode(BaseNode):
    """A node that iterates over a collection and executes a inner graph flow for each item."""

    type: NodeType = "for"

    input_schema: ParamSet = (
        ParamSet.new()
            .var("batch_data: List", required=True)
            .build()
    )

    output_schema: ParamSet = (
        ParamSet.new()
            .var("batch_result: List", required=True)
            .build()
    )



    def __init__(self, max_concurrency: Optional[int] = 4, sleep_interval: Optional[float] = None, **kwargs):
        """Initialize a GraphNode with a name"""
        super().__init__(**kwargs)

        if max_concurrency is not None:
            if not isinstance(max_concurrency, int):
                raise TypeError(f"max_concurrency must be an integer, got {type(max_concurrency).__name__}")
            if max_concurrency <= 0:
                raise ValueError(f"max_concurrency must be positive, got {max_concurrency}")
            self.max_concurrency = max_concurrency
        else:
            self.max_concurrency = None  # Fallback to default (no concurrency limit)
            
        if sleep_interval is not None:
            if not isinstance(sleep_interval, float):
                raise TypeError(f"sleep_interval must be a float, got {type(sleep_interval).__name__}")
            if sleep_interval <= 0:
                raise ValueError(f"sleep_interval must be positive, got {sleep_interval}")
            self.sleep_interval = sleep_interval
        else:
            self.sleep_interval = None  # Fallback to default (no sleep between iterators)
        
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

    def add_node(self, node: BaseNode) -> BaseNode:
        """Delegate node addition to inner graph"""
        return self._graph.add_node(node)

    def add_edge(self, source: str, target: str, type=None):
        """Delegate edge addition to inner graph"""
        return self._graph.add_edge(source, target, type)

    def build(self):
        self._graph.build()
        self._post_init()

    async def _run_one(self, state: WorkflowState, loop_data: Dict[str, Any], task_id: str, sem: Optional[asyncio.Semaphore] = None):
        state.inject_inputs(
            node=self._graph.full_name,
            inputs=loop_data,
            context_id=task_id
        )
        if sem:
            async with sem:
                return await self._graph.run(state, task_id)
        else:
            return await self._graph.run(state, task_id)

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

            batch_data = _inputs.get("batch_data", [])

            # Log truncated inputs for debugging
            LOGGER.info("request[%s]: %s, running NODE: %s: %s, inputs = %s", 
                request_id, context_id, self.name, str(self.type).upper(), str(_inputs)[:200])

            sem = asyncio.Semaphore(self.max_concurrency) if self.max_concurrency else None

            if self.sleep_interval:
                batch_result = []
                for (i, loop_data) in enumerate(batch_data):
                    task_id = f"for[{i}]"

                    result = await self._run_one(state, loop_data, task_id)
                    
                    batch_result.append(result)
                    
                    await asyncio.sleep(self.sleep_interval)

                _outputs = {"batch_result": batch_result}
            else:
                active_tasks = []
                for (i, loop_data) in enumerate(batch_data):
                    task_id = f"{context_id}_for[{i}]" if context_id else f"for[{i}]"
                    active_tasks.append(self._run_one(state, loop_data, task_id, sem))

                _outputs = {"batch_result": await asyncio.gather(*active_tasks)}

            self.store_result(state, _outputs, context_id=context_id)

        except Exception as e:
            error_msg = traceback.format_exc()
            LOGGER.error(f"Error in node {self.full_name}: {str(e)}")
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
            if self.stream:
                asyncio.create_task(STREAM_SERVICE.end(request_id, self.identity(context_id)))
            return _outputs        




