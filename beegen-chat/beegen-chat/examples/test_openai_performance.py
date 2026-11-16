import requests
import json
import time
from datetime import datetime

def make_api_request(stream_mode=True):
    url = "http://10.1.39.127:30042/v1/chat/completions"
    
    payload = json.dumps({
        "model": "model/Qwen2.5-72B-Instruct-GPTQ-Int4",
        "temperature": 0,
        "top_p": 0.001,
        "n": 1,
        "stream": stream_mode,
        "frequency_penalty": 0,
        "presence_penalty": 0,
        "messages": [
            {
                "role": "user",
                "content": "giữa mày và gpt, ai thông minh hơn"
            }
        ]
    })
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer mb123456789',
        'Cookie': 'BIGipServer~ACI~k8s_dgx-llm-core-service_pool_30042=rd3o00000000000000000000ffff0a011f13o30042'
    }

    print(f"\n=== Making {'Streaming' if stream_mode else 'Non-streaming'} Request ===")
    
    # Start timing
    start_time = time.time()
    
    try:
        # Make the request
        response = requests.request("POST", url, headers=headers, data=payload, stream=stream_mode)
        
        if stream_mode:
            # Handle streaming response
            first_token_received = False
            first_token_time = None
            full_response = ""
            
            for line in response.iter_lines():
                if line:
                    # First token timing
                    if not first_token_received:
                        first_token_time = time.time()
                        first_token_received = True
                    
                    # Process and print the response
                    try:
                        decoded_line = line.decode('utf-8')
                        # print(decoded_line)
                        full_response += decoded_line + "\n"
                    except Exception as e:
                        print(f"Error processing line: {e}")
            
        else:
            # Handle non-streaming response
            first_token_time = time.time()  # For non-streaming, this is when we get the complete response
            response_json = response.json()
            print("Response:", json.dumps(response_json, indent=2))
        
        # Calculate timings
        end_time = time.time()
        total_time = end_time - start_time
        time_to_first_token = first_token_time - start_time if first_token_time else None
        
        # Print timing information
        print("\n=== Timing Information ===")
        print(f"Total response time: {total_time:.3f} seconds")
        if time_to_first_token:
            print(f"Time to {'first token' if stream_mode else 'complete response'}: {time_to_first_token:.3f} seconds")
        print(f"Request started at: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S.%f')}")
        print(f"Request ended at: {datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S.%f')}")
        
        # Print response status and size
        print(f"Response status code: {response.status_code}")
        print(f"Response size: {len(response.content)} bytes")
        
        return response
        
    except Exception as e:
        print(f"Error during request: {e}")
        return None

# Test both streaming and non-streaming modes
print("\nTesting Streaming Mode:")
streaming_response = make_api_request(stream_mode=True)

print("\nTesting Non-Streaming Mode:")
non_streaming_response = make_api_request(stream_mode=False)