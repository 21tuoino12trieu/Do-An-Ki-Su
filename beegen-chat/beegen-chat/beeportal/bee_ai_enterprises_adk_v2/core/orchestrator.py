import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from pydantic import ValidationError

from google.adk import Context, Event
from google.adk.workflow._errors import DynamicNodeFailError
from google.adk.workflow import Workflow, BaseNode
from google.adk.agents import BaseAgent
from google.genai import types

from ..agents.main_agent import build_main_agent
from ..agents.reviewer_agent import build_reviewer_agent
from .schemas import ReviewInput, ReviewVerdict, MainInput, ChatTurn
from .guardrails import input_content_filter_guardrail
from ..utils.memory_manager import get_memory_manager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cross-node synchronisation (Cancellation Flag Pattern)
# ---------------------------------------------------------------------------

@dataclass
class _SharedSync:
    """Shared state between InputGuardrailNode and ActorCriticOrchestrator.

    Both nodes run as parallel static nodes in the same Workflow.
    This object lives in an in-process registry keyed by invocation_id,
    which is safe because asyncio is single-threaded per event-loop.
    """

    guardrail_done: asyncio.Event = field(default_factory=asyncio.Event)
    guardrail_failed: asyncio.Event = field(default_factory=asyncio.Event)
    refusal_message: str = ""


_SYNC_REGISTRY: dict[str, _SharedSync] = {}


def _get_or_create_sync(invocation_id: str) -> _SharedSync:
    if invocation_id not in _SYNC_REGISTRY:
        _SYNC_REGISTRY[invocation_id] = _SharedSync()
    return _SYNC_REGISTRY[invocation_id]


def _cleanup_sync(invocation_id: str) -> None:
    _SYNC_REGISTRY.pop(invocation_id, None)


def _parse_qna_content(content: str):
    doc_name = ""
    pages = ""
    section = ""
    for line in content.splitlines():
        if line.startswith("Tên tài liệu:"):
            doc_name = line[len("Tên tài liệu:"):].strip()
        elif line.startswith("Trang:"):
            pages = line[len("Trang:"):].strip()
        elif line.startswith("Mục:"):
            section = line[len("Mục:"):].strip()
    return doc_name, pages, section

def _get_first_page_num(pages: str) -> int:
    match = re.search(r'\d+', pages)
    return int(match.group()) if match else 999999

def _filter_docs_for_ui(docs: list[dict]) -> list[dict]:
    """Lọc và reformat docs trước khi gửi về UI.
    - BM docs (id bắt đầu bằng 'bm') hoặc form docs: bỏ.
    - QnA docs: Gom nhóm theo Tên tài liệu và Trang, nối các Mục bằng '\\n', bỏ Tên tài liệu khỏi content, sort theo Tên tài liệu và Trang.
    """
    filtered_non_qna = []
    seen_ids = set()
    qna_groups = {}
    
    for doc in docs:
        doc_id_raw = str(doc.get("id", ""))
        doc_doc = str(doc.get("doc", ""))
        unique_id = f"{doc_id_raw}_{doc_doc}"
        source_type = doc.get("source_type", "")
        
        # Skip BM docs and form docs
        if doc_id_raw.lower().startswith("bm") or source_type == "form":
            continue
            
        if source_type != "qna":
            # Dedup for non-QnA
            if unique_id in seen_ids:
                continue
            seen_ids.add(unique_id)
            filtered_non_qna.append(dict(doc))
        else:
            # Gom nhóm QnA
            doc_name, pages, section = _parse_qna_content(doc.get("content", ""))
            group_key = (doc_name, pages)
            if group_key not in qna_groups:
                qna_groups[group_key] = {
                    "doc": dict(doc),
                    "sections": []
                }
            if section and section not in qna_groups[group_key]["sections"]:
                qna_groups[group_key]["sections"].append(section)

    # Xử lý các nhóm QnA
    qna_list = []
    for (doc_name, pages), group_data in qna_groups.items():
        base_doc = group_data["doc"]
        content_lines = []
        if pages:
            content_lines.append(f"Trang: {pages}")
        if group_data["sections"]:
            sections_str = "\n".join(group_data["sections"])
            content_lines.append(f"Mục: {sections_str}")
            
        base_doc["content"] = "\n".join(content_lines)
        
        first_page = _get_first_page_num(pages)
        qna_list.append({
            "doc_name": doc_name,
            "first_page": first_page,
            "doc": base_doc
        })
        
    # Sort QnA theo Tên tài liệu, sau đó theo số Trang
    qna_list.sort(key=lambda x: (x["doc_name"], x["first_page"]))
    sorted_qna_docs = [x["doc"] for x in qna_list]
    
    return filtered_non_qna + sorted_qna_docs

