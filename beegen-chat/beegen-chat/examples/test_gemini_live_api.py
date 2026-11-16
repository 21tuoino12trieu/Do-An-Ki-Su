import json
from google import genai
from google.genai.types import (
    Content,
    LiveConnectConfig,
    Modality,
    Part,
)

# Your service account configuration
service_account_info = {
    "type": "service_account",
    "project_id": "mb-data-science-production",
    "private_key_id": "53f83b4f9fbbaa341a48cdd7eb778969410c4f36",
    "private_key": """REPLACE_WITH_LOCAL_SECRET""",
    "client_email": "vertex-ai-access@mb-data-science-production.iam.gserviceaccount.com",
    "client_id": "103724194458338450863",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/vertex-ai-access%40mb-data-science-production.iam.gserviceaccount.com",
    "universe_domain": "googleapis.com"
}

# Extract project info from service account
GOOGLE_CLOUD_PROJECT = service_account_info["project_id"]
GOOGLE_CLOUD_LOCATION = "us-central1"  # You may need to adjust this to your preferred region

async def main():
    # Create client with service account credentials
    client = genai.Client(
        vertexai=True,
        project=GOOGLE_CLOUD_PROJECT,
        location=GOOGLE_CLOUD_LOCATION,
        # Pass service account info for authentication
        credentials_info=service_account_info
    )
    
    MODEL_ID = "gemini-live-2.5-flash"

    async with client.aio.live.connect(
        model=MODEL_ID,
        config=LiveConnectConfig(response_modalities=[Modality.TEXT]),
    ) as session:
        text_input = "Hello? Gemini, are you there?"
        print("> ", text_input, "\n")
        await session.send_client_content(
            turns=Content(role="user", parts=[Part(text=text_input)])
        )

        response = []

        async for message in session.receive():
            if message.text:
                response.append(message.text)

        print("".join(response))

# Run the async function
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())