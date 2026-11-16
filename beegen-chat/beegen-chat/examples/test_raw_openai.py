import requests
import json

# Your OpenAI API key
api_key = "your_api_key_here"

# API endpoint
url = "https://10.1.13.168:9443/bee247dev/openai/deployments/gpt-4o/chat/completions?api-version=2025-01-01-preview&api-key=REPLACE_WITH_LOCAL_SECRET"

# Headers
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}

# Request body with JSON mode enabled
data = {
    "model": "gpt-4o",  # or another compatible model
    "messages": [
        {"role": "system", "content": "You are a helpful assistant that outputs JSON."},
        {"role": "user", "content": "Return a JSON object with three fields: name, age, and favorite_color"}
    ],
    "response_format": {"type": "json_object"}  # This enables JSON mode
}

# Make the request
response = requests.post(url, headers=headers, data=json.dumps(data), verify=False)

# Parse the response
if response.status_code == 200:
    response_data = response.json()
    json_content = response_data["choices"][0]["message"]["content"]
    parsed_json = json.loads(json_content)
    print(parsed_json)
else:
    print(f"Error: {response.status_code}")
    print(response.text)