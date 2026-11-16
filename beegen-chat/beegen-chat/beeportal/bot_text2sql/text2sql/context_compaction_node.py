from typing import Any, Dict, List

from beeflow.nodes.graph.graph_node import GraphNode
from beeportal.bot_text2sql.text2sql.agent_state_revision import (
    INSERT_AGENT_STATE_REVISION_SQL,
    LIST_AGENT_STATE_REVISIONS_SQL,
    build_insert_agent_state_revision_params,
    build_list_agent_state_revision_params,
)
from beeportal.bot_text2sql.text2sql.context_compaction import (
    build_agent_state_revision,
    build_summary_messages,
    estimate_provider_tokens,
    hash_api_prefix,
    hydrate_agent_context,
    plan_compaction,
    sanitize_tool_history,
    validate_summary,
)


CONTEXT_COMPACTION_PROGRESS_MESSAGE = (
    '<details style="opacity:0.7"><summary>Tiến trình</summary>'
    "Đang rút gọn ngữ cảnh hội thoại để tiếp tục xử lý yêu cầu."
    "</details>"
)


CONTEXT_COMPACTION_TOKEN_THRESHOLD = 80_000


def prepare_compaction(
    api_messages: List[Dict[str, Any]],
    revision_rows: List[Dict[str, Any]],
    session_id: str,
    system_prompt: str,
    trusted_context: str,
    tool_schemas: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Hydrate, sanitize và lập summary candidate trước khi gọi Plan agent."""
    assembled = hydrate_agent_context(api_messages, revision_rows, session_id)
    sanitized = sanitize_tool_history(assembled["messages"])
    fixed_tokens = estimate_provider_tokens(
        system_prompt,
        trusted_context,
        assembled["historical_summary"],
        [],
        tool_schemas,
    )
    estimated_tokens = fixed_tokens + estimate_provider_tokens(
        "",
        "",
        "",
        sanitized["messages"],
        [],
    )
    plan = plan_compaction(
        api_messages,
        sanitized["messages"],
        assembled["summary_covered_api_message_count"],
        estimated_tokens,
        fixed_tokens,
        CONTEXT_COMPACTION_TOKEN_THRESHOLD,
    )
    prepared = {
        **assembled,
        "messages": sanitized["messages"],
        "estimated_tokens": estimated_tokens,
        "should_compact": plan["should_compact"],
        "summary_messages": (
            build_summary_messages(
                assembled["historical_summary"],
                plan["compacted_messages"],
                plan["recent_messages"],
            )
            if plan["should_compact"]
            else []
        ),
        "plan": plan,
    }
    if plan["should_compact"]:
        prepared["covered_api_prefix_hash"] = hash_api_prefix(
            api_messages,
            int(plan["covered_api_message_count"]),
        )
    return prepared


def finalize_compaction(
    prepared: Dict[str, Any],
    summary_validation: Dict[str, Any],
) -> Dict[str, Any]:
    """Chọn context compact hoặc fail-open bằng raw context khi summary lỗi."""
    if summary_validation.get("valid") == 1:
        return {
            "messages": prepared["plan"]["recent_messages"],
            "historical_summary": str(summary_validation.get("summary") or ""),
            "summary_covered_api_message_count": prepared["plan"][
                "covered_api_message_count"
            ],
            "summary_covered_api_prefix_hash": prepared[
                "covered_api_prefix_hash"
            ],
        }
    return {
        "messages": prepared["messages"],
        "historical_summary": prepared["historical_summary"],
        "summary_covered_api_message_count": prepared[
            "summary_covered_api_message_count"
        ],
        "summary_covered_api_prefix_hash": prepared[
            "summary_covered_api_prefix_hash"
        ],
    }


def _prepare_node(
    api_messages: List[Dict[str, Any]],
    revision_rows: List[Dict[str, Any]],
    session_id: str,
    system_prompt: str,
    trusted_context: str,
    tool_schemas: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Đổi kết quả prepare thành đúng output contract của CodeNode."""
    prepared = prepare_compaction(
        api_messages,
        revision_rows,
        session_id,
        system_prompt,
        trusted_context,
        tool_schemas,
    )
    return {
        "prepared": prepared,
        "summary_messages": prepared["summary_messages"],
        "estimated_tokens": prepared["estimated_tokens"],
        "should_compact": prepared["should_compact"],
    }


def _finalize_without_compaction(prepared: Dict[str, Any]) -> Dict[str, Any]:
    """Hoàn tất nhánh không compact hoặc nhánh summary không hợp lệ."""
    return finalize_compaction(prepared, {"valid": 0, "summary": ""})


def _finalize_compacted_context(
    prepared: Dict[str, Any],
    valid: int,
    summary: str,
) -> Dict[str, Any]:
    """Hoàn tất nhánh đã gọi LLM summary bằng kết quả validation."""
    return finalize_compaction(prepared, {"valid": valid, "summary": summary})


def _notify_context_compaction() -> Dict[str, Any]:
    """Phát tín hiệu stream trước khi gọi LLM tóm tắt ngữ cảnh."""
    return {}


def _build_agent_state_revision_params(
    final_state_messages: List[Dict[str, Any]],
    api_messages: List[Dict[str, Any]],
    session_id: str,
    client_message_id: str,
    historical_summary: str,
    summary_covered_api_message_count: int,
    summary_covered_api_prefix_hash: str,
) -> Dict[str, Any]:
    """Chuyển final agent state thành params cho INSERT revision cố định."""
    revision = build_agent_state_revision(
        final_state_messages,
        api_messages,
        session_id,
        client_message_id,
        historical_summary,
        summary_covered_api_message_count,
        summary_covered_api_prefix_hash,
    )
    return build_insert_agent_state_revision_params(
        revision["session_id"],
        revision["client_message_id"],
        revision["summary"],
        revision["recent_agent_messages"],
        revision["summary_covered_api_message_count"],
        revision["summary_covered_api_prefix_hash"],
        revision["synced_api_message_count"],
        revision["synced_api_prefix_hash"],
    )


class AgentContextCompactionNode(GraphNode):
    """Đọc revision PostgreSQL và dựng provider context trước Plan agent."""

    def __init__(
        self,
        resource_key: str,
        sql_resource_key: str,
        system_prompt: str,
        tool_schemas: List[Dict[str, Any]],
        **kwargs,
    ):
        self.resource_key = resource_key
        self.sql_resource_key = sql_resource_key
        self.system_prompt = system_prompt
        self.tool_schemas = tool_schemas
        super().__init__(**kwargs)
        self._build_graph()

    def _build_graph(self) -> None:
        """Tạo graph đọc revision, compact có điều kiện và fail-open khi lỗi."""
        from beeflow.nodes import BranchNode, CodeNode, END, INPUT, LLMNode, OUTPUT, START
        from beeflow.nodes.primitives.data.sql_node import SQLNode
        from beegen.configs.storage.sql_config import SQLOperation

        with self:
            code_build_agent_state_list_params = CodeNode(
                name="code_build_agent_state_list_params",
                code_fn=build_list_agent_state_revision_params,
                inputs={"session_id": INPUT["session_id"]},
                return_keys={"params: list"},
            )
            data_query_agent_state_revisions = SQLNode(
                name="data_query_agent_state_revisions",
                operation=SQLOperation.QUERY,
                resource_key=self.sql_resource_key,
                inputs={
                    "query": LIST_AGENT_STATE_REVISIONS_SQL,
                    "params": {code_build_agent_state_list_params: "params"},
                    "limit": 3,
                },
            )
            code_prepare_context_compaction = CodeNode(
                name="code_prepare_context_compaction",
                code_fn=_prepare_node,
                inputs={
                    "api_messages": INPUT["api_messages"],
                    "revision_rows": {data_query_agent_state_revisions: "data"},
                    "session_id": INPUT["session_id"],
                    "system_prompt": self.system_prompt,
                    "trusted_context": INPUT["trusted_context"],
                    "tool_schemas": self.tool_schemas,
                },
                return_keys={
                    "prepared: dict",
                    "summary_messages: list[dict]",
                    "estimated_tokens: int",
                    "should_compact: int",
                },
            )
            branch_should_compact_context = BranchNode(
                name="branch_should_compact_context",
                cases={"should_compact == 1": "code_notify_context_compaction"},
                default="code_finalize_context_without_summary",
                inputs={
                    "should_compact": {
                        code_prepare_context_compaction: "should_compact"
                    }
                },
            )
            code_notify_context_compaction = CodeNode(
                name="code_notify_context_compaction",
                code_fn=_notify_context_compaction,
                return_keys=[],
                stream=True,
                status_message=CONTEXT_COMPACTION_PROGRESS_MESSAGE,
            )
            code_finalize_context_without_summary = CodeNode(
                name="code_finalize_context_without_summary",
                code_fn=_finalize_without_compaction,
                inputs={"prepared": {code_prepare_context_compaction: "prepared"}},
                return_keys={
                    "messages: list[dict]",
                    "historical_summary: str",
                    "summary_covered_api_message_count: int",
                    "summary_covered_api_prefix_hash: str",
                },
                outputs={
                    "messages": {OUTPUT: "context_messages"},
                    "historical_summary": OUTPUT,
                    "summary_covered_api_message_count": OUTPUT,
                    "summary_covered_api_prefix_hash": OUTPUT,
                },
            )
            llm_summarize_context = LLMNode(
                name="llm_summarize_context",
                resource_key=self.resource_key,
                inputs={
                    "messages": {code_prepare_context_compaction: "summary_messages"},
                    "reasoning_effort": "minimal",
                },
                stream=False,
            )
            code_validate_context_summary = CodeNode(
                name="code_validate_context_summary",
                code_fn=validate_summary,
                inputs={
                    "content": {llm_summarize_context: "content"},
                    "finish_reason": {llm_summarize_context: "finish_reason"},
                },
                return_keys={"valid: int", "summary: str"},
            )
            branch_summary_valid = BranchNode(
                name="branch_summary_valid",
                cases={"valid == 1": "code_finalize_compacted_context"},
                default="code_finalize_context_without_summary",
                inputs={"valid": {code_validate_context_summary: "valid"}},
            )
            code_finalize_compacted_context = CodeNode(
                name="code_finalize_compacted_context",
                code_fn=_finalize_compacted_context,
                inputs={
                    "prepared": {code_prepare_context_compaction: "prepared"},
                    "valid": {code_validate_context_summary: "valid"},
                    "summary": {code_validate_context_summary: "summary"},
                },
                return_keys={
                    "messages: list[dict]",
                    "historical_summary: str",
                    "summary_covered_api_message_count: int",
                    "summary_covered_api_prefix_hash: str",
                },
                outputs={
                    "messages": {OUTPUT: "context_messages"},
                    "historical_summary": OUTPUT,
                    "summary_covered_api_message_count": OUTPUT,
                    "summary_covered_api_prefix_hash": OUTPUT,
                },
            )
            START >> code_build_agent_state_list_params >> data_query_agent_state_revisions >> code_prepare_context_compaction >> branch_should_compact_context
            branch_should_compact_context >> code_notify_context_compaction >> llm_summarize_context
            branch_should_compact_context >> code_finalize_context_without_summary
            llm_summarize_context >> code_validate_context_summary >> branch_summary_valid
            branch_summary_valid >> [
                code_finalize_compacted_context,
                code_finalize_context_without_summary,
            ]
            code_finalize_compacted_context >> END
            code_finalize_context_without_summary >> END
        self.build()


class AgentStateRevisionPersistenceNode(GraphNode):
    """Ghi best-effort một revision PostgreSQL sau khi Plan agent hoàn tất."""

    def __init__(self, sql_resource_key: str, **kwargs):
        self.sql_resource_key = sql_resource_key
        super().__init__(**kwargs)
        self._build_graph()

    def _build_graph(self) -> None:
        """Tạo graph CodeNode -> SQLNode INSERT, không phát thêm output UI."""
        from beeflow.nodes import CodeNode, END, INPUT, START
        from beeflow.nodes.primitives.data.sql_node import SQLNode
        from beegen.configs.storage.sql_config import SQLOperation

        with self:
            code_build_agent_state_revision_params = CodeNode(
                name="code_build_agent_state_revision_params",
                code_fn=_build_agent_state_revision_params,
                inputs={
                    "final_state_messages": INPUT["final_state_messages"],
                    "api_messages": INPUT["api_messages"],
                    "session_id": INPUT["session_id"],
                    "client_message_id": INPUT["client_message_id"],
                    "historical_summary": INPUT["historical_summary"],
                    "summary_covered_api_message_count": INPUT[
                        "summary_covered_api_message_count"
                    ],
                    "summary_covered_api_prefix_hash": INPUT[
                        "summary_covered_api_prefix_hash"
                    ],
                },
                return_keys={"params: list"},
            )
            data_insert_agent_state_revision = SQLNode(
                name="data_insert_agent_state_revision",
                operation=SQLOperation.EXECUTE,
                resource_key=self.sql_resource_key,
                inputs={
                    "query": INSERT_AGENT_STATE_REVISION_SQL,
                    "params": {code_build_agent_state_revision_params: "params"},
                    "returning": False,
                },
            )
            START >> code_build_agent_state_revision_params >> data_insert_agent_state_revision >> END
        self.build()
