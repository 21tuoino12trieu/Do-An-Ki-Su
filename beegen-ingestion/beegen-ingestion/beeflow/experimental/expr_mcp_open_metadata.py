import requests
import json

url = "https://ai-platform-open-metadata.tanzu-dev.mbbank.com.vn/mcp"

payload = json.dumps({
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": {}
})
headers = {
  'Content-Type': 'application/json',
  'Accept': 'application/json, text/event-stream',
  'Authorization': 'Bearer REPLACE_WITH_LOCAL_SECRET'
}

response = requests.request("POST", url, headers=headers, data=payload, verify=False)

print(response.text)