def _extract_query(node_input: Any) -> str:
    if isinstance(node_input, types.Content):
        return "".join(
            part.text or ""
            for part in node_input.parts or []
            if part.text
        ).strip()
    return str(node_input).strip()

def _extract_history(ctx: Context) -> list[ChatTurn]:
    """Trích xuất lịch sử trò chuyện sạch, chỉ lấy user query gốc và final answer."""
    history = []
    for event in ctx.session.events:
        if getattr(event, "invocation_id", None) == ctx.invocation_id:
            continue
            
        # Kiểm tra event đã bị tóm tắt (compaction)
        actions = getattr(event, "actions", None)
        compaction = getattr(actions, "compaction", None) if actions else None
        compacted_content = getattr(compaction, "compacted_content", None) if compaction else None
        
        if compacted_content:
            text = "".join(part.text for part in compacted_content.parts if hasattr(part, "text") and part.text)
            if text:
                history.append(ChatTurn(role="model", text=f"[Tóm tắt hội thoại cũ]: {text}"))
            continue
            
        content = getattr(event, "content", None)
        if not content: continue
        
        text = "".join(part.text for part in content.parts if getattr(part, "text", None))
        if not text: continue
        
        metadata = event.custom_metadata or {}
        visibility = metadata.get("visibility")
        role = content.role
        
        if (
            role == "user" 
            and event.author == "user"
            and getattr(event, "invocation_id", None)
            and not getattr(event.node_info, "path", None)
        ):
            history.append(ChatTurn(role="user", text=text))
        elif role == "model" and visibility == "final":
            history.append(ChatTurn(role="model", text=text))
            
    return history[-15:]

