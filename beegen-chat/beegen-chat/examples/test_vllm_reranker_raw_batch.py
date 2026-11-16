import requests
import json
import time

# Connection configuration
config = {
    "api_type": "vllm",
    "api_key": "mb123456789",
    "base_url": "http://10.1.87.71:30043/rerank",
    "model": "model/bge-reranker-v2-m3"
}

def send_batch_rerank_request():
    # Sample query and documents
    query = "What is machine learning?"
    
    # Create 10 sample documents (in a real scenario, these would be your retrieved documents)
    documents = [
        {"text": f"Sample document {i} about machine learning and AI concepts.", "id": f"doc_{i}"} 
        for i in range(10)
    ]
    
    # Prepare the payload for vLLM reranker
    payload = {
        "inputs": [
            {
                "query": query,
                "passages": documents
            }
        ],
        "parameters": {
            "top_k": 10
        }
    }
    
    # Add headers with API key
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config['api_key']}"
    }
    
    # Log request start time
    start_time = time.time()
    
    # Send the request
    response = requests.post(
        config["base_url"],
        headers=headers,
        data=json.dumps(payload)
    )
    
    # Calculate elapsed time
    elapsed_time = time.time() - start_time
    
    # Process the response
    if response.status_code == 200:
        results = response.json()
        print(f"Request successful! Processed in {elapsed_time:.4f} seconds")
        print(f"Top ranked document: {results['outputs'][0]['documents'][0]}")
        return results
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
        return None

# Execute the batch request
if __name__ == "__main__":
    results = send_batch_rerank_request()