import os
from openai import AzureOpenAI
import httpx

endpoint = "https://context-understading-ag-resource.cognitiveservices.azure.com/"
model_name = "gpt-4.1"
deployment = "gpt-4.1"

subscription_key = "REPLACE_WITH_LOCAL_SECRET"
api_version = "2024-12-01-preview"


http_client = httpx.Client(
    timeout=30.0,
    verify=False
)


client = AzureOpenAI(
    api_version=api_version,
    azure_endpoint=endpoint,
    api_key=subscription_key,
    http_client=http_client
)

response = client.chat.completions.create(
    messages=[
        {
            "role": "system",
            "content": "You are a helpful assistant.",
        },
        {
            "role": "user",
            "content": "cuộc sống có giống cuộc đời không em ?",
        }
    ],
    max_completion_tokens=13107,
    temperature=1.0,
    top_p=1.0,
    frequency_penalty=0.0,
    presence_penalty=0.0,
    model=deployment
)

print(response.choices[0].message.content)