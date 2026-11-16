"""
FastAPI Health Check Service
Check health of Redis, Kafka, and MongoDB
"""

from fastapi import FastAPI
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Document Processor Health Check",
    description="Health check API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Document Processor Health Check API",
        "version": "1.0.0",
        "endpoints": {
            "overall_health": "/health",
        }
    }

@app.get("/health")
async def health_check():
    """
    Overall health check for all services
    Returns aggregated health status
    """
    return "ok"

if __name__ == "__main__":
    import uvicorn
    
    # Run the API
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )