import asyncio

# At the top of your main file, before any other imports
import json
from typing import List, Dict, Any
from beegen.utils.common import fake_chunk_from
from beegen.registry.resource_hub import RESOURCE_HUB
from beegen.prompts.prompt_manager import PromptManager
from beegen.loggings.loggers import LOGGER
from beeflow.workflow import WorkflowEngine
from beeflow.nodes.templates.basic_chain_node import BasicChainNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes.base_node import END, START, OUTPUT, INPUT
from beeportal.bot_text2metadata.text2metadata.nlp import annotate_query, init_query
from beeportal.bot_text2metadata.text2metadata.metadata import parse_tool_calls_from_llm, build_search_params_for_generation, fetch_sample_data
from typing import Any, Dict, List
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.configs.mcp.mcp_config import MCPMethod
from beeflow.nodes import START, END, INPUT, LLMNode, BranchNode, CodeNode, ParserNode, MCPGatewayNode

PROMPTS = PromptManager("text2metadata")

def format_initial_prompt(rewrite: str) -> Dict[str, Any]: 
    """ CodeNode: Chuẩn bị prompt đầu tiên cho LLM. """ 
    return {"template": [{"role": "system", "content": PROMPTS["TEXT2META:SEARCH_TOOL_SELECTION_PROMPT"]}, 
                         {"role": "user", "content": rewrite}]}

