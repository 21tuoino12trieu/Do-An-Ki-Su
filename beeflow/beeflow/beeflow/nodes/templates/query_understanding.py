from typing import Dict, List, Optional

from beeflow.nodes.base_node import INPUT, OUTPUT
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.configs.node_config import NodeType
from beegen.tools.schema.param import ParamSet
from beegen.loggings import LOGGER
import json as json_lib

TERM_SELECTION_QUERY = """
Bạn là một AI Data Architect chuyên phân tích ý định người dùng và chọn thuật ngữ nghiệp vụ phù hợp.
Nhiệm vụ của bạn là đọc câu hỏi của người dùng, đối chiếu với danh sách các 'Business Terms' được cung cấp, và chọn ra những term thực sự phù hợp.

### QUY TẮC BẮT BUỘC:
1. Chỉ chọn thuật ngữ thật sự khớp với câu hỏi, phải thỏa mãn ĐỒNG THỜI cả hai điều kiện:
   - **Điều kiện 1 (Từ ngữ):** `term_name` xuất hiện trực tiếp trong câu hỏi, HOẶC câu hỏi mô tả đúng khái niệm mà description của thuật ngữ đó định nghĩa.
   - **Điều kiện 2 (Ngữ nghĩa):** Thuật ngữ đó thực sự cần thiết để làm rõ ý định câu hỏi, không chỉ liên quan gián tiếp hay cùng lĩnh vực.
   - Ví dụ: "CIR của MB trong 3 tháng đầu năm 2025 là bao nhiêu?"
     - Chọn `CIR` — xuất hiện trong câu hỏi và cần thiết để hiểu ý định.
     - Không chọn `MBS` — dù cùng hệ sinh thái MB nhưng không xuất hiện trong câu hỏi và không cần thiết để hiểu ý định.
2. Nếu KHÔNG CÓ term nào phù hợp, trả về JSON có dạng: selected_terms là mảng rỗng.
3. Trả về JSON với trường "selected_terms" là mảng các object, mỗi object giữ nguyên các trường: term_name, description, similarity_score.
4. Chỉ được chọn trong danh sách Business Terms được cung cấp, không tự thêm từ khóa và mô tả.

### CÂU HỎI NGƯỜI DÙNG:
{query}

### DANH SÁCH BUSINESS TERMS:
{context_terms}
"""


def build_vector_search_query(emb_result: List, role_ids: List[str]) -> Dict:
    """
    Build SQL query for vector search with role-based filtering.

    Args:
        emb_result: List of embedding vectors from EmbeddingNode.
                     Each inner list contains 1024 float values.
        role_ids: List of role IDs to filter business terms.

    Returns:
        Dict with 'query' (SQL string) and 'params' (list of parameters).
    """
    if not emb_result or not isinstance(emb_result, list):
        return {"query": "SELECT NULL LIMIT 0", "params": []}

    # Flatten: List[List[100]] -> List[1024] (thử không duỗi mà lưu or truyền thẳng thì bị lỗi)
    query_embedding = [val for sublist in emb_result for val in sublist]

    if not query_embedding:
        return {"query": "SELECT NULL LIMIT 0", "params": []}

    embedding_json = json_lib.dumps(query_embedding)

    # Build role_ids filter using array overlap operator
    placeholders = ','.join(['%s'] * len(role_ids))
    role_filter = f"role_ids && ARRAY[{placeholders}]::text[]"

    sql_query = f"""
        SELECT
            id,
            term_name,
            description,
            1 - (embedding <=> %s::vector) AS similarity_score
        FROM meta.business_term_mapping
        WHERE embedding IS NOT NULL
        AND {role_filter}
        AND 1 - (embedding <=> %s::vector) > 0.4
        ORDER BY embedding <=> %s::vector
    """
    params = [embedding_json] + role_ids + [embedding_json, embedding_json]
    return {
        "query": sql_query,
        "params": params
    }



