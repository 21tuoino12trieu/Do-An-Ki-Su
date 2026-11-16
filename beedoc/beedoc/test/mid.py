import os
from datetime import datetime
from markitdown import MarkItDown
from openai import OpenAI

file_path = "assets/7439.QD-HS.22.pdf"

# --- LLM client (LiteLLM gateway) ---
client = OpenAI(
    api_key="REPLACE_WITH_LOCAL_SECRET",
    base_url="https://llm-gateway-dev.mbbank.com.vn/v1"
)

md = MarkItDown(
    enable_plugins=True,
    llm_client=client,
    llm_model="gemini-2.5-flash"
)

# --- Convert ---
result = md.convert(file_path)

# --- Build output path ---
filename = os.path.basename(file_path)
name_wo_ext = os.path.splitext(filename)[0]

output_dir = os.path.join("assets", name_wo_ext)
os.makedirs(output_dir, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_path = os.path.join(output_dir, f"{timestamp}.txt")

# --- Write file ---
with open(output_path, "w", encoding="utf-8") as f:
    f.write(result.text_content)

print(f"Saved to: {output_path}")