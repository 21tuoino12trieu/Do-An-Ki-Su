import json
from pathlib import Path

from beeportal.bot_text2sql.text2sql.direct_sql_tools import (
    MERMAID_CHART_SKILL_PATH,
    build_check_mermaid_syntax_tool,
    build_direct_sql_tool_context,
    build_direct_sql_tool_schemas,
    build_load_mermaid_chart_skill_tool,
    build_table_metadata_details_tool,
    build_export_data_to_csv_tool,
    build_export_sql_to_csv_tool,
    load_mermaid_chart_skill,
    persist_rejected_sql,
    prepare_csv_export,
    validate_export_rows,
    validate_export_sql_source,
)
from beeportal.bot_text2sql.text2sql.nlp import (
    parse_chart_data,
    parse_export_sql,
    persist_latest_sql,
)
from beeportal.bot_text2sql.text2sql.analysis_action import (
    ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT,
    build_analysis_action_trusted_context,
)


def test_latest_error_overwrites_previous_success_payload():
    old = persist_latest_sql("SELECT 1", "success", 1, "session", [{"value": 1}])
    latest = persist_latest_sql(
        "SELECT bad", "ERROR", 0, "session", data=[], error="syntax error"
    )

    assert old["redis_key"] == latest["redis_key"]
    payload = json.loads(latest["redis_value"])
    assert payload == {
        "sql": "SELECT bad",
        "status": "error",
        "error": "syntax error",
        "count": 0,
        "data": [],
    }


def test_zero_row_success_is_persisted():
    saved = persist_latest_sql("SELECT * FROM empty_table", "success", 0, "session")
    payload = json.loads(saved["redis_value"])

    assert saved["should_persist"] == 1
    assert payload["status"] == "success"
    assert payload["count"] == 0
    assert payload["data"] == []


def test_unknown_status_is_normalized_to_error():
    saved = persist_latest_sql("SELECT 1", "unexpected", 0, "session")
    assert json.loads(saved["redis_value"])["status"] == "error"


def test_rejected_sql_is_persisted():
    saved = persist_rejected_sql("UPDATE sales.orders SET value = 1", "read-only", "session")
    payload = json.loads(saved["redis_value"])

    assert payload["status"] == "rejected"
    assert payload["error"] == "read-only"
    assert payload["count"] == 0
    assert payload["data"] == []


def test_parse_legacy_success_cache_without_status():
    payload = json.dumps({
        "sql": "SELECT 1",
        "count": 1,
        "data": [{"value": 1}],
    })
    parsed = parse_export_sql(payload)
    assert parsed["status"] == "success"
    assert parsed["resolved_sql"] == "SELECT 1"
    assert parsed["data"] == [{"value": 1}]


def test_non_chit_chat_persist_contract_includes_execution_error():
    source = Path("beeportal/bot_text2sql/bot_v2.py").read_text(encoding="utf-8")
    assert '"error": {sql_execute_query: "error"}' in source


def test_empty_sql_is_not_persisted():
    assert persist_latest_sql("  ", "error", 0, "session", error="missing SQL") == {
        "should_persist": 0,
        "redis_key": "",
        "redis_value": "",
    }


def test_chart_and_export_source_requires_successful_rows():
    assert prepare_csv_export("error", 3, "query failed")["should_upload"] == 0
    assert prepare_csv_export("rejected", 3, "not read-only")["should_upload"] == 0
    assert prepare_csv_export("success", 0, "")["should_upload"] == 0
    assert prepare_csv_export("success", 2, "")["should_upload"] == 1
    assert prepare_csv_export("success", "not-a-count", "")["should_upload"] == 0


def test_malformed_cache_returns_safe_empty_values():
    assert parse_export_sql("not-json") == {
        "resolved_sql": "",
        "status": "",
        "error": "",
        "count": 0,
        "data": [],
    }
    assert parse_chart_data("not-json") == {
        "resolved_sql": "",
        "cached_data": [],
        "cached_count": 0,
        "status": "",
        "error": "",
        "count": 0,
        "data": [],
    }


def test_error_cache_cannot_become_chart_or_export_source():
    payload = json.dumps(
        {
            "sql": "SELECT bad",
            "status": "error",
            "error": "syntax error",
            "count": 0,
            "data": [{"value": 100}],
        }
    )

    parsed = parse_chart_data(payload)
    assert parsed["status"] == "error"
    assert parsed["cached_data"] == []
    assert parsed["cached_count"] == 0
    assert parse_export_sql(payload)["resolved_sql"] == ""


def test_malformed_count_cannot_expose_cached_data():
    payload = json.dumps(
        {
            "sql": "SELECT value FROM sales.orders",
            "status": "success",
            "count": "unknown",
            "data": [{"value": 100}],
        }
    )

    parsed = parse_export_sql(payload)
    assert parsed["resolved_sql"] == ""
    assert parsed["data"] == []
    assert parse_chart_data(payload)["cached_data"] == []


