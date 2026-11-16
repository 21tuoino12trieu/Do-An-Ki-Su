from openai import AsyncAzureOpenAI
from .openai_sdk_model import OpenAISDKModel
from beegen_v1.configs import AzureConfig
import httpx
import os


# Set proxy bypass for internal services
# os.environ['NO_PROXY'] = 'llm-gateway-dev.mbbank.com.vn,10.1.87.71,10.1.13.168'
os.environ['NO_PROXY'] = 'llm-gateway-dev.mbbank.com.vn'


class AzureSDKModel(OpenAISDKModel):
    """Azure model using openai sdk with tool calls and multimodal support."""
    
    def __init__(self, config: AzureConfig):
        super().__init__(config)
        
        # Configure HTTP client with timeout and no SSL verification
        self.http_client = httpx.AsyncClient(
            verify=False,
            timeout=httpx.Timeout(
                connect=10.0,
                read=120.0,
                write=10.0,
                pool=5.0
            ),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=10
            )
        )
        # Initialize OpenAI client
        self.client = AsyncAzureOpenAI(
            azure_endpoint=config.azure_endpoint,
            api_key=config.api_key,
            api_version=config.api_version,
            http_client=self.http_client
        )
        

async def main():
    from beegen_v1.const import BEEGEN_ROOT
    from beegen_v1.configs import LLMConfig
    
    config = LLMConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/azure.yaml") 
        
    model = AzureSDKModel(config)
        
    async for chunk in model.stream(messages=[{"role": "user", "content": "xin chào"}]):
        print(chunk)
        

async def test_tools_calling():
    from beegen_v1.const import BEEGEN_ROOT
    import json
    
    model = AzureSDKModel(AzureConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/azure.yaml"))
    
    # Define some example tools
    weather_tool = {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA"
                    }
                },
                "required": ["location"]
            }
        }
    }
    
    calculator_tool = {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Perform a calculation",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to evaluate"
                    }
                },
                "required": ["expression"]
            }
        }
    }
    
    tools = [weather_tool, calculator_tool]
    
    # Text-only example with tools
    print("Text-only example with tools:")
    completion = await model.generate(
        messages=[{"role": "user", "content": "What's the weather like in San Francisco?"}],
        tools=tools
    )
    print(json.dumps(completion.model_dump(), indent=2))
    
    # Text-only example with tools
    print("Text-only (stream) example with tools:")
    stream_response = model.stream(
        messages=[{"role": "user", "content": "What's the weather like in San Francisco?"}],
        tools=tools
    )
    async for chunk in stream_response:
        print(chunk)
        

async def test_multimodal_image():
    from beegen_v1.const import BEEGEN_ROOT
    import json
    
    model = AzureSDKModel(AzureConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/azure.yaml"))

    # Multimodal example with tools
    print("\nMultimodal example with tools:")
    completion = await model.generate(
        messages=[{
            "role": "user", 
            "content": [
                {"type": "text", "text": "What can you see in this image?"},
                {"type": "image_url", "image_url": {"url": r"C:\Users\thanglq2\Downloads\deepseek.png"}}
            ]
        }],
        # tools=tools
    )
    print(completion)

    print("\nMultimodal example (stream) with tools:")
    stream_response = model.stream(
        messages=[{
            "role": "user", 
            "content": [
                {"type": "text", "text": "What can you see in this image?"},
                {"type": "image_url", "image_url": {"url": r"C:\Users\thanglq2\Downloads\deepseek.png"}}
            ]
        }],
        # tools=tools
    )
    async for chunk in stream_response:
        print(chunk)

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_multimodal_image())