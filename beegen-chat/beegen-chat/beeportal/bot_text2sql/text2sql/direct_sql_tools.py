from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

from beeportal.bot_text2sql.text2sql.metadata import (
    build_table_overview_query,
    get_authorized_metadata_filter,
    validate_db_dialect,
)
from beeportal.bot_text2sql.text2sql.nlp import (
    persist_latest_sql,
    resolve_direct_metadata_tables,
)
from beeportal.bot_text2sql.text2sql.mermaid_validator import validate_mermaid
from beeportal.bot_text2sql.text2sql.post_processing_sql import inspect_sql


PRIVATE_TOOL_INPUTS = {
    "role_ids",
    "metadata",
    "session_id",
    "bot_id",
    "client_message_id",
    "allowed_tables",
}

MERMAID_CHART_SKILL_PATH = (
    Path(__file__).resolve().parent / "skills" / "mermaid-chart" / "SKILL.md"
)


def build_direct_sql_tool_context(
    role_ids: List[str],
    metadata: Dict[str, Any],
    session_id: str,
    bot_id: str = "",
    client_message_id: str = "",
) -> Dict[str, Dict[str, Any]]:
    """Inject trusted role, TableDomain and session values outside the LLM schema."""
    accessible = list((metadata or {}).get("TableDomain") or [])
    return {"tool_context": {
        "role_ids": list(role_ids or []),
        "metadata": metadata or {},
        "session_id": str(session_id or ""),
        "bot_id": str(bot_id or ""),
        "client_message_id": str(client_message_id or ""),
        "allowed_tables": accessible,
    }}


def build_direct_sql_tool_schemas(tools: List[Any]) -> List[Dict[str, Any]]:
    """Expose only model-owned arguments; permission inputs stay private."""
    schemas = []
    for tool in tools:
        schema = deepcopy(tool.get_openai_tool_schema())
        function = schema.setdefault("function", {})
        parameters = function.setdefault("parameters", {})
        properties = parameters.get("properties", {})
        parameters["properties"] = {
            key: value for key, value in properties.items()
            if key not in PRIVATE_TOOL_INPUTS
        }
        parameters["required"] = [
            key for key in parameters.get("required", [])
            if key not in PRIVATE_TOOL_INPUTS
        ]
        if function.get("name") in {"execute_sql", "export_sql_to_csv"}:
            parameters["properties"]["dialect"]["enum"] = ["oracle", "postgres"]
        schemas.append(schema)
    return schemas


def inspect_sql_syntax(sql: str) -> Dict[str, Any]:
    inspection = inspect_sql(sql)
    return {
        key: inspection[key]
        for key in ("syntax_valid", "statement_count", "physical_tables", "parse_error")
    }


def check_mermaid_syntax(mermaid_code: str) -> Dict[str, Any]:
    """Validate Mermaid code and return a stable tool response."""
    result = validate_mermaid(str(mermaid_code or ""))
    return {"valid": result.valid, "error": result.error or ""}


def load_mermaid_chart_skill() -> Dict[str, str]:
    """Load the fixed, repository-owned Mermaid chart skill on demand."""
    try:
        content = MERMAID_CHART_SKILL_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        return {
            "skill_name": "mermaid-chart",
            "content": "",
            "error": f"Unable to load Mermaid chart skill: {exc}",
        }
    return {"skill_name": "mermaid-chart", "content": content, "error": ""}


def prepare_sql_verification(sql: str, allowed_tables: Any) -> Dict[str, Any]:
    """Inspect SQL and resolve its physical tables against the accessible overview."""
    final_sql = str(sql or "").strip()
    inspection = inspect_sql(final_sql)
    resolved = resolve_direct_metadata_tables(
        inspection["physical_tables"],
        inspection["metadata_references_valid"],
        allowed_tables,
    )
    reason = "" if resolved["use_metadata"] == 1 else (
        "Không xác minh được toàn bộ bảng theo phạm vi quyền."
    )
    return {
        "tables": resolved["tables"],
        "precheck_reason": reason,
    }


