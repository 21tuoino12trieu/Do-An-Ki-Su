from typing import Dict, List, Optional, Any, Union, Callable, Tuple
from beeflow.configs.node_config import NodeConfig, NodeType
from beeflow.configs.edge_config import EdgeConfig
from beeflow.configs import *
from beegen.configs import *
from beegen.tools.schema.param import ParamSet


class GraphNodeConfig(NodeConfig):
    """Configuration for a graph of nodes in the workflow."""
    type: NodeType = "graph"
    nodes: Dict[str, NodeConfig] = {}
    edges: List[EdgeConfig] = []
    entries: List[str] = []  # Key of the start node
    exits: List[str] = []  # Key of the end node
    
    output_schema: ParamSet = ParamSet.new().build()
    
    # @classmethod
    # def new(cls) -> 'GraphNodeConfigBuilder':
    #     return GraphNodeConfigBuilder()
    
    def model_post_init(self, __context: Any) -> None:
        """Pydantic v2 post initialization hook."""
        super().model_post_init(__context)
        
        # Find start and end nodes if not explicitly set
        if not self.entries:
            self.entries = [
                key
                for key, node in self.nodes.items() 
                if hasattr(node, 'start') and node.start
            ]
            
        
        # Find all end nodes and add them to the self.end list
        if not self.exits:
            self.exits = [
                key 
                for key, node in self.nodes.items() 
                if hasattr(node, 'end') and node.end
            ]
        
        # Graph Input Schema = collect the var with reference to graph name
        for _, node in self.nodes.items():
            for var, ref in node.inputs.items():
                if ref == self.name:
                    schema = node.input_schema[var]
                    self.input_schema[var] = schema
                elif isinstance(ref, Dict):
                    ref_key, ref_value = next(iter(ref.items()))
                    if ref_key == self.name:
                        schema = node.input_schema[var]
                        self.input_schema[ref_value] = schema
            
        # Graph Output Schema = merge(end nodes)
        for end_key in self.exits:
            end_node = self.nodes[end_key]
            _output_schema = getattr(end_node, 'output_schema', None)
            if _output_schema:
                self.output_schema += _output_schema


# region: OLD CODE
# class GraphNodeConfigBuilder:
#     """Builder for constructing GraphNodeConfig objects with a clean, DRY design."""
    
#     def __init__(self):
#         self._nodes: Dict[str, NodeConfig] = {}
#         self._edges: List[EdgeConfig] = []
#         self._name: str = "default_graph"
#         self._description: str = ""
#         self._inputs: Dict[str, Any] = {}
        
#         # Node type registry - single source of truth
#         self._node_registry = {
#             'llm_chain': {
#                 'class': 'LLMChainNodeConfig',
#                 'module': 'beeflow.nodes.templates.llm_chain_node',
#                 'defaults': {
#                     'model': 'beegen-v1',
#                     'parser': 'xml',
#                     'output_schema': []
#                 }
#             },
#             'retriever': {
#                 'class': 'RetrieverNodeConfig', 
#                 'module': 'beeflow.nodes.templates.retriever_node',
#                 'defaults': {
#                     'embed_model': 'bge-m3',
#                     'rerank_model': 'bge-m3',
#                     'milvus_model': 'chatbot-libra',
#                     'mongo_model': 'aicenter-chatbot',
#                     'mongo_coll': 'chunk_data',
#                     'top_k': 10,
#                     'threshold': 0.0,
#                     'rerank_top_k': 0,
#                     'rerank_threshold': 0.0
#                 }
#             },
#             'llm': {
#                 'class': 'LLMNodeConfig',
#                 'defaults': {}
#             },
#             'fake-llm': {
#                 'class': 'FakeLLMNodeConfig',
#                 'defaults': {}  
#             },
#             'embedding': {
#                 'class': 'EmbeddingNodeConfig',
#                 'defaults': {'model': 'bge-m3'}
#             },
#             'rerank': {
#                 'class': 'RerankNodeConfig',
#                 'defaults': {'model': 'bge-m3', 'threshold': 0.0}
#             },
#             'prompt': {
#                 'class': 'PromptNodeConfig',
#                 'defaults': {}
#             },
#             'code': {
#                 'class': 'CodeNodeConfig',
#                 'defaults': {}
#             },
#             'parser': {
#                 'class': 'ParserNodeConfig',
#                 'defaults': {}
#             },
#             'milvus': {
#                 'class': 'MilvusNodeConfig',
#                 'defaults': {}
#             },
#             'mongo': {
#                 'class': 'MongoNodeConfig',
#                 'defaults': {}
#             },
#             'branch': {
#                 'class': 'BranchNodeConfig',
#                 'defaults': {}
#             },
#             'for_loop': {
#                 'class': 'ForLoopNodeConfig',
#                 'defaults': {}
#             },
#             'graph': {
#                 'class': 'GraphNodeConfig',
#                 'defaults': {}
#             },
#             'default': {
#                 'class': 'NodeConfig',
#                 'defaults': {}
#             }
#         }
        
    
#     def add_node(self, type: str, name: str, inputs: Dict[str, Any] = None, **kwargs) -> 'GraphNodeConfigBuilder':
#         """
#         Universal method to add any type of node.
        
