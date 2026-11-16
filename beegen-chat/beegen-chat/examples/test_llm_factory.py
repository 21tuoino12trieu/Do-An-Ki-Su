from beegenerate.llms.core import LLMFactory

async def single_request():
    from beegenerate.configs import LLMConfig, CompletionConfig

    llm_model = LLMFactory.create(
        config=LLMConfig(
            api_key="REPLACE_WITH_LOCAL_SECRET",
            api_type="azure",
            api_version="2024-02-15-preview",
            base_url="https://10.1.13.168:8443/mbdevai",
            model="azure-chat-engine-gpt-4o-base"
        )
    )
    
    async for chunk in llm_model.run(
        messages=[
            {
                "role": "user",
                "content": "xin chào tình yêu, em khỏe không ?"
            }
        ],
        completion=CompletionConfig(
            temperature= 0.0
        )
    ):
        print(chunk.model_dump_json())
        
        
if __name__ == "__main__":
    import asyncio
    asyncio.run(single_request())