def finalize_sql_verification(
    sql: str,
    allowed_tables: Any,
    db_dialect: Any,
    tables: Any,
    precheck_reason: str = "",
) -> Dict[str, Any]:
    """Verify executable SQL against its accessible overview and dialect."""
    final_sql = str(sql or "").strip()
    verified_tables = list(tables or [])
    if precheck_reason:
        return {
            "final_sql": final_sql,
            "is_verified": 0,
            "decision_reason": str(precheck_reason),
            "verified_tables": verified_tables,
        }

    execution = validate_execute_request(
        final_sql,
        str(db_dialect or ""),
        verified_tables,
        allowed_tables,
    )
    if not execution["can_execute"]:
        reason = execution["reason"]
    else:
        return {
            "final_sql": execution["final_sql"],
            "is_verified": 1,
            "decision_reason": "SQL hợp lệ, read-only, đúng quyền và dialect.",
            "verified_tables": verified_tables,
        }
    return {
        "final_sql": execution["final_sql"],
        "is_verified": 0,
        "decision_reason": reason,
        "verified_tables": verified_tables,
    }


def validate_execute_request(
    sql: str,
    dialect: str,
    tables: List[str] | None = None,
    allowed_tables: Any = None,
) -> Dict[str, Any]:
    """Check read-only SQL; check tables too only when verify supplies an access scope."""
    final_sql = str(sql or "").strip()
    db_dialect = str(dialect or "").strip().lower()
    if db_dialect not in {"oracle", "postgres"}:
        return {
            "final_sql": final_sql,
            "can_execute": 0,
            "reason": "Missing or invalid database dialect; call get_table_metadata_details.",
        }

    inspection = inspect_sql(final_sql, db_dialect)
    if not inspection["syntax_valid"]:
        return {
            "final_sql": final_sql,
            "can_execute": 0,
            "reason": f"Invalid SQL: {inspection['parse_error']}",
        }
    if not inspection["is_read_only"]:
        return {
            "final_sql": final_sql,
            "can_execute": 0,
            "reason": "Only read-only SELECT/CTE queries are allowed.",
        }
    if allowed_tables is None:
        return {"final_sql": final_sql, "can_execute": 1, "reason": ""}

    sql_tables = resolve_direct_metadata_tables(
        inspection["physical_tables"],
        inspection["metadata_references_valid"],
        allowed_tables,
    )
    selected_tables = resolve_direct_metadata_tables(tables, 1, allowed_tables)
    if not sql_tables["use_metadata"] or not selected_tables["use_metadata"]:
        reason = "A table is outside the accessible scope."
    elif set(sql_tables["tables"]) != set(selected_tables["tables"]):
        reason = "The supplied tables do not match the SQL."
    else:
        return {"final_sql": final_sql, "can_execute": 1, "reason": ""}
    return {"final_sql": final_sql, "can_execute": 0, "reason": reason}


def rejected_sql_execution(reason: str) -> Dict[str, Any]:
    return {"count": 0, "data": [], "status": "rejected", "error": reason}


def persist_rejected_sql(sql: str, reason: str, session_id: str) -> Dict[str, Any]:
    """Persist a validation rejection so it supersedes an older successful cache."""
    return persist_latest_sql(sql, "rejected", 0, session_id, [], reason)


def rejected_csv_export(reason: str) -> Dict[str, Any]:
    return {
        "download_link": "",
        "file_name": "",
        "row_count": 0,
        "error": str(reason or "Export failed."),
    }


def prepare_csv_export(status: str, count: int, error: str) -> Dict[str, Any]:
    try:
        row_count = int(count or 0)
    except (TypeError, ValueError):
        row_count = 0
    if str(status or "").strip().lower() == "success" and row_count > 0:
        return {"should_upload": 1, "export_error": ""}
    return {
        "should_upload": 0,
        "export_error": str(error or "No data to export"),
    }


def _normalize_export_allowed_tables(allowed_tables: Any) -> List[Dict[str, str]]:
    """Normalize trusted scope rows for the existing metadata resolver."""
    normalized = []
    for item in allowed_tables or []:
        if not isinstance(item, dict):
            continue
        schema = str(
            item.get("schema_name") or item.get("schemaName") or item.get("schema") or ""
        ).strip()
        table = str(
            item.get("table_name") or item.get("tableName") or item.get("table") or ""
        ).strip()
        if not schema and table.count(".") == 1:
            schema, table = (part.strip() for part in table.split(".", 1))
        if schema and table:
            normalized.append({"schema_name": schema, "table_name": table})
    return normalized