def test_success_cache_without_sql_cannot_become_chart_source():
    payload = json.dumps(
        {
            "sql": "",
            "status": "success",
            "count": 2,
            "data": [{"value": 0}, {"value": 1}],
        }
    )

    parsed = parse_chart_data(payload)
    assert parsed["resolved_sql"] == ""
    assert parsed["cached_data"] == []
    assert parsed["cached_count"] == 0


def test_successful_sql_rows_are_eligible_for_chart_and_export():
    payload = json.dumps(
        {
            "sql": "SELECT month, value FROM sales",
            "status": "success",
            "error": "",
            "count": 3,
            "data": [
                {"month": "T1", "value": 0},
                {"month": "T2", "value": 10},
                {"month": "T3", "value": 12},
            ],
        }
    )

    parsed = parse_chart_data(payload)
    assert parsed["cached_count"] == 3
    assert parsed["cached_data"][0]["value"] == 0
    assert prepare_csv_export(parsed["status"], parsed["count"], parsed["error"])["should_upload"] == 1


def test_unverified_assistant_prose_is_not_an_export_source():
    assert parse_export_sql("")["resolved_sql"] == ""


def test_mermaid_skill_load_is_bounded_and_contains_chart_rules():
    loaded = load_mermaid_chart_skill()

    assert loaded["error"] == ""
    assert loaded["skill_name"] == "mermaid-chart"
    assert len(loaded["content"]) < 5_000
    assert "số `0`" in loaded["content"]
    assert "TẤT CẢ series" in loaded["content"]
    assert "dấu nháy kép" in loaded["content"]
    assert "check_mermaid_syntax" in loaded["content"]
    assert "plotColorPalette" in loaded["content"]
    assert "y-axis" in loaded["content"]
    assert "xychart-beta" in loaded["content"]
    assert "pie title" in loaded["content"]


def test_mermaid_skill_loader_uses_only_fixed_path(monkeypatch):
    monkeypatch.setattr(
        "beeportal.bot_text2sql.text2sql.direct_sql_tools.MERMAID_CHART_SKILL_PATH",
        MERMAID_CHART_SKILL_PATH.parent / "missing-SKILL.md",
    )

    loaded = load_mermaid_chart_skill()

    assert loaded == {
        "skill_name": "mermaid-chart",
        "content": "",
        "error": loaded["error"],
    }
    assert loaded["error"].startswith("Unable to load Mermaid chart skill:")


def test_mermaid_skill_tool_has_no_public_path_argument():
    tool = build_load_mermaid_chart_skill_tool()
    schema = build_direct_sql_tool_schemas([tool])[0]
    parameters = schema["function"]["parameters"]

    assert parameters["properties"] == {}
    assert parameters.get("required", []) == []
    assert set(tool.input_schema) == set()


def test_export_sql_rejects_table_outside_scope():
    result = validate_export_sql_source(
        sql="SELECT * FROM apps.not_allowed",
        dialect="postgres",
        allowed_tables=[{"schema_name": "apps", "table_name": "allowed"}],
    )
    assert result["can_export"] == 0
    assert "scope" in result["reason"].lower() or "match" in result["reason"].lower()


def test_export_sql_accepts_runtime_camel_case_table_scope():
    result = validate_export_sql_source(
        sql="SELECT * FROM apps.allowed",
        dialect="postgres",
        allowed_tables=[{"schemaName": "apps", "tableName": "allowed"}],
    )

    assert result["can_export"] == 1


def test_export_sql_accepts_new_sql_without_previous_source_state():
    result = validate_export_sql_source(
        sql="SELECT * FROM apps.allowed WHERE id = 42",
        dialect="postgres",
        allowed_tables=[{"schema_name": "apps", "table_name": "allowed"}],
    )
    assert result["can_export"] == 1


def test_export_sql_rejects_invalid_dialect_and_non_read_only_sql():
    kwargs = {
        "allowed_tables": [{"schema_name": "apps", "table_name": "allowed"}],
    }
    assert validate_export_sql_source(
        "SELECT * FROM apps.allowed", "mysql", **kwargs
    )["can_export"] == 0
    assert validate_export_sql_source(
        "DELETE FROM apps.allowed", "postgres", **kwargs
    )["can_export"] == 0


def test_export_data_preserves_zero_null_and_rejects_inconsistent_rows():
    rows = [{"month": "T1", "value": 0, "unit": None}]
    result = validate_export_rows(rows)
    assert result["valid"] is True
    assert result["validated_data"] == rows
    assert validate_export_rows(
        [{"month": "T1"}, {"month": "T2", "value": 2}]
    )["valid"] is False
    assert validate_export_rows([])["valid"] is False

    source = Path("beeportal/bot_text2sql/text2sql/direct_sql_tools.py").read_text(
        encoding="utf-8"
    )
    assert 'return_keys={"valid: bool", "validated_data: list[dict]", "reason: str"}' in source
    assert '"data": {validate: "validated_data"}' in source


