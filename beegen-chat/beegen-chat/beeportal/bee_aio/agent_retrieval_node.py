from typing import Dict, List, Any, Optional

from beeflow.nodes.base_node import END, START, INPUT, OUTPUT
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.configs.node_config import NodeType
from beeflow.configs.graph_config import GraphNodeConfig
from beegen.loggings import LOGGER

# ── Pure functions ────────────────────────────────────────────────────────────

def build_all_agent_texts(metadata: Dict) -> Dict[str, Any]:          
    valid_agents: List[Dict[str, Any]] = []
    for agent in metadata["agents"]:                                
        desc    = agent.get("description", "")
        keyword = agent.get("keywords", [])              
        if not desc:
            continue
        content = f"{desc} | keyword: {', '.join(keyword)}" if keyword else desc
        valid_agents.append({**agent, "content": content})

    LOGGER.info(
        "[AgentRetrievalNode] build_texts — valid=%d / total=%d",
        len(valid_agents),
        len(metadata["agents"]),
    )
    return {"valid_agents": valid_agents}


def prepare_rerank_docs(
    valid_agents: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {"documents": [a["content"] for a in valid_agents]}


def map_rerank_to_agents(
    reranks: List[Dict[str, Any]],
    valid_agents: List[Dict[str, Any]],
) -> Dict[str, Any]:
    content_to_agent = {a["content"]: a for a in valid_agents}
    candidates = []
    for r in reranks:
        content = r.get("content", "")
        agent = content_to_agent.get(content)
        if agent:
            candidate = {k: v for k, v in agent.items()}
            candidate["score"] = r.get("score", 0)
            candidates.append(candidate)

    LOGGER.info(
        "[AgentRetrievalNode] map_rerank — matched=%d / total=%d",
        len(candidates),
        len(reranks),
    )
    return {"candidates": candidates}


def build_agent_context(
    candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    lines = []
    for a in candidates:
        parts = [f'- bot_id: "{a["bot_id"]}"']
        if a.get("name"):
            parts.append(f'name: "{a["name"]}"')
        parts.append(a["content"])
        lines.append(" | ".join(parts))
    agent_context = "\n".join(lines) if lines else "Không có agent phù hợp."

    return {
        "final_candidates": candidates,
        "agent_context":    agent_context,
    }


# ── Config ────────────────────────────────────────────────────────────────────

class AgentRetrievalNodeConfig(GraphNodeConfig):
    type:      NodeType = "agent_retrieval"
    embedding: str      = "bge-m3"
    top_k:     int      = 5


# ── Node ──────────────────────────────────────────────────────────────────────

class AgentRetrievalNode(GraphNode):
    type: NodeType = "graph"

    def __init__(
        self,
        embedding: Optional[str] = "bge-m3",
        redis:     Optional[str] = "aicenter-chatbot",
        top_k:     Optional[int] = 5,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.embedding = embedding
        self.redis     = redis
        self.top_k     = top_k
        self._build_graph()

    def _build_graph(self):
        from beeflow.nodes import CodeNode, START, END, INPUT, OUTPUT
        from beeflow.nodes.primitives.ai.rerank_node import RerankNode

        with self:
            _build_texts = CodeNode(
                name="build_agent_texts",
                code_fn=build_all_agent_texts,
                inputs={"metadata": INPUT},                            
                return_keys=["valid_agents: List[Dict]"],
            )

            _prepare_docs = CodeNode(
                name="prepare_rerank_docs",
                code_fn=prepare_rerank_docs,
                inputs={"valid_agents": _build_texts["valid_agents"]},
                return_keys=["documents: List[str]"],
            )

            _rerank = RerankNode(
                name="rerank",
                resource_key=self.embedding,
                inputs={
                    "query":     {INPUT: "query"},
                    "documents": _prepare_docs["documents"],
                    "top_k":     self.top_k,
                    "threshold": 0.0,
                },
            )

            _map_results = CodeNode(
                name="map_rerank_to_agents",
                code_fn=map_rerank_to_agents,
                inputs={
                    "reranks":      _rerank["reranks"],
                    "valid_agents": _build_texts["valid_agents"],
                },
                return_keys=["candidates: List[Dict]"],
            )

            _build_context = CodeNode(
                name="build_context",
                code_fn=build_agent_context,
                inputs={"candidates": _map_results["candidates"]},
                return_keys=["final_candidates: List[Dict]", "agent_context: str"],
                outputs=OUTPUT,
            )

            START >> _build_texts >> _prepare_docs >> _rerank >> _map_results >> _build_context >> END

        self.build()


# ── Test ──────────────────────────────────────────────────────────────────────

async def main():
    from beeflow.workflow import WorkflowEngine

    with WorkflowEngine(
        name="test-agent-retrieval",
        description="Test AgentRetrievalNode",
    ) as test_wf:

        agent_retrieval = AgentRetrievalNode(
            name="agent_retrieval",
            inputs=INPUT,
            outputs=OUTPUT,
        )

        START >> agent_retrieval >> END

    test_wf.compile()

    result = await test_wf.run(
        inputs={
            "query": "Tôi muốn hỏi về chính sách vay mua nhà",
            "metadata": {            
                        "agents": [
                {
                    "bot_id":      "347f7a6e-83d2-4cfa-9e85-6bc080c234c4",
                    # "name":        "deposit",
                    "description": "Bot deposit chuyên cung cấp thông tin chính xác và chi tiết về các sản phẩm gửi tiền (deposit), bao gồm lãi suất, điều kiện gửi tiền và các chính sách liên quan đến huy động vốn cho cán bộ nhân viên.",
                    # "keyword":    ["vay", "thẻ", "tiết kiệm", "app MB", "KHCN"],
                    # "role":        ["QM", "MY VIP", "SPK", "CRU", "APP"],
                },
                {
                    "bot_id":      "dfb5a874-b980-4275-bd34-0ddbd1acefdf",
                    # "name":        "AI_Enterprise_KHCN",
                    "description": "Agent chuyên trả lời câu hỏi liên quan đến policy sản phẩm vay, tín dụng",
                    "keyword":    ["policy", "tín dụng", "điều kiện vay", "quy định"],
                    # "role":        ["L1", "Team 2", "Team 3"],
                },
                {
                    "bot_id":      "269c75a7-b3dc-4a34-ae6f-a337ad7e8d34",
                    # "name":        "BeeRM",
                    "description": "Agent hỗ trợ tra cứu chính sách của MB, pháp luật",
                    "keyword":    ["chính sách", "pháp luật"],
                    # "role":        ["L1"],
                },
                {
                    "bot_id":      "a1b2c3d4-0005-0005-0005-000000000005",
                    # "name":        "CHATBOT_RM/UB",
                    "description": "Agent hỗ trợ doanh nghiệp về thanh toán quốc tế, L/C, chuyển tiền ngoại tệ",
                    "keyword":    ["doanh nghiệp", "thanh toán quốc tế", "chuyển tiền ngoại tệ", "L/C"],
                    # "role":        ["L1", "L2", "L3"],
                }
                ]
            }
        }
    )

    print("=" * 60)
    print(f"Candidates returned: {len(result['final_candidates'])}")
    print()
    print("Candidates (sorted by relevance):")
    for i, a in enumerate(result["final_candidates"], 1):
        score = round(a.get("score", 0), 4)
        print(f"  {i}. [{a['bot_id'][:8]}...] score={score} | {a['description'][:60]}")
    print()
    print("Agent context (gửi vào LLM):")
    print(result["agent_context"])
    print("=" * 60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())