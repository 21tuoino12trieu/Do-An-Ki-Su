from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()


@router.get("/actuator/health")
def health_check():
    return {"status": "UP", "version": "1.0.0"}


@router.get("/actuator/prometheus", response_class=PlainTextResponse)
def prometheus_metrics():
    return "# beegen-portal-api metrics\n"
