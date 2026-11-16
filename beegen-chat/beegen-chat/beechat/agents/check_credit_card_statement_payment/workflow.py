import json
import time
from datetime import datetime
from typing import Optional, List, Any, Dict, Tuple
from uuid import uuid4
from zoneinfo import ZoneInfo

from agents import Agent, Runner, RunConfig, ModelSettings
from langfuse.decorators import observe
from openai.types.responses import ResponseTextDeltaEvent

from beechat.config import load_settings
from beechat.llms_extend.litellm import litellm_model

_settings = load_settings()
from beechat.agents.check_credit_card_statement_payment.models import (
    PaymentMethodIntent,
    RoleIntent,
    PaymentRouterOutput,
    RoleRouterOutput,
    MbTransferExtractionResult,
    OtherBankExtractionResult,
    CrmExtractionResult,
    BranchExtractionResult,
)
from beechat.utils.prompt_loader import get_prompt
from beegen_v1.utils.common import fake_chunk_from


def _render(text: str, replacements: Dict[str, str]) -> str:
    for key, val in replacements.items():
        text = text.replace(key, val)
    return text


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _agent_for_text(name: str, text: str, output_type: Optional[Any] = None) -> Agent:
    return Agent(name=name, model=litellm_model, instructions=text, output_type=output_type)

