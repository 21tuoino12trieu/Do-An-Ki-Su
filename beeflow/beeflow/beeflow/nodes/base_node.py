from abc import ABC
from typing import Dict, Any, AsyncGenerator, Callable, Optional, List
from datetime import datetime
from beeflow.utils.streaming import STREAM_SERVICE
from beeflow.configs.node_config import NodeType
from beegen.tools.exporters.schema_exporter import OpenAISchemaExporter
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from beegen.tools.schema.param import ParamSet
from ..states.workflow_state import WorkflowState
from beegen.llms.response import LLMGenerator
from beegen.utils.common import fake_chunk_from
from beegen.loggings import LOGGER
from beegen.utils.common import unique_name
from beeflow.utils.context import get_current, _current_graph
import traceback
import asyncio
import uuid
import time


class BaseNode(ABC):
    """Base class for all nodes - extended to support Airflow-style operators."""
    
    TYPE_MAP = {"int": int, "float": float, "str": str, "bool": bool}
    NULL_VALUES = ('None', None, 'none', 'null', 'Null')
    
    INNER_PROCESS = "__inner__"
    
    __slots__ = [
        'id',               # Node identifier
        'name',             # Node name
        'description',
        'status_message',
        'type',             # Node type
        
        'enabled',
        
        'stream',           # Whether node streams output
        'start',            # Start marker
        'end',              # End marker
        
        'sources',          # List of source node names
        'targets',          # List of target node names
        
        'inputs',           # Dictionary of input variable mappings
        'outputs',          # Dictionary of output variable mappings
        
        'input_schema',
        'output_schema',
        
        'hard_input_schema',
        'hard_output_schema',
        
        'input_indexes',
        'output_indexes',
        
        'metrics',          # Dictionary of metric variable mappings
        'default_inputs',
        
        'core',             # Core function to be set by subclasses
        'father',            # Parent node reference
        'contain_generation',
        'continue_loop'     # use in while-loop, whether this node should be marked for continue the loop
    ]
    
    def __init_subclass__(cls, **kwargs):
        """Hook that runs when a subclass is created."""
        super().__init_subclass__(**kwargs)
        
        # Store the original __init__ method
        original_init = cls.__init__
        
        def wrapped_init(self, *args, **kwargs):
            # Call the original __init__
            original_init(self, *args, **kwargs)
            # Automatically call _post_init if this is the final initialization
            # and it's not a dummy or graph node
            if type(self) is cls and getattr(self, 'type', None) not in ["dummy", "graph"]:
                self._post_init()
        
        # Replace __init__ with our wrapped version
        cls.__init__ = wrapped_init
        
    def __init__(
        self,
        id: str = None,
        name: str = None,
        description: str = "",
        status_message: str = "",
        inputs: Dict[str, Any] = {},
        outputs: Dict[str, Any] = {},
        input_schema: ParamSet = None,
        output_schema: ParamSet = None,
        sources: List[str] = None,
        targets: List[str] = None,
        stream: bool = False,
        start: bool = False,
        end: bool = False,
        contain_generation: bool = False
    ):
        """Create a node instance from either a NodeConfig object or keyword arguments.
        
        Args:
            config: Optional NodeConfig object. If provided, kwargs are ignored.
            **kwargs: Keyword arguments to create a NodeConfig. Only used if config is None.
        """
        # Core node properties
        self.id = id or uuid.uuid4().hex
        self.name = name or unique_name()
        self.description = description
        self.status_message = status_message
        self.enabled = True

        self.stream = stream
        self.start = start
        self.end = end
        
        # Connection tracking
        self.sources: List[str] = sources or []
        self.targets: List[str] = targets or []
        
        # State management
        self.inputs = inputs
        self.outputs = outputs
        
        # set hard schema
        self.hard_input_schema = input_schema
        self.hard_output_schema = output_schema
        
        self.input_indexes: Dict[str, int] = {}
        self.output_indexes: Dict[str, int] = {}
        
        self.metrics: Dict[str, int] = {}
                
        # Core function to be set by subclasses
        self.core: Optional[Callable] = None
        
        self.contain_generation = contain_generation
        
        self.continue_loop = False
        
        # Detect father within Graph context
        self.father = get_current()
        
        if self.father:
            if hasattr(self.father, "add_node"):
                self.father.add_node(self)
        
        # Simple name validation
        if self.name and not self.name.replace('_', '').replace('-', '').isalnum():
            raise ValueError(f"Node name '{self.name}' must be alphanumeric with underscores/hyphens")
                
    def _post_init(self):
        """
        Xử lý và chuẩn hóa cấu hình input/output sau khi khởi tạo node.
        
        Chuyển đổi các định dạng input/output khác nhau thành format chuẩn:
        - Dict với key là string hoặc tuple[string]
        - Node reference đơn lẻ
        
        Ví dụ:
            {("a", "b"): source} -> {"a": source, "b": source}
            {node_ref} -> {"param1": {node_ref: "param1"}, ...}
        """
        # Set hard schema nếu có
        if self.hard_input_schema:
            self.input_schema = self.hard_input_schema
        if self.hard_output_schema:
            self.output_schema = self.hard_output_schema
            
        # Kiểm tra và validate: Phát hiện các key trùng lặp giữa input và output schemas
        if hasattr(self, "input_schema") and hasattr(self, "output_schema"):
            if self.input_schema and self.output_schema:
                # Trích xuất keys từ schemas (xử lý cả dict-like objects và iterables)
                input_keys = set(self.input_schema.keys())
                output_keys = set(self.output_schema.keys())
                
                overlap = input_keys & output_keys
                if overlap:
                    raise ValueError(
                        f"Node '{self.name}' có các tên parameter trùng lặp giữa input và output schemas: {sorted(overlap)}. "
                        f"Mỗi tên parameter phải unique giữa input và output schemas."
                    )
        
        # Xử lý inputs
        if isinstance(self.inputs, Dict):
            expanded_inputs = {}
            for k, v in (self.inputs or {}).items():
                
                if isinstance(k, tuple):
                    # Mở rộng tuple keys: {("a", "b"): c} -> {"a": c, "b": c}
                    # Cho phép nhiều input parameters ánh xạ đến cùng một source
                    for key in k:
                        # Mỗi key riêng lẻ được map với value riêng
                        processed_v = {v: key} if hasattr(v, "name") else v
                        expanded_inputs[key] = processed_v
                else:
                    # Trường hợp key đơn lẻ (string)
                    processed_v = {v: k} if hasattr(v, "name") else v
                    expanded_inputs[k] = processed_v
            
            self.inputs = expanded_inputs
            
        elif hasattr(self.inputs, "name"):
            # Trường hợp self.inputs là node reference đơn lẻ
            # Tạo mapping cho tất cả parameters trong input_schema
            if self.input_schema:
                self.inputs = {
                    k: {self.inputs: k} for k in self.input_schema
                }

        # Xử lý outputs (logic tương tự như inputs)
        if isinstance(self.outputs, Dict):
            expanded_outputs = {}
            for k, v in (self.outputs or {}).items():
                
                if isinstance(k, tuple):
                    # Mở rộng tuple keys cho outputs
                    # Cho phép nhiều output parameters ánh xạ đến cùng một target
                    for key in k:
                        # Mỗi key riêng lẻ được map với value riêng
                        processed_v = {v: key} if hasattr(v, "name") else v
                        expanded_outputs[key] = processed_v
                else:
                    # Trường hợp key đơn lẻ (string)
                    processed_v = {v: k} if hasattr(v, "name") else v
                    expanded_outputs[k] = processed_v
                    
            self.outputs = expanded_outputs
            
        elif hasattr(self.outputs, "name"):
            # Trường hợp self.outputs là node reference đơn lẻ
            # Tạo mapping cho tất cả parameters trong output_schema
            if self.output_schema:
                self.outputs = {
                    k: {self.outputs: k} for k in self.output_schema
                }
                
    @property
    def full_name(self) -> str:
        """Returns the full hierarchical path of this node."""
        if self.father:
            return f"{self.father.full_name}.{self.name}"
        else:
            return self.name    
    
    def identity(self, context_id: str) -> str:
        """Returns the full hierarchical path of this node, plus context_id."""
        return f"{self.full_name}[{context_id or 'main'}]"
                
    def __getitem__(self, item: str):
        if self.type == "dummy":
            return {self: item}
        
        # Nếu item là output thì trả về reference
        if item in self.output_schema:
            return {self: item}
        # Nếu item là input thì cũng cho reference
        if item in self.input_schema:
            return {self: item}

        return None
        
    def __rshift__(self, other):
        type = "normal"
        if self.type == "branch":
            type = "condition"
        
        if isinstance(other, list):
            # n1 >> [n2, n3] - connect this node to multiple nodes
            for node in other:
                if hasattr(self.father, "add_edge"):
                    self.father.add_edge(self.name, node.name, type)
            return other
        elif hasattr(other, 'name'):
            # n1 >> n2 - connect this node to another node
            if hasattr(self.father, "add_edge"):
                self.father.add_edge(self.name, other.name, type)
            return other
        else:
            # Return NotImplemented for unsupported types
            return NotImplemented
    
    def __lshift__(self, other):
        type = "normal"
        if self.type == "branch":
            type = "condition"
        
        if isinstance(other, list):
            # [n2, n3] << n1 - connect multiple nodes to this node
            for node in other:
                if hasattr(self.father, "add_edge"):
                    self.father.add_edge(node.name, self.name, type)
            return other
        elif hasattr(other, 'name'):
            # n2 << n1 - connect another node to this node
            if hasattr(self.father, "add_edge"):
                self.father.add_edge(other.name, self.name, type)
            return self
        else:
            # Return NotImplemented for unsupported types
            return NotImplemented
        
    def __rrshift__(self, other):
        """Called for [n1, n2] >> self because lists don't have __rshift__"""
        self.__lshift__(other)
        return self
    
    def __rlshift__(self, other):
        """Called for [n1, n2] << self because lists don't have __lshift__"""
        self.__rshift__(other)
        return self
    
    def is_base_node(self) -> bool:
        return True
    
    def get_openai_tool_schema(self):
        return OpenAISchemaExporter.export_tool_schema(
            param_set=self.input_schema,
            function_name=self.name,
            function_description=self.description
        )
        
    def get_openai_function_schema(self):
        return OpenAISchemaExporter.export_function_schema(
            param_set=self.input_schema,
            function_name=self.name,
            function_description=self.description
        )
    
    async def run(
        self,
        state: WorkflowState,
        context_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run the node with the given state"""
        
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
            
            # Execute standard node logic
            # Support both async and sync core functions
            if asyncio.iscoroutinefunction(self.core):
                _outputs = await self.core(**_inputs)
            else:
                _outputs = self.core(**_inputs)
                        
            # save the result into relevant indexing key
            self.store_result(
                state=state, 
                result=_outputs,
                context_id=context_id
            )
                                
            # Stream success message if enabled
            if self.stream:
                asyncio.create_task(STREAM_SERVICE.push(
                    request_id=request_id,
                    channel_name=self.identity(context_id),
                    data=LLMGenerator.make_chunk(
                        chat_id=state.request_id,
                        content=self.status_message,
                        model=self.name
                    )
                ))
        
            LOGGER.info("request[%s]: %s, complete NODE: %s: %s, _outputs = %s", 
                request_id, context_id, self.name, str(self.type).upper(), str(_outputs)[:200])
                        
        except Exception as e:
            error_msg = traceback.format_exc()
            LOGGER.error(f"Error in node {self.name}: {str(e)}")
            LOGGER.error(error_msg)
            # Propagate the error but ensure metrics are recorded
            state[self.full_name, "error", context_id] = error_msg
            
            default_answers = 'Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại sau.'
            
            if self.stream:
                asyncio.create_task(STREAM_SERVICE.push(
                    request_id=request_id,
                    channel_name=self.identity(context_id),
                    data=fake_chunk_from(
                        content=default_answers,
                        model="error"
                    )
                ))
                
            
        finally:
            # Always record timing metrics            
            await asyncio.sleep(0.00000)
            end_time = datetime.now()
            state.set_by_index(self.metrics['start_time'], start_time, context_id=context_id)
            state.set_by_index(self.metrics['end_time'], end_time, context_id=context_id)
            if self.stream:
                asyncio.create_task(STREAM_SERVICE.end(request_id, self.identity(context_id)))
            return _outputs
            
    def cast_value(self, value: Any, type_str: str):
        if value in self.NULL_VALUES:
            return None
        
        if value and type_str in self.TYPE_MAP:
            return self.TYPE_MAP[type_str](value)
        
        return value
    
    def get_input_variables(self) -> List[str]:
        """Return the list of input variables in input schema"""
        return self.input_schema.keys()
    
    def get_output_variables(self) -> List[str]:
        """Return the list of output variables in input schema"""
        return self.output_schema.keys()
    
    def get_inputs(self, state: WorkflowState, context_id: str) -> Dict[str, Any]:
        """
        Efficiently retrieves all input values from state using pre-registered indices,
        returning only those with non-None values.
        Args:
            state: The state object containing values
        Returns:
            Dictionary mapping input names to their non-None values
        """
        return {
            k: state.get_by_index(
                index=idx, 
                context_id=context_id
            ) 
            for k, idx in self.input_indexes.items()
        }
    
    def get_outputs(self, state: WorkflowState, context_id: str) -> Dict[str, Any]:
        """
        Efficiently retrieves all output values from state using pre-registered indices.
        
        Args:
            state: The state object containing values
            
        Returns:
            Dictionary mapping output names to their values
        """
        # Direct access to state.data for maximum performance
        return {
            k: state.get_by_index(
                index=idx, 
                context_id=context_id
            )
            for k, idx in self.output_indexes.items()
        }
        
    def get_result(self, state: WorkflowState) -> Dict[str, Any]:
        return self.get_outputs(state, None)
    
    def store_result(
        self,
        state: WorkflowState,
        result: Dict[str, Any],
        context_id: str
    ) -> None:
        """
        Stores the result dict in the state dict using self.name as the key.
        
        Args:
            state (Dict): Target state dictionary.
            result (Dict): Result to be stored.
            
        Returns:
            None: Modifies state in-place.
        """        
        if not result or not self.output_schema:
            return
        
        for key, value in result.items():
            _type = self.output_schema[key].type
            
            # Time cast_value
            cast_val = self.cast_value(value, _type)
            
            # Time set_by_index
            state.set_by_index(
                index=self.output_indexes[key], 
                value=cast_val,
                context_id=context_id
            )
            
    def specific_metadata(self) -> Dict[str, Any]:
        """Return subclass-specific metadata dictionary."""
        return {}
    
    @staticmethod
    def _remove_url_keys(metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove all keys exactly named 'url' from a nested dict.
        Returns modified_obj.
        """
        def walk(node: Any) -> Any:
            if isinstance(node, dict):
                if "url" in node:
                    node.pop("url", None)
                for k, v in list(node.items()):
                    node[k] = walk(v)
                return node

            if isinstance(node, list):
                for i, v in enumerate(node):
                    node[i] = walk(v)
                return node

            if isinstance(node, tuple):
                return tuple(walk(v) for v in node)

            # primitives (str, int, float, bool, None, etc.)
            return node

        return walk(metadata)
    
    def metadata(self) -> Dict[str, Any]:
        """
        Generate a complete metadata dictionary for the node.
        
        Combines base node properties with subclass-specific metadata.
        Only includes non-empty/non-None properties.
        
        Returns:
            Dict[str, Any]: Complete node metadata dictionary
        """
        # Start with required fields
        result = {
            "id": self.id,
            "name": self.full_name,
            "type": str(self.type).replace('NodeType.', '').lower()
        }
        
        # Add optional fields if they exist
        # Helper function to get the appropriate key name
        def get_connect_key(value):
            if isinstance(value, dict) and value:
                node, var = next(iter(value.items()))
                node_iden = node.full_name if hasattr(node, 'full_name') else node
                return {node_iden: var}
            return value

        optional_fields = {
            "description": self.description,
            "input_connects": {k: get_connect_key(v) for k, v in self.inputs.items()},
            "output_connects": {k: get_connect_key(v) for k, v in self.outputs.items()},
        }
        
        # Add connection information if present
        if self.sources:
            optional_fields["sources"] = f"<- ({','.join(self.sources)})"
        
        if self.targets:
            optional_fields["targets"] = f"-> ({','.join(self.targets)})"
        
        # Add flags if set
        for flag in ["stream", "start", "end"]:
            if locals().get(flag):
                optional_fields[flag] = True
        
        # Add all non-empty optional fields to result
        result.update({k: v for k, v in optional_fields.items() if v})
        
        # Add non-None values from subclass-specific metadata
        specific_data = {k: v for k, v in self.specific_metadata().items() if v}
        result.update(specific_data)

        return self._remove_url_keys(result)
    
    def _sanitize_trace_data(self, data: Dict[str, Any], threshold_bytes: int) -> Dict[str, Any]:
        """
        Check and replace values in a dictionary that exceed the size threshold.
        
        - str: calculate size using len(value.encode('utf-8'))
        - bytes/bytearray: calculate size using len(value)
        - numpy array: use nbytes
        - dict/list: convert to string summary or hash
        """
        import sys
        import numpy as np
        from hashlib import sha256

        if not isinstance(data, dict):
            return data

        sanitized = {}
        for key, value in data.items():
            try:
                size = 0
                # Calculate size based on type
                if isinstance(value, str):
                    size = len(value.encode('utf-8'))
                elif isinstance(value, (bytes, bytearray)):
                    size = len(value)
                elif isinstance(value, np.ndarray):
                    size = value.nbytes
                elif isinstance(value, (dict, list)):
                    # Convert dict/list to a string summary
                    size = len(str(value).encode('utf-8'))
                else:
                    size = sys.getsizeof(value)

                # Replace with placeholder if size exceeds threshold
                if size > threshold_bytes:
                    # For bytes or str, replace with a short hash
                    if isinstance(value, (str, bytes, bytearray)):
                        h = sha256(value if isinstance(value, bytes) else value.encode('utf-8')).hexdigest()
                        sanitized[key] = f"<exceeded {size/1024/1024:.2f} MB, sha256={h[:8]}...>"
                    else:
                        sanitized[key] = f"<exceeded {size/1024/1024:.2f} MB>"
                else:
                    sanitized[key] = value
            except Exception:
                # If size calculation fails, keep the original value
                sanitized[key] = value

        return sanitized

    def trace_data(self, state: WorkflowState, context_id: str, size_threshold_bytes: int = 100000) -> Dict[str, Any]:
        full_name = self.full_name
        name = self.name
        
        if context_id:
            name = f"{name}:{context_id}"
        
        # Lấy input/output và kiểm tra size (mặc định 100KB)
        raw_input = self.get_inputs(state, context_id)
        raw_output = self.get_outputs(state, context_id)
        
        _data = {
            "name": name,
            "start_time": state[full_name, "start_time", context_id],
            "end_time": state[full_name, "end_time", context_id],
            "input": self._sanitize_trace_data(raw_input, size_threshold_bytes),
            "output": self._sanitize_trace_data(raw_output, size_threshold_bytes),
            "contain_generation": self.contain_generation,
            "metadata": self.metadata()
        }
        
        error_msg = state[full_name, "error", context_id]
        if not error_msg:
            _data.update({"level": "DEFAULT"})
            
            if self.type == "llm":
                _data.update({
                    "model": self.resource_key,
                    "usage": state[full_name, "usage", context_id],
                    "completion_start_time": state[full_name, "completion_start_time", context_id]
                })
        else:
            # Nếu có lỗi thì ghi đè output bằng error message
            _data.update({
                "output": error_msg,
                "level": "ERROR"
            })
        
        return _data
    

class DummyNode(BaseNode):
    """Dummy node for START/END markers"""
    
    type: NodeType = "dummy"
    
    def __init__(self, name: str):
        super().__init__(name=name)
    
    def __rshift__(self, other):
        """Handle START >> node or START >> [nodes] case"""
        if self == START:
            # Get current graph context
            current_graph = get_current()
            if current_graph and hasattr(current_graph, 'add_edge'):
                if isinstance(other, list):
                    for node in other:
                        current_graph.add_edge(self.name, node.name)
                    return other
                elif hasattr(other, 'name'):
                    current_graph.add_edge(self.name, other.name)
                    return other
        
        # Fallback to parent implementation
        return super().__rshift__(other)
    
    def __rrshift__(self, other):
        """Handle [nodes] >> START or [nodes] >> END case
        
        This method is called when the left operand doesn't have __rshift__,
        typically when using lists: [node1, node2] >> END
        
        Examples:
        - [node1, node2] >> END: marks both nodes as end nodes
        - [node1, node2] >> START: marks both nodes as start nodes (less common)
        """
        current_graph = get_current()
        if current_graph and hasattr(current_graph, 'add_edge'):
            if self == START:
                # [nodes] >> START doesn't make logical sense, but handle it
                # This would mean multiple nodes are starting points
                if isinstance(other, list):
                    for node in other:
                        current_graph.add_edge(self.name, node.name)
                elif hasattr(other, 'name'):
                    current_graph.add_edge(self.name, other.name)
                return self
            
            elif self == END:
                # [nodes] >> END means multiple nodes end at END
                if isinstance(other, list):
                    for node in other:
                        current_graph.add_edge(node.name, self.name)
                elif hasattr(other, 'name'):
                    current_graph.add_edge(other.name, self.name)
                return self
        
        return self
    
    def __rlshift__(self, other):
        """Handle node >> END or END << node case"""
        if self == END:
            # Get current graph context
            current_graph = get_current()
            if current_graph and hasattr(current_graph, 'add_edge'):
                if isinstance(other, list):
                    for node in other:
                        current_graph.add_edge(node.name, self.name)
                    return self
                elif hasattr(other, 'name'):
                    current_graph.add_edge(other.name, self.name)
                    return self
        
        return self


# Replace the existing START and END definitions
START = DummyNode("__START__")
END = DummyNode("__END__")
CONTINUE = DummyNode("__CONTINUE__")
INPUT = DummyNode("__INPUT__")
OUTPUT = DummyNode("__OUTPUT__")