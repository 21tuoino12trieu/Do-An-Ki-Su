import requests
import json
from typing import Optional

url = "http://10.1.39.127:30042/v1/chat/completions"

payload = json.dumps({
    "temperature": 0,
    "top_p": 0.1,
    "stream": True,
    "frequency_penalty": 0,
    "model": "model/beegen-model-v",
    "messages": [
        {
            "role": "user",
            "content": "viết cho 1 câu truyện dài vãi nồi đi"
        }
    ]
})

headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer mb123456789',
}

with requests.request(
    "POST",
    url,
    headers=headers,
    data=payload,
    stream=True,
    timeout=(1, 2) 
) as response:
    response.raise_for_status()
    
    first_chunk_received = False
    
    for chunk in response.iter_lines(decode_unicode=True):
        if chunk:
            try:
                if not first_chunk_received:
                    # Set socket timeout to None after first chunk
                    response.raw.connection.sock.settimeout(None)
                    first_chunk_received = True
                
                # Process chunk
                if chunk.startswith('data: '):
                    chunk = chunk[6:]
                if chunk == '[DONE]':
                    break
                    
                chunk_data = json.loads(chunk)
                if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                    content = chunk_data['choices'][0].get('delta', {}).get('content', '')
                    if content:
                        print(content, end='', flush=True)

            except json.JSONDecodeError as e:
                print(f"\nError decoding chunk: {e}")
            except Exception as e:
                print(f"\nError processing chunk: {e}")
