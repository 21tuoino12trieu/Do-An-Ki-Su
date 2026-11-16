import asyncio
import time
from typing import Dict, Any
from uuid import uuid4
try:
    from openai.types.responses import ResponseTextDeltaEvent
except ImportError:
    class ResponseTextDeltaEvent:
        delta: str = ""
from beechat.agents import *
from beechat.config import load_settings
from beechat.prompts.scenario_prompts import SCENARIO_ROUTING_PROMPT
from beechat.services.llm_service import LLMService
from beechat.utils.prompt_loader import get_prompt
from beegen_v1.utils.common import fake_chunk_from
from beegenerate.loggings import LOGGER

_settings = load_settings()


async def build_generator(response):
    current_timestamp = int(time.time())
    result_id = str(uuid4().hex)
    model_name = _settings.scenario_model
    default_fallback = "Dạ, Bee đã ghi nhận thông tin của bạn. Bạn vui lòng cho Bee biết thêm chi tiết để Bee hỗ trợ bạn tốt nhất nhé!"
    
    if response is None:
        yield fake_chunk_from(
            content=default_fallback,
            model=model_name,
            chat_id=result_id,
            current_time=current_timestamp
        )
        return
        
    if isinstance(response, str):
        content_text = response.strip() if response.strip() else default_fallback
        yield fake_chunk_from(
            content=content_text,
            model=model_name,
            chat_id=result_id,
            current_time=current_timestamp
        )
        return

    if hasattr(response, "stream_events"):
        has_content = False
        try:
            async for event in response.stream_events():
                if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                    delta_str = str(event.data.delta)
                    if delta_str:
                        has_content = True
                        yield fake_chunk_from(
                            content=delta_str,
                            model=model_name,
                            chat_id=result_id,
                            current_time=current_timestamp
                        )
        except Exception as e:
            LOGGER.error(f"Error during stream_events: {e}", exc_info=True)

        if not has_content:
            yield fake_chunk_from(
                content=default_fallback,
                model=model_name,
                chat_id=result_id,
                current_time=current_timestamp
            )