def validate_export_sql_source(
    sql: str,
    dialect: str,
    allowed_tables: Any,
) -> Dict[str, Any]:
    """Validate a user-provided read-only SQL query before exporting it."""
    final_sql = str(sql or "").strip()
    result = {"final_sql": final_sql, "can_export": 0, "reason": "", "tables": []}
    accessible = _normalize_export_allowed_tables(allowed_tables)
    inspection = inspect_sql(final_sql, str(dialect or "").strip().lower())
    tables = list(inspection.get("physical_tables") or [])
    result["tables"] = tables
    execution = validate_execute_request(
        final_sql,
        dialect,
        tables,
        accessible,
    )
    if not execution["can_execute"]:
        result["reason"] = execution["reason"]
        return result

    result.update(
        final_sql=execution["final_sql"],
        can_export=1,
        reason="",
        tables=tables,
    )
    return result


def validate_export_rows(data: Any) -> Dict[str, Any]:
    """Validate rectangular rows without changing values or column labels."""
    if not isinstance(data, list) or not data:
        return {
            "valid": False,
            "validated_data": [],
            "reason": "Data must be a non-empty list.",
        }
    if not all(isinstance(row, dict) and row for row in data):
        return {
            "valid": False,
            "validated_data": [],
            "reason": "Each row must be a non-empty dictionary.",
        }
    columns = tuple(data[0].keys())
    column_set = set(columns)
    if any(set(row.keys()) != column_set for row in data[1:]):
        return {
            "valid": False,
            "validated_data": [],
            "reason": "All rows must contain the same columns.",
        }
    return {"valid": True, "validated_data": data, "reason": ""}


def build_verify_sql_tool():
    """Verify SQL syntax, permissions and dialect from the accessible overview."""
    from beegen.configs.storage.sql_config import SQLOperation
    from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
    from beeflow.nodes.graph.graph_node import GraphNode
    from beeflow.nodes.primitives.data.sql_node import SQLNode
    from beeflow.nodes.primitives.transform.code_node import CodeNode

    exposed = {
        "final_sql": OUTPUT,
        "is_verified": OUTPUT,
        "decision_reason": OUTPUT,
        "verified_tables": OUTPUT,
    }
    verification_keys = {
        "final_sql: str",
        "is_verified: int",
        "decision_reason: str",
        "verified_tables: list[str]",
    }
    with GraphNode(
        name="verify_sql",
        description="Verify final SQL syntax, read-only safety, table permission and dialect; never execute.",
        inputs={"sql": INPUT["sql"], "role_ids": INPUT["role_ids"], "metadata": INPUT["metadata"]},
        outputs=exposed,
    ) as tool:
        name = "verify_sql"
        build_overview = CodeNode(
            name=f"{name}_build_overview_query",
            code_fn=build_table_overview_query,
            inputs={"role_ids": INPUT["role_ids"], "metadata": INPUT["metadata"]},
            return_keys={"sql_table: str"},
        )
        allowed = SQLNode(
            name=f"{name}_get_overview",
            operation=SQLOperation.QUERY,
            resource_key="anapp",
            inputs={"query": {build_overview: "sql_table"}, "limit": 100},
        )
        prepare = CodeNode(
            name=f"{name}_inspect",
            code_fn=prepare_sql_verification,
            inputs={"sql": INPUT["sql"], "allowed_tables": {allowed: "data"}},
            return_keys={
                "tables: list[str]",
                "precheck_reason: str",
            },
        )
        dialect = CodeNode(
            name=f"{name}_validate_dialect",
            code_fn=validate_db_dialect,
            inputs={"table_metadata": {allowed: "data"}},
            return_keys={
                "db_dialect: str",
                "is_consistent: int",
                "dialects_found: list[str]",
                "table_count: int",
            },
        )
        common = {
            "sql": INPUT["sql"],
            "allowed_tables": {allowed: "data"},
            "tables": {prepare: "tables"},
            "precheck_reason": {prepare: "precheck_reason"},
        }
        finish = CodeNode(
            name=f"{name}_finish",
            code_fn=finalize_sql_verification,
            inputs={**common, "db_dialect": {dialect: "db_dialect"}},
            return_keys=verification_keys,
            outputs=exposed,
        )
        START >> build_overview >> allowed >> [prepare, dialect]
        prepare >> finish
        dialect >> finish >> END
    tool.build()
    return tool


