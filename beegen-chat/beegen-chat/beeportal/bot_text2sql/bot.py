import asyncio

# At the top of your main file, before any other imports
from beegen.utils.common import fake_chunk_from
from beegen.registry.resource_hub import RESOURCE_HUB
from beegen.prompts.prompt_manager import PromptManager
from beegen.loggings.loggers import LOGGER
from beeflow.workflow import WorkflowEngine
from beeflow.nodes.templates.basic_chain_node import BasicChainNode
from beeflow.nodes.templates.retriever_node_v2 import RetrieverNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes.base_node import END, START, OUTPUT
from beeflow.nodes.primitives.memory.mem0_node import Mem0Node, Mem0Operation
from beeportal.bot_text2sql.text2sql.nlp import (annotate_query, init_query, extract_latest_bot_response,
                                    prepare_mem0_data_merge, format_context_examples, get_current_timestamp)
from beeportal.bot_text2sql.text2sql.metadata import (validate_db_dialect, get_dialect_specific_prompt,
                                    build_table_overview_query, get_metadata_filter)
from typing import Dict, List, Tuple, Union
from beeflow.nodes.primitives.data.sql_node import SQLNode
from beegen.configs.storage.sql_config import SQLOperation
from beeflow.nodes.base_node import END, START, INPUT
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.utils.common import transform_bot_id

PROMPTS = PromptManager("text2sql")


