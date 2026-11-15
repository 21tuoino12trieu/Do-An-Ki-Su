from beeflow.nodes.base_node import BaseNode
from beeflow.configs import NodeConfig, NodeType
from beegen.tools.schema.param import ParamSet
from beegen.tools.services.callable_analyzer import analyze_callable
from typing import Dict, Callable, Any, Union, Optional, List
import asyncio
import ast
import inspect
from beegen.utils.common import ensure_async
    
    
class CodeNodeConfig(NodeConfig):
    """Configuration for (Python) Code execution node in the workflow."""
        
    code_fn: Callable


class CodeNode(BaseNode):
    """
    A node that executes custom Python code within the graph flow.
    
    This node allows for running arbitrary code functions as part of the flow,
    supporting both synchronous and asynchronous functions. The code can be provided
    as a function object, lambda function, or a string containing the function definition.
    """
    type: NodeType = "code"
    
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
        self._handle_regular_function(return_keys)
        
    def _handle_regular_function(self, output_vars: List[str]):
        """Handle regular function configuration (existing logic)."""
        # Extract function information
        function_info = analyze_callable(self.code_fn)
        self.source = function_info.source
        # Only override description if none was provided by user
        if not self.description:  # Only set if description is empty/None
            self.description = function_info.description
        
        if not self.name:
            self.name = function_info.name
        
        # Build schemas
        self.input_schema = function_info.input_schema
        self.output_schema = self._build_output_schema(
            function_info.output_schema, 
            output_vars
        )
    
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
                output_schema = output_schema.var(f"{name.strip()}: {type_hint.strip()}", required=True)
            return output_schema.build()
        
    def specific_metadata(self) -> Dict[str, Any]:
        """Return subclass-specific metadata dictionary."""
        return {
            "code_fn": self.source,
            "function_name": self.code_fn.__name__
        }


# Test the fixed CodeNode
    
    # print(regular_node.get_openai_function_schema())
    # print(regular_node.output_schema)