class ActorCriticOrchestrator(BaseNode):
    rerun_on_resume: bool = True
    main_agent: BaseAgent | None = None
    reviewer_agent: BaseAgent | None = None
    max_revisions: int = 1
    max_reviewer_retries: int = 1
    max_evidence_size: int = 200000  # Defensive limit cho tổng ký tự evidence
    has_review: bool = False  # False: trả thẳng answer, True: qua reviewer

    # --- Guardrail checkpoint helper -------------------------------------------

    async def _wait_and_check_guardrail(
        self, sync: _SharedSync,
    ) -> str | None:
        """Block until the parallel guardrail node signals completion.

        Returns the refusal message when the guardrail blocked the input,
        or ``None`` when the input passed.
        """
        if not sync.guardrail_done.is_set():
            logger.debug("[ActorCritic] Main agent done. Waiting for guardrail...")
            await sync.guardrail_done.wait()

        if sync.guardrail_failed.is_set():
            return sync.refusal_message or "Tin nhắn vi phạm chính sách."
        return None

    def _extract_evidence(self, ctx: Context, start_idx: int) -> tuple[list[str], list[dict], int]:
        evidence_texts = []
        retrieved_docs = []
        events = ctx.session.events
        n = len(events)
        
        for i in range(start_idx, n):
            event = events[i]
            if getattr(event, "invocation_id", None) == ctx.invocation_id:
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.function_response:
                            try:
                                resp_dict = part.function_response.response
                                if isinstance(resp_dict, dict):
                                    if "evidence_text" in resp_dict:
                                        evidence_texts.append(resp_dict["evidence_text"])
                                    if "docs" in resp_dict and isinstance(resp_dict["docs"], list):
                                        retrieved_docs.extend(resp_dict["docs"])
                            except Exception:
                                pass
        return evidence_texts, retrieved_docs, n

    async def _run_impl(self, *, ctx: Context, node_input: Any):
        sync = _get_or_create_sync(ctx.invocation_id)
        final_answer = None
        phase = None
        try:
            async for event in self._run_impl_inner(
                ctx=ctx, node_input=node_input, sync=sync,
            ):
                metadata = getattr(event, "custom_metadata", {}) or {}
                if metadata.get("visibility") == "final":
                    if event.content and event.content.parts:
                        final_answer = "".join(p.text for p in event.content.parts if p.text)
                    elif getattr(event, "output", None):
                        final_answer = str(event.output)
                
                # In ADK Event, 'state' kwarg is moved to actions.state_delta
                actions = getattr(event, "actions", None)
                if actions and getattr(actions, "state_delta", None):
                    if "phase" in actions.state_delta:
                        phase = actions.state_delta["phase"]
                yield event
        finally:
            _cleanup_sync(ctx.invocation_id)
            from ..utils.intent_detector import cleanup_intent_future
            cleanup_intent_future(ctx.invocation_id)
            if final_answer and phase in {"completed", "ask_back", "review_exhausted"}:
                original_query = _extract_query(node_input)
                user_id = getattr(ctx, "user_id", None) or "adk_web_user"
                session_id = (getattr(ctx.session, "id", "") or "") if getattr(ctx, "session", None) else "adk_web_session"
                if user_id and original_query:
                    try:
                        logger.info("[ActorCritic] Triggering background mem0 ingestion for user=%s", user_id)
                        asyncio.create_task(
                            get_memory_manager().add_memory(
                                user_query=original_query,
                                answer=final_answer,
                                user_id=user_id,
                                session_id=session_id,
                            )
                        )
                    except Exception as e:
                        logger.warning("[ActorCritic] Failed to fire add_memory task: %s", e)

    async def _run_impl_inner(
        self,
        *,
        ctx: Context,
        node_input: Any,
        sync: _SharedSync,
    ):
        original_query = _extract_query(node_input)
        if not original_query:
            msg = "Vui lòng nhập câu hỏi hợp lệ."
            yield Event(
                content=types.Content(role="model", parts=[types.Part.from_text(text=msg)]),
                output=msg,
                custom_metadata={"visibility": "final"},
                state={"phase": "invalid_request"}
            )
            return
            
        history = _extract_history(ctx)

        # Tra cứu long-term memory từ mem0 (fail-open: bỏ qua nếu lỗi)
        user_context = ""
        try:
            user_id = getattr(ctx, "user_id", None) or "adk_web_user"
            session_id = (getattr(ctx.session, "id", "") or "") if getattr(ctx, "session", None) else "adk_web_session"
            if user_id:
                user_context = await get_memory_manager().search_memory(
                    query=original_query,
                    user_id=user_id,
                    session_id=session_id,
                )
        except Exception:
            logger.exception("[ActorCritic] mem0 search_memory failed — continuing without memory")


        current_feedback = None
        current_draft = None
        global_evidence_parts = []
        global_retrieved_docs = []
        seen_docs = set()
        iteration = 0
        last_event_idx = 0
        
        while iteration <= self.max_revisions:
            yield Event(state={"phase": "main_running", "iteration": iteration})
            
            # Giới hạn kích thước ký tự tổng cộng
            evidence_str = "\n---\n".join(global_evidence_parts)
            if len(evidence_str) > self.max_evidence_size:
                logger.warning(f"Evidence exceeded size limit ({len(evidence_str)} chars). Truncating oldest items.")
                while len(evidence_str) > self.max_evidence_size and len(global_evidence_parts) > 1:
                    global_evidence_parts.pop(0)
                    evidence_str = "\n---\n".join(global_evidence_parts)
            
            if iteration == 0:
                main_payload = MainInput(
                    user_query=original_query,
                    conversation_history=history,
                    user_context=user_context,
                )
            else:
                main_payload = MainInput(
                    user_query=original_query,
                    conversation_history=history,
                    previous_draft=current_draft,
                    review_feedback=current_feedback,
                    evidence=evidence_str,
                    instruction="Hãy sửa lại draft dựa trên feedback trên và evidence hiện có.",
                    user_context=user_context,
                )

            main_run_id = f"main-{iteration}"
            is_final = True if not self.has_review else (iteration >= self.max_revisions)
            
            main_task = asyncio.create_task(
                ctx.run_node(
                    self.main_agent,
                    main_payload.model_dump_json(exclude_none=True),
                    run_id=main_run_id,
                    use_as_output=is_final
                )
            )
            guardrail_fail_task = asyncio.create_task(sync.guardrail_failed.wait())
            
            done, pending = await asyncio.wait(
                [main_task, guardrail_fail_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            if guardrail_fail_task in done:
                main_task.cancel()
                refusal = sync.refusal_message or "Tin nhắn vi phạm chính sách."
                logger.info("[ActorCritic] Guardrail blocked during main agent run. Returning refusal.")
                yield Event(
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=refusal)],
                    ),
                    custom_metadata={"visibility": "final"},
                    state={"phase": "completed", "guardrail_blocked": True},
                )
                return
                
            guardrail_fail_task.cancel()
            raw_draft = main_task.result()

            # ── GUARDRAIL CHECKPOINT ──────────────────────────────────
            # The parallel InputGuardrailNode may still be running.
            # We MUST wait for it before yielding any content to the UI.
            refusal = await self._wait_and_check_guardrail(sync)
            if refusal:
                logger.info("[ActorCritic] Guardrail blocked. Returning refusal.")
                yield Event(
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=refusal)],
                    ),
                    custom_metadata={"visibility": "final"},
                    state={"phase": "completed", "guardrail_blocked": True},
                )
                return
            # ── END CHECKPOINT ────────────────────────────────────────

            # ── NO-REVIEW FAST PATH ───────────────────────────────────
            # Khi has_review=False, main agent trả plain text (không có
            # output_schema), ta trả thẳng answer mà không qua reviewer.
            if not self.has_review:
                answer = str(raw_draft)
                # Collect docs nếu main agent đã gọi retrieval tools
                new_texts, new_docs, _ = self._extract_evidence(ctx, last_event_idx)
                for d in new_docs:
                    doc_id = str(d.get("id", ""))
                    doc_doc = str(d.get("doc", ""))
                    src_type = str(d.get("source_type", ""))
                    key = f"{src_type}::{doc_id}::{doc_doc}"
                    if key not in seen_docs:
                        seen_docs.add(key)
                        global_retrieved_docs.append(d)
                ft_docs = _filter_docs_for_ui(global_retrieved_docs) if global_retrieved_docs else []
                yield Event(
                    content=types.Content(role="model", parts=[types.Part.from_text(text=answer)]),
                    custom_metadata={"visibility": "final", "docs": ft_docs},
                    state={"phase": "completed", "iteration": 0, "has_review": False}
                )
                return
            # ── END NO-REVIEW FAST PATH ───────────────────────────────

            needs_review = True
            current_draft = str(raw_draft)

            draft_dict = None
            if isinstance(raw_draft, dict):
                draft_dict = raw_draft
            elif hasattr(raw_draft, "model_dump"):
                draft_dict = raw_draft.model_dump()
            elif isinstance(raw_draft, str):
                try:
                    draft_dict = json.loads(raw_draft)
                except Exception:
                    pass

            if draft_dict and isinstance(draft_dict, dict):
                current_draft = str(draft_dict.get("answer", current_draft))
                if "needs_review" in draft_dict:
                    needs_review = bool(draft_dict.get("needs_review"))

            if not needs_review:
                # Fast-track: chỉ trả docs nếu có evidence thực sự
                # (iteration 0 + no evidence = câu chào hỏi/từ chối, không cần docs)
                ft_docs = _filter_docs_for_ui(global_retrieved_docs) if global_retrieved_docs else []
                yield Event(
                    content=types.Content(role="model", parts=[types.Part.from_text(text=current_draft)]),
                    custom_metadata={"visibility": "final", "docs": ft_docs},
                    state={"phase": "completed", "iteration": iteration, "fast_track": True}
                )
                return
            
            new_texts, new_docs, last_event_idx = self._extract_evidence(ctx, last_event_idx)
            if new_texts:
                global_evidence_parts.extend(new_texts)
                global_evidence_parts = global_evidence_parts[-10:]
                evidence_str = "\n---\n".join(global_evidence_parts)
                
            for d in new_docs:
                doc_id = str(d.get("id", ""))
                doc_doc = str(d.get("doc", ""))
                src_type = str(d.get("source_type", ""))
                key = f"{src_type}::{doc_id}::{doc_doc}"
                if key not in seen_docs:
                    seen_docs.add(key)
                    global_retrieved_docs.append(d)
            
            review_payload = ReviewInput(
                user_query=original_query,
                conversation_history=history,
                previous_draft=current_draft,
                review_feedback=current_feedback,
                evidence=evidence_str,
                iteration=iteration,
                is_final_iteration=(iteration >= self.max_revisions)
            )
            
            yield Event(state={"phase": "reviewing", "iteration": iteration})
            
            verdict_obj = None
            for reviewer_attempt in range(self.max_reviewer_retries):
                try:
                    reviewer_run_id = f"review-{iteration}-attempt-{reviewer_attempt}"
                    review_output = await ctx.run_node(
                        self.reviewer_agent,
                        review_payload.model_dump_json(),
                        run_id=reviewer_run_id,
                        use_as_output=False
                    )
                    
                    if isinstance(review_output, str):
                        verdict_obj = ReviewVerdict.model_validate_json(review_output)
                    else:
                        verdict_obj = ReviewVerdict.model_validate(review_output)
                    break 
                    
                except ValidationError as exc:
                    logger.warning("Reviewer validation error directly: %s", exc)
                    continue
                except DynamicNodeFailError as exc:
                    if isinstance(exc.error, ValidationError):
                        logger.warning("Reviewer validation error in DynamicNodeFailError: %s", exc.error)
                        continue
                    raise
            
            if verdict_obj is None:
                msg = "Hệ thống không thể kiểm duyệt câu trả lời. Vui lòng thử lại sau."
                yield Event(
                    content=types.Content(role="model", parts=[types.Part.from_text(text=msg)]),
                    custom_metadata={"visibility": "final", "docs": _filter_docs_for_ui(global_retrieved_docs)},
                    state={"phase": "terminal_error"}
                )
                return
                
            final_state = {
                "iteration": iteration,
                "reviewer_verdict": verdict_obj.status,
                "reviewer_feedback": verdict_obj.issues or verdict_obj.recommendations,
                "reviewer_action_plan": verdict_obj.action_plan
            }

            if verdict_obj.status == "PASS":
                final_state["phase"] = "completed"
                yield Event(
                    content=types.Content(role="model", parts=[types.Part.from_text(text=current_draft)]),
                    custom_metadata={"visibility": "final", "docs": _filter_docs_for_ui(global_retrieved_docs)},
                    state=final_state
                )
                return
            elif verdict_obj.status == "ASK_BACK":
                final_state["phase"] = "completed"
                msg = verdict_obj.ask_back_question or "Vui lòng cung cấp thêm thông tin."
                yield Event(
                    content=types.Content(role="model", parts=[types.Part.from_text(text=msg)]),
                    custom_metadata={"visibility": "final", "docs": []},
                    state=final_state
                )
                return
            elif verdict_obj.status == "REVISE":
                if iteration >= self.max_revisions:
                    final_state["phase"] = "review_exhausted"
                    msg = "Xin lỗi, hệ thống không thể xác minh chính xác thông tin lúc này. Vui lòng thử lại hoặc hỏi chi tiết hơn."
                    yield Event(
                        content=types.Content(role="model", parts=[types.Part.from_text(text=msg)]),
                        custom_metadata={"visibility": "final", "docs": _filter_docs_for_ui(global_retrieved_docs)},
                        state=final_state
                    )
                    return
                if verdict_obj.action_plan:
                    current_feedback = f"Feedback: {verdict_obj.recommendations}\n\nAction Plan:\n{verdict_obj.action_plan}"
                else:
                    current_feedback = verdict_obj.recommendations
                iteration += 1