def build_check_sql_syntax_tool():
    from beegen.tools.schema.param import ParamSet
    from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
    from beeflow.nodes.graph.graph_node import GraphNode
    from beeflow.nodes.primitives.transform.code_node import CodeNode

    with GraphNode(
        name="check_sql_syntax",
        description="Inspect SQL syntax, statement count and referenced physical tables.",
        input_schema=(
            ParamSet.new()
            .var("sql: str", "SQL to inspect", required=True)
            .build()
        ),
    ) as tool:
        inspect = CodeNode(
            name="check_sql_syntax_inspect",
            code_fn=inspect_sql_syntax,
            inputs={"sql": INPUT["sql"]},
            return_keys={
                "syntax_valid: int",
                "statement_count: int",
                "physical_tables: list[str]",
                "parse_error: str",
            },
            outputs=OUTPUT,
        )
        START >> inspect >> END
    tool.build()
    return tool


def build_check_mermaid_syntax_tool():
    from beegen.tools.schema.param import ParamSet
    from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
    from beeflow.nodes.graph.graph_node import GraphNode
    from beeflow.nodes.primitives.transform.code_node import CodeNode

    with GraphNode(
        name="check_mermaid_syntax",
        description="Validate Mermaid syntax without returning rendered output.",
        input_schema=(
            ParamSet.new()
            .var("mermaid_code: str", "Mermaid code to validate", required=True)
            .build()
        ),
    ) as tool:
        validate = CodeNode(
            name="check_mermaid_syntax_validate",
            code_fn=check_mermaid_syntax,
            inputs={"mermaid_code": INPUT["mermaid_code"]},
            return_keys={"valid: bool", "error: str"},
            outputs=OUTPUT,
        )
        START >> validate >> END
    tool.build()
    return tool


def build_load_mermaid_chart_skill_tool():
    from beegen.tools.schema.param import ParamSet
    from beeflow.nodes.base_node import END, OUTPUT, START
    from beeflow.nodes.graph.graph_node import GraphNode
    from beeflow.nodes.primitives.transform.code_node import CodeNode

    outputs = {
        "skill_name": OUTPUT,
        "content": OUTPUT,
        "error": OUTPUT,
    }
    with GraphNode(
        name="load_mermaid_chart_skill",
        description="Load the repository-owned Mermaid chart instructions on demand.",
        input_schema=ParamSet.new().build(),
        outputs=outputs,
    ) as tool:
        load = CodeNode(
            name="load_mermaid_chart_skill_load",
            code_fn=load_mermaid_chart_skill,
            inputs={},
            return_keys={
                "skill_name: str",
                "content: str",
                "error: str",
            },
            outputs=outputs,
        )
        START >> load >> END
    tool.build()
    return tool


def build_accessible_table_metadata_tool():
    from beegen.configs.storage.sql_config import SQLOperation
    from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
    from beeflow.nodes.graph.graph_node import GraphNode
    from beeflow.nodes.primitives.data.sql_node import SQLNode
    from beeflow.nodes.primitives.transform.code_node import CodeNode

    with GraphNode(
        name="get_accessible_table_metadata",
        description="List active schema.table names and descriptions allowed by role and TableDomain.",
    ) as tool:
        build_query = CodeNode(
            name="accessible_metadata_build_query",
            code_fn=build_table_overview_query,
            inputs={"role_ids": INPUT["role_ids"], "metadata": INPUT["metadata"]},
            return_keys={"sql_table: str"},
        )
        get_tables = SQLNode(
            name="accessible_metadata_get_tables",
            operation=SQLOperation.QUERY,
            resource_key="anapp",
            inputs={"query": {build_query: "sql_table"}, "limit": 100},
            outputs={
                "data": {OUTPUT: "tables"},
                "count": {OUTPUT: "table_count"},
                "status": {OUTPUT: "status"},
                "error": {OUTPUT: "error"},
            },
        )
        START >> build_query >> get_tables >> END
    tool.build()
    return tool