#         Args:
#             node_type: Type of node ('llm_chain', 'retriever', etc.)
#             name: Name of the node
#             inputs: Input connections for the node
#             **kwargs: Node-specific configuration parameters
#         """
#         if type not in self._node_registry:
#             available_types = ', '.join(self._node_registry.keys())
#             raise ValueError(f"Unknown node type: {type}. Available types: {available_types}")
        
#         node_info = self._node_registry[type]
        
#         # Import the node class dynamically if module is specified
#         if 'module' in node_info:
#             module = __import__(node_info['module'], fromlist=[node_info['class']])
#             node_class = getattr(module, node_info['class'])
#         else:
#             # Assume it's already imported in globals
#             node_class = globals()[node_info['class']]
        
#         # Merge defaults with provided kwargs
#         node_config = {**node_info['defaults'], **kwargs}
#         node_config['name'] = name
#         node_config['inputs'] = inputs or {}
        
#         # Create and add the node
#         node = node_class(**node_config)
#         self._nodes[name] = node
#         return self
    
#     def node(self, node: NodeConfig, **kwargs) -> 'GraphNodeConfigBuilder':
#         """Add a pre-configured node to the graph."""
#         for key, value in kwargs.items():
#             if value:
#                 node.__setattr__(key, value)
                
#         self._nodes[node.name] = node
#         return self
    
#     # Specific methods with full type hints and autocomplete
#     def llm_chain(
#         self,
#         name: str,
#         user_prompt: str,
#         output_schema: Optional[List[str]] = None,
#         model: str = "beegen-v1",
#         parser: Optional[str] = "xml",
#         system_prompt: Optional[str] = None,
#         inputs: Dict[str, Any] = None,
#         start: bool = False,
#         end: bool = False,
#         **kwargs
#     ) -> 'GraphNodeConfigBuilder':
#         """Add an LLM chain node to the graph."""
#         # from beeflow.nodes.templates.llm_chain_node import LLMChainNodeConfig
        
#         return self.add_node(
#             "llm_chain",
#             name,
#             inputs=inputs,
#             model=model,
#             system_prompt=system_prompt,
#             user_prompt=user_prompt,
#             parser=parser,
#             output_schema=output_schema or [],
#             start=start,
#             end=end,
#             **kwargs
#         )
        
#     def retriever(
#         self,
#         name: str,
#         collection: str,
#         embed_model: str = "bge-m3",
#         rerank_model: str = "bge-m3",
#         milvus: str = "chatbot-libra",
#         mongo: str = "aicenter-chatbot",
#         mongo_collection: str = "chunk_data",
#         use_rerank=True,
#         inputs: Dict[str, Any] = None,
#         start: bool = False,
#         end: bool = False,
#         **kwargs
#     ) -> 'GraphNodeConfigBuilder':
#         """Add a retriever node to the graph."""
#         # from beeflow.nodes.templates.retriever_node import RetrieverNodeConfig

#         return self.add_node(
#             "retriever",
#             name,
#             inputs=inputs,
#             embed_model=embed_model,
#             rerank_model=rerank_model,
#             milvus=milvus,
#             collection=collection,
#             mongo=mongo,
#             mongo_collection=mongo_collection,
#             use_rerank=use_rerank,
#             start=start,
#             end=end,
#             **kwargs
#         )
        
