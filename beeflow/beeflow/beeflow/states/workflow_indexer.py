from typing import Dict, Any, Optional, Tuple, List

from beegen.utils.common import verify_data


class WorkflowIndexer:
    """
    Bộ đánh chỉ mục workflow cho việc quản lý node dependencies và variable mapping.
    
    Tạo ra hệ thống index mapping hiệu năng cao cho các node trong workflow, hỗ trợ
    zero-copy variable sharing và lazy index allocation. Cho phép các node truy cập
    variables của nhau thông qua shared indices thay vì copy dữ liệu.
    
    Kiến trúc Core:
    --------------
    - _indices: Dict mapping (node, variable) → array index trong workflow
    - _values: Mảng chứa giá trị variables của tất cả nodes
    - _nodes: Registry các node đã được đăng ký vào workflow
    
    Workflow Node Dependencies:
    --------------------------
    Indexer xử lý 3 loại dependency giữa các node:
    1. Node Reference: node_a["specific_var"] → node_b
    2. Variable Reference: node_a["specific_var"] → node_b["specific_var2]
    3. Literal Values: Giá trị cụ thể được gán trực tiếp
    
    Quy trình Index Management:
    --------------------------
    1. Registration: Đăng ký node vào workflow indexer
    2. Variable Mapping: Map input/output variables của node
    3. Index Allocation: Cấp phát index cho variables (lazy)
    4. Dependency Resolution: Giải quyết dependencies giữa các node
    5. Index Distribution: Phân phát indices về cho từng node
    
    Ví dụ Workflow Pipeline:
    -----------------------
    ```python
    # Tạo workflow indexer
    indexer = WorkflowIndexer("sentiment_analysis_pipeline")
    
    # Định nghĩa workflow nodes
    prompt_node = PromptNode(
        name="prompt_generator",
        user_prompt="Phân tích sentiment: {user_input}",
        inputs={"user_input": INPUT["query"]}  # Link đến workflow input
    )
    
    llm_node = LLMNode(
        name="llm_processor", 
        model="gpt-4o", 
        inputs={"messages": prompt_node}  # Link đến output của prompt_node
    )
        
    result_parser = ParserNode(
        name="result_extractor",
        extract_schema=["sentiment: str", "confidence: float"],
        inputs={"text": llm_node["content"]},  # Link đến specific variable
        outputs={
            "sentiment": OUTPUT["final_sentiment"],  # Link đến workflow output
            "confidence": OUTPUT["confidence_score"]
        }
    )
    
    # Xây dựng workflow indexer
    workflow = (indexer
        .add_node(prompt_node)      # Đăng ký node vào workflow  
        .add_node(llm_node)         # Tự động map dependencies
        .add_node(result_parser)    # Resolve variable references
        .build())                   # Phân phát indices cho các node
    
    # Workflow ready để execute
    workflow.show()  # Debug index mappings
    
    # Các node giờ có thể truy cập variables qua indices:
    # prompt_node.input_indexes["user_input"] → index trong workflow
    # llm_node.input_indexes["messages"] → cùng index với prompt_node output
    ```
    
    Zero-Copy Node Communication:
    ----------------------------
    Thay vì copy dữ liệu giữa nodes, indexer tạo shared index references:
    - node_a.output_indexes["result"] = 5
    - node_b.input_indexes["data"] = 5  (cùng index)  
    - Cả 2 node đều truy cập _values[5] → zero-copy sharing
    
    Performance Benefits:
    --------------------
    - O(1) variable access time cho bất kỳ node nào
    - Zero-copy communication giữa nodes trong workflow
    - Lazy index allocation tiết kiệm memory
    - Efficient dependency resolution cho complex workflows
    - Centralized workflow state management
    """
    
    __slots__ = ["_indices", "_values", "_name", "_nodes"]
    
    
    def __init__(self, name: str) -> None:
        """
        Khởi tạo WorkflowIndexer cho một workflow cụ thể.
        
        Args:
            name: Tên định danh của workflow
        """
        self._name = name
        # Index mapping: (node_name, variable_name) → position trong workflow array
        self._indices: Dict[Tuple[str], int] = {}
        # Workflow variable storage - mảng chứa values của tất cả nodes
        self._values: List[Any] = []
        # Node registry để quản lý workflow dependencies
        self._nodes: Dict[str, 'BaseNode'] = {} # type: ignore
        
    def __iter__(self):
        """Iterator qua tất cả (node, variable) mappings trong workflow."""
        for (node, var) in self._indices:
            yield (node, var)
    
    def __getitem__(self, key: Tuple[str, str]) -> int:
        """
        Lấy workflow index của một node variable.
        
        Args:
            key: Tuple (node_name, variable_name)
            
        Returns:
            Index position trong workflow _values array
            
        Raises:
            ValueError: Nếu node variable chưa được map trong workflow
        """
        if key in self:
            node, var = key
            index = self._indices[node, var]
            return index
        
        raise ValueError(f"{key} chưa được map trong workflow indexer: {self._name}")

    def __contains__(self, key: Tuple[str, str]) -> bool:
        """
        Kiểm tra node variable đã được map trong workflow chưa.
        
        Args:
            key: Tuple (node_name, variable_name)
            
        Returns:
            True nếu variable đã được map trong workflow
        """        
        return key in self._indices
    
    def __len__(self) -> int:
        """
        Số lượng variable slots đã được allocated trong workflow.
        
        Returns:
            Tổng số positions trong workflow _values array
        """
        return len(self._values)
    
    def __repr__(self) -> str:
        """Representation string của workflow indexer."""
        return f"WorkflowIndexer(workflow='{self._name}', variables={len(self._values)})"
        
    def _register(self, node: str, var: str) -> None:
        """
        Đăng ký node variable vào workflow mà chưa allocate index (lazy registration).
        
        Chỉ đánh dấu variable này sẽ cần index trong workflow, actual allocation
        sẽ được thực hiện khi gọi _allocate().
        
        Args:
            node: Tên node trong workflow
            var: Tên variable của node
        """
        if (node, var) not in self:
            # Đăng ký với None - sẽ allocate index khi cần
            self._indices[node, var] = None
            
    def _allocate(self, node: str, var: str) -> int:
        """
        Cấp phát workflow index cho node variable.
        
        Nếu chưa đăng ký thì đăng ký trước. Nếu đã có index rồi thì return
        index hiện tại (idempotent operation).
        
        Args:
            node: Tên node trong workflow
            var: Tên variable của node
            
        Returns:
            Index position trong workflow _values array
        """
        # Đảm bảo variable đã được đăng ký trong workflow
        self._register(node, var)
        
        current_index = self._indices[node, var]
        
        if current_index is None:
            # Allocate index position mới trong workflow
            index = len(self._values)
            self._indices[node, var] = index
            self._values.append(None)
            return index
        
        # Return existing index
        return current_index
    
    def _link(self, 
              node: str, var: str, 
              ref_node: str, ref_var: Optional[str] = None) -> None:
        """
        Tạo dependency link giữa nodes trong workflow (zero-copy variable sharing).
        
        Thay vì copy data, hai node variables sẽ point đến cùng index position
        trong workflow, tạo zero-copy communication channel.
        
        Args:
            node: Node cần nhận data
            var: Variable của node cần nhận data  
            ref_node: Node cung cấp data
            ref_var: Variable của ref_node (default: cùng tên với var)
        """
        if ref_var is None:
            # Link đến cùng variable name trong ref_node
            self._indices[node, var] = self._allocate(ref_node, var)
        else:
            # Link đến specific variable trong ref_node
            self._indices[node, var] = self._allocate(ref_node, ref_var)
            
    def put(self, node: str, var: str, value: Any) -> None:
        """
        Set giá trị cho node variable trong workflow.
        
        Args:
            node: Tên node trong workflow
            var: Tên variable của node
            value: Giá trị cần set
            
        Raises:
            ValueError: Nếu node variable chưa được đăng ký trong workflow
        """
        if (node, var) not in self:
            raise ValueError(f"{(node, var)} chưa được đăng ký trong workflow: {self._name}")
        
        verify_data(value)
        
        # Allocate index nếu cần và set value
        index = self._allocate(node, var)
        if value is None and self._values[index] is not None:
            return
        self._values[index] = value
    
    def get(self, node: str, var: str) -> Any:
        """
        Lấy giá trị của node variable từ workflow.
        
        Args:
            node: Tên node trong workflow
            var: Tên variable của node
            
        Returns:
            Giá trị của variable hoặc None nếu chưa được set
        """        
        index = self._indices.get((node, var), None)
        if index is None:  # Chưa được allocated trong workflow
            return None
            
        return self._values[index]
    
    def resolve(self, node: str, var: str, value: Any, default_value: Any) -> None:
        """
        Resolve dependency của node variable trong workflow context.
        
        Xử lý 3 loại node dependencies:
        1. BaseNode reference: Link toàn bộ output của node khác
        2. Dict với BaseNode key: Link specific variable của node khác  
        3. Literal value: Set giá trị trực tiếp cho variable
        
        Args:
            node: Node cần resolve dependency
            var: Variable cần resolve
            value: Dependency definition (BaseNode, dict mapping, hoặc literal)
            default_value: giá trị default của biến node, var trong trường hợp = None
        """
        
        from beeflow.nodes import INPUT, OUTPUT
        
        base_node = self._nodes[node]
        
        if hasattr(value, "is_base_node"):
            # Case 1: Reference đến toàn bộ BaseNode output
            ref_name = value.full_name
            # Special handling cho workflow INPUT/OUTPUT dummy nodes
            if value in [INPUT, OUTPUT]:
                if base_node.father:
                    ref_name = base_node.father.full_name
                else:
                    ref_name = self._name
            self._link(node, var, ref_name)
            
        elif isinstance(value, dict) and value:
            # Case 2: Dictionary mapping - link specific variable
            ref, ref_var = next(iter(value.items()))
            if hasattr(ref, "is_base_node"):
                ref_name = ref.full_name
                # Special handling cho workflow INPUT/OUTPUT dummy nodes
                if ref in [INPUT, OUTPUT]:
                    if base_node.father:
                        ref_name = base_node.father.full_name
                    else:
                        ref_name = self._name
                self._link(node, var, ref_name, ref_var)
            else:
                # Regular dict value - store trực tiếp
                self.put(node, var, value)
        else:
            # Case 3: Literal value - store trong workflow
            self.put(node, var, value)
        
        # Kiểm tra xem biến (node, var) đã có giá trị chưa, nếu chưa thì gán default
        _idx = self[node, var]
        if self._values[_idx] is None:
            self._values[_idx] = default_value            
    
    def add_node(self, node: 'BaseNode') -> 'WorkflowIndexer': # type: ignore
        """
        Thêm node vào workflow và đăng ký variable mappings.
        
        Tự động register tất cả input/output variables của node và setup
        execution metrics tracking. Metrics bao gồm timing, errors, và 
        node-specific data như token usage cho LLM nodes.
        
        Args:
            node: BaseNode instance cần add vào workflow
        
        Returns:
            Self để support method chaining trong workflow building
        """
        node_name = node.full_name
        self._nodes[node_name] = node
                
        # Register input/output variables của node (lazy registration)
        if node.input_schema:
            for var_name in node.input_schema:
                self._register(node_name, var_name)
        
        if node.output_schema:
            for var_name in node.output_schema:
                self._register(node_name, var_name)
        
        # Register execution metrics (allocate ngay cho monitoring)
        metrics = ["start_time", "end_time", "error"]
        if node.type == "llm":
            # LLM-specific metrics cho performance tracking
            metrics.extend(["completion_start_time", "usage", "token_count", "model"])
        
        for metric in metrics:
            self._allocate(node_name, metric)
            
        if hasattr(node, "_nodes"):
            for _, sub_node in node._nodes.items():
                self.add_node(sub_node)
                
        if hasattr(node, "_graph"):
            self.add_node(node._graph)
        
        if hasattr(node, "_tools"):
            for _, tool_node in node._tools.items():
                self.add_node(tool_node)
        
        return self
    
    def build(self) -> 'WorkflowIndexer':
        """
        Build workflow index mappings và resolve tất cả node dependencies.
        
        Thực hiện workflow construction pipeline:
        1. Resolve input/output connections cho tất cả nodes
        2. Distribute input indices về các nodes để direct access
        3. Distribute output indices về các nodes  
        4. Distribute metric indices cho execution monitoring
        
        Sau khi build xong, workflow ready để execute với optimized
        index-based variable access.
        
        Returns:
            Self để support method chaining
        """
        for node_name, node in self._nodes.items():            
            # Resolve input/output dependencies của node
            for schema, connections in [
                (node.input_schema, node.inputs),
                (node.output_schema, node.outputs)
            ]:
                if schema:
                    for var_name in schema:
                        # Lấy default value từ schema definition
                        default_value = schema[var_name].default
                        # Use connection nếu có, otherwise dùng default
                        value = connections.get(var_name)
                        # Resolve dependency này trong workflow context
                        self.resolve(node_name, var_name, value, default_value)
            
            # Distribute input indices về node để O(1) access
            if node.input_schema:
                for var_name in node.input_schema:
                    node.input_indexes[var_name] = self[node_name, var_name]
            
            # Distribute output indices về node để O(1) write
            if node.output_schema:
                for var_name in node.output_schema:
                    node.output_indexes[var_name] = self[node_name, var_name]
                    
            # Distribute common execution metric indices
            common_metrics = ["start_time", "end_time", "error"]
            for metric in common_metrics:
                node.metrics[metric] = self[node_name, metric]
            
            # Distribute node-type specific metric indices
            if node.type == "llm":
                llm_metrics = ["completion_start_time", "usage"]
                for metric in llm_metrics:
                    node.metrics[metric] = self[node_name, metric]
        
        return self
    
    def show(self):
        """
        Debug display của workflow index mappings.
        
        Hiển thị toàn bộ node variable mappings trong workflow bao gồm:
        - Node và variable names
        - Index positions trong workflow array
        - Current values (nếu có)
        
        Useful để debug workflow dependency issues.
        """
        print(f"\n=== Workflow Indexer: {self._name} ===")
        for (node, var) in self:
            try:
                idx = self[node, var]
                value = self.get(node, var)
                print(f"{node}.{var} → index[{idx}] = {value}")
            except ValueError as e:
                print(f"{node}.{var} → {e}")
        print(f"Total workflow variables: {len(self._values)}\n")
                

