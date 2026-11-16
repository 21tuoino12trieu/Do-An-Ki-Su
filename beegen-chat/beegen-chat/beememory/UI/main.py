from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction
import requests
import httpx
from dotenv import load_dotenv
import os

# Load .env file
load_dotenv(".env.local", override=True)

# Replace with your FastAPI endpoint
FASTAPI_SERVER_URL = os.getenv('FASTAPI_SERVER_URL')
TELE_BOT_ID = os.getenv('TELE_BOT_ID')

async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Hello {update.effective_user.first_name}')

async def new_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = " ".join(context.args)  # Extract name argument from command
    response = requests.get(f"{FASTAPI_SERVER_URL}/new_user", params={"name": name})
    
    if response.status_code == 200:
        response_data = response.json()
        await update.message.reply_text(f"New user created: {response_data}")
    else:
        await update.message.reply_text(f"Error: {response.status_code} - {response.text}")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    response = requests.get(f"{FASTAPI_SERVER_URL}/list_users")
    
    if response.status_code == 200:
        response_data = response.json()
        await update.message.reply_text(f"New users: {response_data}")
    else:
        await update.message.reply_text(f"Error: {response.status_code} - {response.text}")
        
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = " ".join(context.args)  # Extract name argument from command
    response = requests.get(f"{FASTAPI_SERVER_URL}/clear")
    
    if response.status_code == 200:
        response_data = response.json()
        await update.message.reply_text(f"Succesfully clear history")
    else:
        await update.message.reply_text(f"Error: {response.status_code} - {response.text}")

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message_text = update.message.text
    tele_id = update.effective_user.id
    
    print(f"\n==> Telegram id: {tele_id}\nQuery: {message_text}")
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        async with client.stream("POST", f"{FASTAPI_SERVER_URL}/chat", 
                                 json={
                                     "query": message_text, 
                                     "telegram_id": str(tele_id)
                                     }) as response:
            async for line in response.aiter_text():
            # Iterate over the stream chunks using async for
                if line:
                    # Decode the line and remove the "data:" prefix
                    decoded_line = line.strip()
                    if decoded_line.startswith("data:"):
                        # Remove "data:" and send the rest as a reply
                        content = decoded_line[len("data:"):].strip()
                        await update.message.reply_text(content)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Call /chat for any message that isn't /new_user or /list_users
    message_text = update.message.text
    if message_text.startswith("/clear"):
        clear(update, context)
    elif not message_text.startswith(("/new_user", "/list_users")):
        await chat(update, context)

app = ApplicationBuilder().token(TELE_BOT_ID).build()

# Add command handlers for specific commands
app.add_handler(CommandHandler("hello", hello))
app.add_handler(CommandHandler("new_user", new_user))
app.add_handler(CommandHandler("list_users", list_users))
app.add_handler(CommandHandler("clear", clear))


# Add a handler for all other messages (non-commands)
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Start polling to listen for messages
app.run_polling()