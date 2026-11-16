import asyncio
import uuid
from beeflow.nodes.templates.basic_chain_node import BasicChainNode
from beeflow.nodes.base_node import INPUT, OUTPUT, START, END
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.workflow_state import WorkflowState
from beeflow.workflow import WorkflowEngine
from pprint import pprint

from beeflow.nodes.templates.agent_executor_node import AgentExecutorNode
from beegen.prompts.prompt_manager import PromptManager
from examples.utils.nlp import encode_to_base64

from examples.workflow_cua import BeeCUA
from examples.workflow_rag import BeeRAG

wf_cua = BeeCUA(bot_id="71eff3f6-1fc4-48c4-8ca8-df836d26d4c5").workflow
wf_rag = BeeRAG(bot_id="71eff3f6-1fc4-48c4-8ca8-df836d26d4c5").workflow

async def main():

    with WorkflowEngine(name="test_multi-agent_workflow") as wf_multi:
        orchestration_agent = BasicChainNode(
            name="orchestration_agent",
            resource_key="qwen-instruct-chat",
            system_prompt="""
                Bạn là một chuyên gia lựa chọn workflow và trả về tham số phù hợp. 
                Bạn có 2 workflow sau:

                1. wf_cua: Bóc tách schema của tài liệu
                - document_key: S3 key của tài liệu. Định dạng string.
                - document_id: ID tương ứng với document_key, được tạo bằng cách encode base64 của document_key. Định dạng string.

                2. wf_rag: Truy vấn thông tin về thuế phí
                - messages: Câu hỏi cần truy vấn. Định dạng List[Dict]. Ví dụ [{{"role": "user", "content": "Quy định về hoàn thuế giá trị gia tăng đối với dự án đầu tư của cơ sở kinh doanh ngành, nghề đầu tư kinh doanh có điều kiện"}}]
                - custom_data: Thông tin bổ sung bạn muốn ghi chú. Định dạng dict[string, string].

                Lưu ý:
                - Format trả về: JSON với 2 trường bắt buộc là `workflow_name` và `workflow_inputs`.
                - Không trả về bất kỳ thông tin nào khác ngoài JSON đó.

                Ví dụ:

                Câu hỏi người dùng: 
                "Tôi muốn bóc tách schema cho tài liệu có key là rnd/thaivd/work/cua/origin/sample2.pdf"

                Kết quả phải trả về:

                {{
                    "workflow_name": "wf_cua",
                    "workflow_inputs": {{
                        "document_key": "rnd/thaivd/work/cua/origin/sample2.pdf",
                        "document_id": "encode_base64_document_key"
                    }}
                }}
            """,
            user_prompt="{query}",
            inputs={
                "query": INPUT,
            },
            parser="json",
            extract_schema=["workflow_name: str", "workflow_inputs: dict"]
        )

        agent_node = AgentExecutorNode(
            name="agent_test",
            available_workflows={"wf_rag": wf_rag, "wf_cua": wf_cua},
            inputs=orchestration_agent
        )

        START >> orchestration_agent >> agent_node >> END
    wf_multi.compile()
    results = await wf_multi.run(
            inputs={"query": "Tôi muốn bóc tách schema cho tài liệu rnd/thaivd/work/cua/origin/sample1.jpg"},
            request_id=str(uuid.uuid4())
        )
    pprint(results)

if __name__ == "__main__":
    asyncio.run(main())