class ScenarioService:
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
        self.conversation_map = {}

    def _format_conversation(self, messages: list) -> str:
        if not messages:
            return ""
        lines = []
        for msg in messages:
            if isinstance(msg, dict):
                role = "Khách hàng" if msg.get("role") == "user" else "Trợ lý Bee"
                content = msg.get("content", "").strip()
                if content:
                    lines.append(f"{role}: {content}")
        return "\n".join(lines)

    async def select_scenario(self, state: Dict) -> str:
        query = state.get('query', '')
        messages = state.get('messages', [])
        formatted_history = self._format_conversation(messages)
        scenario = ""
        if 'scenario_context' in state and state['scenario_context'].get('scenario'):
            scenario = state['scenario_context']['scenario']

        query_clean = query.strip().upper()
        if any(keyword in query_clean for keyword in ["LIÊN HỆ TVV", "GẶP TVV", "GẶP TƯ VẤN VIÊN", "GẶP NHÂN VIÊN", "CHUYỂN TVV"]):
            LOGGER.info("[ScenarioService] Handover request detected -> meet_consultant")
            return "meet_consultant"

        try:
            prompt_template = SCENARIO_ROUTING_PROMPT
            response = await self.llm_service.llm_task(
                inputs={
                    "query": query,
                    "conversation_history": formatted_history or "Chưa có lịch sử hội thoại trước đó.",
                    "current_scenario": scenario or "None"
                },
                prompt_template=prompt_template,
                use_primary=True
            )
            clean_resp = response.strip().strip('`"\'').strip()
            if clean_resp == 'None' or clean_resp == 'none' or not clean_resp:
                return None
            LOGGER.info(f"[ScenarioService] LLM Routing selected scenario -> {clean_resp}")
            return clean_resp
        except Exception as e:
            LOGGER.error(f"Error during LLM scenario selection: {e}", exc_info=True)
            return None

    async def run(self, state: Dict, scenario: str) -> tuple[Any, Any] | None:
        if not scenario:
            scenario = await self.select_scenario(state)
            state["scenario_context"]["scenario"] = scenario
        try:
            res_result = None
            extraction_result = state
            if scenario == 'meet_consultant':
                res_result = "Bạn đã yêu cầu gặp Tư vấn viên, vui lòng đợi trong giây lát ạ!"
            elif scenario == 'handle_card_swallowed':
                res_result, extraction_result =  await self._handle_card_swallowed(state)
            elif scenario == 'handle_atm_withdrawal_dispute':
                res_result, extraction_result =  await self._handle_atm_withdrawal_dispute(state)
            elif scenario == 'handle_pos_transaction_dispute':
                res_result, extraction_result =  await self._handle_pos_transaction_dispute(state)
            elif scenario == 'handle_online_payment_dispute':
                res_result, extraction_result =  await self._handle_online_payment_dispute(state)
            elif scenario == 'handle_unknown_transaction_dispute':
                res_result, extraction_result =  await self._handle_unknown_transaction_dispute(state)
            elif scenario == 'handle_early_installment_settlement':
                res_result, extraction_result =  await self._handle_early_installment_settlement(state)
            elif scenario == 'check_card_delivery_status':
                res_result, extraction_result =  await self._check_card_delivery_status(state)
            elif scenario == 'check_credit_card_statement_payment':
                res_result, extraction_result =  await self._check_credit_card_statement_payment(state)
            elif scenario == 'check_failed_card_transaction':
                res_result, extraction_result =  await self._check_failed_card_transaction(state)
            elif scenario == 'check_failed_refund_to_account':
                res_result, extraction_result =  await self._check_failed_refund_to_account(state)

            return build_generator(res_result), extraction_result
        except Exception as e:
            LOGGER.error(f"Error during LLM scenario: {e}", exc_info=True)
            return None, None

    async def _handle_card_swallowed(self, state: Dict):
        messages = state.get('messages', [])
        conversation = messages[-20:] if len(messages) > 1 else messages
        scenario_context = state.get('scenario_context', {})
        try:
            res, scenario_context = await card_swallowed.run_workflow(conversation, scenario_context)

            return res, scenario_context
        except Exception as e:
            LOGGER.error(f"Error during LLM card_swallowed: {e}", exc_info=True)
            return None, None

    async def _handle_atm_withdrawal_dispute(self, state: Dict):
        messages = state.get('messages', [])
        conversation = messages[-20:] if len(messages) > 1 else messages
        scenario_context = state.get('scenario_context', {})
        try:
            res, scenario_context = await atm_withdrawal_dispute.run_workflow(conversation, scenario_context)

            return res, scenario_context
        except Exception as e:
            LOGGER.error(f"Error during LLM atm_withdrawal_dispute: {e}", exc_info=True)
            return None, None

    async def _handle_pos_transaction_dispute(self, state: Dict):
        messages = state.get('messages', [])
        conversation = messages[-20:] if len(messages) > 1 else messages
        scenario_context = state.get('scenario_context', {})
        try:
            res, scenario_context = await pos_transaction_dispute.run_workflow(conversation, scenario_context)

            return res, scenario_context
        except Exception as e:
            LOGGER.error(f"Error during LLM pos_transaction_dispute: {e}", exc_info=True)
            return None, None

    async def _handle_online_payment_dispute(self, state: Dict):
        messages = state.get('messages', [])
        conversation = messages[-20:] if len(messages) > 1 else messages
        scenario_context = state.get('scenario_context', {})
        try:
            res, scenario_context = await online_payment_dispute.run_workflow(conversation, scenario_context)

            return res, scenario_context
        except Exception as e:
            LOGGER.error(f"Error during LLM online_payment_dispute: {e}", exc_info=True)
            return None, None

    async def _handle_unknown_transaction_dispute(self, state: Dict):
        messages = state.get('messages', [])
        conversation = messages[-20:] if len(messages) > 1 else messages
        scenario_context = state.get('scenario_context', {})
        try:
            res, scenario_context = await unknown_transaction_dispute.run_workflow(conversation, scenario_context)

            return res, scenario_context
        except Exception as e:
            LOGGER.error(f"Error during LLM unknown_transaction_dispute: {e}", exc_info=True)
            return None, None

    async def _handle_early_installment_settlement(self, state: Dict):
        messages = state.get('messages', [])
        conversation = messages[-20:] if len(messages) > 1 else messages
        scenario_context = state.get('scenario_context', {})
        try:
            res, scenario_context = await early_installment_settlement.run_workflow(conversation, scenario_context)

            return res, scenario_context
        except Exception as e:
            LOGGER.error(f"Error during LLM early_installment_settlement: {e}", exc_info=True)
            return None, None

    async def _check_card_delivery_status(self, state: Dict):
        messages = state.get('messages', [])
        conversation = messages[-20:] if len(messages) > 1 else messages
        scenario_context = state.get('scenario_context', {})
        try:
            res, scenario_context = await check_card_delivery_status.run_workflow(conversation, scenario_context)

            return res, scenario_context
        except Exception as e:
            LOGGER.error(f"Error during LLM check_card_delivery_status: {e}", exc_info=True)
            return None, None

    async def _check_credit_card_statement_payment(self, state: Dict):
        messages = state.get('messages', [])
        conversation = messages[-20:] if len(messages) > 1 else messages
        scenario_context = state.get('scenario_context', {})
        try:
            res, scenario_context = await check_credit_card_statement_payment.run_workflow(conversation, scenario_context)

            return res, scenario_context
        except Exception as e:
            LOGGER.error(f"Error during LLM check_failed_card_transaction: {e}", exc_info=True)
            return None, None

    async def _check_failed_card_transaction(self, state: Dict):
        messages = state.get('messages', [])
        conversation = messages[-20:] if len(messages) > 1 else messages
        scenario_context = state.get('scenario_context', {})
        try:
            res, scenario_context = await check_failed_card_transaction.run_workflow(conversation,
                                                                                           scenario_context)

            return res, scenario_context
        except Exception as e:
            LOGGER.error(f"Error during LLM check_failed_card_transaction: {e}", exc_info=True)
            return None, None

    async def _check_failed_refund_to_account(self, state: Dict):
        messages = state.get('messages', [])
        conversation = messages[-20:] if len(messages) > 1 else messages
        scenario_context = state.get('scenario_context', {})
        try:
            res, scenario_context = await check_failed_refund_to_account.run_workflow(conversation, scenario_context)

            return res, scenario_context
        except Exception as e:
            LOGGER.error(f"Error during LLM check_failed_refund_to_account: {e}", exc_info=True)
            return None, None


