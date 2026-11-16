# -*- coding: utf-8 -*-
import logging
from typing import Tuple, Optional
import uuid

from google.adk.events import Event
from google.genai import types

logger = logging.getLogger(__name__)

async def recover_stale_request(
    session_service,
    app_name: str,
    session_id: str,
    username: str,
    invocation_id: str
) -> Tuple[bool, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Recover events from an interrupted run.
    
    Returns:
        (is_recovered, draft_text, reasoning_text, draft_event_id, user_event_id)
    """
    working_session = await session_service.get_session(app_name=app_name, user_id=username, session_id=session_id)
    if not working_session:
        return False, None, None, None, None

    draft_text = ""
    reasoning_parts = []
    draft_event_id = None
    user_event_id = None
    
    for evt in working_session.events:
        if evt.invocation_id == invocation_id and evt.author == "user":
            user_event_id = evt.id
        elif evt.invocation_id == invocation_id and evt.author != "user":
            is_final = False
            if hasattr(evt, "is_final_response"):
                is_final = evt.is_final_response()
            elif hasattr(evt, "partial"):
                is_final = not evt.partial

            if evt.content and evt.content.parts:
                for part in evt.content.parts:
                    if getattr(part, "text", None):
                        if is_final:
                            draft_text = part.text
                            draft_event_id = evt.id
                        else:
                            reasoning_parts.append(part.text)
                    elif getattr(part, "function_call", None):
                        fc = part.function_call
                        reasoning_parts.append(f"Function Call: {fc.name}({fc.args})")
                    elif getattr(part, "function_response", None):
                        fr = part.function_response
                        fr_name = getattr(fr, "name", "unknown")
                        fr_response = getattr(fr, "response", {})
                        reasoning_parts.append(f"Function Response [{fr_name}]: {fr_response}")

    reasoning_text = "\n".join(reasoning_parts) if reasoning_parts else None
    draft_text = draft_text if draft_text else None

    if draft_text and draft_event_id:
        return True, draft_text, reasoning_text, draft_event_id, user_event_id
    return False, None, reasoning_text, None, user_event_id


async def seed_working_session_if_needed(
    session_service,
    app_name: str,
    bot_id: str,
    username: str,
    session_id: str,
    working_session_id: str,
    request_id: str
) -> None:
    """Seed working session with canonical events."""
    working_session = await session_service.get_session(app_name=app_name, user_id=username, session_id=working_session_id)
    if not working_session:
        working_session = await session_service.create_session(app_name=app_name, user_id=username, session_id=working_session_id)

    canonical_session = await session_service.get_session(app_name=app_name, user_id=username, session_id=session_id)
    if not canonical_session or not canonical_session.events:
        return

    existing_events_by_id = {e.id: e for e in working_session.events}

    for event in canonical_session.events:
        try:
            if getattr(event, "partial", False):
                continue
                
            is_user_message = (
                getattr(event, "author", None) == "user"
                and getattr(event, "content", None)
                and getattr(event.content, "role", None) == "user"
            )

            is_final_output = False
            is_ask_back = False
            if hasattr(event, "custom_metadata") and event.custom_metadata:
                metadata = event.custom_metadata
                evt_type = getattr(metadata, "get", lambda k: None)("type")
                if evt_type == "final_output":
                    is_final_output = True
                    is_ask_back = getattr(metadata, "get", lambda k: None)("is_ask_back")
            
            if is_final_output and not is_ask_back:
                continue

            working_identity = f"{app_name}|{bot_id}|{username}|{session_id}|{request_id}|clone|{event.id}"
            EVENT_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")
            clone_id = uuid.uuid5(EVENT_NAMESPACE, working_identity).hex
            
            if clone_id not in existing_events_by_id:
                clone_event = event.model_copy(deep=True)
                clone_event.id = clone_id
                
                if clone_event.custom_metadata is None:
                    clone_event.custom_metadata = {}
                clone_event.custom_metadata["canonical_source_event_id"] = event.id
                
                await session_service.append_event(working_session, clone_event)
            else:
                existing = existing_events_by_id[clone_id]
                existing_text = ""
                event_text = ""
                
                def _normalize_parts(content):
                    if not content or not getattr(content, "parts", None):
                        return ""
                    out = []
                    for p in content.parts:
                        if getattr(p, "text", None):
                            out.append(p.text)
                        elif getattr(p, "function_call", None):
                            out.append(f"FC:{p.function_call.name}({p.function_call.args})")
                        elif getattr(p, "function_response", None):
                            out.append(f"FR:{getattr(p.function_response, 'name', '')}:{getattr(p.function_response, 'response', {})}")
                    return "".join(out)
                
                existing_text = _normalize_parts(getattr(existing, "content", None))
                event_text = _normalize_parts(getattr(event, "content", None))
                
                canonical_source_id = getattr(existing.custom_metadata, "get", lambda k: None)("canonical_source_event_id") if existing.custom_metadata else None
                
                existing_role = getattr(existing.content, "role", None) if getattr(existing, "content", None) else None
                event_role = getattr(event.content, "role", None) if getattr(event, "content", None) else None
                
                if existing.author != event.author or                    existing_role != event_role or                    existing_text.strip() != event_text.strip() or                    canonical_source_id != event.id:
                    raise RuntimeError(f"Invariant violation: Seeded event mismatch metadata. Expected canonical source {event.id}, got {canonical_source_id}")
        except RuntimeError:
            raise
        except Exception as e:
            logger.error("[BeeAiEnterprisesADK] Lỗi khi seed event %s: %s", getattr(event, "id", "unknown"), e)


async def commit_canonical_events(
    bot_id: str,
    app_name: str,
    session_service,
    req_state,
    username: str,
    session_id: str,
    request_id: str,
    user_query: str,
    final_answer: str,
    is_ask_back: bool = False
) -> None:
    """Commit events from working session to canonical session."""
    import time
    canonical_session = await session_service.get_session(app_name=app_name, user_id=username, session_id=session_id)
    if not canonical_session:
        canonical_session = await session_service.create_session(app_name=app_name, user_id=username, session_id=session_id)

    existing_event_ids = {e.id for e in canonical_session.events}

    EVENT_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")
    identity_user = f"{app_name}|{bot_id}|{username}|{session_id}|{request_id}|user"
    user_event_id = uuid.uuid5(EVENT_NAMESPACE, identity_user).hex

    identity_final = f"{app_name}|{bot_id}|{username}|{session_id}|{request_id}|final"
    final_event_id = uuid.uuid5(EVENT_NAMESPACE, identity_final).hex

    if user_event_id not in existing_event_ids:
        user_evt = Event(
            id=user_event_id,
            author="user",
            invocation_id=f"{request_id}:user",
            content=types.Content(role="user", parts=[types.Part.from_text(text=user_query)]),
            timestamp=time.time(),
            partial=False,
            custom_metadata={"request_id": request_id, "type": "user_input"}
        )
        await session_service.append_event(canonical_session, user_evt)
        
    if final_event_id not in existing_event_ids:
        final_evt = Event(
            id=final_event_id,
            author="ENTERPRISES_MAIN_AGENT",
            invocation_id=f"{request_id}:final",
            content=types.Content(role="model", parts=[types.Part.from_text(text=final_answer)]),
            timestamp=time.time() + 1e-3,
            partial=False,
            custom_metadata={"request_id": request_id, "type": "final_output", "is_ask_back": is_ask_back}
        )
        await session_service.append_event(canonical_session, final_evt)

    await req_state.mark_completed(response=final_answer, final_event_id=final_event_id, user_event_id=user_event_id)