#     def custom(
#         self, 
#         name: str, 
#         core: Callable, 
#         start: bool = False,
#         end: bool = False,
#         **kwargs
#     ) -> 'GraphNodeConfigBuilder':
#         """Add an LLM node to the graph."""
#         return self.add_node("custom", name, start=start, end=end, core=core, **kwargs)
    
#     def embedding(
#         self, 
#         name: str, 
#         model: str = "bge-m3", 
#         inputs: Dict[str, Any] = None, 
#         start: bool = False,
#         end: bool = False,
#         **kwargs
#     ) -> 'GraphNodeConfigBuilder':
#         """Add an Embedding node to the graph."""
#         return self.add_node("embedding", name, inputs=inputs, model=model, start=start, end=end, **kwargs)

#     def llm(
#         self, 
#         name: str, 
#         model: str, 
#         inputs: Dict[str, Any] = None, 
#         start: bool = False,
#         end: bool = False,
#         **kwargs
#     ) -> 'GraphNodeConfigBuilder':
#         """Add an LLM node to the graph."""
#         return self.add_node("llm", name, inputs=inputs, model=model, start=start, end=end, **kwargs)
    
#     def embedding(
#         self, 
#         name: str, 
#         model: str = "bge-m3", 
#         inputs: Dict[str, Any] = None, 
#         start: bool = False,
#         end: bool = False,
#         **kwargs
#     ) -> 'GraphNodeConfigBuilder':
#         """Add an Embedding node to the graph."""
#         return self.add_node("embedding", name, inputs=inputs, model=model, start=start, end=end, **kwargs)

#     def rerank(
#         self, 
#         name: str, 
#         model: str = "bge-m3", 
#         inputs: Dict[str, Any] = None, 
#         start: bool = False,
#         end: bool = False,
#         **kwargs
#     ) -> 'GraphNodeConfigBuilder':
#         """Add a Reranking node to the graph."""
#         return self.add_node(
#             "rerank", 
#             name, 
#             inputs=inputs, 
#             model=model, 
#             start=start, 
#             end=end, 
#             **kwargs
#         )
        
#     def prompt(
#         self, 
#         name: str, 
#         user_prompt: str, 
#         inputs: Dict[str, Any] = None, 
#         system_prompt: Optional[str] = None, 
#         start: bool = False,
#         end: bool = False,
#         **kwargs
#     ) -> 'GraphNodeConfigBuilder':
#         """Add a Prompt node to the graph."""
#         return self.add_node(
#             "prompt",
#             name,
#             inputs=inputs, 
#             user_prompt=user_prompt, 
#             system_prompt=system_prompt, 
#             start=start, 
#             end=end, 
#             **kwargs
#         )
        
#     def code(
#         self, 
#         code_fn: Union[Callable, str], 
#         name: str = None,
#         inputs: Dict[str, Any] = None, 
#         start: bool = False,
#         end: bool = False,
#         **kwargs
#     ) -> 'GraphNodeConfigBuilder':
#         """Add a Code Interpreter node to the graph.""" 
#         if not name:
#             name = code_fn.__name__               
#         return self.add_node("code", name, inputs=inputs, code_fn=code_fn, start=start, end=end, **kwargs)

#     def parser(
#         self, 
#         name: str, 
#         format: 'ParserType', 
#         output_schema: List[str], 
#         inputs: Dict[str, Any] = None, 
#         start: bool = False,
#         end: bool = False,
#         **kwargs
#     ) -> 'GraphNodeConfigBuilder':
#         """Add a Parser node to the graph."""
#         return self.add_node(
#             "parser", 
#             name,
#             inputs=inputs, 
#             format=format, 
#             output_schema=output_schema, 
#             start=start, 
#             end=end, 
#             **kwargs
#         )
        
#     def milvus(
#         self, 
#         name: str, 
#         model: str, 
#         operation: 'MilvusOperation', 
#         inputs: Dict[str, Any] = None, 
#         start: bool = False,
#         end: bool = False,
#         **kwargs
#     ) -> 'GraphNodeConfigBuilder':
#         """Add a Milvus node to the graph."""
#         return self.add_node(
#             "milvus", 
#             name, 
#             inputs=inputs, 
#             model=model, 
#             operation=operation, 
#             start=start, 
#             end=end, 
#             **kwargs
#         )
        
