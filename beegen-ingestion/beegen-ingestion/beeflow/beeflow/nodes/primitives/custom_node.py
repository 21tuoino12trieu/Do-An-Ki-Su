from beeflow.nodes.base_node import BaseNode
from beeflow.states.workflow_state import WorkflowState
from beeflow.states.state_manager import StateRegistry
from beeflow.configs import NodeConfig, NodeType
from beegen.llms.response import LLMGenerator
from beegen.tools.schema.param import ParamSet
from beegen.loggings.loggers import LOGGER
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from typing import List, Optional, Callable, AsyncGenerator
from datetime import datetime
import asyncio


class CustomNode(BaseNode):
    """Flexible custom node - just attach any function as core logic."""
    
    __slots__ = []
    
    def __init__(
        self,
        name: Optional[str] = None,
        core: Optional[Callable] = None,
        input_schema: Optional[List[str]] = None,
        output_schema: Optional[List[str]] = [],
        **kwargs
    ):
        """Initialize CustomNode with any function as core."""
        # Prepare config
        config = self._prepare_config(
            name=name, 
            core=core, 
            input_schema=input_schema, 
            output_schema=output_schema, 
            **kwargs
        )
        
        # Initialize base node
        super().__init__(config=config)
        
        # Set core function
        if core:
            self.core = core
    
    def _prepare_config(self, 
                        name: str, 
                        core: Callable, 
                        input_schema: List[str], 
                        output_schema: List[str], 
                        **kwargs):
        """Prepare NodeConfig with converted schemas."""
        # Auto-generate name if needed
        if name is None and core:
            kwargs['name'] = core.__name__
        elif name is not None:
            kwargs['name'] = name
        
        # Extract schema lists
        input_list = input_schema or kwargs.pop('input_schema', [])
        output_list = output_schema or kwargs.pop('output_schema', [])
        
        # Create config and add converted schemas
        config = NodeConfig(**kwargs)
        config.input_schema = self._build_param_set(input_list, "input_schema")
        config.output_schema = self._build_param_set(output_list, "output_schema")
        
        return config
    
    def _build_param_set(self, schema_list, schema_name):
        """Convert List[str] to ParamSet."""
        # if not schema_list:
        #     raise TypeError(f"{schema_name} has not been provided")
        
        param_set = ParamSet.new()
        for r in schema_list:
            if ":" not in r:
                r += ": Any"
            name, type_hint = r.split(":", 1)
            param_set = param_set.var(f"{name.strip()}: {type_hint.strip()}")
        
        return param_set.build()

    async def run(
        self,
        state: WorkflowState
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Run the node with the given state"""
        request_id = state.request_id
        
        start_time = datetime.now()
        
        LOGGER.info("request: %s, running NODE: %s: %s", request_id, self.name, str(self.type).upper())  

        try:
            if self.core:
                if asyncio.iscoroutinefunction(self.core):
                    await self.core(state)
                else:
                    self.core(state)
                
            if self.stream:
                yield LLMGenerator.make_chunk(
                    chat_id=state.request_id,
                    content=self.config.status_message,
                    model=self.name
                )
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            LOGGER.error("Error in node %s: %s", self.name, str(e))
            LOGGER.error(error_msg)
            # Propagate the error but ensure metrics are recorded
            state[self.name, "error"] = error_msg
        finally:
            # Always record timing metrics
            parent_name = self.father.full_name if self.father else None
            await asyncio.sleep(0.000001)
            end_time = datetime.now()
            state.set_by_index(self.metrics['start_time'], start_time)
            state.set_by_index(self.metrics['end_time'], end_time)


def calculate_price(state) -> None:
    """Old style: function(state) -> None (stores in state)"""
    # get products from state
    products = state["workflow01", "products"]
    
    # Running the main flow
    total_price = sum(product.get('price', 0) for product in products)
    avg_price = total_price / len(products) if products else 0
    
    # Store the result to state
    state["workflow01", "total"] = total_price
    state["workflow01", "avg"] = avg_price
    

async def main():    
    custom_node = CustomNode(
        core=calculate_price
    )
    
    result = await custom_node.simulate(inputs={
        "products": [
            {"name": "xxx", "price": 320.5},
            {"name": "yyy", "price": 105.7},
            {"name": "zzz", "price": 220.3}
        ],
        "total": 100,
        "avg": 0
    })


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())