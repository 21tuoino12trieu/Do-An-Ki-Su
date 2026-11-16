from fastapi import FastAPI

from app.controller.health import router as health_router
from app.controller.router import router
from app.exception.portal import register_exception_handlers
from app.logging import RequestLoggingMiddleware


def get_application() -> FastAPI:
    application = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(router=router)
    application.add_middleware(RequestLoggingMiddleware)
    return application

app = get_application()
