from beeportal.bot_text2sql.text2sql.context_compaction import (
    build_agent_state_revision,
    hash_api_prefix,
    hydrate_agent_context,
)
from beeportal.bot_text2sql.text2sql.direct_sql_agent import (
    PlanExecuteVerifyAgentNode,
    _init_agent_messages,
)


def test_agent_nodes_accept_caller_system_prompt(monkeypatch):
    direct_prompt = "DIRECT PROMPT"
    analysis_prompt = "ANALYSIS PROMPT"
    monkeypatch.setattr(PlanExecuteVerifyAgentNode, "_build_graph", lambda self: None)
    direct = PlanExecuteVerifyAgentNode(
        name="direct_test_agent",
        resource_key="gemini-3.5-flash-chat",
        tools=[],
        system_prompt=direct_prompt,
    )
    analysis = PlanExecuteVerifyAgentNode(
        name="analysis_test_agent",
        resource_key="gemini-3.5-flash-chat",
        tools=[],
        system_prompt=analysis_prompt,
    )

    assert direct.system_prompt == direct_prompt
    assert analysis.system_prompt == analysis_prompt


def test_init_messages_replaces_persisted_system_prompt():
    restored = _init_agent_messages(
        [
            {"role": "system", "content": "OLD PROMPT"},
            {"role": "user", "content": "follow-up"},
        ],
        "CALLER PROMPT",
    )

    assert restored["initialized_messages"] == [
        {"role": "system", "content": "CALLER PROMPT"},
        {"role": "user", "content": "follow-up"},
    ]


def test_shared_agent_messages_are_prompt_neutral():
    api_messages = [{"role": "user", "content": "Chạy câu SQL"}]
    messages = [
        *api_messages,
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": '{"status":"success"}'},
    ]
    revision = build_agent_state_revision(
        messages,
        api_messages,
        "session-1",
        "message-1",
        "",
        0,
        hash_api_prefix([], 0),
    )

    restored = hydrate_agent_context(
        api_messages,
        [{**revision, "status": "valid"}],
        "session-1",
    )

    assert restored["messages"] == messages
    assert all(message.get("role") != "system" for message in restored["messages"])
