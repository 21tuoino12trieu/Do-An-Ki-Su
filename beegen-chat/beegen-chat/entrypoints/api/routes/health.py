"""
Health check and monitoring endpoints.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any

from beegenerate.loggings import LOGGER

# Create router
router = APIRouter(tags=["health"], prefix="/api")

class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    version: str
    
class MetricsResponse(BaseModel):
    """System metrics response model."""
    status: str
    metrics: Dict[str, Any]

@router.get("/actuator/health", response_model=HealthResponse)
async def health_check():
    """
    Basic health check endpoint.
    
    Returns:
        HealthResponse: Health status information
    """
    LOGGER.debug("Health check requested")
    return HealthResponse(
        status="UP",
        version="1.0.0"
    )

@router.get("/actuator/prometheus", status_code=200)
async def prometheus_metrics():
    """
    Endpoint for Prometheus metrics.
    
    Returns:
        str: Prometheus-compatible metrics data
    """
    LOGGER.debug("Prometheus metrics requested")
    return "# HELP api_up Indicates if the API is up\napi_up 1"