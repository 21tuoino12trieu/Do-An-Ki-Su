# Beegen Memory

## 🚀 Getting Started

**Running the System**
```bash
#Message queue service
uvicorn "beememory.message_queue.api:app" --host "0.0.0.0" --port "8002"

#Agent memory service
uvicorn "beememory.entrypoint.api:app" --host "0.0.0.0" --port "8000"

#UI service
python -m beememory.UI.server.py --port 8001
```

## 💻 Usage Examples

Visit the site http://localhost:8001/
- Enter your user ID
- Chat with bot
- The extracted memory will appear in the right panel of the screen after every 2 chat turns