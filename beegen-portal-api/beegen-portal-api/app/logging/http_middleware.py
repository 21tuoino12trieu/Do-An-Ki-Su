import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.logging.loggers import HTTP_LOGGER


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, skip_paths: list[str] = None):
        super().__init__(app)
        self.skip_paths = skip_paths or ["/actuator/health", "/actuator/prometheus"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.skip_paths:
            return await call_next(request)

        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        method = request.method
        url = str(request.url)
        path = request.url.path

        HTTP_LOGGER.log_request(
            request_id=request_id,
            method=method,
            url=url,
            path=path,
        )

        start_time = time.time()

        try:
            response = await call_next(request)

            duration_ms = (time.time() - start_time) * 1000
            response_content = ""
            response_msg = ""

            HTTP_LOGGER.log_response(
                request_id=request_id,
                method=method,
                url=url,
                path=path,
                responsecode=response.status_code,
                duration_ms=duration_ms,
                response_msg=response_msg,
                response_content=response_content,
            )

            return response
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            HTTP_LOGGER.log_error(
                request_id=request_id,
                method=method,
                url=url,
                path=path,
                responsecode=500,
                error_msg=str(e)[:300],
                duration_ms=duration_ms,
            )
            raise
