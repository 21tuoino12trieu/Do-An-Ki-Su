"""
Main entry point for running the API server.
"""
from dotenv import load_dotenv

import uvicorn
import asyncio
from entrypoints.api.server import app

if __name__ == "__main__":
    load_dotenv()
    # Start the API server
    uvicorn.run(
        app=app,
        host="0.0.0.0", 
        port=8000,
        loop="asyncio"
    )