def build_table_metadata_details_tool():
    from beegen.configs.storage.sql_config import SQLOperation
    from beegen.tools.schema.param import ParamSet
    from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
    from beeflow.nodes.graph.graph_node import GraphNode
    from beeflow.nodes.primitives.data.sql_node import SQLNode
    from beeflow.nodes.primitives.transform.code_node import CodeNode

    with GraphNode(
        name="get_table_metadata_details",
        description=(
            "Return dialect, columns and descriptions only for requested permitted "
            "schema.table names. Pass tables as strings, for example "
            "['apps.FIN_SMY_CUSTOMER_MONTHLY_POC'], never overview row objects."
        ),
        input_schema=(
            ParamSet.new()
            .var(
                "tables: list[str]",
                "Permitted schema.table strings, for example ['apps.table_name']",
                required=True,
            )
            .var("role_ids: list[str]", "Trusted role scope", required=True)
            .var("metadata: dict", "Trusted TableDomain scope", required=True)
            .build()
        ),
    ) as tool:
        build_detail = CodeNode(
            name="details_build_authorized_query",
            code_fn=get_authorized_metadata_filter,
            inputs={
                "tables": INPUT["tables"],
                "role_ids": INPUT["role_ids"],
                "metadata": INPUT["metadata"],
            },
            return_keys={"query: str", "params: list"},
        )
        detail = SQLNode(
            name="details_get_metadata",
            operation=SQLOperation.QUERY,
            resource_key="anapp",
            inputs={"query": {build_detail: "query"}, "params": {build_detail: "params"}, "limit": 100},
            outputs={
                "data": {OUTPUT: "table_metadata"},
                "status": {OUTPUT: "status"},
                "error": {OUTPUT: "error"},
            },
        )
        dialect = CodeNode(
            name="details_validate_dialect",
            code_fn=validate_db_dialect,
            inputs={"table_metadata": {detail: "data"}},
            return_keys={
                "db_dialect: str",
                "is_consistent: int",
                "dialects_found: list[str]",
                "table_count: int",
            },
            outputs={"db_dialect": OUTPUT},
        )
        START >> build_detail
        build_detail >> detail >> dialect >> END
    tool.build()
    return tool


def build_execute_sql_tool():
    from beegen.configs.cache.redis_config import RedisOperation
    from beegen.tools.schema.param import ParamSet
    from beeflow.nodes import RedisNode
    from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
    from beeflow.nodes.flow.branch_node import BranchNode
    from beeflow.nodes.graph.graph_node import GraphNode
    from beeflow.nodes.primitives.transform.code_node import CodeNode
    from beeportal.bot_text2sql.text2sql.executor import execute_sql_via_bytebase

    result_keys = {
        "count: int",
        "data: list[dict]",
        "status: str",
        "error: str",
    }
    with GraphNode(
        name="execute_sql",
        description="Execute a verified read-only SQL query after a dialect-aware read-only check.",
        input_schema=(
            ParamSet.new()
            .var("sql: str", "Verified SQL to execute", required=True)
            .var("dialect: str", "Database dialect from table metadata", required=True)
            .var("session_id: str", "Private session for successful-result cache", required=True)
            .build()
        ),
    ) as tool:
        validate = CodeNode(
            name="execute_sql_validate",
            code_fn=validate_execute_request,
            inputs={
                "sql": INPUT["sql"],
                "dialect": INPUT["dialect"],
            },
            return_keys={"final_sql: str", "can_execute: int", "reason: str"},
        )
        branch = BranchNode(
            name="execute_sql_branch",
            cases={"can_execute == 1": "execute_sql_bytebase"},
            default="execute_sql_rejected",
            inputs={"can_execute": {validate: "can_execute"}},
        )
        rejected = CodeNode(
            name="execute_sql_rejected",
            code_fn=rejected_sql_execution,
            inputs={"reason": {validate: "reason"}},
            return_keys=result_keys,
            outputs=OUTPUT,
        )
        bytebase = CodeNode(
            name="execute_sql_bytebase",
            code_fn=execute_sql_via_bytebase,
            inputs={"query": {validate: "final_sql"}, "query_timeout": 120},
            return_keys=result_keys,
            outputs=OUTPUT,
        )
        persist = CodeNode(
            name="execute_sql_prepare_cache",
            code_fn=persist_latest_sql,
            inputs={
                "sql": {validate: "final_sql"},
                "status": {bytebase: "status"},
                "count": {bytebase: "count"},
                "session_id": INPUT["session_id"],
                "data": {bytebase: "data"},
                "error": {bytebase: "error"},
            },
            return_keys={"should_persist: int", "redis_key: str", "redis_value: str"},
        )
        save_branch = BranchNode(
            name="execute_sql_branch_cache",
            cases={"should_persist == 1": "execute_sql_save_cache"},
            default=END,
            inputs={"should_persist": {persist: "should_persist"}},
        )
        save = RedisNode(
            name="execute_sql_save_cache",
            resource_key="aicenter-chatbot",
            operation=RedisOperation.SETEX,
            inputs={"key": {persist: "redis_key"}, "value": {persist: "redis_value"}, "seconds": 7200},
        )
        persist_rejected = CodeNode(
            name="execute_sql_prepare_rejected_cache",
            code_fn=persist_rejected_sql,
            inputs={
                "sql": {validate: "final_sql"},
                "reason": {validate: "reason"},
                "session_id": INPUT["session_id"],
            },
            return_keys={"should_persist: int", "redis_key: str", "redis_value: str"},
        )
        rejected_save_branch = BranchNode(
            name="execute_sql_branch_rejected_cache",
            cases={"should_persist == 1": "execute_sql_save_rejected_cache"},
            default=END,
            inputs={"should_persist": {persist_rejected: "should_persist"}},
        )
        rejected_save = RedisNode(
            name="execute_sql_save_rejected_cache",
            resource_key="aicenter-chatbot",
            operation=RedisOperation.SETEX,
            inputs={
                "key": {persist_rejected: "redis_key"},
                "value": {persist_rejected: "redis_value"},
                "seconds": 7200,
            },
        )
        START >> validate >> branch >> [bytebase, rejected]
        rejected >> persist_rejected >> rejected_save_branch >> [rejected_save, END]
        rejected_save >> END
        bytebase >> persist
        persist >> save_branch >> [save, END]
        save >> END
    tool.build()
    return tool