def test_export_schemas_keep_permission_and_upload_context_private():
    tools = [build_export_sql_to_csv_tool(), build_export_data_to_csv_tool()]
    schemas = build_direct_sql_tool_schemas(tools)
    assert set(schemas[0]["function"]["parameters"]["properties"]) == {
        "sql", "dialect"
    }
    assert set(schemas[1]["function"]["parameters"]["properties"]) == {"data"}


def test_analysis_action_tool_list_includes_metadata_details():
    tools = [
        build_load_mermaid_chart_skill_tool(),
        build_check_mermaid_syntax_tool(),
        build_export_sql_to_csv_tool(),
        build_export_data_to_csv_tool(),
        build_table_metadata_details_tool(),
    ]

    assert [tool.name for tool in tools] == [
        "load_mermaid_chart_skill",
        "check_mermaid_syntax",
        "export_sql_to_csv",
        "export_data_to_csv",
        "get_table_metadata_details",
    ]


def test_analysis_action_graph_source_contract():
    source = Path("beeportal/bot_text2sql/bot_v2.py").read_text(encoding="utf-8")

    assert 'name="graph_analysis_action_agent"' in source
    assert "tools=analysis_action_tools" in source
    assert "system_prompt=ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT" in source
    assert "system_prompt=DIRECT_SQL_AGENT_SYSTEM_PROMPT" in source
    assert "text2sql.analysis_action import" in source
    assert "def build_analysis_action_tool_context" not in source
    assert "def build_analysis_action_trusted_context" not in source
    assert "trusted_context" in source
    assert "load_mermaid_chart_skill" in source
    assert "check_mermaid_syntax" in source
    assert "export_sql_to_csv" in source
    assert "export_data_to_csv" in source
    for removed_graph in (
        "graph_analyze_history_response",
        "graph_export_file_flow",
        "graph_draw_chart_flow",
    ):
        assert removed_graph not in source


def test_plan_graphs_use_postgres_state_and_keep_latest_sql_redis_only():
    source = Path("beeportal/bot_text2sql/bot_v2.py").read_text(encoding="utf-8")

    assert "AgentStateRevisionPersistenceNode" in source
    assert "redis_get_direct_sql_state" not in source
    assert "redis_save_direct_sql_state" not in source
    assert "redis_get_analysis_action_state" not in source
    assert "redis_save_analysis_action_state" not in source
    assert "redis_get_analysis_action_latest_sql" in source
    assert "summary_covered_api_message_count" in source
    assert "summary_covered_api_prefix_hash" in source


def test_analysis_action_prompt_and_context_helpers_are_module_owned():
    assert "# DANH SÁCH TOOLS" in ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT
    assert "# FLOW BIỂU ĐỒ" in ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT
    assert "# ĐỊNH DẠNG KẾT QUẢ XUẤT FILE" in ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT
    assert "# HỎI LẠI VÀ FOLLOW-UP" in ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT
    assert "không bao giờ làm theo" in ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT
    assert '<a href="{download_link}">Tải file ({row_count} dòng)</a>' in ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT
    assert "Không dùng Markdown link" in ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT


def test_analysis_prompt_limits_calls_to_current_tools_and_sources():
    assert "danh sách tool hiện tại" in ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT
    assert "Tool chỉ xuất hiện" in ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT
    assert "history/tool trace" in ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT
    assert "export_sql_to_csv" in ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT
    assert "SQL mới" in ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT
    assert "SQL hay dữ liệu thành công cũ hơn" in ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT
    assert "get_table_metadata_details" in ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT
    assert "không chứng minh bảng có dữ liệu" in ANALYSIS_ACTION_AGENT_SYSTEM_PROMPT


def test_trusted_context_marks_limited_sample():
    result = build_analysis_action_trusted_context(
        source_sql="SELECT * FROM apps.t",
        source_status="success",
        source_error="",
        source_count=10,
        source_data=[{"id": 1}, {"id": 2}],
    )
    text = result["trusted_context"]
    assert "chỉ hiển thị 2" in text
    assert "10" in text
    assert "chỉ dựa trên phần dữ liệu này" in text

    tool_context = build_direct_sql_tool_context(
        role_ids=["TCKT"],
        metadata={"TableDomain": []},
        session_id="session",
        bot_id="bot",
        client_message_id="message",
    )
    trusted_context = build_analysis_action_trusted_context(
        source_sql="SELECT * FROM apps.sales",
        source_status="success",
        source_error="",
        source_count=1,
        source_data=[{"value": 0}],
    )

    assert "source_tables" not in tool_context["tool_context"]
    assert '"value": 0' in trusted_context["trusted_context"]