class InputGuardrailNode(BaseNode):
    """Content-safety guardrail that runs in parallel with the main agent.

    This node is a **signal-only** node: it MUST NOT yield any Event with
    content or output.  Producing output would violate the ADK constraint
    that only one terminal node may produce output.

    Instead it communicates its result to ``ActorCriticOrchestrator`` via
    the in-process ``_SharedSync`` registry (keyed by ``invocation_id``).
    """

    async def _run_impl(self, *, ctx: Context, node_input: Any):
        sync = _get_or_create_sync(ctx.invocation_id)
        yield Event(state={"phase": "guardrail_started"})

        original_query = _extract_query(node_input)
        if not original_query:
            # Empty query — let ActorCriticOrchestrator handle it.
            sync.guardrail_done.set()
            yield Event(state={"phase": "guardrail_skipped"})
            return

        model_name = "gemini-3.1-flash-lite"
        history = _extract_history(ctx)

        try:
            result = await input_content_filter_guardrail(
                user_query=original_query,
                model_name=model_name,
                history=history,
            )

            if result.get("guardrail_trigger_route") != "none":
                sync.refusal_message = result.get(
                    "message", "Tin nhắn vi phạm chính sách."
                )
                sync.guardrail_failed.set()
                logger.info(
                    "[Guardrail] Blocked — category=%s",
                    result.get("guardrail_trigger_route"),
                )
                yield Event(state={"phase": "guardrail_blocked", "category": result.get("guardrail_trigger_route")})
            else:
                yield Event(state={"phase": "guardrail_passed"})
        except Exception:
            # Fail-open: do not block the user because of infra errors.
            logger.exception("[Guardrail] Error during evaluation — fail-open")
            yield Event(state={"phase": "guardrail_error_failopen"})
        finally:
            # Always signal completion so ActorCritic never waits forever.
            sync.guardrail_done.set()


