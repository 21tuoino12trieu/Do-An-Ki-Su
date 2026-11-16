import requests
import json

url = "http://10.7.39.38:8000/v1/chat/completions_"

payload = json.dumps({
  "bot_id": "da498399-56c2-479f-80c6-b79e605dcd66",
  "topic": "default",
  "role": "L1",
  "messages": [
    {
      "role": "user",
      "content": "nhân viên MB làm ăn như cứt"
    }
  ]
})
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)