def build_export_sql_to_csv_tool():
    from beegen.tools.schema.param import ParamSet
    from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
    from beeflow.nodes.flow.branch_node import BranchNode
    from beeflow.nodes.graph.graph_node import GraphNode
    from beeflow.nodes.primitives.transform.code_node import CodeNode
    from beeportal.bot_text2sql.text2sql.executor import execute_sql_with_custom_limit
    from beeportal.bot_text2sql.text2sql.exporter import create_csv_and_upload_s3

    export_outputs = {
        "download_link": OUTPUT,
        "file_name": OUTPUT,
        "row_count": OUTPUT,
        "error": OUTPUT,
    }
    export_keys = {
        "download_link: str",
        "file_name: str",
        "row_count: int",
        "error: str",
    }
    with GraphNode(
        name="export_sql_to_csv",
        description="Execute a read-only SQL query with a 1000-row limit and upload its result as CSV.",
        input_schema=(
            ParamSet.new()
            .var("sql: str", "Read-only SQL to export", required=True)
            .var("dialect: str", "Database dialect for SQL validation", required=True)
            .var("bot_id: str", "Private bot ID for upload", required=True)
            .var("client_message_id: str", "Private client message ID for upload", required=True)
            .var("allowed_tables: list[dict]", "Private accessible table scope", required=True)
            .build()
        ),
        outputs=export_outputs,
    ) as tool:
        validate = CodeNode(
            name="export_sql_to_csv_validate",
            code_fn=validate_export_sql_source,
            inputs={
                "sql": INPUT["sql"],
                "dialect": INPUT["dialect"],
                "allowed_tables": INPUT["allowed_tables"],
            },
            return_keys={
                "final_sql: str",
                "can_export: int",
                "reason: str",
                "tables: list[str]",
            },
        )
        validate_branch = BranchNode(
            name="export_sql_to_csv_validate_branch",
            cases={"can_export == 1": "export_sql_to_csv_execute"},
            default="export_sql_to_csv_validation_rejected",
            inputs={"can_export": {validate: "can_export"}},
        )
        validation_rejected = CodeNode(
            name="export_sql_to_csv_validation_rejected",
            code_fn=rejected_csv_export,
            inputs={"reason": {validate: "reason"}},
            return_keys=export_keys,
            outputs=export_outputs,
        )
        execute = CodeNode(
            name="export_sql_to_csv_execute",
            code_fn=execute_sql_with_custom_limit,
            inputs={"query": {validate: "final_sql"}, "limit": 1000},
            return_keys={"count: int", "data: list[dict]", "status: str", "error: str"},
        )
        prepare = CodeNode(
            name="export_sql_to_csv_prepare",
            code_fn=prepare_csv_export,
            inputs={
                "status": {execute: "status"},
                "count": {execute: "count"},
                "error": {execute: "error"},
            },
            return_keys={"should_upload: int", "export_error: str"},
        )
        upload_branch = BranchNode(
            name="export_sql_to_csv_upload_branch",
            cases={"should_upload == 1": "export_sql_to_csv_upload"},
            default="export_sql_to_csv_execution_rejected",
            inputs={"should_upload": {prepare: "should_upload"}},
        )
        execution_rejected = CodeNode(
            name="export_sql_to_csv_execution_rejected",
            code_fn=rejected_csv_export,
            inputs={"reason": {prepare: "export_error"}},
            return_keys=export_keys,
            outputs=export_outputs,
        )
        upload = CodeNode(
            name="export_sql_to_csv_upload",
            code_fn=create_csv_and_upload_s3,
            inputs={
                "data": {execute: "data"},
                "bot_id": INPUT["bot_id"],
                "client_message_id": INPUT["client_message_id"],
            },
            return_keys={"download_link: str", "file_name: str", "row_count: int", "error: str"},
            outputs=export_outputs,
        )
        START >> validate >> validate_branch >> [execute, validation_rejected]
        validation_rejected >> END
        execute >> prepare >> upload_branch >> [upload, execution_rejected]
        upload >> END
        execution_rejected >> END
    tool.build()
    return tool


