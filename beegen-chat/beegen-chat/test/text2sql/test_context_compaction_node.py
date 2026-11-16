from pathlib import Path

from beeportal.bot_text2sql.text2sql.context_compaction_node import (
    _prepare_node,
    finalize_compaction,
    prepare_compaction,
)


PREPARED = {
    "messages": [{"role": "user", "content": "old"}],
    "historical_summary": "S1",
    "summary_covered_api_message_count": 2,
    "summary_covered_api_prefix_hash": "a" * 64,
    "plan": {
        "recent_messages": [{"role": "user", "content": "recent"}],
        "covered_api_message_count": 4,
    },
    "covered_api_prefix_hash": "b" * 64,
}


def test_finalize_uses_valid_summary_without_database_insert():
    result = finalize_compaction(PREPARED, {"valid": 1, "summary": "S2"})

    assert result["messages"] == PREPARED["plan"]["recent_messages"]
    assert result["historical_summary"] == "S2"
    assert result["summary_covered_api_message_count"] == 4
    assert result["summary_covered_api_prefix_hash"] == "b" * 64


def test_finalize_keeps_unpruned_messages_when_summary_is_invalid():
    result = finalize_compaction(PREPARED, {"valid": 0, "summary": ""})

    assert result["messages"] == PREPARED["messages"]
    assert result["historical_summary"] == "S1"
    assert result["summary_covered_api_message_count"] == 2
    assert result["summary_covered_api_prefix_hash"] == "a" * 64


def test_context_node_reads_three_revisions_and_persistence_node_inserts_after_agent():
    source = Path(
        "beeportal/bot_text2sql/text2sql/context_compaction_node.py"
    ).read_text(encoding="utf-8")

    assert 'name="data_query_agent_state_revisions"' in source
    assert '"limit": 3,' in source
    assert 'name="data_insert_agent_state_revision"' in source
    assert "operation=SQLOperation.EXECUTE" in source
    assert '"returning": False' in source
    assert "redis_state" not in source
    assert "INSERT_CHECKPOINT_SQL" not in source


def test_context_node_streams_progress_only_before_summary_llm():
    source = Path(
        "beeportal/bot_text2sql/text2sql/context_compaction_node.py"
    ).read_text(encoding="utf-8")

    assert 'name="code_notify_context_compaction"' in source
    assert "stream=True" in source
    assert "Đang rút gọn ngữ cảnh hội thoại" in source
    assert (
        "branch_should_compact_context >> code_notify_context_compaction "
        ">> llm_summarize_context"
    ) in source
    assert '"reasoning_effort": "minimal"' in source


def test_prepare_omits_summary_messages_below_threshold():
    prepared = prepare_compaction(
        [{"role": "user", "content": "u1"}, {"role": "assistant", "content": "a1"}],
        [],
        "session-1",
        "system",
        "",
        [],
    )

    assert prepared["summary_messages"] == []
    assert prepared["should_compact"] == 0


def test_prepare_omits_new_summary_anchor_below_threshold():
    prepared = prepare_compaction(
        [{"role": "user", "content": "u1"}, {"role": "assistant", "content": "a1"}],
        [],
        "session-1",
        "system",
        "",
        [],
    )

    assert "covered_api_prefix_hash" not in prepared


def test_prepare_node_returns_estimated_tokens_for_trace_visibility():
    result = _prepare_node(
        [{"role": "user", "content": "u1"}],
        [],
        "session-1",
        "system",
        "",
        [],
    )

    assert isinstance(result["estimated_tokens"], int)
    assert result["estimated_tokens"] == result["prepared"]["estimated_tokens"]
