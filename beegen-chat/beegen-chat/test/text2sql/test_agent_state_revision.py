from beeportal.bot_text2sql.text2sql.agent_state_revision import (
    INSERT_AGENT_STATE_REVISION_SQL,
    LIST_AGENT_STATE_REVISIONS_SQL,
    build_insert_agent_state_revision_params,
    build_list_agent_state_revision_params,
)


def test_revision_sql_is_fixed_and_selects_valid_session_rows():
    hostile_session = "s1'; DROP TABLE meta_poc.text2sql_agent_state_revision; --"

    assert "FROM meta_poc.text2sql_agent_state_revision" in LIST_AGENT_STATE_REVISIONS_SQL
    assert "WHERE session_id = %s" in LIST_AGENT_STATE_REVISIONS_SQL
    assert "status = 'valid'" in LIST_AGENT_STATE_REVISIONS_SQL
    assert "ORDER BY revision_id DESC" in LIST_AGENT_STATE_REVISIONS_SQL
    assert "INSERT INTO meta_poc.text2sql_agent_state_revision" in (
        INSERT_AGENT_STATE_REVISION_SQL
    )
    assert "ON CONFLICT (session_id, client_message_id) DO NOTHING" in (
        INSERT_AGENT_STATE_REVISION_SQL
    )
    assert hostile_session not in LIST_AGENT_STATE_REVISIONS_SQL
    assert build_list_agent_state_revision_params(hostile_session) == {
        "params": [hostile_session]
    }


def test_revision_insert_params_keep_json_in_params_not_sql():
    messages = [{"role": "user", "content": "x"}]

    result = build_insert_agent_state_revision_params(
        "session-1",
        "message-1",
        "summary",
        messages,
        2,
        "a" * 64,
        4,
        "b" * 64,
    )

    assert set(result) == {"params"}
    assert result["params"][0:3] == ["session-1", "message-1", "summary"]
    assert result["params"][4:] == [2, "a" * 64, 4, "b" * 64]
    assert '"role": "user"' in result["params"][3]
    assert "RETURNING" not in INSERT_AGENT_STATE_REVISION_SQL
