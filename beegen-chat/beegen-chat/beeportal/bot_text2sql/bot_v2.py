import asyncio
from textwrap import dedent

# At the top of your main file, before any other imports
from beegen.utils.common import fake_chunk_from
from beegen.registry.resource_hub import RESOURCE_HUB
from beegen.prompts.prompt_manager import PromptManager
from beegen.loggings.loggers import LOGGER
from beeflow.workflow import WorkflowEngine
from beeflow.nodes.templates.basic_chain_node import BasicChainNode
from beeflow.nodes.templates.retriever_node_v2 import RetrieverNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.primitives.ai.embedding_node import EmbeddingNode
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes import RedisNode
from beeflow.nodes.base_node import END, START, OUTPUT
from beeportal.bot_text2sql.text2sql.nlp import (annotate_query, init_query,
                                    format_context_examples, get_current_timestamp, persist_latest_sql,
                                    build_export_sql_key, parse_export_sql, check_chart_intent)
from beeportal.bot_text2sql.text2sql.direct_sql_agent import (
    DIRECT_SQL_AGENT_SYSTEM_PROMPT,
    PlanExecuteVerifyAgentNode,
)
from beeportal.bot_text2sql.text2sql.context_compaction_node import (
    AgentContextCompactionNode,
    AgentStateRevisionPersistenceNode,
)
from beeportal.bot_text2sql.text2sql.direct_sql_tools import (
    build_direct_sql_tool_context,
    build_accessible_table_metadata_tool,
    build_check_sql_syntax_tool,
    build_execute_sql_tool,
    build_check_mermaid_syntax_tool,
    build_export_data_to_csv_tool,
    build_export_sql_to_csv_tool,
    build_load_mermaid_chart_skill_tool,
    build_table_metadata_details_tool,
    build_verify_sql_tool,
    build_direct_sql_tool_schemas,
)
from beeportal.bot_text2sql.text2sql.analysis_action import (
    ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT,
    build_analysis_action_trusted_context,
)
from beeportal.bot_text2sql.text2sql.executor import execute_sql_via_bytebase, execute_sql_with_custom_limit
from beeportal.bot_text2sql.text2sql.exporter import create_csv_and_upload_s3

from beeportal.bot_text2sql.text2sql.metadata import (
    validate_db_dialect, get_dialect_specific_prompt,
    build_table_overview_query, get_metadata_filter,
)
from beeportal.bot_text2sql.text2sql.metadata_search_context import (
    format_metadata_search_context,
    select_metadata_search_context,
)
from beeportal.bot_text2sql.text2sql.metadata_search_intent import (
    normalize_metadata_search_intent,
)
from beeportal.bot_text2sql.text2sql.metadata_search_query import (
    build_primary_metadata_query,
    build_rrf_metadata_query,
    should_fallback_semantic,
)
from beeportal.bot_text2sql.text2sql.metadata_prompts import (
    METADATA_SEARCH_INTENT_PLANNER_PROMPT,
    TEXT2QUERY_CHIT_CHAT_PROMPT,
)
from typing import Dict, List
from beeflow.nodes.primitives.data.sql_node import SQLNode
from beegen.configs.storage.sql_config import SQLOperation
from beegen.configs.cache.redis_config import RedisOperation
from beeflow.nodes.base_node import END, START, INPUT
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.utils.common import transform_bot_id

