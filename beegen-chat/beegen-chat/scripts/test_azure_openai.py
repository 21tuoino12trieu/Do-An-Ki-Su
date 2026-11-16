from openai import AzureOpenAI, OpenAI, AsyncAzureOpenAI, AsyncOpenAI
import sys
import os
import httpx

os.environ['NO_PROXY'] = 'llm-gateway-dev.mbbank.com.vn'


async def main():
    # # Create HTTP client
    http_client = httpx.AsyncClient(verify=False)
    
    # Configure the client
    client = AsyncAzureOpenAI(
        azure_endpoint="https://10.1.13.168:9443/bee247dev/",
        api_key="REPLACE_WITH_LOCAL_SECRET",
        api_version="2024-08-01-preview",
        http_client=http_client
    )
    # client = AsyncAzureOpenAI(
    #     azure_endpoint="https://10.1.13.168:8443/mbdevai/",
    #     api_key="REPLACE_WITH_LOCAL_SECRET",
    #     api_version="2024-08-01-preview",
    #     http_client=http_client
    # )
    
    # client = AsyncOpenAI(
    #     base_url="http://10.1.87.71:30042/v1/",
    #     api_key="mb123456789",
    #     http_client=http_client
    # )
    
    try:
        # Create a streaming completion
        response = await client.chat.completions.create(
            # model="model/beegen-model-v1",
            model="gpt-4o",
            messages=[
                {'role': 'system', 'content': 'Tôi là Beehi, sở thích của tôi là: hihi'}, 
                {'content': 'hihi', 'role': 'user'}, 
                {'role': 'assistant', 'content': 'haha'}, 
                {'role': 'user', 'content': 'alo, tôi là Thắng, năm nay tôi 17 tuổi'}
            ],
            temperature=0,
            stream=True
        )
        
        async for chunk in response:
            print(chunk)
            
    finally:
        # Manual cleanup
        await client.close()
        await http_client.aclose()
        

if __name__ == "__main__":
    import asyncio
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
    asyncio.run(main())