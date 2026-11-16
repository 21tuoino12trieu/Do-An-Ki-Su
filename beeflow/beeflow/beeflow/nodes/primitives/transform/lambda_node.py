from beeflow.nodes.base_node import BaseNode
from beeflow.configs import NodeConfig, NodeType
from beegen.tools.schema.param import ParamSet
from beegen.tools.services.callable_analyzer import analyze_callable
from typing import Dict, Callable, Any, Union, Optional, List
import asyncio
import ast
import inspect
from beegen.utils.common import ensure_async
import re
import textwrap


def get_lambda_source(lambda_func):
    """Extract source code of a lambda function."""
    try:
        source = inspect.getsource(lambda_func)
        return textwrap.dedent(source)
    except:
        return str(lambda_func)  # Fallback
    
    
    
class LambdaNodeConfig(NodeConfig):
    """Configuration for (Python) Code execution node in the workflow."""
        
    code_fn: Callable


class LambdaNode(BaseNode):
    """
    A node that executes custom Python code within the graph flow.
    
    This node allows for running arbitrary code functions as part of the flow,
    supporting both synchronous and asynchronous functions. The code can be provided
    as a function object, lambda function, or a string containing the function definition.
    """
    type: NodeType = "lambda"
    
    __slots__ = ["code_fn", "original_function", "source"]  # Store both processed and original
    
    def __init__(
        self,
        code_fn: Optional[Union[str, Callable]] = None,
        return_keys: Optional[List[str]] = None,
        **kwargs
    ):
        """Initialize CodeNode from either config or kwargs.
        
        Args:
            config: Optional CodeNodeConfig object. If provided, other args are ignored.
            name: Node name (optional, can be inferred from function)
            code_fn: Python function, lambda, or string containing function definition
            output_schema: List of output variable definitions (required for lambdas)
            **kwargs: Additional keyword arguments for NodeConfig
        """
        # Merge explicit params with kwargs        
        super().__init__(**kwargs)
        
        self.code_fn = code_fn
        # Ensure core is always async
        self.core = ensure_async(self.code_fn)
        self.source = ""
        if self._is_lambda_function(self.code_fn):
            self._handle_lambda_function(return_keys)
        else:
            raise ValueError(f"{self.code_fn} is not a lambda function")
        
    def _is_lambda_function(self, func) -> bool:
        """Check if the function is a lambda function."""
        if not callable(func):
            return False
        return getattr(func, '__name__', None) == '<lambda>'
        
    def _handle_lambda_function(self, output_vars: List[str]):
        """Handle lambda function configuration."""
        self.source = get_lambda_source(self.code_fn)

        # For lambdas, we can't extract source easily, so use the function directly
        # but we need the user to provide output_schema
        if not output_vars:
            raise TypeError(f"Lambda functions require explicit output_schema")
        
        # Set basic properties for lambda
        code_function_name = f"lambda_{id(self.code_fn)}"
        # Only override description if none was provided by user
        if not self.description:  # Only set if description is empty/None
            self.description = f"Lambda function: {code_function_name}"
        
        if not self.name:
            self.name = code_function_name
        
        # Try to get lambda signature for input schema
        try:
            sig = inspect.signature(self.code_fn)
            input_schema = ParamSet.new()
            
            for param_name, param in sig.parameters.items():
                # Try to infer type from annotation, default to Any
                param_type = "Any"
                if param.annotation != inspect.Parameter.empty:
                    param_type = getattr(param.annotation, '__name__', str(param.annotation))
                
                # Check if parameter has default value
                if param.default != inspect.Parameter.empty:
                    input_schema = input_schema.var(f"{param_name}: {param_type} = {repr(param.default)}")
                else:
                    input_schema = input_schema.var(f"{param_name}: {param_type}", required=True)
            
            self.input_schema = input_schema.build()
            
        except Exception:
            # If we can't analyze the lambda signature, create empty input schema
            # User should provide inputs explicitly
            self.input_schema = ParamSet.new().build()
        
        # Build output schema from provided variables
        self.output_schema = self._build_output_schema(None, output_vars)
        
    def _build_output_schema(self, 
                             docstring_schema: ParamSet, 
                             provided_schema: List[str]):
        """Build output schema from docstring or provided list."""
        if docstring_schema:
            return docstring_schema
        elif provided_schema:
            output_schema = ParamSet.new()
            for var_def in provided_schema:
                if ":" not in var_def:
                    var_def += ": Any"
                name, type_hint = var_def.split(":", 1)
                output_schema = output_schema.var(f"{name.strip()}: {type_hint.strip()}")
            return output_schema.build()
        else:
            raise TypeError(f"{self.name}'s output_schema has not been provided")
        
    def specific_metadata(self) -> Dict[str, Any]:
        """Return subclass-specific metadata dictionary."""
        return {
            "code_fn": self.source,
            "is_lambda": self.config.is_lambda,
            "function_name": self.config.code_function_name
        }


# Test the fixed CodeNode
async def main():
    from beeflow.states.workflow_indexer import WorkflowIndexer
    from beeflow.states.workflow_state import WorkflowState
    from beeflow.nodes.base_node import INPUT, OUTPUT
    
    print("=== Testing Lambda Function ===")
    
    # Test with lambda (this should now work)
    lambda_node = LambdaNode(
        name="lambda_test",
        code_fn=lambda expression: {"result": eval(expression)},
        return_keys=["result: float"],
        inputs=INPUT,
        outputs=OUTPUT
    )
    
    indexer = WorkflowIndexer(name="workflow01")\
        .add_node(lambda_node).build()
    
    state = WorkflowState(
        indexer=indexer, 
        inputs={"expression": "25 * 47 + 139"}
    )
    async for chunk in lambda_node.run(state=state):
        pass
    
    print(lambda_node.get_outputs(state))
        
    print("\n=== Testing Complex Lambda ===")
    
    # Test more complex lambda
    complex_lambda = LambdaNode(
        name="complex_lambda", 
        code_fn=lambda query, docs: {
            "cache_qa": docs[0]["content"] + ": " + query if docs else None,
            "doc_count": len(docs)
        },
        return_keys=["cache_qa: str", "doc_count: int"],
        inputs=INPUT,
        outputs=OUTPUT
    )
    
    indexer = WorkflowIndexer(name="workflow01")\
        .add_node(complex_lambda).build()
        
    state = WorkflowState(
        indexer=indexer,
        inputs={
            "query": "test query",
            "docs": [{"content": "This is cached QA content"}]
        }
    )
    
    async for chunk in complex_lambda.run(state=state):
        pass
    
    print(complex_lambda.get_outputs(state))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())