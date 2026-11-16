from http import HTTPStatus
from typing import Any, Dict, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


SOA_SUCCESS = "200"
SOA_AUTH = "3001"
SOA_VALIDATION = "4001"
SOA_NOT_FOUND = "4041"
SOA_CONFLICT = "4091"
SOA_INTERNAL = "5000"
SOA_NOT_IMPLEMENTED = "5011"
AUTH_ERROR_DESC = "You do not have permission to access this data"
VALIDATION_ERROR_DESC = (
    "Request body/form-data does not match the schema or is missing required fields"
)


def success_response(data: Any = None, message: str = "Success") -> Dict[str, Any]:
    response = {
        "status": status.HTTP_200_OK,
        "error": "OK",
        "soaErrorCode": SOA_SUCCESS,
        "soaErrorDesc": message,
    }
    if data is not None:
        response["data"] = data
    return response


def error_body(
    status_code: int,
    error: str,
    soa_error_code: str,
    soa_error_desc: str,
    client_message_id: Optional[str] = None,
    data: Any = None,
) -> Dict[str, Any]:
    body = {
        "status": status_code,
        "error": error,
        "soaErrorCode": soa_error_code,
        "soaErrorDesc": soa_error_desc,
    }
    if client_message_id:
        body["clientMessageId"] = client_message_id
    if data is not None:
        body["data"] = data
    return body


def error_response(
    status_code: int,
    error: str,
    soa_error_code: str,
    soa_error_desc: str,
    client_message_id: Optional[str] = None,
    data: Any = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_body(
            status_code=status_code,
            error=error,
            soa_error_code=soa_error_code,
            soa_error_desc=soa_error_desc,
            client_message_id=client_message_id,
            data=data,
        ),
    )


def _client_message_id(request: Request) -> Optional[str]:
    return request.headers.get("clientMessageId") or request.headers.get("X-Request-ID")


def _desc(detail: Any, fallback: str) -> str:
    if isinstance(detail, str) and detail:
        return detail
    if isinstance(detail, dict) and detail.get("message"):
        return str(detail["message"])
    if detail:
        return str(detail)
    return fallback


def _map_http_exception(exc: StarletteHTTPException) -> Tuple[str, str, str]:
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        return (
            "Unauthorized",
            SOA_AUTH,
            _desc(exc.detail, "Authentication required"),
        )
    if exc.status_code == status.HTTP_403_FORBIDDEN:
        return ("Forbidden", SOA_AUTH, _desc(exc.detail, AUTH_ERROR_DESC))
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        return ("Not Found", SOA_NOT_FOUND, _desc(exc.detail, "Resource not found"))
    if exc.status_code == status.HTTP_409_CONFLICT:
        return ("Conflict", SOA_CONFLICT, _desc(exc.detail, "Resource state conflict"))
    if exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
        return (
            "Validation Error",
            SOA_VALIDATION,
            _desc(exc.detail, VALIDATION_ERROR_DESC),
        )
    if exc.status_code == status.HTTP_501_NOT_IMPLEMENTED:
        return (
            "Not Implemented",
            SOA_NOT_IMPLEMENTED,
            _desc(exc.detail, "Feature is not implemented"),
        )
    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        return (
            "Internal Server Error",
            SOA_INTERNAL,
            _desc(exc.detail, "Internal server error"),
        )

    try:
        phrase = HTTPStatus(exc.status_code).phrase
    except ValueError:
        phrase = "error"
    return (phrase, str(exc.status_code), _desc(exc.detail, phrase))


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    error, soa_error_code, soa_error_desc = _map_http_exception(exc)
    return error_response(
        status_code=exc.status_code,
        error=error,
        soa_error_code=soa_error_code,
        soa_error_desc=soa_error_desc,
        client_message_id=_client_message_id(request),
        data=exc.detail if isinstance(exc.detail, dict) else None,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error="Validation Error",
        soa_error_code=SOA_VALIDATION,
        soa_error_desc=VALIDATION_ERROR_DESC,
        client_message_id=_client_message_id(request),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error="Internal Server Error",
        soa_error_code=SOA_INTERNAL,
        soa_error_desc="Internal server error",
        client_message_id=_client_message_id(request),
    )


def register_exception_handlers(application: FastAPI) -> None:
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.add_exception_handler(HTTPException, http_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)