#     def mongo(
#         self, 
#         name: str, 
#         model: str, 
#         operation: 'MongoOperation', 
#         inputs: Dict[str, Any] = None, 
#         start: bool = False,
#         end: bool = False,
#         **kwargs
#     ) -> 'GraphNodeConfigBuilder':
#         """Add a MongoDB node to the graph."""
#         return self.add_node(
#             "mongo", 
#             name, 
#             inputs=inputs, 
#             model=model, 
#             operation=operation, 
#             start=start, 
#             end=end, 
#             **kwargs
#         )
        
#     def branch(
#         self, 
#         name: str, 
#         cases: Dict[str, str] = {}, 
#         default_target: Optional[str] = None,
#         inputs: Dict[str, Any] = None,
#         start: bool = False,
#         end: bool = False,
#         **kwargs
#     ) -> 'GraphNodeConfigBuilder':
#         """Add a Branch node to the graph."""
#         return self.add_node(
#             "branch",
#             name,
#             inputs=inputs,
#             cases=cases,
#             default_target=default_target,
#             start=start,
#             end=end,
#             **kwargs
#         )
        
#     def for_loop(
#         self,
#         name: str,
#         func_node: NodeConfig,
#         output_schema: List[str],
#         inputs: Dict[str, Any] = None,
#         start: bool = False,
#         end: bool = False,
#         **kwargs
#     ) -> 'GraphNodeConfigBuilder':
#         """Add a ForLoop node that wraps another node for batch processing."""
#         return self.add_node(
#             "for_loop",
#             name,
#             inputs=inputs,
#             func_node=func_node,
#             output_schema=output_schema,
#             start=start,
#             end=end,
#             **kwargs
#         )
    
#     # Edge management methods
#     def edge(self, *nodes: str) -> 'GraphNodeConfigBuilder':
#         """Add edges between nodes in sequence."""
#         if len(nodes) < 2:
#             raise ValueError("At least 2 nodes are required to create an edge")
        
#         for i in range(len(nodes) - 1):
#             self._edges.append((nodes[i], nodes[i + 1]))
#         return self
    
#     def fork(self, source: str, targets: List[str]) -> 'GraphNodeConfigBuilder':
#         """Add edges from source to multiple targets."""
#         for target in targets:
#             self._edges.append((source, target))
#         return self

#     def merge(self, sources: List[str], target: str) -> 'GraphNodeConfigBuilder':
#         """Add edges from multiple sources to target."""
#         for source in sources:
#             self._edges.append((source, target))
#         return self
    
#     # Graph metadata methods
#     def name(self, name: str) -> 'GraphNodeConfigBuilder':
#         """Set the name of the graph."""
#         self._name = name
#         return self
    
#     def description(self, description: str) -> 'GraphNodeConfigBuilder':
#         """Set the description of the graph."""
#         self._description = description
#         return self
    
#     def inputs(self, inputs: Dict[str, Any]) -> 'GraphNodeConfigBuilder':
#         """Set the inputs of the graph."""
#         self._inputs = inputs
#         return self
    
#     def build(self) -> 'GraphNodeConfig':
#         """Build and return a GraphNodeConfig object."""
#         return GraphNodeConfig(
#             name=self._name,
#             description=self._description,
#             nodes=self._nodes,
#             edges=self._edges,
#             inputs=self._inputs
#         )


# # Usage example with your existing code:
# async def main():
#     from beegen.registry.model_registry import ModelRegistry
#     from typing import Dict, Any, List
        
#     REWRITTEN_QUERY_PROMPT = """Mục tiêu: 
# - Viết lại đoạn hội thoại của người dùng thành một câu, vẫn mang đủ ý của khách hàng.

# Đầu ra định dạng (xml format):
# <query>câu query ngắn gọn được viết lại cho đủ ý của khách hàng</query>

# Example:
# Input:
# - lịch sử trò chuyện:
# ['Người dùng: chủ tịch của MB là ai ?', 'BOT: chủ tịch của MB là anh Lưu Trung Thái']
# - câu chat gần nhất: anh ấy tại vị được bao lâu rồi?

# Output (xml format):
# <query>Chủ tịch Lưu Trung Thái đã tại vị được bao lâu?</query>

# Các thông tin đầu vào:
# - lịch sử trò chuyện: 
# {history}
# - câu chat gần nhất: {query}"""

