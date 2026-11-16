import json
from unittest.mock import patch

from beeportal.bot_text2sql.text2sql import context_compaction
from beeportal.bot_text2sql.text2sql.context_compaction import (
    build_agent_state_revision,
    estimate_provider_tokens,
    hash_api_prefix,
    hydrate_agent_context,
    plan_compaction,
    sanitize_tool_history,
    validate_summary,
)


API_MESSAGES = [
    {"role": "user", "content": "run SQL"},
    {"role": "assistant", "content": "<details>progress</details>\n\n10 rows"},
    {"role": "user", "content": "explain"},
]

INTERNAL_MESSAGES = [
    {"role": "user", "content": "run SQL"},
    {"role": "assistant", "content": "progress", "tool_calls": [{"id": "c1"}]},
    {"role": "tool", "tool_call_id": "c1", "content": '{"success": true}'},
    {"role": "assistant", "content": "10 rows"},
]


def _revision(
    api_messages,
    messages,
    *,
    synced_count,
    summary_count=0,
    summary="",
    revision_id=7,
):
    return {
        "revision_id": revision_id,
        "session_id": "session-1",
        "status": "valid",
        "summary": summary,
        "recent_agent_messages": messages,
        "summary_covered_api_message_count": summary_count,
        "summary_covered_api_prefix_hash": hash_api_prefix(api_messages, summary_count),
        "synced_api_message_count": synced_count,
        "synced_api_prefix_hash": hash_api_prefix(api_messages, synced_count),
    }


def test_hydrate_reuses_matching_revision_and_drops_ui_replay():
    revision = _revision(API_MESSAGES, INTERNAL_MESSAGES, synced_count=1)

    result = hydrate_agent_context(API_MESSAGES, [revision], "session-1")

    assert result["messages"] == INTERNAL_MESSAGES + API_MESSAGES[2:]
    assert result["historical_summary"] == ""


def test_hydrate_fallback_uses_summary_and_api_tail_without_raw_tool_trace():
    revision = _revision(
        API_MESSAGES,
        INTERNAL_MESSAGES,
        synced_count=99,
        summary_count=2,
        summary="summary",
    )

    result = hydrate_agent_context(API_MESSAGES, [revision], "session-1")

    assert result["historical_summary"] == "summary"
    assert result["messages"] == API_MESSAGES[2:]
    assert all(message.get("role") != "tool" for message in result["messages"])


def test_hydrate_accepts_json_encoded_recent_agent_messages():
    revision = _revision(API_MESSAGES, json.dumps(INTERNAL_MESSAGES), synced_count=1)

    result = hydrate_agent_context(API_MESSAGES, [revision], "session-1")

    assert result["messages"] == INTERNAL_MESSAGES + API_MESSAGES[2:]


def test_hydrate_uses_previous_matching_revision_then_full_api_when_none_match():
    matching = _revision(API_MESSAGES, INTERNAL_MESSAGES, synced_count=1, revision_id=6)
    broken_latest = {
        **_revision(API_MESSAGES, INTERNAL_MESSAGES, synced_count=1, revision_id=7),
        "synced_api_prefix_hash": "0" * 64,
        "summary_covered_api_prefix_hash": "1" * 64,
    }

    result = hydrate_agent_context(
        API_MESSAGES,
        [broken_latest, matching],
        "session-1",
    )

    assert result["messages"] == INTERNAL_MESSAGES + API_MESSAGES[2:]
    assert hydrate_agent_context(API_MESSAGES, [broken_latest], "session-1")[
        "messages"
    ] == API_MESSAGES


def test_revision_payload_excludes_system_messages_and_keeps_tool_results():
    payload = build_agent_state_revision(
        [
            {"role": "system", "content": "current prompt"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "tool_call_id": "c1", "content": '{"result": 1}'},
        ],
        [{"role": "user", "content": "run"}],
        "session-1",
        "message-1",
        "",
        0,
        hash_api_prefix([], 0),
    )

    assert payload["recent_agent_messages"] == [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": '{"result": 1}'},
    ]
    assert "status" not in payload
    assert payload["synced_api_message_count"] == 1


