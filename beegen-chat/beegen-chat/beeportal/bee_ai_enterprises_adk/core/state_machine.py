# -*- coding: utf-8 -*-
import logging
from typing import Tuple, Optional
import uuid
import asyncio

from google.adk.agents.run_config import RunConfig
from .session_utils import recover_stale_request, commit_canonical_events, seed_working_session_if_needed
from ..agents.reviewer_agent import run_reviewer

from .exceptions import MissingFinalDraftError

logger = logging.getLogger(__name__)

async def run_state_machine(
    runner,
    app_name: str,
    req_state,
    session_service,
    request,
    enable_reviewer: bool,
    main_agent_name: str,
    bot_id: str,
    max_iterations: int = 3,
    event_queue: asyncio.Queue | None = None,
) -> Tuple[Optional[str], bool]:
    """Execute the ADK state machine iterations."""
    ans = None
    iteration = req_state.iteration
    user_query = request.user_query
    username = request.user_id
    session_id = request.conversation_id
    request_id = request.request_id

    name_str = f"{app_name}|{bot_id}|{username}|{session_id}|{request_id}|working"
    working_session_id = str(uuid.uuid5(uuid.NAMESPACE_URL, name_str))

    current_message = user_query

    await seed_working_session_if_needed(
        session_service=session_service,
        app_name=app_name,
        bot_id=bot_id,
        username=username,
        session_id=session_id,
        working_session_id=working_session_id,
        request_id=request_id
    )

    try:
        # Khôi phục ngữ cảnh Revision Prompt nếu crash giữa chừng
        if iteration > 0 and req_state.phase in ('main_running', 'reviewing') and req_state.reviewer_feedback:
            is_recov_prev, draft_prev, _, _, _ = await recover_stale_request(session_service, app_name, working_session_id, username, f"{request_id}:main:{iteration-1}")
            current_message = (
                f"[INTERNAL REVISION INSTRUCTION]\n"
                f"Lệnh ban đầu: {user_query}\n\n"
                f"Draft trước đó của bạn bị từ chối:\n{draft_prev}\n\n"
                f"Reviewer phát hiện các vấn đề sau:\n"
                f"{req_state.reviewer_feedback}\n\n"
                f"Vui lòng tìm kiếm lại và đưa ra câu trả lời mới."
            )

        while iteration < max_iterations:
            req_state.raise_if_heartbeat_failed()
            invocation_id = f"{request_id}:main:{iteration}"

            # 1. State: main_running
            if req_state.phase in ('main_running', 'reviewing'):
                is_recovered, draft, reasoning, draft_event_id, recov_user_evt_id = await recover_stale_request(session_service, app_name, working_session_id, username, invocation_id)
                if is_recovered:
                    logger.info("[BeeAiEnterprisesADK] Đã khôi phục Draft thành công từ DB.")
                    kwargs = {"phase": "draft_ready", "iteration": iteration, "draft_event_id": draft_event_id}
                    if recov_user_evt_id and not req_state.user_event_id:
                        kwargs["user_event_id"] = recov_user_evt_id
                    await req_state.update_state(**kwargs)
                else:
                    await req_state.update_state(phase="main_running", iteration=iteration)
                    rc = RunConfig(custom_metadata={"request_id": request_id, "internal": iteration > 0})

                    logger.info("[BeeAiEnterprisesADK] Gọi Main Agent.")

                    draft = ""
                    final_event = None

                    from google.genai import types
                    async for event in runner.run_async(
                        user_id=username,
                        session_id=working_session_id,
                        new_message=types.Content(role="user", parts=[types.Part.from_text(text=current_message)]),
                        run_config=rc,
                        invocation_id=invocation_id,
                    ):
                        if event_queue is not None:
                            if event.content and getattr(event.content, "role", "") != "model":
                                await event_queue.put(event)

                        if hasattr(event, "author") and event.author == main_agent_name:
                            if hasattr(event, "invocation_id") and event.invocation_id and event.invocation_id != invocation_id:
                                continue
                            if getattr(event, "partial", False):
                                continue
                            if getattr(event, "error", None) is not None:
                                continue
                            if not event.content or not getattr(event.content, "parts", None):
                                continue

                            has_fc = any(hasattr(p, "function_call") and getattr(p, "function_call", None) for p in event.content.parts)
                            has_fr = any(hasattr(p, "function_response") and getattr(p, "function_response", None) for p in event.content.parts)
                            if has_fc or has_fr:
                                continue

                            text_parts = [p.text for p in event.content.parts if hasattr(p, "text") and getattr(p, "text", None)]
                            if text_parts:
                                draft = "".join(text_parts)
                                final_event = event

                    _, check_draft, reasoning, draft_event_id, user_event_id = await recover_stale_request(
                        session_service, app_name, working_session_id, username, invocation_id
                    )

                    if user_event_id and iteration == 0:
                        await req_state.update_state(user_event_id=user_event_id)

                    if not final_event or not draft:
                        await req_state.mark_failed("Missing final draft event from main agent stream.", status="retryable_failed")
                        raise MissingFinalDraftError("Main agent did not yield a valid final draft event.")

                    await req_state.update_state(phase="draft_ready", draft_event_id=draft_event_id)
            else:
                draft_event_id = req_state.draft_event_id
                # Load lại reasoning cho phase reviewing đang resume
                _, draft, reasoning, _, recov_user_evt_id = await recover_stale_request(session_service, app_name, working_session_id, username, invocation_id)
                if recov_user_evt_id and not req_state.user_event_id:
                    await req_state.update_state(user_event_id=recov_user_evt_id)

            if not enable_reviewer:
                await req_state.update_state(phase="accepted", reviewer_verdict="PASS")
                break

            # 2. State: reviewing
            req_state.raise_if_heartbeat_failed()
            if req_state.phase == "draft_ready":
                await req_state.update_state(phase="reviewing")

                try:
                    verdict = await run_reviewer(
                        user_query=user_query,
                        agent_answer=draft or "",
                        reasoning_draft=reasoning or "",
                        iteration=iteration,
                        max_iteration=max_iterations,
                        session_service=session_service,
                    )
                    # ASK_BACK: Lưu câu hỏi ngược vào feedback để bước completed có thể xử lý
                    if verdict.status == "ASK_BACK":
                        await req_state.update_state(
                            phase="reviewing_done",
                            reviewer_verdict=verdict.status,
                            reviewer_feedback=verdict.ask_back_question
                        )
                    else:
                        await req_state.update_state(
                            phase="reviewing_done",
                            reviewer_verdict=verdict.status,
                            reviewer_feedback=verdict.recommendations
                        )
                except Exception as e:
                    logger.error("[BeeAiEnterprisesADK] Lỗi lưu Reviewer verdict %s: %s", working_session_id, e)
                    await req_state.mark_failed(str(e), status="retryable_failed")
                    raise

            if req_state.phase == "reviewing_done":
                if req_state.reviewer_verdict == "PASS" or req_state.reviewer_verdict == "ASK_BACK":
                    await req_state.update_state(phase="accepted")
                    break
                else:
                    if iteration >= max_iterations - 1:
                        # Không được REVISE ở vòng cuối
                        await req_state.mark_failed("terminal_failed:max_iterations - Max iterations reached without reviewer passing.", status="terminal_failed")
                        break
                    # REVISE
                    iteration += 1
                    await req_state.update_state(phase="main_running", iteration=iteration)

        # 3. State: completed
        req_state.raise_if_heartbeat_failed()

        final_answer = None
        is_ask_back = False

        if req_state.status == "terminal_failed" or req_state.phase != "accepted":
            final_answer = "Xin lỗi, hệ thống không thể tìm được câu trả lời phù hợp sau nhiều lần thử."
            if req_state.status != "terminal_failed":
                await req_state.mark_failed("terminal_failed:max_iterations - Max iterations reached or failed.", status="terminal_failed")
        else:
            is_recov, ans, _, final_evt_id, recov_user_evt_id = await recover_stale_request(session_service, app_name, working_session_id, username, f"{request_id}:main:{iteration}")
            if recov_user_evt_id and not req_state.user_event_id:
                await req_state.update_state(user_event_id=recov_user_evt_id)

            if req_state.reviewer_verdict == "ASK_BACK" and req_state.reviewer_feedback:
                final_answer = req_state.reviewer_feedback
                is_ask_back = True
            elif not is_recov:
                await req_state.mark_failed("terminal_failed:missing_draft - Accepted but draft not recovered.", status="terminal_failed")
                final_answer = "Xin lỗi, hệ thống không thể tìm lại dữ liệu sau khi kiểm duyệt."
                return final_answer, is_ask_back
            else:
                final_answer = ans

            await commit_canonical_events(
                bot_id=bot_id,
                app_name=app_name,
                session_service=session_service,
                req_state=req_state,
                username=username,
                session_id=session_id,
                request_id=request_id,
                user_query=user_query,
                final_answer=final_answer,
                is_ask_back=is_ask_back
            )

        return final_answer, is_ask_back

    finally:
        if req_state.status in ('completed', 'terminal_failed'):
            try:
                await session_service.delete_session(app_name=app_name, user_id=username, session_id=working_session_id)
            except Exception as e:
                logger.error("[BeeAiEnterprisesADK] Lỗi xóa working session %s: %s", working_session_id, e)

    return None, False
