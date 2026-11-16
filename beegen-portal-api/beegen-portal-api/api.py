import uvicorn
from dotenv import load_dotenv

load_dotenv()

from app.app import app

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", reload=False)
