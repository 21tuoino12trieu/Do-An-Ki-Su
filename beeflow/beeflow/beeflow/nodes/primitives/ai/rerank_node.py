from beeflow.nodes.base_node import BaseNode
from beeflow.configs import NodeConfig, NodeType
from beegen.tools.schema.param import ParamSet
from beegen.registry.resource_hub import ResourceHub
from typing import Dict, Any, List, Optional


class RerankNodeConfig(NodeConfig):
    """Configuration for Reranking node in the workflow."""
    model: str

class RerankNode(BaseNode):
    """Class for rerank node in the beeflow graph"""
    
    type: NodeType = "rerank"
    
    input_schema: ParamSet = (
        ParamSet.new()
            .var("query: str", required=True)
            .var("documents: List", required=True)
            .var("top_k: int = -1")
            .var("threshold: float = 0.0")
            .build()
    )
    
    output_schema: ParamSet = (
        ParamSet.new()
            .var("reranks: List[Dict]")
            .build()
    )
    
    __slots__ = [
        'resource_key',      # The reranking model name/identifier
        'top_k',      # Number of top results to return
        'threshold',  # Minimum score threshold for results
        'backend'     # Reference to the reranker service
    ]
    
    def __init__(
        self,
        resource_key: Optional[str] = None,
        **kwargs
    ):
        """Initialize RerankNode from either config or kwargs.
        
        Args:
            model: Reranking model name (required if config not provided)
            **kwargs: Additional keyword arguments for NodeConfig
        """
        super().__init__(**kwargs) 
                
        self.resource_key = resource_key
        self.backend = ResourceHub.self().reranker(self.resource_key)
        self.core = self._process
        
    async def _process(
        self,
        query: str,
        documents: List,
        top_k: int,
        threshold: float
    ) -> Dict[str, Any]:
        is_dict = False
        if not documents:  # Check if the list is empty
            # Handle empty list case
            return {"reranks": []}
        
        elif isinstance(documents[0], str):
            # documents is a List[str]
            texts = documents
        elif isinstance(documents[0], dict):
            is_dict = True
            # documents is a List[Dict]
            # Extract text field from each dictionary
            texts = [doc.get('content', '') for doc in documents]
        else:
            # Handle unexpected type
            raise TypeError(f"Expected documents to be List[str] or List[Dict], got list of {type(documents[0]).__name__}")

        results = await self.backend.run(
            query = query,
            texts = texts,
            top_k = top_k if top_k > 0 else len(texts),
            threshold = threshold
        )
        
        reranked_docs = []
        
        for r in results:
            if is_dict:   
                reranked_docs.append({
                    **documents[r['index']],
                    "score": r['score']
                })
            else:
                reranked_docs.append({
                    "content": documents[r['index']],
                    "score": r['score']
                })
             
        return {
            "reranks": reranked_docs
        }
        
    def specific_metadata(self) -> Dict[str, Any]:
        """Return rerank-specific metadata dictionary."""
        return {
            "model": self.resource_key
        }
        

async def main():
    from beeflow.states.workflow_indexer import WorkflowIndexer
    from beeflow.states.workflow_state import WorkflowState
    from beeflow.nodes.base_node import INPUT, OUTPUT
    
    rerank_node = RerankNode(
        name="rerank0",
        resource_key="bge-m3",
        inputs={"query": INPUT, "documents": INPUT, "top_k": INPUT},
        outputs=OUTPUT,
    )
    
    indexer = WorkflowIndexer(name="workflow01").add_node(rerank_node).build()
        
    state = WorkflowState(
        indexer=indexer, 
        inputs={
            "top_k": 2,
            "query": "Thời gian xử lý và cung cấp giấy báo có cho giao dịch chuyển tiền nhanh 247 qua Napas là bao lâu?",
            "documents": [
            {"id": 1, "content": """File tài liệu: Quy định về giao dịch chuyển tiền nhanh 247
Câu hỏi: Thời gian xử lý tra soát giao dịch chuyển 
tiền nhanh 247 qua Napas là bao lâu?
Câu trả lời: Tối đa 04 ngày làm việc (không tính thứ 7, chủ nhật và ngày nghỉ lễ)"""},

            {"id": 2, "content": """File tài liệu: Hướng dẫn giao dịch ngân hàng điện tử
Câu hỏi: Phí giao dịch chuyển tiền nhanh 247 là bao nhiêu?
Câu trả lời: Miễn phí cho giao dịch dưới 500.000 VND, 11.000 VND cho giao dịch trên 500.000 VND"""},

            {"id": 3, "content": """File tài liệu: Chính sách khách hàng ưu tiên
Câu hỏi: Khách hàng VIP được ưu đãi gì khi chuyển tiền 247?
Câu trả lời: Miễn phí toàn bộ giao dịch chuyển tiền 247, không giới hạn số tiền"""},

            {"id": 4, "content": """File tài liệu: Quy trình xử lý khiếu nại
Câu hỏi: Quy trình xử lý tra soát giao dịch lỗi là gì?
Câu trả lời: Tiếp nhận yêu cầu, xác minh thông tin trong 24h, phản hồi kết quả trong 04 ngày làm việc"""},

            {"id": 5, "content": """File tài liệu: Hạn mức giao dịch
Câu hỏi: Hạn mức chuyển tiền 247 qua Napas là bao nhiêu?
Câu trả lời: Tối đa 500 triệu VND/giao dịch và 2 tỷ VND/ngày"""},

            {"id": 6, "content": """File tài liệu: Thời gian hoạt động dịch vụ
Câu hỏi: Thời gian hoạt động của dịch vụ chuyển tiền 247?
Câu trả lời: Hoạt động 24/7, kể cả ngày nghỉ và ngày lễ"""},

            {"id": 7, "content": """File tài liệu: Hướng dẫn tra soát giao dịch
Câu hỏi: Cách thức gửi yêu cầu tra soát giao dịch?
Câu trả lời: Khách hàng có thể gửi yêu cầu qua email, tổng đài 24/7 hoặc trực tiếp tại quầy"""},

            {"id": 8, "content": """File tài liệu: Quy định về bằng chứng giao dịch
Câu hỏi: Giấy báo có được cung cấp như thế nào?
Câu trả lời: Được cung cấp qua email trong vòng 04 ngày làm việc sau khi nhận yêu cầu"""},

            {"id": 9, "content": """File tài liệu: Chính sách hoàn tiền
Câu hỏi: Thời gian hoàn tiền cho giao dịch lỗi?
Câu trả lời: Tối đa 07 ngày làm việc sau khi có kết quả tra soát"""},

            {"id": 10, "content": """File tài liệu: Quy định về xác thực giao dịch
Câu hỏi: Phương thức xác thực giao dịch chuyển tiền 247?
Câu trả lời: Soft OTP hoặc Smart OTP, tùy theo đăng ký của khách hàng"""}
            ]
        }
    )
    
    result = await rerank_node.run(state=state)
    
    print(rerank_node.trace_data(state, None))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())