import time
from typing import Dict, Any, List, Optional
from uuid import uuid4

from agents import Runner, ModelSettings, RunConfig, Agent
from langfuse.decorators import observe
from openai.types.responses import ResponseTextDeltaEvent

from beechat.agents.check_card_issuing_branch.models import *
from beechat.config import load_settings
from beechat.llms_extend.litellm import litellm_model

_settings = load_settings()
from beechat.utils.prompt_loader import get_prompt
from beegen_v1.utils.common import fake_chunk_from

@observe(name="Card Issuing Branch (1.15)")
async def run_workflow(conversation: List[Dict[str, str]], state: Optional[Dict[str, Any] | str] = None):
    if state is None:
        state = {}

    # Create extraction agent
    extraction_agent = Agent(
        name="Card Issuing Branch Extractor",
        model=litellm_model,
        instructions=get_prompt("CARD_ISSUING_BRANCH_PARAMETER_EXTRACTOR_PROMPT"),
        output_type=CardIssuingBranchExtractionResult
    )
    
    # Create response agent
    response_agent = Agent(
        name="Card Issuing Branch Responder",
        model=litellm_model
    )

    # Run extraction
    extraction = await Runner.run(
        starting_agent=extraction_agent,
        input=conversation,
        run_config=RunConfig(model_settings=ModelSettings(temperature=0, include_usage=True))
    )
    
    # Set response agent instructions with extracted information
    response_agent.instructions = get_prompt("CARD_ISSUING_BRANCH_RESPONSE_PROMPT").format(informations=extraction.final_output.json())
    
    # Run response
    response = Runner.run_streamed(
        starting_agent=response_agent,
        input=conversation,
        run_config=RunConfig(model_settings=ModelSettings(temperature=0.7, include_usage=True))
    )
    
    # Update state with completion status
    state.update({'is_complete': extraction.final_output.is_complete})
    
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
