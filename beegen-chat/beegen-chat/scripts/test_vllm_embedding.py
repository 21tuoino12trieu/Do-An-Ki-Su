import requests
import json

url = "http://10.1.39.127:30068/v1/embeddings"
api_key = 'mb123456789'

payload = json.dumps({
    "model": "model/bge-m3",
    "input": ["tổng giám đốc mb là ai?"]
})

headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json'
}

response = requests.request("POST", url, headers=headers, data=payload)
print(response.json())