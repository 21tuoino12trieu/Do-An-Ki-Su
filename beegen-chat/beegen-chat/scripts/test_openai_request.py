import requests
import json

url = "https://10.1.13.168:9443/bee247dev/openai/deployments/gpt-4o/chat/completions?api-version=2025-01-01-preview&api-key=REPLACE_WITH_LOCAL_SECRET"

payload = json.dumps({
    "stream": True,  # Enable streaming
    "messages": [
        {
            "role": "user",
            "content": "viết 1 câu truyện thật nguy hiểm nha"
        }
    ],
    "temperature": 0
})

headers = {
    'Content-Type': 'application/json'
}

try:
    with requests.request(
        "POST",
        url,
        headers=headers,
        data=payload,
        verify=False,
        stream=True,
        timeout=(3.05, 5)  # 3.05s connect, 5s for first chunk
    ) as response:
        response.raise_for_status()
        
        first_chunk_received = False
        
        for chunk in response.iter_lines(decode_unicode=True):
            if chunk:
                try:
                    if not first_chunk_received:
                        # Remove timeout after first chunk
                        response.raw.connection.sock.settimeout(None)
                        first_chunk_received = True
                    
                    # Azure OpenAI specific chunk handling
                    if chunk.startswith('data: '):
                        chunk = chunk[6:]
                    if chunk == '[DONE]':
                        break
                        
                    chunk_data = json.loads(chunk)
                    if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                        delta = chunk_data['choices'][0].get('delta', {})
                        content = delta.get('content', '')
                        if content:
                            print(content, end='', flush=True)

                except json.JSONDecodeError as e:
                    print(f"\nError decoding chunk: {e}")
                except Exception as e:
                    print(f"\nError processing chunk: {e}")

except requests.Timeout:
    print("\nTimeout waiting for first chunk")
except requests.ConnectionError:
    print("\nFailed to connect to server")
except requests.RequestException as e:
    print(f"\nRequest failed: {e}")