class Text2SqlBot:
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
            name="text2sql",
            description="Đây là luồng chat standard của bot text2sql",
        ) as text2sql_workflow:
            code_init_query = CodeNode(name="code_init_query", code_fn=init_query, inputs={
                                   "messages": INPUT})
            code_annotate_query = CodeNode(name="code_annotate_query", code_fn=annotate_query, inputs={
                                       "origin_query": code_init_query})
            code_extract_last_response = CodeNode(name="code_extract_last_response", code_fn=extract_latest_bot_response, inputs={
                                    "messages": INPUT})

            llm_rewrite_intent_classifier = BasicChainNode(
                name="llm_rewrite_intent_classifier",
                resource_key="gpt-4.1",
                parser="yaml",
                user_prompt=PROMPTS["TEXT2QUERY:REWRITE_AND_CLASSIFY_PROMPT"],
                extract_schema=["rewrite: str", "intent: str"],
                inputs={"query": code_annotate_query, "conversation": code_init_query},
                # stream=True
            )

            mem0_search = Mem0Node(
                name="mem0_search",
                resource_key="mem0",
                operation=Mem0Operation.SEARCH,
                inputs={
                    "query": {llm_rewrite_intent_classifier: "rewrite"},
                    "session_id": {INPUT: "session_id"}
                }
            )

            branch_check_intent = BranchNode(
                name="branch_check_intent",
                cases={
                     "intent == 'chit_chat'": "llm_chit_chat_response",
                     "intent == 'analyze_history'": "llm_analyze_history_response", # Nhánh mới
                },
                inputs={
                    "intent": {llm_rewrite_intent_classifier: "intent"}
                },
                default="graph_non_chit_chat_response"
            )

            llm_chit_chat_response = BasicChainNode(
                name="llm_chit_chat_response",
                resource_key="qwen-instruct-chat",
                user_prompt=PROMPTS["TEXT2QUERY:CHIT_CHAT_PROMPT"],
                inputs={"definition": self.definition},
                stream=True,
                outputs={"content": OUTPUT}
            )

            llm_analyze_history_response = BasicChainNode(
                name="llm_analyze_history_response", 
                resource_key="gpt-4.1",
                user_prompt=PROMPTS["TEXT2QUERY:ANALYZE_HISTORY_PROMPT"],
                inputs={
                    "query": {llm_rewrite_intent_classifier: "rewrite"},
                    "previous_response": {code_extract_last_response: "previous_response"},
                    "user_memories": {mem0_search: "results"}
                },
                stream=True,
                outputs={"content": OUTPUT}
            )

            llm_generate_chart_analyze = BasicChainNode(
                name="llm_generate_chart_analyze",
                resource_key="gpt-4.1",
                user_prompt=PROMPTS["TEXT2QUERY: GENERATE_MERMAID_CHART_FROM_ANALYZE_PROMPT"],
                inputs={
                    "history_response": {llm_analyze_history_response: "content"},
                    "query": {llm_rewrite_intent_classifier: "rewrite"}
                },
                outputs={"content": OUTPUT},
                stream=True
            )

            with GraphNode(
                name="graph_non_chit_chat_response",
                description="Đây là luồng non chit chat",
                inputs={
                    "query": {llm_rewrite_intent_classifier: "rewrite"},
                    "role_ids": INPUT,
                    "definition": self.definition,
                    "metadata": {INPUT: "metadata"}
                },
                outputs={
                    "answer": OUTPUT,      # ← Từ các nốt llm trả về
                    "sql": OUTPUT,
                    "count": OUTPUT,
                    "data": OUTPUT
                }
            ) as graph_non_chit_chat_response:
                code_build_overview_query = CodeNode(
                    name="code_build_overview_query",
                    code_fn=build_table_overview_query,
                    inputs={
                        "role_ids": INPUT,
                        "metadata": INPUT
                    },
                    return_keys={"sql_table: str"}
                )
                sql_get_overview = SQLNode(
                    name="sql_get_overview",
                    operation=SQLOperation.QUERY,
                    resource_key="anapp",
                    inputs={
                        "query": code_build_overview_query["sql_table"],
                        "limit": 100
                    }
                )
                code_get_current_timestamp = CodeNode(
                    name="code_get_current_timestamp",
                    code_fn=get_current_timestamp,
                    return_keys={"current_timestamp"}
                )
                llm_select_tables = BasicChainNode(
                    name="llm_select_tables",
                    resource_key="gpt-5.1-chat",
                    system_prompt="Bạn là chuyên gia chọn ra các bảng phù hợp cho hệ thống text-to-sql",
                    user_prompt=PROMPTS["TEXT2QUERY:TABLE_SELECTION"],
                    parser="xml",
                    inputs={"query": {llm_rewrite_intent_classifier: "rewrite"},    # Thay query của người dùng (INPUT) bằng câu đã rewrite
                            "table_overview": {sql_get_overview: "data"}
                    },
                    llm_configs={"reasoning_effort": "low"},
                    extract_schema=["table_name: list"],
                    # stream=True
                )
                branch_has_table = BranchNode(
                    name="branch_has_table",
                    cases={
                        "table_name == '' or table_name is None": "llm_recommend_no_table", 
                        "table_name != ''": "code_get_metadata_filter"
                    },
                    inputs={"table_name": llm_select_tables}
                )
                code_get_metadata_filter = CodeNode(
                    name="code_get_metadata_filter",
                    code_fn=get_metadata_filter,
                    inputs={"tables": {llm_select_tables: "table_name"}},
                    # output_schema=["query: str", "params: list"]
                )
                sql_get_metadata = SQLNode(
                    name="sql_get_metadata",
                    operation=SQLOperation.QUERY,
                    resource_key="anapp",
                    inputs={"query": code_get_metadata_filter,
                            "params": code_get_metadata_filter}
                )
                code_validate_db_dialect = CodeNode(
                    name="code_validate_db_dialect",
                    code_fn=validate_db_dialect,
                    inputs={"table_metadata": {sql_get_metadata: "data"}}, 
                    return_keys={"db_dialect : str" , "is_consistent : int", "dialects_found : list[str]", "table_count : int"}
                )
                branch_db_dialect_check = BranchNode(
                    name="branch_db_dialect_check",
                    cases={
                        "is_consistent == 1": "code_get_dialect_prompt",
                        "is_consistent == 0 or is_consistent is None": "llm_recommend_mixed_db"
                    },
                    inputs={"is_consistent": {code_validate_db_dialect: "is_consistent"}}
                )
                llm_recommend_mixed_db = BasicChainNode(
                    name="llm_recommend_mixed_db",
                    resource_key="qwen-instruct-chat",
                    user_prompt=PROMPTS["TEXT2QUERY:MIXED_DB_ERROR_PROMPT"],
                    inputs={
                        "query": INPUT,
                        "dialects_found": {code_validate_db_dialect: "dialects_found"}
                    },
                    outputs={"content": {OUTPUT: "answer"}}
                )
                code_get_dialect_prompt = CodeNode(
                    name="code_get_dialect_prompt",
                    code_fn=lambda db_dialect: get_dialect_specific_prompt(db_dialect, PROMPTS),
                    inputs={"db_dialect": {code_validate_db_dialect: "db_dialect"}},
                    return_keys={"dialect_instructions : str"}
                )

                retriever_node = RetrieverNode(
                    name="retriever_get_context",
                    inputs={
                        "query": INPUT, 
                        "partition_names": ["QA"], 
                        "bot_id": self.bot_id,
                        "collection": transform_bot_id(self.bot_id),
                        "allowed_roles": {INPUT: "role_ids"},
                        "top_k": 10,  
                        "threshold": 0.0,
                        "output_fields": ['chunk_id'],
                        "rerank_top_k": 5,  
                    },
                    use_rerank=True,
                )
                code_format_context = CodeNode(
                    name="code_format_context",
                    code_fn=format_context_examples,
                    inputs={"retriever_results": {retriever_node: "docs"}},
                    return_keys={"context_examples: str"}
                )
                llm_text2sql_processor = BasicChainNode(
                    name="llm_text2sql_processor",
                    resource_key="gpt-5.1-chat",
                    system_prompt="Bạn là chuyên gia chuyển đổi text sang sql của hệ thống text-to-sql",
                    user_prompt=PROMPTS["TEXT2QUERY:TEXT2SQL"],
                    inputs={"query": {llm_rewrite_intent_classifier: "rewrite"},        # Thay query của người dùng (INPUT) bằng câu đã rewrite
                            "table_metadata": {sql_get_metadata: "data"},
                            "db_dialect": {code_validate_db_dialect: "db_dialect"},
                            "dialect_instructions": {code_get_dialect_prompt: "dialect_instructions"},
                            "current_timestamp": {code_get_current_timestamp: "current_timestamp"},
                            "context_examples": {code_format_context: "context_examples"}
                    },
                    llm_configs={"reasoning_effort": "low"},
                    parser="yaml",
                    extract_schema=["sql: str", "explain: str"],
                    outputs={"sql": OUTPUT},
                    stream=True
                )
                llm_sql_validator = BasicChainNode(
                    name="llm_sql_validator",
                    resource_key="gpt-4.1",
                    user_prompt=PROMPTS["TEXT2QUERY:SQL_VALIDATOR_PROMPT"],
                    inputs={"sql": {llm_text2sql_processor: "sql"}},
                    parser="yaml",
                    extract_schema=["is_valid: int", "reason: str"],
                )
                branch_sql_available = BranchNode(
                    name="branch_sql_available",
                    cases={
                        "sql == '' or sql is None": "llm_recommend_empty_sql",
                        "is_valid == 1": "sql_execute_query", # SQL hợp lệ
                        "is_valid == 0": "llm_recommend_invalid_sql"
                    },
                    inputs={
                        "sql": {llm_text2sql_processor: "sql"},
                        "is_valid": {llm_sql_validator: "is_valid"}
                    }
                )

                llm_recommend_invalid_sql = BasicChainNode(
                    name="llm_recommend_invalid_sql",
                    resource_key="qwen-instruct-chat",
                    user_prompt=PROMPTS["TEXT2QUERY:SQL_SECURITY_REJECT_PROMPT"],
                    inputs={
                        "query": INPUT,
                        "sql": {llm_text2sql_processor: "sql"},
                        "reason": {llm_sql_validator: "reason"}
                    },
                    outputs={"content": {OUTPUT: "answer"}},
                )
                sql_execute_query = SQLNode(
                    name="sql_execute_query",
                    operation=SQLOperation.QUERY,
                    resource_key="tckt",
                    inputs={"query": {llm_text2sql_processor: "sql"}},
                    outputs={"count": OUTPUT,
                             "data": OUTPUT}
                )
                branch_row_number = BranchNode(
                    name="branch_row_number",
                    cases={
                        # nếu row_number trả về null thì vẫn là != 0 và chạy vào nhánh dù ko có data
                        "status == 'error' or status is None": "llm_recommend_sql_error",
                        "row_number is not None and row_number > 0": "llm_generate_answer",
                        "row_number == 0 or row_number is None": "llm_recommend_no_data"
                    },
                    inputs={"row_number": {sql_execute_query: "count"},
                            "status": {sql_execute_query: "status"}}
                )
                llm_recommend_sql_error = BasicChainNode(
                    name="llm_recommend_sql_error",
                    resource_key="qwen-instruct-chat",
                    user_prompt=PROMPTS["TEXT2QUERY:SQL_EXECUTION_ERROR_PROMPT"],
                    inputs={
                        "query": INPUT,
                        "sql": {llm_text2sql_processor: "sql"},
                        "error": {sql_execute_query: "error"} 
                    },
                    outputs={"content": {OUTPUT: "answer"}},
                )

                llm_generate_answer = BasicChainNode(
                    name="llm_generate_answer",
                    resource_key="gpt-4.1",
                    system_prompt=PROMPTS["TEXT2QUERY:NON_CHIT_CHAT_PROMPT"],
                    user_prompt="{query}",
                    inputs={
                        "definition": INPUT,
                        "query": INPUT,
                        "table_data": {sql_execute_query: "data"},
                        "sql": {llm_text2sql_processor: "sql"},
                        "table_metadata": {sql_get_metadata: "data"},
                        "row_number": {sql_execute_query: "count"}
                    },
                    outputs={"content": {OUTPUT: "answer"}}
                )

                llm_recommend_empty_sql = BasicChainNode(
                    name="llm_recommend_empty_sql",
                    resource_key="qwen-instruct-chat",
                    system_prompt="Bạn là chuyên gia từ chối và gợi ý câu hỏi người dùng trong hệ thống text2sql khi hệ thống cơ sở dữ liệu query thành công nhưng không có bản ghi nào trả về",
                    user_prompt=PROMPTS["TEXT2QUERY:NON_CHIT_CHAT_RECOMMEND_PROMPT"],
                    inputs={
                        "definition": INPUT,
                        "query": INPUT,
                        "sql": llm_text2sql_processor,
                        "table_metadata": {sql_get_metadata: "data"},
                        "current_timestamp": {code_get_current_timestamp: "current_timestamp"},
                        "explain": llm_text2sql_processor
                    },
                    outputs={"content": {OUTPUT: "answer"}},
                    # stream=True
                )
                llm_recommend_no_data = BasicChainNode(
                    name="llm_recommend_no_data",
                    resource_key="qwen-instruct-chat",
                    system_prompt="Bạn là chuyên gia từ chối và gợi ý câu hỏi người dùng trong hệ thống text2sql khi hệ thống cơ sở dữ liệu query thành công nhưng không có bản ghi nào trả về",
                    user_prompt=PROMPTS["TEXT2QUERY:NON_CHIT_CHAT_RECOMMEND_PROMPT"],
                    inputs={
                        "definition": INPUT,
                        "query": INPUT,
                        "sql": llm_text2sql_processor,
                        "table_metadata": {sql_get_metadata: "data"},
                        "current_timestamp": {code_get_current_timestamp: "current_timestamp"},
                        "explain": llm_text2sql_processor
                    },
                    outputs={"content": {OUTPUT: "answer"}},
                    # stream=True
                )
                llm_recommend_no_table = BasicChainNode(
                    name="llm_recommend_no_table",
                    resource_key="qwen-instruct-chat",
                    system_prompt="Bạn là chuyên gia từ chối và gợi ý câu hỏi người dùng trong hệ thống text2sql khi hệ thống cơ sở dữ liệu query thành công nhưng không có bản ghi nào trả về",
                    user_prompt=PROMPTS["TEXT2QUERY:NON_CHIT_CHAT_RECOMMEND_PROMPT"],
                    inputs={
                        "definition": INPUT,
                        "query": INPUT,
                        "sql": "",
                        "table_metadata": {sql_get_overview: "data"},
                        "current_timestamp": {code_get_current_timestamp: "current_timestamp"},
                        "explain": ""
                    },
                    outputs={"content": {OUTPUT: "answer"}},
                    # stream=True
                )
                # non_chit_chat_refuse_flow = BasicChainNode(
                #     name="non_chit_chat_refuse_flow",
                #     resource_key="qwen-instruct",
                #     system_prompt="Bạn là chuyên gia từ chối trả lời trong hệ thống text2sql",
                #     user_prompt=PROMPTS["TEXT2QUERY:NON_CHIT_CHAT_REFUSE_PROMPT"],
                #     inputs={
                #         "query": graph_non_chit_chat_response,
                #         "definition": graph_non_chit_chat_response,
                #     }
                # )

                START >> code_build_overview_query >> sql_get_overview >> code_get_current_timestamp >> llm_select_tables >> branch_has_table >> [code_get_metadata_filter, llm_recommend_no_table]
                llm_recommend_no_table >> END
                code_get_metadata_filter >> sql_get_metadata >> code_validate_db_dialect >> branch_db_dialect_check >> [code_get_dialect_prompt, llm_recommend_mixed_db]
                llm_recommend_mixed_db >> END
                code_get_dialect_prompt >> retriever_node >> code_format_context >> llm_text2sql_processor >> llm_sql_validator >> branch_sql_available >> [sql_execute_query, llm_recommend_empty_sql, llm_recommend_invalid_sql]
                llm_recommend_empty_sql >> END
                llm_recommend_invalid_sql >> END
                sql_execute_query >> branch_row_number >> [llm_recommend_sql_error, llm_generate_answer, llm_recommend_no_data]
                llm_recommend_sql_error >> END
                llm_recommend_no_data >> END
                llm_generate_answer >> END

            llm_direct_answer_and_verify = BasicChainNode(
                name="llm_direct_answer_and_verify",
                resource_key="gpt-4.1",
                user_prompt=PROMPTS["TEXT2QUERY:DIRECT_ANSWER_AND_VERIFY_PROMPT"],
                inputs={
                    "query": {llm_rewrite_intent_classifier: "rewrite"},
                    "answer": graph_non_chit_chat_response
                },
                outputs={"content": OUTPUT},
                stream=True
            )

            code_prepare_mem0 = CodeNode(
                name="code_prepare_mem0",
                code_fn=prepare_mem0_data_merge,
                inputs={
                    "rewrite": {llm_rewrite_intent_classifier: "rewrite"},
                    "analyze_content": {llm_analyze_history_response: "content"},
                    "sql_content": {graph_non_chit_chat_response: "answer"},
                },
                return_keys={"dialogue: list[dict]"}
            )

            mem0_add = Mem0Node(
                name="mem0_add",
                resource_key="mem0",
                operation=Mem0Operation.ADD,
                inputs={
                    "messages": {code_prepare_mem0: "dialogue"},
                    "session_id": INPUT,
                    "custom_fact_extraction_prompt": PROMPTS["TEXT2QUERY:CUSTOM_FACT_EXTRACTION_PROMPT"]
                }
            )

            branch_should_visualize = BranchNode(
                name="branch_should_visualize",
                cases={
                    "row_number >= 2 and row_number <= 10": "llm_generate_chart",
                },
                inputs={"row_number": {graph_non_chit_chat_response: "count"}},
                default="code_prepare_mem0"
            )

            llm_generate_chart = BasicChainNode(
                name="llm_generate_chart",
                resource_key="gpt-4.1", 
                # system_prompt="Bạn là chuyên gia tạo biểu đồ HTML interactive từ dữ liệu SQL",
                user_prompt=PROMPTS["TEXT2QUERY:GENERATE_MERMAID_CHART_PROMPT"],
                inputs={
                    "query": {llm_rewrite_intent_classifier: "rewrite"},
                    "table_data": {graph_non_chit_chat_response: "data"},
                    "sql": {graph_non_chit_chat_response: "sql"}
                },
                # extract_schema=["chart_html: str"],
                outputs={"content": OUTPUT},
                stream=True
            )

            START >> code_init_query >> code_annotate_query >> code_extract_last_response >> llm_rewrite_intent_classifier >> mem0_search >> branch_check_intent
            branch_check_intent >> [llm_chit_chat_response, llm_analyze_history_response, graph_non_chit_chat_response] 
            llm_chit_chat_response >> END
            llm_analyze_history_response >> llm_generate_chart_analyze >> code_prepare_mem0 >> mem0_add >> END
            graph_non_chit_chat_response >> llm_direct_answer_and_verify >> branch_should_visualize >> [llm_generate_chart, code_prepare_mem0]
            llm_generate_chart >> code_prepare_mem0
            code_prepare_mem0 >> mem0_add >> END

        text2sql_workflow.compile()

        self.workflow = text2sql_workflow

    async def run(
        self,
        messages: List[Dict],
        session_id: str,
        client_message_id: str,
        role_ids: List,
        metadata: Dict,
        **kwargs
    ):
        """Main pipeline with updated logic flow."""
        try:
            request_id = client_message_id
            table_domain = metadata.get("TableDomain", [])
            asyncio.create_task(self.workflow.run(
                request_id=request_id,
                inputs={
                    "messages": messages,
                    "session_id": session_id,
                    "role_ids": role_ids,
                    "metadata": metadata
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
    bot = Text2SqlBot(bot_id="097a3a10-cf7e-4f2d-b9ae-87cedcb15ff4")
    
    dialogue_id = str(uuid.uuid4())
    client_message_id = str(uuid.uuid4())

    metadata = {
        "TableDomain": [
            {"schemaName": "apps", "tableName": "FIN_RPT_GIAOBAN_TOAN_HANG_POC"},
            {"schemaName": "apps", "tableName": "FIN_RPT_CEO_DAILY_POC"},
            {"schemaName": "apps", "tableName": "FIN_GUARANTEE_SMY_MONTHLY_POC"},
            {"schemaName": "apps", "tableName": "REP_TOI_FINAL_TT_KH_POC"},
            {"schemaName": "apps", "tableName": "FIN_HDV_SMY_MONTHLY_POC"},
            {"schemaName": "apps", "tableName": "FIN_LOAN_SMY_MONTHLY_POC"},
            {"schemaName": "apps", "tableName": "FIN_SMY_CUSTOMER_MONTHLY_POC"},
        ]
    }
    
    async for chunk in bot.run(
        messages=[{"role": "user", "content": "Top 5 tỉnh có nhiều khách hàng active App Biz nhất vào cuối tháng 6/2025?"}],
        session_id = dialogue_id,
        client_message_id=client_message_id,
        role_ids=["TCKT"],
        metadata=metadata
    ):
        print(f"{chunk.choices[0].delta.content or ''}", end= "")

    await asyncio.sleep(4)


if __name__ == "__main__":
    asyncio.run(main())