#     ANSWER_PROMPT = """Nhiệm vụ: Trả lời câu hỏi của người dùng dựa trên tài liệu được cung cấp

# Hướng dẫn:
# 1. Phân tích tài liệu và trả lời dựa trên thông tin trong tài liệu.
# 2. Nếu tài liệu không có đủ thông tin để trả lời chính xác, hãy nói: "Xin lỗi, tôi chưa có đủ thông tin để trả lời câu hỏi này."
# 3. Trả lời bằng tiếng Việt, lịch sự, không có nội dung bạo lực hoặc kích động.
# 4. Trích dẫn nguyên văn nội dung từ tài liệu khi cần thiết.
# 5. Sử dụng emoji phù hợp để tăng tính sinh động.
# 6. Nếu câu hỏi không nêu thời gian cụ thể, cung cấp thông tin mới nhất.
# 7. Khi cần thêm thông tin, hãy đặt câu hỏi để làm rõ yêu cầu của người dùng.
# 8. Không thêm câu chào hỏi, giới thiệu hay trích dẫn tài liệu không cần thiết.
# 9. Không trả lời các thông tin ngoài tài liệu được cung cấp.
# 10. Với đường link: 
# - Link thường: Giữ nội dung + link gốc
# - Link HTML: Giữ nguyên cấu trúc thẻ
# Ví dụ: <video preload="none"  width="250" height="150" controls><source src="https://beegen-portal.tanzu-dev.mbbank.com.vn/beegen-portal-be/public/multimedia/download/073be7db-28f3-4744-b33a-d2f7a69bd8a5" type="video/mp4"></video> 
# => kết quả giữ nguyên định dạng: <video preload="none"  width="250" height="150" controls><source src="https://beegen-portal.tanzu-dev.mbbank.com.vn/beegen-portal-be/public/multimedia/download/073be7db-28f3-4744-b33a-d2f7a69bd8a5" type="video/mp4"></video>
# Tài liệu:
# {documents}
# Câu hỏi: {query}"""

#     def format_messages(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
#         """
#         Returns:
#             query (str)
#             history (List)
#         """
#         query = messages[-1]['content']        
#         history = [
#             f"USER: {m['content']}" 
#             if m['role']=='user' 
#             else f"BOT: {m['content']}" 
#             for m in messages[-21:-1]
#         ]
        
#         return {
#             "query": query,
#             "history": history
#         }

#     def final_format(docs: List[Dict]) -> Dict[str, Any]:
#         """
#         Returns:
#             docs (List)
#             doc_text (str)
#         """
#         documents_text="\n[SEP]\n".join([d['content'] for d in docs])
#         return {
#             'docs': [r['doc'] for r in docs],
#             'doc_text': documents_text
#         }
    
#     config = (
#         GraphNodeConfigBuilder()
#             .name("basic_rag_flow")
#             .description("a basic rag flow: rewrite query -> embedding -> retrieve -> rerank -> response")
#             .inputs({"messages": "workflow01"})
#             .code(
#                 code_fn=format_messages, 
#                 inputs={"messages": "basic_rag_flow"}, 
#                 start=True
#             )
#             .llm_chain(
#                 name="rewrite_query",
#                 # model="gpt-4o",
#                 user_prompt=REWRITTEN_QUERY_PROMPT,
#                 output_schema=["query: str"],
#                 inputs={"query": "format_messages"}
#             )
#             .retriever(
#                 name="retriever0",
#                 collection="bot_4aa0843a_46d2_4acf_8b96_84d0d144a862",
#                 top_k=5,
#                 inputs={"query": "rewrite_query", "partition_names": ["QA"]}
#             )
#             .code(
#                 code_fn=final_format, 
#                 inputs={"docs": "retriever0"}
#             )
#             .llm_chain(
#                 name="final_response",
#                 # model="gpt-4o",
#                 user_prompt=ANSWER_PROMPT,
#                 inputs={
#                     "query": "rewrite_query",
#                     "documents": {"final_format": "doc_text"}
#                 },
#                 end=True
#             )
#             .edge("format_messages", "rewrite_query", "retriever0", "final_format", "final_response")
#             .build()
#     )
        

# if __name__ == "__main__":
#     import asyncio
#     asyncio.run(main())
# endregion