class QueryUnderstandingNode(GraphNode):
    """
    Query Understanding Agent - Vector search + LLM annotate.

    This node performs semantic search on business terms and uses LLM to
    rewrite and annotate the user query with relevant context.
    """
    type: NodeType = "query_understanding"

    input_schema: ParamSet = (
        ParamSet.new()
            .var("query: str", required=True, description="User query to understand and rewrite.")
            .var("role_ids: List[str]", required=True, description="List of role IDs for filtering business terms.")
            .build()
    )

    output_schema: ParamSet = (
        ParamSet.new()
            .var("selected_terms: List[Dict]", description="List of selected business terms with term_name, description, similarity_score.")
            .build()
    )

    def __init__(
        self,
        embedding: Optional[str] = "bge-m3",
        resource_key: Optional[str] = "gpt-4.1",
        sql_resource: Optional[str] = "anapp",
        limit: int = 5,
        **kwargs
    ):
        """
        Initialize QueryUnderstandingNode.

        Args:
            embedding: Resource key for embedding model.
            llm: Resource key for LLM model.
            sql_resource: Resource key for SQL connection.
            limit: Number of business terms to search from database.
            **kwargs: Additional keyword arguments for GraphNode.
        """
        super().__init__(**kwargs)

        self.embedding = embedding
        self.resource_key = resource_key
        self.sql_resource = sql_resource
        self.limit = limit

        self._build_graph()

    def _build_graph(self):
        from beeflow.nodes import (
            CodeNode, EmbeddingNode, SQLNode, BasicChainNode,
            START, END, INPUT, OUTPUT
        )
        from beegen.configs.storage.sql_config import SQLOperation  

        def sub(suffix: str):
            return suffix

        with self:
            # Generate embedding for user query
            emb_generate_query = EmbeddingNode(
                name=sub("emb_generate_query"),
                resource_key=self.embedding,
                inputs={"texts": INPUT["query"]}
            )

            # Build vector search query
            code_build_search_query = CodeNode(
                name=sub("code_build_search_query"),
                code_fn=build_vector_search_query,
                inputs={
                    "emb_result": {emb_generate_query: "embeddings"},
                    "role_ids": INPUT["role_ids"]
                },
                return_keys=["query: str", "params: list"]
            )

            # Vector search to find similar business terms
            sql_search_terms = SQLNode(
                name=sub("sql_search_terms"),
                operation=SQLOperation.QUERY,
                resource_key=self.sql_resource,
                inputs={
                    "query": code_build_search_query["query"],
                    "params": code_build_search_query["params"],
                    "limit": self.limit
                }
            )

            # LLM select appropriate terms from search results
            llm_select_terms = BasicChainNode(
                name=sub("llm_select_terms"),
                resource_key=self.resource_key,
                user_prompt=TERM_SELECTION_QUERY,
                parser="json",
                extract_schema=["selected_terms: list"],
                inputs={
                    "context_terms": sql_search_terms["data"],
                    "query": INPUT["query"]
                },
                llm_configs={"reasoning_effort": "none"},
                outputs={"selected_terms": OUTPUT},
                stream=False
            )

            # Connect nodes
            START >> emb_generate_query >> code_build_search_query >> sql_search_terms >> llm_select_terms >> END

        self.build()


async def main():
    from beeflow.states import WorkflowState, WorkflowIndexer

    query_understanding = QueryUnderstandingNode(
        name="query_understanding",
        inputs=INPUT,
        outputs=OUTPUT
    )

    indexer = WorkflowIndexer(name="query_understanding").add_node(query_understanding).build()

    state = WorkflowState(
        indexer=indexer,
        inputs={
            "query": "Tính đến tháng 6/2025 lợi nhuận trước thuế của MB AMC là bao nhiêu tỷ?",
            "role_ids": ["TCKT", "LOG_APP"]
        }
    )

    try:
        result = await query_understanding.run(state=state)
        print("Query Understanding Result:")
        print(result)
    except Exception as e:
        LOGGER.error(f"Workflow execution failed: {e}", exc_info=True)
        print(f"Error during execution: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