async def main():
    """Ví dụ xây dựng sentiment analysis workflow với node dependencies."""
    from beeflow.nodes.primitives.transform.prompt_node import PromptNode
    from beeflow.nodes.primitives.ai.llm_node import LLMNode
    from beeflow.nodes.primitives.transform.parser_node import ParserNode
    from beeflow.nodes import INPUT, OUTPUT
    
    # Tạo workflow indexer
    indexer = WorkflowIndexer("sentiment_analysis_workflow")
    
    # Node 1: Tạo prompt từ user input
    prompt_node = PromptNode(
        name="prompt_generator",
        user_prompt="Hãy phân tích query: {query} cùng lịch sử {history} và trả ra <category>(positive/negative)</category>",
        inputs={
            "query": INPUT["query"],      # Link đến workflow input
            "history": INPUT["history"]   # Link đến workflow input khác
        }
    )
    
    # Node 2: Process prompt qua LLM
    llm_node = LLMNode(
        name="llm_processor", 
        resource_key="gpt-4o", 
        inputs={"messages": prompt_node},  # Link đến entire prompt_node output
        stream=False
    )
    
    # Node 3: Parse LLM response
    parser_node = ParserNode(
        name="result_extractor",
        extract_schema=["category: str"],
        inputs={"text": llm_node["content"]},  # Link đến specific LLM output
        outputs={"category": OUTPUT["final_result"]}  # Link đến workflow output
    )
    
    # Build workflow với node dependencies
    workflow = (indexer
        .add_node(prompt_node)      # Register node vào workflow
        .add_node(llm_node)         # Auto-resolve Node Reference (prompt_node.messages)
        .add_node(parser_node)      # Auto-resolve Variable Reference (llm_node["content"])
        .build())                   # Finalize workflow indexing
    
    # Debug workflow structure
    workflow.show()
    
    print("Workflow ready để execute!")
    print("Nodes có thể access variables qua distributed indices:")
    print(f"- prompt_node.input_indexes: {prompt_node.input_indexes}")
    print(f"- llm_node.input_indexes: {llm_node.input_indexes}")  
    print(f"- parser_node.output_indexes: {parser_node.output_indexes}")
    

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())