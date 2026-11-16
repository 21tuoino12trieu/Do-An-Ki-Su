import json
from typing import Any, Dict, List


LIST_AGENT_STATE_REVISIONS_SQL = """
SELECT
    revision_id, session_id, client_message_id, status, summary,
    recent_agent_messages, summary_covered_api_message_count,
    summary_covered_api_prefix_hash, synced_api_message_count,
    synced_api_prefix_hash, created_at
FROM meta_poc.text2sql_agent_state_revision
WHERE session_id = %s
  AND status = 'valid'
ORDER BY revision_id DESC
""".strip()


INSERT_AGENT_STATE_REVISION_SQL = """
INSERT INTO meta_poc.text2sql_agent_state_revision (
    session_id, client_message_id, summary, recent_agent_messages,
    summary_covered_api_message_count, summary_covered_api_prefix_hash,
    synced_api_message_count, synced_api_prefix_hash
)
VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s)
ON CONFLICT (session_id, client_message_id) DO NOTHING
""".strip()


def build_list_agent_state_revision_params(session_id: str) -> Dict[str, List[str]]:
    return {"params": [str(session_id or "")]}


def build_insert_agent_state_revision_params(
    session_id: str,
    client_message_id: str,
    summary: str,
    recent_agent_messages: List[Dict[str, Any]],
    summary_covered_api_message_count: int,
    summary_covered_api_prefix_hash: str,
    synced_api_message_count: int,
    synced_api_prefix_hash: str,
) -> Dict[str, List[Any]]:
    return {
        "params": [
            str(session_id or ""),
            str(client_message_id or ""),
            str(summary or ""),
            json.dumps(recent_agent_messages or [], ensure_ascii=False, default=str),
            int(summary_covered_api_message_count or 0),
            str(summary_covered_api_prefix_hash or ""),
            int(synced_api_message_count or 0),
            str(synced_api_prefix_hash or ""),
        ]
    }
