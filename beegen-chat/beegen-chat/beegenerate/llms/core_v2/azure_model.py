from typing import Dict, Tuple
from beegenerate.configs import LLMConfig
from .openai_model import OpenAICompatibleModel
from beegenerate.loggings import LOGGER
import asyncio


class AzureModel(OpenAICompatibleModel):
    """Azure model backend."""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
                    
    def _prepare_url_headers(
        self 
    ) -> Tuple[str, Dict]:
        # prepare request params
        url = (
            f"{self.config.base_url}/openai/deployments/"
            f"{self.config.model}/chat/completions"
            f"?api-version={self.config.api_version}"
            f"&api-key={self.config.api_key}"
        )
        headers = {
            'Content-Type': 'application/json',
        }
        return url, headers
                    
                    
async def main():
    from beegenerate.const import BEEGEN_ROOT
    model = AzureModel(config=LLMConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/azure.yaml"))
    
    async for chunk in model.stream(
        messages=[{"role": "user", "content": "xin chào"}]
    ):
        pass
    
    completion = await model.generate(
        messages=[{"role": "user", "content": "xin chào"}]
    )
    
    batch_completion = await model.generate_batch(
        batch_messages=[
            [{"role": "user", "content": "xin chào"}],
            [{"role": "user", "content": "hi"}],
            [{"role": "user", "content": "nói gì ngắn gọn đi"}],
            [{"role": "user", "content": "xin chào"}],
            [{"role": "user", "content": "hi"}],
            [{"role": "user", "content": "nói gì ngắn gọn đi"}],
            [{"role": "user", "content": "xin chào"}],
            [{"role": "user", "content": "hi"}],
            [{"role": "user", "content": "nói gì ngắn gọn đi"}]
        ]
    )
        
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
    
    # # Text-only example with tools
    # print("Text-only example with tools:")
    # completion = await model.generate(
    #     messages=[{"role": "user", "content": "What's the weather like in San Francisco?"}],
    #     tools=tools
    # )
    # print(json.dumps(completion.model_dump(), indent=2))
    
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
    
    # # Streaming example with tools
    # print("\nStreaming example with tools:")
    # async for chunk in model.stream(
    #     messages=[{"role": "user", "content": "Calculate 123 * 456"}],
    #     tools=tools
    # ):
    #     if chunk.choices and chunk.choices[0].delta:
    #         delta = chunk.choices[0].delta
    #         if delta.content:
    #             print(f"Content: {delta.content}")
    #         if delta.tool_calls:
    #             for tool_call in delta.tool_calls:
    #                 if hasattr(tool_call, "function") and tool_call.function:
    #                     print(f"Tool call: {tool_call.function.name} - {tool_call.function.arguments}")
    
    # # Batch processing with tools
    # print("\nBatch processing with tools:")
    # batch_completion = await model.generate_batch(
    #     batch_messages=[
    #         [{"role": "user", "content": "What's the weather like in New York?"}],
    #         [{"role": "user", "content": "Calculate 987 / 3"}]
    #     ],
    #     batch_tools=[tools, tools]  # Provide tools for each request
    # )
    # print(f"Received {len(batch_completion)} responses")
        

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())