class Text2MetadataBot:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        mongo_engine = RESOURCE_HUB.sync_mongo("aicenter-chatbot")
        result = mongo_engine._find_one(
            collection_name="botinfo", query={"_id": self.bot_id})
        self.name = result.get('data', {'name': {}}).get('name', None)
        self.config = result.get('data', {'metadata': {}}).get('metadata', {})

        self.definition = self.config.get(
            'system_prompt', "không có mô tả nào được cung cấp")

        self._build_flow()

    def _build_flow(self):
        with WorkflowEngine(
            name="text2metadata",
            description="Đây là luồng chat standard của bot text2metadata",
        ) as text2metadata_workflow:
            init_query_node = CodeNode(
                name="init_query_node",
                code_fn=init_query, 
                inputs={"messages": INPUT},
                # return_keys=["origin_query: str", "conversation: List"]
            )

            annotate_query_node = CodeNode(
                name="annotate_query_node",
                code_fn=annotate_query,
                inputs={"origin_query": init_query_node},
                return_keys=["query: str"]
            )

            rewrite_and_intent_node = BasicChainNode(
                name="rewrite_and_intent_node",
                resource_key="gpt-4.1",
                user_prompt=PROMPTS["TEXT2META:REWRITE_AND_CLASSIFY_PROMPT"],
                inputs={
                    "query": annotate_query_node,
                    "conversation": init_query_node
                },
                extract_schema=["rewrite: str", "intent: str", "reasoning: str"],
                parser="yaml",
                stream=True
            )

            route_flow_branch = BranchNode(
                name="route_flow",
                cases={
                    "intent == 'search_or_generate'": "format_prompt",
                    "intent == 'confirm_update'": "flow2_extract_update_metadata"
                },
                default="error_unknown_intent",
                inputs={"intent": rewrite_and_intent_node["intent"]}
            )

            error_unknown_intent = LLMNode(
                name="error_unknown_intent",
                resource_key="gemini-2.5-flash-chat",
                instant_response=True,
                inputs={"response": "Xin lỗi, tôi chưa hiểu rõ ý định của bạn. Bạn có thể diễn đạt lại được không?"},
                stream=True
            )

            # FLOW 1: SEARCH OR GENERATE

            prompt_node = CodeNode(
                name="format_prompt",
                code_fn=format_initial_prompt,
                inputs={"rewrite": rewrite_and_intent_node["rewrite"]},
                return_keys=["template: List"]
            )

            flow1_tool_selection = LLMNode(
                name="flow1_tool_selection",
                resource_key="gpt-4.1",
                inputs={"messages": prompt_node["template"], "tool_choice": "auto"}
            )

            parser = ParserNode(
                name="parser",
                format="json",
                inputs={"text": flow1_tool_selection["content"]},
                extract_schema=["tool_calls"],
                # outputs={"answer": OUTPUT}
            )

            flow1_parse_tool = CodeNode(
                name="flow1_parse_tool",
                code_fn=parse_tool_calls_from_llm,
                inputs={"tool_calls_json": parser["tool_calls"]},
                return_keys=["tool_name: str", "tool_params: dict", "error: str"]
            )

            # Execute tool (search/get_entity_details/get_entity_lineage)
            flow1_mcp_search = MCPGatewayNode(
                name="flow1_mcp_search",
                resource_key="openmetadata",
                method=MCPMethod.CALL,
                inputs={
                    "tool_name": flow1_parse_tool["tool_name"],
                    "tool_params": flow1_parse_tool["tool_params"]
                }
            )

            flow1_format_tool_result = CodeNode(
                name="flow1_format_tool_result",
                code_fn=lambda result: {
                    "tool_result_text": json.dumps(result, ensure_ascii=False, indent=2) if result else "No result"
                },
                inputs={"result": flow1_mcp_search["result"]},
                return_keys=["tool_result_text: str"]
            )

            flow1_secondary_intent = BasicChainNode(
                name="flow1_secondary_intent",
                resource_key="gpt-4.1",
                user_prompt=PROMPTS["TEXT2META:SECONDARY_INTENT_PROMPT"],
                inputs={
                    "query": rewrite_and_intent_node["rewrite"],
                    "search_result": flow1_format_tool_result["tool_result_text"]
                },
                extract_schema=["intent: str", "reasoning: str"],
                parser="yaml",
                stream=True
            )

            flow1_action_branch = BranchNode(
                name="flow1_action_branch",
                cases={
                    "intent == 'search'": "flow1_explain_search",
                    "intent == 'generate'": "flow1_parse_table_for_generation"
                },
                default="flow1_explain_search",
                inputs={"intent": flow1_secondary_intent["intent"]}
            )

            flow1_explain_search = BasicChainNode(
                name="flow1_explain_search",
                resource_key="gpt-4.1",
                user_prompt=PROMPTS["TEXT2META:EXPLAIN_SEARCH_RESULT_PROMPT"],
                inputs={
                    "query": rewrite_and_intent_node["rewrite"],
                    "search_result": flow1_format_tool_result["tool_result_text"]
                },
                stream=True
            )

            flow1_parse_table_for_generation = CodeNode(
                name="flow1_parse_table_for_generation",
                code_fn=lambda result: {
                    "table_info_json": json.dumps(result["content"][0]["text"] if result else {}, ensure_ascii=False),  
                    "fqn": json.loads(result["content"][0]["text"])["results"][0]["fullyQualifiedName"] if result and result.get("content") else None  # Extract FQN để lấy sample data
                },
                inputs={"result": flow1_mcp_search["result"]},
                return_keys=["table_info_json: str", "fqn: str"]
            )

            flow1_get_sample_data = CodeNode(
                name="flow1_get_sample_data",
                code_fn=fetch_sample_data,
                inputs={"fqn": flow1_parse_table_for_generation["fqn"]},
                return_keys=["sample_data: str", "error: str"]
            )

            flow1_generate_metadata = BasicChainNode(
                name="flow1_generate_metadata",
                resource_key="gpt-4.1",
                user_prompt=PROMPTS["TEXT2META:GENERATE_METADATA_PROMPT"],
                inputs={
                    "table_info": flow1_parse_table_for_generation["table_info_json"],
                    "sample_data": flow1_get_sample_data["sample_data"]
                },
                # extract_schema=["existing_metadata: dict", "generated_metadata: dict"],
                parser="yaml",
                stream=True
            )

            # FLOW 2: CONFIRM UPDATE
            flow2_extract_update_metadata = BasicChainNode(
                name="flow2_extract_update_metadata",
                resource_key="gpt-4.1",
                user_prompt=PROMPTS["TEXT2META:EXTRACT_UPDATE_METADATA_PROMPT"],
                inputs={
                    "conversation": init_query_node["conversation"],
                    "query": rewrite_and_intent_node["rewrite"]
                },
                extract_schema=[
                    "table_name: str", 
                    "metadata: dict",
                    "reasoning: str"
                ],
                parser="yaml",
                stream=False
            )

            flow2_check_metadata = BranchNode(
                name="flow2_check_metadata",
                cases={
                    "(metadata.get('table_description') is not None) or (len(metadata.get('column_descriptions', {})) > 0)": "flow2_build_search"
                },
                default="flow2_error_no_metadata",
                inputs={"metadata": flow2_extract_update_metadata["metadata"]}
            )

            flow2_error_no_metadata = LLMNode(
                name="flow2_error_no_metadata",
                resource_key="gemini-2.5-flash-chat",
                instant_response=True,
                inputs={
                    "response": "Không tìm thấy metadata để cập nhật. Vui lòng:\n- Sinh metadata trước rồi xác nhận, HOẶC\n- Nhập rõ metadata muốn cập nhật (VD: 'cập nhật description của cột A là \"xyz\"')"
                },
                stream=True
            )

            # Search để lấy lại thông tin bảng hiện tại, vị trí các cột
            flow2_build_search = CodeNode(
                name="flow2_build_search",
                code_fn=build_search_params_for_generation,
                inputs={"table_query": flow2_extract_update_metadata["table_name"]},
                return_keys=["tool_name: str", "tool_params: dict"]
            )
            
            flow2_mcp_search = MCPGatewayNode(
                name="flow2_mcp_search",
                resource_key="openmetadata",
                method=MCPMethod.CALL,
                inputs={
                    "tool_name": flow2_build_search["tool_name"],
                    "tool_params": flow2_build_search["tool_params"]
                }
            )

            flow2_format_table = CodeNode(
                name="flow2_format_table",
                code_fn=lambda result: {
                    "table_info_json": json.dumps(
                        json.loads(result["content"][0]["text"])["results"][0], 
                        ensure_ascii=False
                    ) if result and result.get("content") else None
                },
                inputs={"result": flow2_mcp_search["result"]},
                return_keys=["table_info_json: str"]
            )

            flow2_format_patch = BasicChainNode(
                name="flow2_format_patch",
                resource_key="gpt-4.1",
                user_prompt=PROMPTS["TEXT2META:FORMAT_PATCH_PROMPT"],
                inputs={
                    "table_info": flow2_format_table["table_info_json"],
                    "generated_metadata": flow2_extract_update_metadata["metadata"],
                    "rewrite": rewrite_and_intent_node["rewrite"]
                },
                extract_schema=["entityType: str", "entityFqn: str", "patch: list"],
                parser="json"
            )

            flow2_build_patch_params = CodeNode(
                name="flow2_build_patch_params",
                code_fn=lambda et, efqn, p: {
                    "tool_name": "patch_entity",
                    "tool_params": {
                        "entityType": et,
                        "entityFqn": efqn,
                        "patch": json.dumps(p, ensure_ascii=False)
                    }
                },
                inputs={
                    "et": flow2_format_patch["entityType"],
                    "efqn": flow2_format_patch["entityFqn"],
                    "p": flow2_format_patch["patch"]
                },
                return_keys=["tool_name: str", "tool_params: dict"]
            )

            # Execute patch (Hiện tại ở tool patch đang để là add, sẽ cập nhật để linh hoạt add và update ở các ver sau)
            flow2_mcp_patch = MCPGatewayNode(
                name="flow2_mcp_patch",
                resource_key="openmetadata",
                method=MCPMethod.CALL,
                inputs={
                    "tool_name": flow2_build_patch_params["tool_name"],
                    "tool_params": flow2_build_patch_params["tool_params"]
                }
            )

            flow2_explain_result = BasicChainNode(
                name="flow2_explain_result",
                resource_key="gpt-4.1",
                user_prompt=PROMPTS["TEXT2META:EXPLAIN_UPDATE_RESULT_PROMPT"],
                inputs={"patch_result": flow2_mcp_patch["result"]},
                stream=True
            )


            START >> init_query_node >> annotate_query_node >> rewrite_and_intent_node >> route_flow_branch
            route_flow_branch >> [prompt_node, flow2_extract_update_metadata, error_unknown_intent]

            # Không xác định được intent
            error_unknown_intent >> END

            # Nhánh search or generate
            prompt_node >> flow1_tool_selection >> parser >> flow1_parse_tool >> flow1_mcp_search >> flow1_format_tool_result >> flow1_secondary_intent >> flow1_action_branch
            flow1_action_branch >> [flow1_explain_search, flow1_parse_table_for_generation]
            flow1_explain_search >>  END
            flow1_parse_table_for_generation >> flow1_get_sample_data >> flow1_generate_metadata >> END

            # Nhánh update metadata
            flow2_extract_update_metadata >> flow2_check_metadata >> [flow2_error_no_metadata, flow2_build_search] 
            flow2_error_no_metadata >> END
            flow2_build_search >> flow2_mcp_search >> flow2_format_table
            flow2_format_table >> flow2_format_patch >> flow2_build_patch_params >> flow2_mcp_patch >> flow2_explain_result >> END
        text2metadata_workflow.compile()

        self.workflow = text2metadata_workflow

    async def run(
        self,
        messages: List[Dict],
        session_id: str,
        client_message_id: str,
        role_ids: List,
        **kwargs
    ):
        """Main pipeline with updated logic flow."""
        try:
            request_id = client_message_id
            asyncio.create_task(self.workflow.run(
                request_id=request_id,
                inputs={
                    "messages": messages
                }
            ))

            async for channel_name in STREAM_SERVICE.get_channels(request_id):
                print(f"\nChannel: {channel_name}")
                async for chunk in STREAM_SERVICE.get(request_id, channel_name, json_mode=False):
                    yield chunk
                yield fake_chunk_from(
                    content="\n\n",
                    model="gpt-4.1"
                )
        except Exception as e:
            import traceback
            LOGGER.error(traceback.format_exc(e))
            default_answers = 'Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại sau.'
            yield fake_chunk_from(
                content=default_answers,
                resource_key="error"
            )


async def main():
    import uuid
    bot = Text2MetadataBot(bot_id="fa3402b6-2cf0-4283-b5df-fd801d2882b5")

    dialogue_id = str(uuid.uuid4())
    client_message_id = str(uuid.uuid4())

    async for chunk in bot.run(
        messages=[{"role": "user", "content": "sinh metadata cho bảng crm_rm_profile.CRM1_EMPLOYEE_ACCOUNT_TYPE"}],
        client_message_id=client_message_id,
        role_ids=["TCKT"],
        session_id = dialogue_id,
    ):
        print(f"{chunk.choices[0].delta.content or ''}", end= "")

    await asyncio.sleep(4)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
