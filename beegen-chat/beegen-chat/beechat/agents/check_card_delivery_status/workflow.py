import time
from datetime import datetime

from typing import Dict, Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from agents import Runner, ModelSettings, RunConfig, Agent
from langfuse.decorators import observe
from openai.types.responses import ResponseTextDeltaEvent

from beechat.agents.check_card_delivery_status.models import *
from beechat.config import load_settings
from beechat.llms_extend.litellm import litellm_model

_settings = load_settings()
from beechat.utils.prompt_loader import get_prompt
from beegen_v1.utils.common import fake_chunk_from

@observe(name="Card Delivery Status (1.7)")
async def run_workflow(conversation: List[Dict[str, str]], state: Optional[Dict[str, Any] | str] = None):
    if state is None:
        state = {}

    sub_scenario = state.get("sub_scenario", "")

    router_agent = Agent(name="Card Delivery Router", model=litellm_model, instructions=get_prompt("CHECK_CARD_DELIVERY_STATUS_ROUTER_PROMPT").format(sub_scenario=sub_scenario), output_type=CardDeliveryIntent)
    branch_main_response_agent = Agent(name="Card Delivery Main Branch", model=litellm_model, instructions=get_prompt("CHECK_CARD_DELIVERY_STATUS_BRANCH_MAIN_PROMPT"))
    branch_smart_bank_extraction_agent = Agent(name="Card Delivery Smart Bank Extractor", model=litellm_model, instructions=get_prompt("CHECK_CARD_DELIVERY_STATUS_BRANCH_SMART_BANK_PARAMETER_EXTRACTOR_PROMPT"), output_type=BranchSmartBankExtractionResult)
    branch_smart_bank_response_agent = Agent(name="Card Delivery Smart Bank Responder", model=litellm_model)
    branch_home_extraction_agent = Agent(name="Card Delivery Home Extractor", model=litellm_model, instructions=get_prompt("CHECK_CARD_DELIVERY_STATUS_BRANCH_HOME_PARAMETER_EXTRACTOR_PROMPT"), output_type=BranchHomeExtractionResult)
    branch_home_response_agent = Agent(name="Card Delivery Home Responder", model=litellm_model)
    chitchat_agent = Agent(name="Card Delivery Chitchat", model=litellm_model, instructions=get_prompt("CHECK_CARD_DELIVERY_STATUS_BRANCH_CHITCHAT_PROMPT"))

    router_result = await Runner.run(
        starting_agent=router_agent,
        input=conversation,
        run_config=RunConfig(model_settings=ModelSettings(temperature=0, include_usage=True))
    )
    branch = router_result.final_output.branch
    state['sub_scenario'] = branch

    if branch == 'INTENT_MAIN':
        response = Runner.run_streamed(
            starting_agent=branch_main_response_agent,
            input=conversation,
            run_config=RunConfig(model_settings=ModelSettings(temperature=0.7, include_usage=True))
        )
        return response, state
    elif branch == 'INTENT_SMARTBANK':
        extraction = await Runner.run(
            starting_agent=branch_smart_bank_extraction_agent,
            input=conversation,
            run_config=RunConfig(model_settings=ModelSettings(temperature=0, include_usage=True))
        )
        branch_smart_bank_response_agent.instructions = get_prompt("CHECK_CARD_DELIVERY_STATUS_BRANCH_SMART_BANK_RESPONSE_PROMPT").format(informations=extraction.final_output.json())
        response = Runner.run_streamed(
            starting_agent=branch_smart_bank_response_agent,
            input=conversation,
            run_config=RunConfig(model_settings=ModelSettings(temperature=0.7, include_usage=True))
        )
        state.update({'is_complete': extraction.final_output.is_complete})
        return response, state
    elif branch == 'INTENT_HOME_OVER_7_DAYS':
        extraction = await Runner.run(
            starting_agent=branch_home_extraction_agent,
            input=conversation,
            run_config=RunConfig(model_settings=ModelSettings(temperature=0, include_usage=True))
        )
        branch_home_response_agent.instructions = get_prompt("CHECK_CARD_DELIVERY_STATUS_BRANCH_HOME_RESPONSE_PROMPT").format(informations=extraction.final_output.json())
        response = Runner.run_streamed(
            starting_agent=branch_home_response_agent,
            input=conversation,
            run_config=RunConfig(model_settings=ModelSettings(temperature=0.7, include_usage=True))
        )
        state.update({'is_complete': extraction.final_output.is_complete})
        return response, state
    else:
        response = Runner.run_streamed(
            starting_agent=chitchat_agent,
            input=conversation,
            run_config=RunConfig(model_settings=ModelSettings(temperature=0.7, include_usage=True))
        )
        return response, state

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