@observe(name="Check Credit Card Statement (1.8)")
async def run_workflow(conversation: List[Dict[str, str]], state: Optional[Dict[str, Any] | str] = None):
    if state is None:
        state = {}

    if isinstance(state, str):
        try:
            state = json.loads(state)
        except Exception:
            state = {}

    sub_scenario = str(state.get("sub_scenario", ""))
    sub_sub_scenario = str(state.get("sub_sub_scenario", ""))

    router_text = _render(
        get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_ROUTER"),
        {"{#1772695708816.sub_scenario#}": sub_scenario}
    )
    router_agent = _agent_for_text(
        "Payment Method Router", router_text, PaymentRouterOutput)

    router_result = await Runner.run(
        starting_agent=router_agent,
        input=conversation,
        run_config=RunConfig(model_settings=ModelSettings(
            temperature=0, include_usage=True))
    )
    branch = router_result.final_output.branch
    state["sub_scenario"] = branch

    if branch == PaymentMethodIntent.INTENT_CHITCHAT:
        resp_text = get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_CHITCHAT")
        resp_agent = _agent_for_text("Chitchat", resp_text)
        res = Runner.run_streamed(starting_agent=resp_agent, input=conversation, run_config=RunConfig(model_settings=ModelSettings(temperature=0.7, include_usage=True)))
        return res, state

    if branch == PaymentMethodIntent.INTENT_MAIN:
        resp_text = get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_PAYMENT_METHOD_MAIN_RESPONSE")
        resp_agent = _agent_for_text("Main Payment Method Prompt", resp_text)
        res = Runner.run_streamed(starting_agent=resp_agent, input=conversation, run_config=RunConfig(model_settings=ModelSettings(temperature=0.7, include_usage=True)))
        return res, state

    if branch == PaymentMethodIntent.INTENT_TRANSFER_FROM_MB_ACCOUNT:
        extract_text = get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_MB_TRANSFER_EXTRACTOR")
        extractor = _agent_for_text(
            "MB Transfer Extractor", extract_text, MbTransferExtractionResult)
        extraction = await Runner.run(
            starting_agent=extractor,
            input=conversation,
            run_config=RunConfig(model_settings=ModelSettings(
                temperature=0, include_usage=True))
        )
        extraction_data = extraction.final_output.model_dump()
        resp_text = _render(
            get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_MB_TRANSFER_RESPONSE"),
            {"{#1772683333990.structured_output#}": _json(extraction_data)}
        )
        resp_agent = _agent_for_text("MB Transfer Response", resp_text)
        res = Runner.run_streamed(starting_agent=resp_agent, input=conversation, run_config=RunConfig(model_settings=ModelSettings(temperature=0.7, include_usage=True)))
        state['is_complete'] = extraction.final_output.is_complete
        return res, state

    if branch == PaymentMethodIntent.INTENT_CASH_DEPOSIT_AT_CRM:
        extract_text = get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_CRM_EXTRACTOR")
        extractor = _agent_for_text(
            "CRM Extractor", extract_text, CrmExtractionResult)
        extraction = await Runner.run(
            starting_agent=extractor,
            input=conversation,
            run_config=RunConfig(model_settings=ModelSettings(
                temperature=0, include_usage=True))
        )
        extraction_data = extraction.final_output.model_dump()
        resp_text = _render(
            get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_CRM_RESPONSE"),
            {"{#1772706624264.structured_output#}": _json(extraction_data)}
        )
        resp_agent = _agent_for_text("CRM Response", resp_text)
        res = Runner.run_streamed(starting_agent=resp_agent, input=conversation, run_config=RunConfig(model_settings=ModelSettings(temperature=0.7, include_usage=True)))
        state['is_complete'] = extraction.final_output.is_complete
        return res, state

    if branch == PaymentMethodIntent.INTENT_CASH_DEPOSIT_AT_BRANCH:
        extract_text = get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_BRANCH_EXTRACTOR")
        extractor = _agent_for_text(
            "Branch Extractor", extract_text, BranchExtractionResult)
        extraction = await Runner.run(
            starting_agent=extractor,
            input=conversation,
            run_config=RunConfig(model_settings=ModelSettings(
                temperature=0, include_usage=True))
        )
        extraction_data = extraction.final_output.model_dump()
        resp_text = _render(
            get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_BRANCH_RESPONSE"),
            {"{#1772706640704.structured_output#}": _json(extraction_data)}
        )
        resp_agent = _agent_for_text("Branch Response", resp_text)
        res = Runner.run_streamed(starting_agent=resp_agent, input=conversation, run_config=RunConfig(model_settings=ModelSettings(temperature=0.7, include_usage=True)))
        state['is_complete'] = extraction.final_output.is_complete
        return res, state

    if branch == PaymentMethodIntent.INTENT_TRANSFER_FROM_OTHER_BANK:
        role_router_text = _render(
            get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_OTHER_BANK_ROLE_ROUTER"),
            {"{#1772695708816.sub_sub_scenario#}": str(sub_sub_scenario)}
        )
        role_router = _agent_for_text(
            "Other Bank Role Router", role_router_text, RoleRouterOutput)
        role_result = await Runner.run(
            starting_agent=role_router,
            input=conversation,
            run_config=RunConfig(model_settings=ModelSettings(
                temperature=0, include_usage=True))
        )
        role = role_result.final_output.intent
        state["sub_sub_scenario"] = role

        if role == RoleIntent.INTENT_MAIN:
            resp_text = get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_OTHER_BANK_ROLE_MAIN")
            resp_agent = _agent_for_text("Other Bank Role Prompt", resp_text)
            res = Runner.run_streamed(starting_agent=resp_agent, input=conversation, run_config=RunConfig(model_settings=ModelSettings(temperature=0.7, include_usage=True)))
            return res, state

        if role == RoleIntent.INTENT_MB_N__OTHER_BANK_Y:
            resp_text = get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_OTHER_BANK_ROLE_NOT_MB_OWNER")
            resp_agent = _agent_for_text(
                "Other Bank - Not MB Owner", resp_text)
            res = Runner.run_streamed(starting_agent=resp_agent, input=conversation, run_config=RunConfig(model_settings=ModelSettings(temperature=0.7, include_usage=True)))
            return res, state

        if role == RoleIntent.INTENT_MB_N__OTHER_BANK_N:
            resp_text = get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_OTHER_BANK_ROLE_NO_OWNER")
            resp_agent = _agent_for_text("Other Bank - No Owner", resp_text)
            res = Runner.run_streamed(starting_agent=resp_agent, input=conversation, run_config=RunConfig(model_settings=ModelSettings(temperature=0.7, include_usage=True)))
            return res, state

        if role == RoleIntent.INTENT_MB_Y__OTHER_BANK_Y:
            extract_text = get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_OTHER_BANK_OWNER_SENDER_EXTRACTOR")
            extractor = _agent_for_text(
                "Other Bank Extractor (Owner Sender)", extract_text, OtherBankExtractionResult)
            extraction = await Runner.run(
                starting_agent=extractor,
                input=conversation,
                run_config=RunConfig(model_settings=ModelSettings(
                    temperature=0, include_usage=True))
            )
            extraction_data = extraction.final_output.model_dump()
            resp_text = _render(
                get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_OTHER_BANK_OWNER_SENDER_RESPONSE"),
                {"{#1773132966812.structured_output#}": _json(
                    extraction_data)}
            )
            resp_agent = _agent_for_text(
                "Other Bank Response (Owner Sender)", resp_text)
            res = Runner.run_streamed(starting_agent=resp_agent, input=conversation, run_config=RunConfig(model_settings=ModelSettings(temperature=0.7, include_usage=True)))
            state['is_complete'] = extraction.final_output.is_complete
            return res, state

        if role == RoleIntent.INTENT_MB_Y__OTHER_BANK_N:
            extract_text = get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_OTHER_BANK_OWNER_NOT_SENDER_EXTRACTOR")
            extractor = _agent_for_text(
                "Other Bank Extractor (Owner Not Sender)", extract_text, OtherBankExtractionResult)
            extraction = await Runner.run(
                starting_agent=extractor,
                input=conversation,
                run_config=RunConfig(model_settings=ModelSettings(
                    temperature=0, include_usage=True))
            )
            extraction_data = extraction.final_output.model_dump()
            resp_text = _render(
                get_prompt("CHECK_CREDIT_CARD_STATEMENT_PAYMENT_OTHER_BANK_OWNER_NOT_SENDER_RESPONSE"),
                {"{#1773132969532.structured_output#}": _json(
                    extraction_data)}
            )
            resp_agent = _agent_for_text(
                "Other Bank Response (Owner Not Sender)", resp_text)
            res = Runner.run_streamed(starting_agent=resp_agent, input=conversation, run_config=RunConfig(model_settings=ModelSettings(temperature=0.7, include_usage=True)))
            state['is_complete'] = extraction.final_output.is_complete
            return res, state

    return "Bee chưa thể xử lý yêu cầu lúc này. Bạn vui lòng thử lại sau nhé.", state


async def build_generator(response):
    current_timestamp = int(time.time())
    result_id = str(uuid4().hex)
    async for event in response.stream_events():
        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
            yield fake_chunk_from(
                content=str(event.data.delta),
                model=_settings.scenario_model,
                chat_id=result_id,
                current_time=current_timestamp
            )


async def main():
    conversation = []
    while True:
        question = str(input("\nNhập câu hỏi: "))
        conversation.append({"role": "user", "content": question})
        reply, next_state = await run_workflow(conversation, state={})
        response = ""
        async for chunk in build_generator(reply):
            response += chunk.choices[0].delta.content
        print(response)
        conversation.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