async def main():
    from beegenerate.const import BEEGEN_ROOT
    model_config_paths = {
        "gemini": BEEGEN_ROOT / "config/gemini.yaml",
        "chatgpt": BEEGEN_ROOT / "config/chatgpt.yaml",
        "beegen_v2": BEEGEN_ROOT / "config/llms/beegen_v2.yaml"
    }
    llm_service = LLMService(config_paths=model_config_paths, default_model_name="chatgpt")
    scenario = ScenarioService(llm_service=llm_service)

    result = await scenario.select_scenario({'messages': [{"role": "user", "content": "số tổng đài MB là bao nhiều"}], "scenarioClassifyOnly": True})
    print(result)

    result = await scenario.run(
        {
            'messages': [
                {"role": "user", "content": "tôi bị nuốt thẻ, 44440213, mã máy 12321323"},
                {"role": "assistant", "content": "Chào bạn, Bee đã ghi nhận ID thẻ của bạn là 44440213.\n\nVề mã máy ATM bạn cung cấp (12321323), mã máy MB thường có 8 chữ số và luôn bắt đầu bằng số 8 nha bạn. Bạn có thể kiểm tra lại trên thân máy hoặc biên lai giao dịch, giúp Bee xác nhận lại nhé.\n\nNgoài ra, bạn vui lòng cung cấp thêm Địa điểm Chi nhánh/PGD MB thuận tiện nhất mà bạn muốn nhận lại thẻ nha."},
                {"role": "user", "content": "à 81239293"},
            ],
            "scenarioClassifyOnly": True
        }
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
