from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.state_value import VariableCell
from typing import Dict, Any, List, Optional, Tuple
import uuid



class WorkflowState:
    
    __slots__ = ["_indexer", "_values", '_execution_order', '_metadata']
    
    def __init__(self,
                 indexer: WorkflowIndexer,
                 inputs: Dict[str, Any] = None,
                 **metadata) -> None:
        self._indexer = indexer
        self._values = [VariableCell(v) for v in indexer._values]
        self._execution_order: List[Dict[str, str]] = []
        self._metadata = {
            'user_id': str(uuid.uuid4()),
            'session_id': str(uuid.uuid4()), 
            'request_id': str(uuid.uuid4()),
            **metadata
        }
        
        # Set initial input values
        if inputs:
            for var_name, value in inputs.items():
                self[indexer._name, var_name, None] = value
                
    def inject_inputs(self,
                      node: str,
                      inputs: Dict[str, Any],
                      context_id: str = None) -> None:
        if inputs:
            for var_name, value in inputs.items():
                self[node, var_name, context_id] = value
    
    def __setitem__(self, key: Tuple[str, str, str], value: Any) -> None:
        if len(key) == 3:
            node, var, context = key
            index = self._indexer[node, var]
            self._values[index][context] = value
        else:
            raise ValueError(f"key truyền vào state phải là (node, var, context)")
    
    def __getitem__(self, key: Tuple[str, str, str]) -> Any:
        if len(key) == 3:
            node, var, context = key
            index = self._indexer[node, var]
            return self._values[index][context]
        else:
            raise ValueError(f"key truyền vào state phải là (node, var, context)")
        
    def get(self, node: str, var: str) -> VariableCell:
        index = self._indexer[node, var]
        return self._values[index]

    def get_by_index(self, index: int, context_id: str) -> Any:
        """Direct array access by index."""
        if 0 <= index < len(self._values):
            return self._values[index][context_id]
        raise IndexError(f"Index {index} out of range")
    
    def set_by_index(self, index: int, value: Any, context_id: str) -> None:
        """Direct array assignment by index."""
        if 0 <= index < len(self._values):
            self._values[index][context_id] = value
        else:
            raise IndexError(f"Index {index} out of range")
        
    def record_execution(self, node_name: str, parent: str, context_id: str) -> None:
        """Record node execution for observability tracking."""
        self._execution_order.append({"node": node_name, "parent": parent, "context_id": context_id})
        
        
    @property
    def name(self) -> str:
        """Workflow name."""
        return self._indexer._name
    
    @property 
    def execution_order(self) -> List[str]:
        """Execution history (copy)."""
        return self._execution_order.copy()
    
    @property
    def metadata(self) -> Dict[str, Any]:
        """State metadata (copy)."""
        return self._metadata.copy()
    
    @property
    def user_id(self) -> str:
        """Get user identifier."""
        return self._metadata["user_id"]
    
    @property
    def session_id(self) -> str:
        """Get session identifier."""
        return self._metadata["session_id"]
    
    @property
    def request_id(self) -> str:
        """Get request identifier."""
        return self._metadata["request_id"]

    def __contains__(self, key: Tuple[str, str]) -> bool:
        """Check if (node, variable) mapping exists."""
        return key in self._indexer
    
    def __len__(self) -> int:
        """Number of storage slots."""
        return len(self._values)
    
    def __enter__(self) -> 'WorkflowState':
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        pass
    
    def __repr__(self) -> str:
        return (f"WorkflowState(name='{self.name}', "
                f"variables={len(self)}, "
                f"executions={len(self._execution_order)})")
        
    def show(self):
        for (node, var) in self._indexer:
            variable_cell = self.get(node, var)
            
            if not variable_cell.contexts:
                # No values set, show default
                print(f"{node}.{var} → {variable_cell.DEFAULT_VALUE}")
            elif len(variable_cell.contexts) == 1:
                # Single context, show inline
                context_id = variable_cell.versions[0]
                value = variable_cell.contexts[context_id]
                print(f"{node}.{var} → [{context_id}] → {value}")
            else:
                # Multiple contexts, show on separate lines
                print(f"{node}.{var}:")
                for context_id in variable_cell.versions:
                    value = variable_cell.contexts[context_id]
                    print(f"  [{context_id}] → {value}")
            

async def test_fast_indexer_state():
    """Test the FastIndexerState functionality."""
    from beeflow.nodes.primitives.transform.prompt_node import PromptNode
    from beeflow.nodes.primitives.ai.llm_node import LLMNode
    from beeflow.nodes.primitives.transform.parser_node import ParserNode
    from beeflow.nodes import INPUT
    
    # Create indexer with input variables
    indexer = WorkflowIndexer("workflow01")
        
    prompt_node = PromptNode(
        name="prompt0",
        user_prompt="Hãy phân tích query: {query} cùng lịch sử hội thoại {history} và trả ra <category>(positive/negative)</category>",
        inputs={
            "query": INPUT,
            "history": INPUT
        }
    )
    
    llm_node = LLMNode(
        name="llm0", 
        resource_key="gpt-4o", 
        inputs={"messages": prompt_node}, 
        stream=False
    )

    parser_node = ParserNode(
        name="parser0",
        extract_schema=["category: str"],
        inputs={"text": llm_node["content"]}
    )

    indexer = (indexer
        .add_node(prompt_node)
        .add_node(llm_node)
        .add_node(parser_node)
        .build()
    )
    
       
    state = WorkflowState(
        indexer=indexer, 
        inputs={
            "query": "hướng dẫn tôi mua cổ phiếu trên app MB đi",
            "history": [
                {"role": "user", "content": "xin chào"},
                {"role": "assistant", "content": "chào bạn, tôi là trợ lý ảo của MB, bạn cần giúp gì?"}
            ]
        },
        user_id="thanglq2"
    )
    
    # state.show()
    print(state["workflow01", "query"])
    
    state["workflow01", "query", "loop1"] = "hihi"
    print(state["workflow01", "query"])

    state["workflow01", "query", "loop2"] = "haha"
    print(state["workflow01", "query"])

    state["workflow01", "query", "loop3"] = "hehe"
    
    print(state["workflow01", "query"])
    
    print(state["workflow01", "query", "loop1"])
    
    print(state["workflow01", "query", None])
    
    print(state.get("workflow01", "query").versions)

    

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_fast_indexer_state())