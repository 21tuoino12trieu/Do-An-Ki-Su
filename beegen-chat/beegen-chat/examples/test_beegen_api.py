import asyncio
import aiohttp
import json

async def test_streaming_api():
    url = "http://beegen-chat-api.tanzu-dev.mbbank.com.vn/v1/chat/completions"
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer REPLACE_WITH_LOCAL_SECRET'
    }
    
    payload = {
        "bot_id": "b10f0d26-4d91-47f5-8cac-034b87e42c7f",
        "topic": "default",
        "role": "L1",
        "messages": [
            {
                "role": "user",
                "content": "xin chào"
            }
        ]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                # Check if request was successful
                response.raise_for_status()
                
                # Process the streaming response
                async for line in response.content:
                    decoded_line = line.decode('utf-8').strip()
                    if decoded_line:
                        # Remove "data: " prefix if present
                        if decoded_line.startswith('data: '):
                            decoded_line = decoded_line[6:]
                        
                        try:
                            # Parse JSON response
                            json_response = json.loads(decoded_line)
                            print("Received chunk:", json_response)
                            # Add sleep between chunks
                            await asyncio.sleep(0.0001)  # Sleep for 1 second between chunks
                        except json.JSONDecodeError:
                            print("Received non-JSON data:", decoded_line)

    except aiohttp.ClientError as e:
        print(f"Error occurred: {e}")

async def main():
    print("Starting API test...")
    await test_streaming_api()
    print("Test completed!")

if __name__ == "__main__":
    asyncio.run(main())