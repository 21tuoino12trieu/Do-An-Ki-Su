import tiktoken
import openai
import os

openai.api_type = "azure"
openai.api_version = "2024-02-15-preview"
openai.base_url = "https://10.1.13.168:8443/mbdevai"
openai.api_key = ""