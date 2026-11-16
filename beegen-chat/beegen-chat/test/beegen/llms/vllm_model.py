import asyncio
from beegenerate.configs import LLMConfig
from beegenerate.llms.core_v2.factory import LLMFactory
from beegenerate.const import BEEGEN_ROOT
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk


config_path = BEEGEN_ROOT / "config/llms/beegen_v1.yaml"


async def test_stream_mode():
    """Test streaming mode"""
    print("\n=== Testing STREAM mode ===")
    model = LLMFactory.create(
        config=LLMConfig.from_yaml_file(config_path)
    )
        
    stream = model.stream(
        messages=[
            {
                'role': 'user', 'content': 'xin chào'
            }
        ]
    )
    
    print("Streaming response:")
    async for chunk in stream:
        chunk_dict = chunk.model_dump()
        chunk_dict["status_code"] = 200
        chunk_dict["status_message"] = "hihihaha"
        
        _chunk = ChatCompletionChunk(**chunk_dict)
        print(_chunk)


async def test_nonstream_mode():
    """Test non-streaming mode"""
    print("\n=== Testing NONSTREAM mode ===")
    model = LLMFactory.create(
        config=LLMConfig.from_yaml_file(config_path)
    )
    
    prompt = "Hãy viết một câu chào ngắn gọn."
    
    response = await model.generate(
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )
    
    print("Non-streaming response:")
    print(response.choices[0].message.content)
    print()


async def test_batch_mode():
    """Test batch processing mode"""
    print("\n=== Testing BATCH mode ===")
    model = LLMFactory.create(
        config=LLMConfig.from_yaml_file(config_path)
    )
    
    prompts = [
        "Chào buổi sáng là gì tiếng Anh?",
        "Chào buổi tối là gì tiếng Anh?",
        "Tạm biệt là gì tiếng Anh?"
    ]
    
    batch_requests = [
        [{"role": "user", "content": prompt}]
        for prompt in prompts
    ]
    
    responses = await model.generate_batch(
        batch_messages=batch_requests
    )
    
    print("Batch responses:")
    for i, response in enumerate(responses, 1):
        print(f"\nResponse {i}:")
        print(response.choices[0].message.content)
    print()


async def main():
    """Run all test cases"""
    print("Starting LLM Model Tests...")
    
    try:
        # Test streaming mode
        await test_stream_mode()
        
        # # Test non-streaming mode
        # await test_nonstream_mode()
        
        # # Test batch mode
        # await test_batch_mode()
        
        print("All tests completed successfully!")
        
    except Exception as e:
        print(f"Error during testing: {str(e)}")
        raise


if __name__ == "__main__":
    asyncio.run(main())