class IntentDetectionNode(BaseNode):
    """Phân loại phân khúc khách hàng chạy song song để tối ưu tốc độ."""

    async def _run_impl(self, *, ctx: Context, node_input: Any):
        yield Event(state={"phase": "intent_detection_started"})
        from ..utils.intent_detector import detect_segment_llm, get_intent_future
        future = get_intent_future(ctx.invocation_id)

        original_query = _extract_query(node_input)
        if not original_query:
            if not future.done(): future.set_result(None)
            yield Event(state={"phase": "intent_skipped"})
            return

        try:
            intent = await detect_segment_llm(original_query)
            if not future.done(): future.set_result(intent)
            yield Event(state={"phase": "intent_detected", "intent": intent})
        except Exception as e:
            logger.exception("[IntentDetectionNode] Error")
            if not future.done(): future.set_result(None)
            yield Event(state={"phase": "intent_error"})


def build_root_workflow(*, has_review: bool = False) -> Workflow:
    """Build the root workflow.

    Args:
        has_review: Khi ``True``, bật luồng Actor-Critic đầy đủ (main → reviewer
            → revise loop).  Khi ``False`` (default), main agent trả thẳng
            answer cho user mà không qua reviewer.
    """
    guardrail_node = InputGuardrailNode(name="input_guardrail")
    intent_node = IntentDetectionNode(name="intent_detection")
    actor_critic_node = ActorCriticOrchestrator(
        name="actor_critic_orchestrator",
        main_agent=build_main_agent(has_review=has_review),
        reviewer_agent=build_reviewer_agent() if has_review else None,
        has_review=has_review,
    )
    return Workflow(
        name="enterprise_root_workflow",
        edges=[
            ("START", guardrail_node),     # parallel branch 1
            ("START", intent_node),        # parallel branch 2
            ("START", actor_critic_node),  # parallel branch 3
        ],
    )
