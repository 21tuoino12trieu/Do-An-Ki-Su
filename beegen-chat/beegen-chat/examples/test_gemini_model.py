import vertexai
from vertexai.preview.generative_models import GenerativeModel
from google.oauth2 import service_account
from beegenerate.const import BEEGEN_ROOT
import asyncio
import time
from beegenerate.configs import LLMConfig
import nest_asyncio

nest_asyncio.apply()
 
PROJECT_ID = "mb-data-science-production"
LOCATION = "us-central1"
MODELS = [
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite-001",
    # "gemini-2.5-pro-preview-03-25",
    # "gemini-2.5-pro-exp-03-25",
    # "claude-3-7-sonnet"
]
MODEL_NAME = "gemini-2.0-flash-lite-001"

config = LLMConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/gemini_2.5_flash.yaml")
config.model = MODEL_NAME

print(config)

 
def get_vertextai():
    
    credentials = service_account.Credentials.from_service_account_info(
        config.model_dump()
    )
     
    vertexai.init(
        project=config.project_id,
        location=config.location,
        credentials=credentials
    )
 
async def call_gemini_stream(messages, generation_config):
    """Call Gemini model with streaming response and first token latency measurement"""
    # Get system instructions from system messages
    system_instructions = [msg['content'] for msg in messages if msg['role'] == 'system']
    
    # Initialize model with system instructions if present
    model = GenerativeModel(
        config.model,
        system_instruction=system_instructions if system_instructions else None
    ) 
    
    # Get user messages
    prompt = [msg['content'] for msg in messages if msg['role'] != 'system']
    
    # Measure first token latency
    first_token_received = False
    
    start_time = time.time()

    # Generate streaming response
    response = await model.generate_content_async(
        prompt,
        generation_config=generation_config,
        stream=True
    )
    
    async for chunk in response:
        if not first_token_received:
            first_token_latency = time.time() - start_time
            print(f"\nFirst token latency: {first_token_latency:.3f} seconds")
            first_token_received = True
        
        print(chunk.text, end='')
    
    print()  # Add newline at end
    

from beegenerate.prompts.samples import DOCUMENT_FILTER_PROMPT

 
messages = [
    {"role": "user", "content": DOCUMENT_FILTER_PROMPT}
]
 
generation_config = {
    'temperature': 0,
}
 

async def main():
    get_vertextai()
    await call_gemini_stream(messages,generation_config)
    
    
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())