def test_sanitize_removes_orphans_but_keeps_complete_tool_pair():
    messages = [
        {"role": "tool", "tool_call_id": "orphan", "content": "x"},
        {"role": "assistant", "content": "p", "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
        {"role": "assistant", "content": "broken", "tool_calls": [{"id": "missing"}]},
        {"role": "assistant", "content": "final"},
    ]

    result = sanitize_tool_history(messages)

    assert result["messages"] == messages[1:3] + messages[4:]


def test_compaction_keeps_unanchored_current_plan_turn_and_tool_pairs():
    api_messages, agent_messages = [], []
    for index in range(4):
        api_messages.extend([
            {"role": "user", "content": f"u{index}"},
            {"role": "assistant", "content": f"ui-a{index}"},
        ])
        agent_messages.extend([
            {"role": "user", "content": f"u{index}"},
            {"role": "assistant", "content": "progress", "tool_calls": [{"id": f"c{index}"}]},
            {"role": "tool", "tool_call_id": f"c{index}", "content": "result"},
            {"role": "assistant", "content": f"a{index}"},
        ])
    agent_messages.extend([
        {"role": "user", "content": "current"},
        {"role": "assistant", "content": "current answer"},
    ])

    result = plan_compaction(
        api_messages,
        agent_messages,
        base_covered_api_message_count=0,
        estimated_tokens=100_000,
        fixed_tokens=0,
        threshold=80_000,
    )

    assert result["should_compact"] == 1
    assert result["covered_api_message_count"] == 4
    assert result["recent_messages"][-2:] == agent_messages[-2:]
    assert result["compacted_messages"][-1]["role"] == "assistant"
    assert not result["compacted_messages"][-1].get("tool_calls")


def test_compaction_uses_already_sanitized_messages():
    messages = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"},
        {"role": "assistant", "content": "a3"},
    ]

    with patch.object(
        context_compaction,
        "sanitize_tool_history",
        side_effect=AssertionError("plan must not sanitize again"),
    ):
        result = plan_compaction(messages, messages, 0, 100_000, 0, 80_000)

    assert result["should_compact"] == 1


def test_summary_requires_all_sections_and_non_length_finish():
    valid = """## Ngữ cảnh đang hoạt động
X
## Công việc dữ liệu đã hoàn tất
Không có
## Công việc chưa hoàn tất
Không có
## Correction và kết quả đã bị thay thế
Không có"""

    assert validate_summary(valid, "stop")["valid"] == 1
    assert validate_summary(valid, "length")["valid"] == 0
    assert validate_summary("## Ngữ cảnh đang hoạt động\nX", "stop")["valid"] == 0
def test_summary_prompt_requires_bounded_complete_output():
    prompt = context_compaction.CONTEXT_COMPACTION_SYSTEM_PROMPT

    assert "1.500–2.000 token" in prompt
    assert "không vượt 2.500 token" in prompt
    assert "theo đúng thứ tự" in prompt
    assert "Mỗi heading phải có nội dung" in prompt


def test_estimator_counts_system_summary_messages_and_tools():
    base = estimate_provider_tokens("s", "t", "h", [], [])
    expanded = estimate_provider_tokens(
        "s" * 100,
        "t" * 100,
        "h" * 100,
        [{"role": "tool", "content": "r" * 100}],
        [{"type": "function", "function": {"name": "x"}}],
    )

    assert expanded > base


def test_estimator_uses_two_characters_per_token():
    payload = {
        "system_prompt": "s",
        "trusted_context": "t",
        "historical_summary": "h",
        "messages": [],
        "tools": [],
    }

    estimated = estimate_provider_tokens("s", "t", "h", [], [])
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    assert estimated == (len(serialized) + 1) // 2