def build_export_data_to_csv_tool():
    from beegen.tools.schema.param import ParamSet
    from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
    from beeflow.nodes.flow.branch_node import BranchNode
    from beeflow.nodes.graph.graph_node import GraphNode
    from beeflow.nodes.primitives.transform.code_node import CodeNode
    from beeportal.bot_text2sql.text2sql.exporter import create_csv_and_upload_s3

    export_outputs = {
        "download_link": OUTPUT,
        "file_name": OUTPUT,
        "row_count": OUTPUT,
        "error": OUTPUT,
    }
    with GraphNode(
        name="export_data_to_csv",
        description="Upload already available tabular data as a CSV file.",
        input_schema=(
            ParamSet.new()
            .var("data: list[dict]", "Rows to export", required=True)
            .var("bot_id: str", "Private bot ID for upload", required=True)
            .var("client_message_id: str", "Private client message ID for upload", required=True)
            .build()
        ),
        outputs=export_outputs,
    ) as tool:
        validate = CodeNode(
            name="export_data_to_csv_validate",
            code_fn=validate_export_rows,
            inputs={"data": INPUT["data"]},
            return_keys={"valid: bool", "validated_data: list[dict]", "reason: str"},
        )
        validate_branch = BranchNode(
            name="export_data_to_csv_validate_branch",
            cases={"valid == True": "export_data_to_csv_upload"},
            default="export_data_to_csv_validation_rejected",
            inputs={"valid": {validate: "valid"}},
        )
        validation_rejected = CodeNode(
            name="export_data_to_csv_validation_rejected",
            code_fn=rejected_csv_export,
            inputs={"reason": {validate: "reason"}},
            return_keys={
                "download_link: str",
                "file_name: str",
                "row_count: int",
                "error: str",
            },
            outputs=export_outputs,
        )
        upload = CodeNode(
            name="export_data_to_csv_upload",
            code_fn=create_csv_and_upload_s3,
            inputs={
                "data": {validate: "validated_data"},
                "bot_id": INPUT["bot_id"],
                "client_message_id": INPUT["client_message_id"],
            },
            return_keys={"download_link: str", "file_name: str", "row_count: int", "error: str"},
            outputs=export_outputs,
        )
        START >> validate >> validate_branch >> [upload, validation_rejected]
        upload >> END
        validation_rejected >> END
    tool.build()
    return tool
