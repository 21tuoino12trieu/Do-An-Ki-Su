"""
FastAPI middleware for HTTP request/response logging to Kafka.

This middleware automatically logs HTTP requests and responses in the
standard format required by the system.
"""
from __future__ import annotations
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from beegenerate.loggings.loggers import HTTP_LOGGER


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs HTTP requests and responses to Kafka.

    - Logs request when it arrives
    - Logs response when it's sent back
    - Includes timing information
    - Handles errors gracefully
    """

    def __init__(self, app: ASGIApp, skip_paths: list[str] = None):
        """
        Initialize the middleware.

        Args:
            app: The ASGI app
            skip_paths: List of paths to skip logging (e.g., health checks)
        """
        super().__init__(app)
        self.skip_paths = skip_paths or ["/actuator/health", "/actuator/prometheus"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request and log it.

        Args:
            request: The incoming request
            call_next: The next middleware/endpoint

        Returns:
            The response from the endpoint
        """
        # Skip logging for certain paths
        if request.url.path in self.skip_paths:
            return await call_next(request)

        # Generate a unique request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Get request details
        method = request.method
        url = str(request.url)
        path = request.url.path

        # Log the request
        HTTP_LOGGER.log_request(
            request_id=request_id,
            method=method,
            url=url,
            path=path
        )

        # Start timing
        start_time = time.time()

        try:
            # Process the request
            response = await call_next(request)

            # Calculate duration in milliseconds
            duration_ms = (time.time() - start_time) * 1000

            # Note: Do not read response body here as it breaks streaming
            response_content = ""
            response_msg = ""

            # Log the response
            HTTP_LOGGER.log_response(
                request_id=request_id,
                method=method,
                url=url,
                path=path,
                responsecode=response.status_code,
                duration_ms=duration_ms,
                response_msg=response_msg,
                response_content=response_content
            )

            return response

        except Exception as e:
            # Calculate duration even for errors
            duration_ms = (time.time() - start_time) * 1000

            # Log the error response with exception message
            HTTP_LOGGER.log_error(
                request_id=request_id,
                method=method,
                url=url,
                path=path,
                responsecode=500,
                error_msg=str(e)[:300],
                duration_ms=duration_ms
            )

            # Re-raise the exception
            raise
