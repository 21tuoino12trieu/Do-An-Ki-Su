from typing import Dict, Any, Optional
from datetime import datetime
import uuid
import asyncio
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.primitives.transform.lambda_node import LambdaNode
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.workflow import WorkflowEngine
from beegen.tools.schema.param import ParamSet
from beeflow.nodes.base_node import BaseNode
from beeflow.states import WorkflowState
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.loggings import LOGGER
from beegen.utils.common import fake_chunk_from

class AgentExecutorNode(BaseNode):
    """
    Node executor for dynamically selected workflows.
    Supports state isolation and streaming similar to ToolExecutorNode.
    """
    type: str = "agent-executor"

    input_schema: ParamSet = (
        ParamSet.new()
            .var("workflow_name: str", required=True)
            .var("workflow_inputs: Dict[str, Any]", required=True)
            .build()
    )

    output_schema: ParamSet = (
        ParamSet.new()
            .var("result: Any", required=True)
            .var("success: bool", required=True)
            .var("error: Optional[str] = None")
            .var("matched_workflow: str", required=True)
            .build()
    )

    def __init__(
        self,
        available_workflows: Dict[str, WorkflowEngine],
        stream: bool = True,
        **kwargs
    ):
        super().__init__(**kwargs)
        if not available_workflows:
            raise ValueError(f"Node {self.full_name}: available_workflows must not be empty!")
        self.available_workflows = available_workflows
        self.stream = stream
        for wf_name, wf_node in available_workflows.items():
            wf_node.father = self
            LOGGER.info(f"Registered workflow '{wf_name}' with AgentExecutor '{self.full_name}'")

    async def run(
        self,
        state: WorkflowState,
        context_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:

        request_id = state.request_id if state else str(uuid.uuid4())
        start_time = datetime.now()
        _outputs = {}
        _workflow_name = None

        try:
            _inputs = self.get_inputs(state, context_id=context_id)
            _workflow_name = _inputs.get("workflow_name")
            workflow_inputs = _inputs.get("workflow_inputs", {})

            if not _workflow_name:
                raise ValueError("workflow_name is required")
            if _workflow_name not in self.available_workflows:
                raise ValueError(f"Unknown workflow: {_workflow_name}")

            workflow = self.available_workflows[_workflow_name]

            # Record execution
            state.record_execution(self.full_name, self.father.full_name if self.father else None, context_id)

            LOGGER.info("request[%s]: running AgentExecutorNode %s with workflow '%s', inputs = %s", 
                        request_id, self.name, _workflow_name, str(workflow_inputs)[:200])

            # Inject inputs into workflow state
            # state.inject_inputs(node=workflow.name, inputs=workflow_inputs, context_id=context_id)

            _outputs = await workflow.run(inputs=workflow_inputs, request_id=request_id)

            LOGGER.info("request[%s]: AgentExecutorNode %s completed, outputs = %s", 
                        request_id, self.name, str(_outputs)[:200])

        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            LOGGER.error(f"AgentExecutorNode {self.name} failed: {e}\n{error_msg}")
            _outputs = {"error": error_msg, "success": False}

            if self.stream:
                asyncio.create_task(STREAM_SERVICE.push(
                    request_id=request_id,
                    channel_name=self.identity(context_id),
                    data=fake_chunk_from(content="Agent gặp lỗi, vui lòng thử lại.", model="error")
                ))

        finally:
            end_time = datetime.now()
            if state:
                state.set_by_index(self.metrics.get('start_time', None), start_time, context_id)
                state.set_by_index(self.metrics.get('end_time', None), end_time, context_id)

            # Store results
            self.store_result(
                state=state,
                result={
                    "result": _outputs,
                    "success": True if "error" not in _outputs else False,
                    "error": _outputs.get("error"),
                    "matched_workflow": _workflow_name
                },
                context_id=context_id
            )

            if self.stream:
                asyncio.create_task(STREAM_SERVICE.end(request_id, self.identity(context_id)))

        return _outputs
    
async def main():
    from beeflow.nodes.primitives.transform.code_node import CodeNode
    from beeflow.nodes.base_node import INPUT

    workflow_a = LambdaNode(name="workflow_a", code_fn=lambda x: {"result": x["msg"].upper()}, return_keys=["result: str"])
    workflow_b = LambdaNode(name="workflow_b", code_fn=lambda x: {"result": len(x["msg"])}, return_keys=["result: int"])

    available_workflows = {"workflow_a": workflow_a, "workflow_b": workflow_b}

    agent_node = AgentExecutorNode(
        name="agent_manager",
        available_workflows=available_workflows,
        inputs=INPUT
    )

    indexer = WorkflowIndexer(name="workflow01").add_node(workflow_a).add_node(workflow_b).add_node(agent_node).build()

    state = WorkflowState(
        indexer=indexer,
        inputs={
            "workflow_name": "workflow_a",
            "workflow_inputs": {"msg": "Hello World"}
        }
    )

    outputs = await agent_node.run(state)
    print(outputs)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