PROMPTS = PromptManager("beegen")
METADATA_QUERY_LIMIT = 100000


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
        # Build tool graphs before entering the parent workflow so ToolExecutorNode
        # can own them without registering the tools as sibling workflow nodes.
        direct_sql_tools = [
            build_check_sql_syntax_tool(),
            build_accessible_table_metadata_tool(),
            build_table_metadata_details_tool(),
            build_verify_sql_tool(),
            build_execute_sql_tool(),
        ]
        analysis_action_tools = [
            build_load_mermaid_chart_skill_tool(),
            build_check_mermaid_syntax_tool(),
            build_export_sql_to_csv_tool(),
            build_export_data_to_csv_tool(),
            build_table_metadata_details_tool(),
        ]
        direct_sql_tool_schemas = build_direct_sql_tool_schemas(direct_sql_tools)
        analysis_action_tool_schemas = build_direct_sql_tool_schemas(analysis_action_tools)
        with WorkflowEngine(
            name="text2sql",
            description="Đây là luồng chat standard của bot text2sql",
        ) as text2sql_workflow:
            
            with GraphNode(
                name="graph_query_preprocessing",
                description="Tiền xử lý câu hỏi và phân loại intent",
                inputs={
                    "messages": INPUT
                },
                outputs={
                    "rewrite": OUTPUT,
                    "intent": OUTPUT,
                    "origin_query": OUTPUT,
                    "conversation": OUTPUT,
                }
            ) as graph_query_preprocessing:

                code_init_query = CodeNode(
                    name="code_init_query",
                    code_fn=init_query,
                    inputs={"messages": INPUT},
                    outputs={"origin_query": OUTPUT, "conversation": OUTPUT},
                    return_keys={"origin_query: str", "conversation: list"},
                )
                code_annotate_query = CodeNode(name="code_annotate_query", code_fn=annotate_query, inputs={
                                        "origin_query": code_init_query})
                llm_rewrite_intent_classifier = BasicChainNode(
                    name="llm_rewrite_intent_classifier",
                    resource_key="gpt-4.1",
                    parser="yaml",
                    user_prompt=PROMPTS["TEXT2QUERY:REWRITE_AND_CLASSIFY_PROMPT"],
                    extract_schema=["rewrite: str", "intent: str"],
                    inputs={"query": code_annotate_query, "conversation": code_init_query},
                    outputs={
                        "rewrite": OUTPUT,
                        "intent": OUTPUT
                    },
                    # stream=True
                )

                START >> code_init_query >> code_annotate_query >> llm_rewrite_intent_classifier >> END

            
            code_get_current_timestamp = CodeNode(
                name="code_get_current_timestamp",
                code_fn=get_current_timestamp,
                return_keys={"current_timestamp"}
            )

            with GraphNode(
                name="graph_retriever_qna",
                description="Lấy các câu QnA tương đồng với câu hỏi",
                inputs={
                    "allowed_roles": {INPUT: "role_ids"},
                    "query": {graph_query_preprocessing: "rewrite"},
                },
                outputs={
                    "context_examples": OUTPUT
                }
            ) as graph_retriever_qna:
                retriever_node = RetrieverNode(
                    name="retriever_get_context",
                    inputs={
                        "query": INPUT, 
                        "partition_names": ["QA"], 
                        "bot_id": self.bot_id,
                        "collection": transform_bot_id(self.bot_id),
                        "allowed_roles": INPUT,
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
                    return_keys={"context_examples: str"},
                    outputs={"context_examples": OUTPUT}
                )
                START >> retriever_node >> code_format_context >> END

            branch_check_intent = BranchNode(
                name="branch_check_intent",
                cases={
                     "intent == 'chit_chat'": "graph_chit_chat_response",
                     "intent == 'analyze_history'": "graph_analysis_action_agent",
                     "intent == 'execute_sql'": "graph_execute_sql_flow",
                     "intent == 'export_file'": "graph_analysis_action_agent",
                     "intent == 'draw_chart'": "graph_analysis_action_agent",
                },
                inputs={
                    "intent": {graph_query_preprocessing: "intent"}
                },
                default="graph_non_chit_chat_response"
            )

            with GraphNode(
                name="graph_chit_chat_response",
                description="Tra loi chit-chat va cau hoi metadata/schema",
                inputs={
                    "query": {graph_query_preprocessing: "rewrite"},
                    "origin_query": {graph_query_preprocessing: "origin_query"},
                    "conversation": {graph_query_preprocessing: "conversation"},
                    "role_ids": INPUT,
                    "metadata": {INPUT: "metadata"},
                    "definition": self.definition,
                },
                outputs={
                    "content": OUTPUT
                }
            ) as graph_chit_chat_response:

                llm_metadata_search_intent_planner = BasicChainNode(
                    name="llm_metadata_search_intent_planner",
                    resource_key="qwen-instruct-chat",
                    user_prompt=METADATA_SEARCH_INTENT_PLANNER_PROMPT,
                    parser="yaml",
                    inputs={
                        "query": INPUT,
                        "origin_query": INPUT["origin_query"],
                        "conversation": INPUT["conversation"],
                    },
                    extract_schema=[
                        "search_mode: str",
                        "column_names: list",
                        "table_names: list",
                        "search_terms: list",
                        "value_terms: list",
                        "full_column_list: int",
                        "fallback_allowed: int",
                    ]
                )

                code_normalize_metadata_search_intent = CodeNode(
                    name="code_normalize_metadata_search_intent",
                    code_fn=normalize_metadata_search_intent,
                    inputs={
                        "planner_search_mode": {llm_metadata_search_intent_planner: "search_mode"},
                        "planner_column_names": {llm_metadata_search_intent_planner: "column_names"},
                        "planner_table_names": {llm_metadata_search_intent_planner: "table_names"},
                        "planner_search_terms": {llm_metadata_search_intent_planner: "search_terms"},
                        "planner_value_terms": {llm_metadata_search_intent_planner: "value_terms"},
                        "planner_full_column_list": {llm_metadata_search_intent_planner: "full_column_list"},
                        "planner_fallback_allowed": {llm_metadata_search_intent_planner: "fallback_allowed"},
                    },
                    return_keys={
                        "search_mode: str",
                        "column_names: list",
                        "table_names: list",
                        "search_terms: list",
                        "value_terms: list",
                        "fallback_allowed: int",
                        "full_column_list: int",
                        "full_column_reject_reason: str",
                    }
                )

                branch_metadata_search_mode = BranchNode(
                    name="branch_metadata_search_mode",
                    cases={
                        "search_mode == 'semantic_metadata'": "graph_semantic_metadata_context",
                    },
                    default="code_build_primary_metadata_query",
                    inputs={
                        "search_mode": {code_normalize_metadata_search_intent: "search_mode"}
                    }
                )

                code_build_primary_metadata_query = CodeNode(
                    name="code_build_primary_metadata_query",
                    code_fn=build_primary_metadata_query,
                    inputs={
                        "role_ids": INPUT,
                        "metadata": INPUT,
                        "search_mode": {code_normalize_metadata_search_intent: "search_mode"},
                        "column_names": {code_normalize_metadata_search_intent: "column_names"},
                        "table_names": {code_normalize_metadata_search_intent: "table_names"},
                        "search_terms": {code_normalize_metadata_search_intent: "search_terms"},
                        "full_column_list": {code_normalize_metadata_search_intent: "full_column_list"},
                        "full_column_reject_reason": {code_normalize_metadata_search_intent: "full_column_reject_reason"},
                    },
                    return_keys={"query: str", "params: list"}
                )

                sql_primary_metadata_search = SQLNode(
                    name="sql_primary_metadata_search",
                    operation=SQLOperation.QUERY,
                    resource_key="anapp",
                    inputs={
                        "query": {code_build_primary_metadata_query: "query"},
                        "params": {code_build_primary_metadata_query: "params"},
                        "limit": METADATA_QUERY_LIMIT,
                    }
                )

                code_should_fallback_semantic = CodeNode(
                    name="code_should_fallback_semantic",
                    code_fn=should_fallback_semantic,
                    inputs={
                        "rows": {sql_primary_metadata_search: "data"},
                        "search_mode": {code_normalize_metadata_search_intent: "search_mode"},
                        "column_names": {code_normalize_metadata_search_intent: "column_names"},
                        "table_names": {code_normalize_metadata_search_intent: "table_names"},
                        "fallback_allowed": {code_normalize_metadata_search_intent: "fallback_allowed"},
                    },
                    return_keys={"fallback_semantic: int"}
                )

                branch_metadata_search_fallback = BranchNode(
                    name="branch_metadata_search_fallback",
                    cases={
                        "fallback_semantic == 1": "graph_semantic_metadata_context",
                    },
                    default="code_format_primary_metadata_context",
                    inputs={
                        "fallback_semantic": {code_should_fallback_semantic: "fallback_semantic"}
                    }
                )

                code_format_primary_metadata_context = CodeNode(
                    name="code_format_primary_metadata_context",
                    code_fn=format_metadata_search_context,
                    inputs={
                        "rows": {sql_primary_metadata_search: "data"},
                        "search_mode": {code_normalize_metadata_search_intent: "search_mode"},
                        "table_names": {code_normalize_metadata_search_intent: "table_names"},
                        "value_terms": {code_normalize_metadata_search_intent: "value_terms"},
                        "full_column_list": {code_normalize_metadata_search_intent: "full_column_list"},
                        "full_column_reject_reason": {code_normalize_metadata_search_intent: "full_column_reject_reason"},
                    },
                    return_keys={"metadata_context: str"}
                )

                with GraphNode(
                    name="graph_semantic_metadata_context",
                    description="Hybrid RRF metadata search in Postgres",
                    inputs={
                        "query": INPUT,
                        "role_ids": INPUT,
                        "metadata": INPUT,
                        "search_terms": {code_normalize_metadata_search_intent: "search_terms"},
                        "value_terms": {code_normalize_metadata_search_intent: "value_terms"},
                    },
                    outputs={
                        "metadata_context": OUTPUT,
                    }
                ) as graph_semantic_metadata_context:
                    emb_metadata_query = EmbeddingNode(
                        name="emb_metadata_query",
                        resource_key="bge-m3",
                        inputs={"texts": INPUT["query"]}
                    )

                    code_build_rrf_metadata_query = CodeNode(
                        name="code_build_rrf_metadata_query",
                        code_fn=build_rrf_metadata_query,
                        inputs={
                            "user_query": INPUT["query"],
                            "query_embedding": {emb_metadata_query: "embeddings"},
                            "role_ids": INPUT,
                            "metadata": INPUT,
                            "search_terms": INPUT["search_terms"],
                        },
                        return_keys={"query: str", "params: list"}
                    )

                    sql_rrf_metadata_search = SQLNode(
                        name="sql_rrf_metadata_search",
                        operation=SQLOperation.QUERY,
                        resource_key="anapp",
                        inputs={
                            "query": {code_build_rrf_metadata_query: "query"},
                            "params": {code_build_rrf_metadata_query: "params"},
                            "limit": METADATA_QUERY_LIMIT,
                        }
                    )

                    code_format_semantic_metadata_context = CodeNode(
                        name="code_format_semantic_metadata_context",
                        code_fn=format_metadata_search_context,
                        inputs={
                            "rows": {sql_rrf_metadata_search: "data"},
                            "search_mode": "semantic_metadata",
                            "value_terms": INPUT["value_terms"],
                        },
                        return_keys={"metadata_context: str"},
                        outputs={
                            "metadata_context": OUTPUT,
                        }
                    )

                    START >> emb_metadata_query >> code_build_rrf_metadata_query >> sql_rrf_metadata_search >> code_format_semantic_metadata_context >> END

                code_select_chit_chat_metadata_context = CodeNode(
                    name="code_select_chit_chat_metadata_context",
                    code_fn=select_metadata_search_context,
                    inputs={
                        "primary_metadata_context": {code_format_primary_metadata_context: "metadata_context"},
                        "semantic_metadata_context": {graph_semantic_metadata_context: "metadata_context"},
                    },
                    return_keys={"metadata_context: str"}
                )

                llm_chit_chat_response = BasicChainNode(
                    name="llm_chit_chat_response",
                    resource_key="qwen-instruct-chat",
                    user_prompt=TEXT2QUERY_CHIT_CHAT_PROMPT,
                    inputs={
                        "definition": INPUT,
                        "query": INPUT["origin_query"],
                        "rewrite": INPUT["query"],
                        "conversation": INPUT["conversation"],
                        "metadata_context": {code_select_chit_chat_metadata_context: "metadata_context"},
                    },
                    stream=True,
                    outputs={"content": OUTPUT}
                )

                START >> llm_metadata_search_intent_planner >> code_normalize_metadata_search_intent >> branch_metadata_search_mode
                branch_metadata_search_mode >> [code_build_primary_metadata_query, graph_semantic_metadata_context]
                code_build_primary_metadata_query >> sql_primary_metadata_search >> code_should_fallback_semantic >> branch_metadata_search_fallback
                branch_metadata_search_fallback >> [code_format_primary_metadata_context, graph_semantic_metadata_context]
                code_format_primary_metadata_context >> code_select_chit_chat_metadata_context
                graph_semantic_metadata_context >> code_select_chit_chat_metadata_context
                code_select_chit_chat_metadata_context >> llm_chit_chat_response >> END

            with GraphNode(
                name="graph_analysis_action_agent",
                description="Agent phân tích lịch sử, vẽ Mermaid và xuất CSV từ nguồn đã xác minh",
                inputs={
                    "messages": INPUT,
                    "session_id": INPUT,
                    "role_ids": INPUT,
                    "metadata": {INPUT: "metadata"},
                    "bot_id": {INPUT: "bot_id"},
                    "client_message_id": {INPUT: "client_message_id"},
                },
                outputs={"answer": OUTPUT},
            ) as graph_analysis_action_agent:
                code_analysis_action_export_key = CodeNode(
                    name="code_analysis_action_export_key",
                    code_fn=build_export_sql_key,
                    inputs={"session_id": INPUT["session_id"]},
                    return_keys={"redis_key: str"},
                )
                redis_get_analysis_action_latest_sql = RedisNode(
                    name="redis_get_analysis_action_latest_sql",
                    resource_key="aicenter-chatbot",
                    operation=RedisOperation.GET,
                    inputs={"key": {code_analysis_action_export_key: "redis_key"}},
                )
                code_parse_analysis_action_latest_sql = CodeNode(
                    name="code_parse_analysis_action_latest_sql",
                    code_fn=parse_export_sql,
                    inputs={"redis_result": {redis_get_analysis_action_latest_sql: "value"}},
                    return_keys={
                        "resolved_sql: str",
                        "status: str",
                        "error: str",
                        "count: int",
                        "data: list[dict]",
                    },
                )
                code_analysis_action_tool_context = CodeNode(
                    name="code_analysis_action_tool_context",
                    code_fn=build_direct_sql_tool_context,
                    inputs={
                        "role_ids": INPUT["role_ids"],
                        "metadata": INPUT["metadata"],
                        "session_id": INPUT["session_id"],
                        "bot_id": INPUT["bot_id"],
                        "client_message_id": INPUT["client_message_id"],
                    },
                    return_keys={"tool_context: dict"},
                )
                code_analysis_action_trusted_context = CodeNode(
                    name="code_analysis_action_trusted_context",
                    code_fn=build_analysis_action_trusted_context,
                    inputs={
                        "source_sql": {code_parse_analysis_action_latest_sql: "resolved_sql"},
                        "source_status": {code_parse_analysis_action_latest_sql: "status"},
                        "source_error": {code_parse_analysis_action_latest_sql: "error"},
                        "source_count": {code_parse_analysis_action_latest_sql: "count"},
                        "source_data": {code_parse_analysis_action_latest_sql: "data"},
                    },
                    return_keys={"trusted_context: str"},
                )
                analysis_action_context = AgentContextCompactionNode(
                    name="agent_analysis_action_context_compaction",
                    resource_key="gemini-3.5-flash-chat",
                    sql_resource_key="anapp",
                    system_prompt=ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT,
                    tool_schemas=analysis_action_tool_schemas,
                    inputs={
                        "api_messages": INPUT["messages"],
                        "session_id": INPUT["session_id"],
                        "trusted_context": {code_analysis_action_trusted_context: "trusted_context"},
                    },
                    outputs={
                        "context_messages": OUTPUT,
                        "historical_summary": OUTPUT,
                        "summary_covered_api_message_count": OUTPUT,
                        "summary_covered_api_prefix_hash": OUTPUT,
                    },
                )
                analysis_action_agent = PlanExecuteVerifyAgentNode(
                    name="AnalysisActionAgentNode",
                    tools=analysis_action_tools,
                    resource_key="gemini-3.5-flash-chat",
                    system_prompt=ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT,
                    max_iterations=15,
                    inputs={
                        "messages": {analysis_action_context: "context_messages"},
                        "tool_context": {code_analysis_action_tool_context: "tool_context"},
                        "trusted_context": {code_analysis_action_trusted_context: "trusted_context"},
                        "historical_summary": {analysis_action_context: "historical_summary"},
                    },
                    outputs={"final_answer": {OUTPUT: "answer"}},
                )
                agent_analysis_action_state_revision = AgentStateRevisionPersistenceNode(
                    name="agent_analysis_action_state_revision",
                    sql_resource_key="anapp",
                    inputs={
                        "final_state_messages": {analysis_action_agent: "final_state_messages"},
                        "api_messages": INPUT["messages"],
                        "session_id": INPUT["session_id"],
                        "client_message_id": INPUT["client_message_id"],
                        "historical_summary": {analysis_action_context: "historical_summary"},
                        "summary_covered_api_message_count": {
                            analysis_action_context: "summary_covered_api_message_count"
                        },
                        "summary_covered_api_prefix_hash": {
                            analysis_action_context: "summary_covered_api_prefix_hash"
                        },
                    },
                )

                START >> [
                    code_analysis_action_export_key,
                    code_analysis_action_tool_context,
                ]
                code_analysis_action_export_key >> redis_get_analysis_action_latest_sql >> code_parse_analysis_action_latest_sql
                code_parse_analysis_action_latest_sql >> code_analysis_action_trusted_context >> analysis_action_context
                code_analysis_action_tool_context >> analysis_action_agent
                analysis_action_context >> analysis_action_agent >> agent_analysis_action_state_revision >> END

            with GraphNode(
                name="graph_non_chit_chat_response",
                description="Đây là luồng non chit chat",
                inputs={
                    "query": {graph_query_preprocessing: "rewrite"},
                    "role_ids": INPUT,
                    "definition": self.definition,
                    "session_id": INPUT,
                    "metadata": {INPUT: "metadata"},
                    "context_examples": graph_retriever_qna,
                    "current_timestamp": {code_get_current_timestamp: "current_timestamp"}
                },
                outputs={
                    "answer": OUTPUT,      # ← Từ các nốt llm trả về
                    "sql": OUTPUT,
                    "count": OUTPUT,
                    "data": OUTPUT
                }
            ) as graph_non_chit_chat_response:
                
                with GraphNode(
                    name="graph_get_table_overview",
                    description="Kiểm tra quyền truy cập",
                    inputs={
                        "role_ids": INPUT,
                        "metadata": INPUT
                    },
                    outputs={
                        "table_overview": OUTPUT,
                        "has_permission": OUTPUT,
                    }
                ) as graph_get_table_overview:

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
                        },
                        outputs={
                            "data": {OUTPUT: "table_overview"},
                            "count": {OUTPUT: "has_permission"}
                        }
                    )

                    START >> code_build_overview_query >> sql_get_overview >> END
                

                # Check user có quyền vào bảng nào không or role + domain không có bảng nào phù hợp
                branch_has_permission = BranchNode(
                    name="branch_has_permission",
                    cases={
                        "count > 0": "llm_select_tables",
                    },
                    default="llm_no_permission",  # ← User không có quyền vào bảng nào
                    inputs={"count": {graph_get_table_overview: "has_permission"}}
                )
                
                # Reject: user không có quyền 
                llm_no_permission = BasicChainNode(
                    name="llm_no_permission",
                    resource_key="qwen-instruct-chat",
                    user_prompt=PROMPTS["TEXT2QUERY:NO_PERMISSION_PROMPT"],
                    inputs={"query": INPUT,
                            "current_timestamp": INPUT},
                    outputs={"content": {OUTPUT: "answer"}},
                    stream=True
                )

                llm_select_tables = BasicChainNode(
                    name="llm_select_tables",
                    resource_key="gpt-5.1-chat",
                    system_prompt="Bạn là chuyên gia chọn ra các bảng phù hợp cho hệ thống text-to-sql",
                    user_prompt=PROMPTS["TEXT2QUERY:TABLE_SELECTION"],
                    parser="xml",
                    inputs={"query": INPUT,    # Thay query của người dùng (INPUT) bằng câu đã rewrite
                            "table_overview": {graph_get_table_overview: "table_overview"}
                    },
                    llm_configs={"reasoning_effort": "low"},
                    extract_schema=["table_name: list"],
                    # stream=True
                )
                branch_has_table = BranchNode(
                    name="branch_has_table",
                    cases={
                        "table_name == '' or table_name is None": "llm_recommend_no_table", 
                        "table_name != ''": "graph_metadata_fetch"
                    },
                    inputs={"table_name": llm_select_tables}
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
                        "table_metadata": {graph_get_table_overview: "table_overview"},
                        "current_timestamp": INPUT,
                        "explain": ""
                    },
                    outputs={"content": {OUTPUT: "answer"}},
                    # stream=True
                )

                # ===== Graph: Metadata Fetch & Validation =====
                with GraphNode(
                    name="graph_metadata_fetch",
                    description="Lấy metadata từ database",
                    inputs={
                        "table_name": llm_select_tables,
                    },
                    outputs={
                        "table_metadata": OUTPUT,
                        "db_dialect": OUTPUT,
                        "is_consistent": OUTPUT,
                        "dialects_found": OUTPUT,
                    }
                ) as graph_metadata_fetch:
                    
                    code_get_metadata_filter = CodeNode(
                        name="code_get_metadata_filter",
                        code_fn=get_metadata_filter,
                        inputs={"tables": {INPUT: "table_name"}},
                    )
                    
                    sql_get_metadata = SQLNode(
                        name="sql_get_metadata",
                        operation=SQLOperation.QUERY,
                        resource_key="anapp",
                        inputs={
                            "query": code_get_metadata_filter,
                            "params": code_get_metadata_filter
                        },
                        outputs={"data": {OUTPUT: "table_metadata"}}
                    )
                    
                    code_validate_db_dialect = CodeNode(
                        name="code_validate_db_dialect",
                        code_fn=validate_db_dialect,
                        inputs={"table_metadata": {sql_get_metadata: "data"}},
                        return_keys={
                            "db_dialect: str",
                            "is_consistent: int",
                            "dialects_found: list[str]",
                            "table_count: int"
                        },
                        outputs = {"db_dialect": OUTPUT, "is_consistent": OUTPUT, "dialects_found": OUTPUT}
                    )

                    START >> code_get_metadata_filter >> sql_get_metadata >> code_validate_db_dialect >> END

                branch_db_dialect_check = BranchNode(
                    name="branch_db_dialect_check",
                    cases={
                        "is_consistent == 1": "code_get_dialect_prompt",
                        "is_consistent == 0 or is_consistent is None": "llm_recommend_mixed_db"
                    },
                    inputs={
                        "is_consistent": {graph_metadata_fetch: "is_consistent"}
                    }
                )

                llm_recommend_mixed_db = BasicChainNode(
                    name="llm_recommend_mixed_db",
                    resource_key="qwen-instruct-chat",
                    user_prompt=PROMPTS["TEXT2QUERY:MIXED_DB_ERROR_PROMPT"],
                    inputs={
                        "query": INPUT,
                        "dialects_found": {graph_metadata_fetch: "dialects_found"}
                    },
                    outputs={"content": {OUTPUT: "answer"}}
                )

                code_get_dialect_prompt = CodeNode(
                    name="code_get_dialect_prompt",
                    code_fn=lambda db_dialect: get_dialect_specific_prompt(db_dialect, PROMPTS),
                    inputs={"db_dialect": {graph_metadata_fetch: "db_dialect"}},
                    return_keys={"dialect_instructions: str"}
                )

                llm_text2sql_processor = BasicChainNode(
                    name="llm_text2sql_processor",
                    resource_key="gpt-5.1-chat",
                    system_prompt="Bạn là chuyên gia chuyển đổi text sang sql của hệ thống text-to-sql",
                    user_prompt=PROMPTS["TEXT2QUERY:TEXT2SQL"],
                    inputs={"query": INPUT,        # Thay query của người dùng (INPUT) bằng câu đã rewrite
                            "table_metadata": {graph_metadata_fetch: "table_metadata"},
                            "db_dialect": {graph_metadata_fetch: "db_dialect"},
                            "dialect_instructions": {code_get_dialect_prompt: "dialect_instructions"},
                            "current_timestamp": INPUT,
                            "context_examples": INPUT
                    },
                    llm_configs={"reasoning_effort": "low"},
                    parser="yaml",
                    extract_schema=["sql: str", "explain: str"],
                    outputs={"sql": OUTPUT},
                    stream=True
                )

                with GraphNode(
                    name="graph_sql_validation",
                    description="Validate SQL trước khi thực thi",
                    inputs={
                        "sql": llm_text2sql_processor,
                        "explain": llm_text2sql_processor,
                        "query": INPUT,
                        "table_metadata": {graph_metadata_fetch: "table_metadata"},
                        "current_timestamp": INPUT,
                        "definition": INPUT
                    },
                    outputs={
                        "answer": OUTPUT,
                        "is_valid": OUTPUT,
                        "reason": OUTPUT
                    }
                ) as graph_sql_validation:

                    llm_sql_validator = BasicChainNode(
                        name="llm_sql_validator",
                        resource_key="gpt-4.1",
                        user_prompt=PROMPTS["TEXT2QUERY:SQL_VALIDATOR_PROMPT"],
                        inputs={"sql": INPUT},
                        parser="yaml",
                        extract_schema=["is_valid: int", "reason: str"],
                        outputs={"is_valid": OUTPUT, "reason": OUTPUT}
                    )

                    branch_sql_available = BranchNode(
                        name="branch_sql_available",
                        cases={
                            "sql == '' or sql is None": "llm_recommend_empty_sql",
                            "is_valid == 1": END,  # SQL hợp lệ -> tiếp tục sang execute
                            "is_valid == 0": "llm_recommend_invalid_sql"
                        },
                        inputs={
                            "sql": INPUT,
                            "is_valid": {llm_sql_validator: "is_valid"}
                        }
                    )

                    llm_recommend_empty_sql = BasicChainNode(
                        name="llm_recommend_empty_sql",
                        resource_key="qwen-instruct-chat",
                        system_prompt="Bạn là chuyên gia từ chối và gợi ý câu hỏi người dùng trong hệ thống text2sql khi không có câu sql nào được trả về",
                        user_prompt=PROMPTS["TEXT2QUERY:NON_CHIT_CHAT_RECOMMEND_PROMPT"],
                        inputs={
                            "definition": INPUT,
                            "query": INPUT,
                            "sql": INPUT,
                            "table_metadata": INPUT,
                            "current_timestamp": INPUT,
                            "explain": INPUT
                        },
                        outputs={"content": {OUTPUT: "answer"}},
                    )

                    llm_recommend_invalid_sql = BasicChainNode(
                        name="llm_recommend_invalid_sql",
                        resource_key="qwen-instruct-chat",
                        user_prompt=PROMPTS["TEXT2QUERY:SQL_SECURITY_REJECT_PROMPT"],
                        inputs={
                            "query": INPUT,
                            "sql": INPUT,
                            "reason": {llm_sql_validator: "reason"}
                        },
                        outputs={"content": {OUTPUT: "answer"}},
                    )

                    START >> llm_sql_validator >> branch_sql_available >> [llm_recommend_empty_sql, END, llm_recommend_invalid_sql]
                    llm_recommend_empty_sql >> END
                    llm_recommend_invalid_sql >> END

                branch_skip_execute = BranchNode(
                    name="branch_skip_execute",
                    cases={
                        "sql is None or sql == ''": END,
                        "is_valid == 0 or is_valid is None": "code_persist_sql_rejected_non_chit_chat",
                    },
                    default="sql_execute_query",  # Validation pass -> execute SQL
                    inputs={"is_valid": {graph_sql_validation: "is_valid"},
                            "sql": {llm_text2sql_processor: "sql"}
                    }
                )

                # ===== Node: SQL Execute (standalone) =====
                sql_execute_query = CodeNode(
                    name="sql_execute_query",
                    code_fn=execute_sql_via_bytebase,
                    inputs={"query": {llm_text2sql_processor: "sql"}},
                    return_keys={
                        "count: int",
                        "data: List[Dict]",
                        "status: str",
                        "error: str"
                    },
                    outputs={
                        "count": OUTPUT,
                        "data": OUTPUT
                    }
                )

                code_persist_sql_non_chit_chat = CodeNode(
                    name="code_persist_sql_non_chit_chat",
                    code_fn=persist_latest_sql,
                    inputs={
                        "sql": {llm_text2sql_processor: "sql"},
                        "status": {sql_execute_query: "status"},
                        "count": {sql_execute_query: "count"},
                        "session_id": INPUT,
                        "data": {sql_execute_query: "data"},
                        "error": {sql_execute_query: "error"},
                    },
                    return_keys={"should_persist: int", "redis_key: str", "redis_value: str"}
                )

                code_persist_sql_rejected_non_chit_chat = CodeNode(
                    name="code_persist_sql_rejected_non_chit_chat",
                    code_fn=persist_latest_sql,
                    inputs={
                        "sql": {llm_text2sql_processor: "sql"},
                        "status": "rejected",
                        "count": 0,
                        "session_id": INPUT,
                        "data": [],
                        "error": {graph_sql_validation: "reason"},
                    },
                    return_keys={"should_persist: int", "redis_key: str", "redis_value: str"},
                )

                redis_save_sql_rejected_non_chit_chat = RedisNode(
                    name="redis_save_sql_rejected_non_chit_chat",
                    resource_key="aicenter-chatbot",
                    operation=RedisOperation.SETEX,
                    inputs={
                        "key": {code_persist_sql_rejected_non_chit_chat: "redis_key"},
                        "value": {code_persist_sql_rejected_non_chit_chat: "redis_value"},
                        "seconds": 7200,
                    },
                )

                branch_should_persist_non_chit_chat = BranchNode(
                    name="branch_should_persist_non_chit_chat",
                    cases={
                        "should_persist == 1": "redis_save_sql_non_chit_chat"
                    },
                    default=END,
                    inputs={"should_persist": {code_persist_sql_non_chit_chat: "should_persist"}}
                )

                redis_save_sql_non_chit_chat = RedisNode(
                    name="redis_save_sql_non_chit_chat",
                    resource_key="aicenter-chatbot",
                    operation=RedisOperation.SETEX,
                    inputs={
                        "key": {code_persist_sql_non_chit_chat: "redis_key"},
                        "value": {code_persist_sql_non_chit_chat: "redis_value"},
                        "seconds": 7200
                    }
                )

                with GraphNode(
                    name="graph_response",
                    description="Xử lý kết quả SQL và tạo câu trả lời",
                    inputs={
                        "sql": {llm_text2sql_processor: "sql"},
                        "query": INPUT,
                        "table_metadata": {graph_metadata_fetch: "table_metadata"},
                        "current_timestamp": INPUT,
                        "definition": INPUT,
                        "row_number": {sql_execute_query: "count"},
                        "status": {sql_execute_query: "status"},
                        "table_data": {sql_execute_query: "data"},
                        "error": sql_execute_query,
                    },
                    outputs={
                        "answer": OUTPUT,
                    }
                ) as graph_response:

                    branch_row_number = BranchNode(
                        name="branch_row_number",
                        cases={
                            # nếu row_number trả về null thì vẫn là != 0 và chạy vào nhánh dù ko có data
                            "status == 'error' or status is None": "llm_recommend_sql_error",
                            "row_number is not None and row_number > 0": "llm_generate_answer",
                            "row_number == 0 or row_number is None": "llm_recommend_no_data"
                        },
                        inputs={
                            "row_number": INPUT,
                            "status": INPUT
                        }
                    )
                    

                    llm_recommend_sql_error = BasicChainNode(
                        name="llm_recommend_sql_error",
                        resource_key="qwen-instruct-chat",
                        user_prompt=PROMPTS["TEXT2QUERY:SQL_EXECUTION_ERROR_PROMPT"],
                        inputs={
                            "query": INPUT,
                            "sql": INPUT,
                            "error": INPUT
                        },
                        outputs={"content": {OUTPUT: "answer"}},
                    )

                    llm_recommend_no_data = BasicChainNode(
                        name="llm_recommend_no_data",
                        resource_key="qwen-instruct-chat",
                        system_prompt="Bạn là chuyên gia từ chối và gợi ý câu hỏi người dùng trong hệ thống text2sql khi hệ thống cơ sở dữ liệu query thành công nhưng không có bản ghi nào trả về",
                        user_prompt=PROMPTS["TEXT2QUERY:NON_CHIT_CHAT_RECOMMEND_PROMPT"],
                        inputs={
                            "definition": INPUT,
                            "query": INPUT,
                            "sql": INPUT,
                            "table_metadata": INPUT,
                            "current_timestamp": INPUT
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
                            "table_data": INPUT,
                            "sql": INPUT,
                            "table_metadata": INPUT,
                            "row_number": INPUT
                        },
                        outputs={"content": {OUTPUT: "answer"}}
                    )

                    START >> branch_row_number >> [llm_recommend_sql_error, llm_generate_answer, llm_recommend_no_data]
                    llm_recommend_sql_error >> END
                    llm_recommend_no_data >> END
                    llm_generate_answer >> END


                START >> graph_get_table_overview >> branch_has_permission >> [llm_select_tables, llm_no_permission]
                llm_no_permission >> END
                llm_select_tables >> branch_has_table >> [graph_metadata_fetch, llm_recommend_no_table]
                llm_recommend_no_table >> END
                graph_metadata_fetch >> branch_db_dialect_check >> [code_get_dialect_prompt, llm_recommend_mixed_db]
                llm_recommend_mixed_db >> END 
                code_get_dialect_prompt >> llm_text2sql_processor >> graph_sql_validation >> branch_skip_execute >> [sql_execute_query, code_persist_sql_rejected_non_chit_chat]
                sql_execute_query >> [code_persist_sql_non_chit_chat, graph_response]
                code_persist_sql_non_chit_chat >> branch_should_persist_non_chit_chat >> [redis_save_sql_non_chit_chat, END]
                redis_save_sql_non_chit_chat >> END
                code_persist_sql_rejected_non_chit_chat >> redis_save_sql_rejected_non_chit_chat >> END
                graph_response >> END

            # Agent điều phối đúng năm tool; Redis giữ đầy đủ tool trace theo session/quyền.
            with GraphNode(
                name="graph_execute_sql_flow",
                description="Agent kiểm tra, sửa và thực thi SQL trực tiếp bằng tool calling",
                inputs={
                    "messages": INPUT,
                    "session_id": INPUT,
                    "role_ids": INPUT,
                    "metadata": {INPUT: "metadata"},
                    "client_message_id": {INPUT: "client_message_id"},
                },
                outputs={"answer": OUTPUT},
            ) as graph_execute_sql_flow:
                direct_sql_context = AgentContextCompactionNode(
                    name="agent_direct_sql_context_compaction",
                    resource_key="gemini-3.5-flash-chat",
                    sql_resource_key="anapp",
                    system_prompt=DIRECT_SQL_AGENT_SYSTEM_PROMPT,
                    tool_schemas=direct_sql_tool_schemas,
                    inputs={
                        "api_messages": INPUT["messages"],
                        "session_id": INPUT["session_id"],
                        "trusted_context": "",
                    },
                    outputs={
                        "context_messages": OUTPUT,
                        "historical_summary": OUTPUT,
                        "summary_covered_api_message_count": OUTPUT,
                        "summary_covered_api_prefix_hash": OUTPUT,
                    },
                )

                code_direct_sql_tool_context = CodeNode(
                    name="code_direct_sql_tool_context",
                    code_fn=build_direct_sql_tool_context,
                    inputs={
                        "role_ids": INPUT["role_ids"],
                        "metadata": INPUT["metadata"],
                        "session_id": INPUT["session_id"],
                    },
                    return_keys={"tool_context: dict"},
                )

                direct_sql_agent = PlanExecuteVerifyAgentNode(
                    name="PlanExecuteVerifyAgentNode",
                    tools=direct_sql_tools,
                    resource_key="gemini-3.5-flash-chat",
                    system_prompt=DIRECT_SQL_AGENT_SYSTEM_PROMPT,
                    max_iterations=15,
                    inputs={
                        "messages": {direct_sql_context: "context_messages"},
                        "tool_context": {code_direct_sql_tool_context: "tool_context"},
                        "trusted_context": "",
                        "historical_summary": {direct_sql_context: "historical_summary"},
                    },
                    outputs={"final_answer": {OUTPUT: "answer"}},
                )

                agent_direct_sql_state_revision = AgentStateRevisionPersistenceNode(
                    name="agent_direct_sql_state_revision",
                    sql_resource_key="anapp",
                    inputs={
                        "final_state_messages": {direct_sql_agent: "final_state_messages"},
                        "api_messages": INPUT["messages"],
                        "session_id": INPUT["session_id"],
                        "client_message_id": INPUT["client_message_id"],
                        "historical_summary": {direct_sql_context: "historical_summary"},
                        "summary_covered_api_message_count": {
                            direct_sql_context: "summary_covered_api_message_count"
                        },
                        "summary_covered_api_prefix_hash": {
                            direct_sql_context: "summary_covered_api_prefix_hash"
                        },
                    },
                )

                START >> [direct_sql_context, code_direct_sql_tool_context]
                direct_sql_context >> direct_sql_agent
                code_direct_sql_tool_context >> direct_sql_agent >> agent_direct_sql_state_revision >> END

            # Graph export CSV when user requests file export
            with GraphNode(
                name="graph_export_csv",
                description="Xuất CSV và upload lên S3 khi người dùng yêu cầu",
                inputs={
                    "sql": {graph_non_chit_chat_response: "sql"},
                    "query": {graph_query_preprocessing: "rewrite"},
                    "answer": {graph_non_chit_chat_response: "answer"},
                    "bot_id": {INPUT: "bot_id"},
                    "client_message_id": {INPUT: "client_message_id"}
                },
                outputs={
                    "download_link": OUTPUT
                }
            ) as graph_export_csv:
                # LLM detect export intent based on query and answer
                llm_detect_export_intent = BasicChainNode(
                    name="llm_detect_export_intent",
                    resource_key="gpt-4.1",
                    user_prompt=PROMPTS["TEXT2QUERY:DETECT_EXPORT_INTENT_PROMPT"],
                    parser="yaml",
                    extract_schema=["wants_export: int"],
                    inputs={"query": INPUT, "answer": INPUT}
                )

                # Branch to check if user wants export
                branch_should_export = BranchNode(
                    name="branch_should_export",
                    cases={
                        "wants_export == 1": "code_export_sql"
                    },
                    inputs={"wants_export": {llm_detect_export_intent: "wants_export"}},
                    default=END
                )

                # Execute SQL with limit 1000 for export
                code_export_sql = CodeNode(
                    name="code_export_sql",
                    code_fn=execute_sql_with_custom_limit,
                    inputs={"query": {INPUT: "sql"}, "limit": 1000},
                    return_keys={
                        "count: int",
                        "data: List[Dict]",
                        "status: str",
                        "error: str"
                    }
                )

                # Create CSV and upload to S3
                code_create_csv_upload = CodeNode(
                    name="code_create_csv_upload",
                    code_fn=create_csv_and_upload_s3,
                    inputs={
                        "data": {code_export_sql: "data"},
                        "bot_id": {INPUT: "bot_id"},
                        "client_message_id": {INPUT: "client_message_id"}
                    },
                    return_keys={
                        "download_link: str",
                        "file_id: str",
                        "file_name: str",
                        "row_count: int",
                        "error: str"
                    },
                    outputs={
                        "download_link": OUTPUT,
                        "error": OUTPUT,
                        "row_count": OUTPUT
                    }
                )

                START >> llm_detect_export_intent >> branch_should_export >> [code_export_sql, END]
                code_export_sql >> code_create_csv_upload >> END

            llm_direct_answer_and_verify = BasicChainNode(
                name="llm_direct_answer_and_verify",
                resource_key="gpt-4.1",
                user_prompt=PROMPTS["TEXT2QUERY:DIRECT_ANSWER_AND_VERIFY_PROMPT"],
                inputs={
                    "query": {graph_query_preprocessing: "rewrite"},
                    "answer": graph_non_chit_chat_response,
                    "download_link": {graph_export_csv: "download_link"},
                    "export_row_count": {graph_export_csv: "row_count"},    
                    "export_error": {graph_export_csv: "error"}
                },
                outputs={"content": OUTPUT},
                stream=True
            )

            with GraphNode(
                name="graph_visualization",
                description="Tạo biểu đồ (nếu cần) và lưu vào memory",
                inputs={
                    "query": {graph_query_preprocessing: "rewrite"},
                    "row_number": {graph_non_chit_chat_response: "count"},
                    "table_data": {graph_non_chit_chat_response: "data"},
                    "sql": {graph_non_chit_chat_response: "sql"}
                },
                outputs={
                    "content": OUTPUT
                }
            ) as graph_visualization:
                
                code_check_chart_intent = CodeNode(
                    name="code_check_chart_intent",
                    code_fn=check_chart_intent,
                    inputs={
                        "query": INPUT,
                        "table_data": INPUT,
                    },
                    return_keys={"should_visualize: int"}
                )
                
                branch_should_visualize = BranchNode(
                    name="branch_should_visualize",
                    cases={
                        "should_visualize == 1": "llm_generate_chart",
                    },
                    inputs={"should_visualize": code_check_chart_intent},
                    default=END
                )

                llm_generate_chart = BasicChainNode(
                    name="llm_generate_chart",
                    resource_key="gpt-4.1", 
                    # system_prompt="Bạn là chuyên gia tạo biểu đồ HTML interactive từ dữ liệu SQL",
                    user_prompt=PROMPTS["TEXT2QUERY:GENERATE_MERMAID_CHART_PROMPT"],
                    inputs={
                        "query": INPUT,
                        "table_data": INPUT,
                        "sql": INPUT
                    },
                    # extract_schema=["chart_html: str"],
                    outputs={"content": OUTPUT},
                    stream=True
                )
                START >> code_check_chart_intent >> branch_should_visualize >> [llm_generate_chart, END]
                llm_generate_chart >> END

            START >> graph_query_preprocessing >> code_get_current_timestamp >> graph_retriever_qna >> branch_check_intent
            branch_check_intent >> [graph_chit_chat_response, graph_analysis_action_agent, graph_non_chit_chat_response, graph_execute_sql_flow]
            graph_analysis_action_agent >> END
            graph_chit_chat_response >> END
            graph_non_chit_chat_response >> graph_export_csv >> llm_direct_answer_and_verify >> graph_visualization >> END
            graph_execute_sql_flow >> END

        text2sql_workflow.compile()

        self.workflow = text2sql_workflow

    async def run(
        self,
        messages: List[Dict],
        session_id: str,
        client_message_id: str,
        role_ids: List,
        metadata: Dict,
        bot_id: str = None,
        username: str = None,
        **kwargs
    ):
        """Main pipeline with updated logic flow."""
        try:
            request_id = client_message_id
            # Use provided bot_id or fallback to self.bot_id
            final_bot_id = bot_id or self.bot_id
            asyncio.create_task(self.workflow.run(
                request_id=request_id,
                user_id=username,
                inputs={
                    "messages": messages,
                    "session_id": session_id,
                    "role_ids": role_ids,
                    "metadata": metadata,
                    "bot_id": final_bot_id,
                    "client_message_id": client_message_id,
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
        messages=[
            {
                "role": "user",
                "content": "CIR của MB trong 3 tháng đầu năm 2025",
            },
            {
                "role": "assistant",
                "content": dedent(
                    """\
                    ```yaml
                    sql: |
                      SELECT
                        transaction_date,
                        ma_ct,
                        value
                      FROM apps.FIN_RPT_GIAOBAN_TOAN_HANG_POC
                      WHERE ma_ct = 'CIR'
                        AND transaction_date IN (
                          TO_DATE('2025-01-31', 'YYYY-MM-DD'),
                          TO_DATE('2025-02-28', 'YYYY-MM-DD'),
                          TO_DATE('2025-03-31', 'YYYY-MM-DD')
                        )
                      ORDER BY transaction_date
                    explain: ""
                    ```

                    CIR (Tỷ lệ Tổng chi phí hoạt động/Tổng thu nhập thuần hoạt động) của MB trong 3 tháng đầu năm 2025:

                    | Thời điểm | CIR (%) |
                    |---|---:|
                    | Tháng 1/2025 | 25,87 |
                    | Tháng 2/2025 | 25,40 |
                    | Tháng 3/2025 | 21,09 |

                    Dữ liệu gồm 3 dòng tương ứng với thời điểm cuối mỗi tháng.
                    """
                ),
            },
            {
                "role": "user",
                "content": "Hãy phân tích xu hướng CIR, vẽ biểu đồ từ kết quả trên và xuất dữ liệu thành file CSV.",
            },
        ],
        session_id = dialogue_id,
        client_message_id=client_message_id,
        role_ids=["TCKT"],
        metadata=metadata,
        username="user_test"
    ):
        content = chunk.choices[0].delta.content if chunk.choices else ""
        print(content or "", end="", flush=True)

    await asyncio.sleep(4)


if __name__ == "__main__":
    asyncio.run(main())
