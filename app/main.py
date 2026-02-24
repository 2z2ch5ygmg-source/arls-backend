from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from .bootstrap import ensure_seed_admin
from .config import settings
from .db import get_pool
from .routers import (
    attendance_router,
    attendance_requests_router,
    auth_router,
    companies_router,
    employees_router,
    integrations_router,
    leaves_router,
    master_reset_router,
    master_tenants_router,
    reports_router,
    schedules_router,
    sites_router,
    tenants_router,
    users_router,
)

app = FastAPI(title="RG ARLS API", version="0.1.0")
logger = logging.getLogger(__name__)

PRIMARY_FRONTEND_ORIGIN = "https://rgarlsfront50018.z12.web.core.windows.net"
ACCESS_CONTROL_ALLOW_METHODS = "GET, POST, PUT, DELETE, OPTIONS"
ACCESS_CONTROL_ALLOW_HEADERS = "Authorization, Content-Type, Idempotency-Key"

origins = settings.cors_origins
origin_regex = settings.cors_origin_regex
if not origin_regex:
    origin_regex = (
        r"^https://[a-zA-Z0-9-]+\\.z12\\.web\\.core\\.windows\\.net$"
        r"|^https://rg-arls-backend\\.azurewebsites\\.net$"
        r"|^https?://localhost(:\\d+)?$"
        r"|^https?://127\\.0\\.0\\.1(:\\d+)?$"
        r"|^(capacitor|ionic|app)://localhost$"
    )
if not origins:
    origins = [PRIMARY_FRONTEND_ORIGIN]
elif PRIMARY_FRONTEND_ORIGIN not in origins:
    origins = [*origins, PRIMARY_FRONTEND_ORIGIN]

_allowed_origins = set(origins)
try:
    _allowed_origin_pattern = re.compile(origin_regex) if origin_regex else None
except re.error:
    _allowed_origin_pattern = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)


def _is_api_path(path: str) -> bool:
    return path.startswith("/api/")


def _is_allowed_origin(origin: str) -> bool:
    if not origin:
        return False
    if origin in _allowed_origins:
        return True
    if _allowed_origin_pattern and _allowed_origin_pattern.match(origin):
        return True
    return False


def _apply_cors_headers(request: Request, response: Response) -> Response:
    origin = str(request.headers.get("origin") or "").strip()
    allow_origin = origin if _is_allowed_origin(origin) else PRIMARY_FRONTEND_ORIGIN
    response.headers["Access-Control-Allow-Origin"] = allow_origin
    response.headers["Access-Control-Allow-Methods"] = ACCESS_CONTROL_ALLOW_METHODS
    response.headers["Access-Control-Allow-Headers"] = ACCESS_CONTROL_ALLOW_HEADERS
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Vary"] = "Origin"
    return response


def _api_error_payload(status_code: int, detail: Any = None) -> dict[str, Any]:
    default_map: dict[int, tuple[str, str]] = {
        400: ("BAD_REQUEST", "입력값을 확인해주세요."),
        401: ("UNAUTHORIZED", "로그인이 필요합니다."),
        403: ("FORBIDDEN", "접근 권한이 없습니다."),
        404: ("NOT_FOUND", "요청한 리소스를 찾을 수 없습니다."),
        409: ("CONFLICT", "요청이 충돌했습니다."),
        422: ("VALIDATION_ERROR", "요청 형식이 올바르지 않습니다."),
        500: ("INTERNAL", "서버 오류입니다. 잠시 후 다시 시도해주세요."),
    }
    default_code, default_message = default_map.get(status_code, (f"HTTP_{status_code}", "요청 처리 중 오류가 발생했습니다."))

    code = default_code
    message = default_message
    detail_value = detail
    fields_value: dict[str, Any] | None = None

    if isinstance(detail, dict):
        detail_code = detail.get("error") or detail.get("code")
        detail_message = detail.get("message") or detail.get("detail")
        if detail_code:
            code = str(detail_code)
        if detail_message:
            message = str(detail_message)
        if isinstance(detail.get("fields"), dict):
            fields_value = detail.get("fields")
        if "errors" in detail:
            detail_value = detail.get("errors")
        elif "detail" in detail and detail.get("detail") not in (None, "", message):
            detail_value = detail.get("detail")
        else:
            detail_value = None
    elif isinstance(detail, str) and detail.strip():
        message = detail.strip()

    generic_map = {"forbidden", "not authenticated", "invalid token", "invalid token payload", "account not found"}
    if status_code == 403 and str(message).strip().lower() in generic_map:
        message = "접근 권한이 없습니다."
        code = "FORBIDDEN"
        detail_value = None
    if status_code == 401 and str(message).strip().lower() in generic_map:
        message = "로그인이 필요합니다."
        code = "UNAUTHORIZED"
        detail_value = None

    error_obj: dict[str, Any] = {"code": code, "message": message}
    if fields_value:
        error_obj["fields"] = fields_value
    if isinstance(detail_value, dict):
        nested_fields = detail_value.get("fields")
        if isinstance(nested_fields, dict):
            error_obj["fields"] = nested_fields
    if detail_value not in (None, "", message):
        error_obj["detail"] = detail_value

    return {"success": False, "data": None, "error": error_obj}


def _is_enveloped_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and "success" in payload
        and "data" in payload
        and "error" in payload
    )


async def _response_body_bytes(response: Response) -> bytes:
    body = getattr(response, "body", None)
    if body is not None:
        return bytes(body)
    body_chunks: list[bytes] = []
    if getattr(response, "body_iterator", None) is not None:
        async for chunk in response.body_iterator:
            body_chunks.append(chunk)
    return b"".join(body_chunks)


async def _wrap_json_response(response: Response) -> Response:
    content_type = str(response.headers.get("content-type") or "").lower()
    if "application/json" not in content_type:
        return response

    body = await _response_body_bytes(response)
    if not body:
        return response

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return Response(
            content=body,
            status_code=response.status_code,
            headers={k: v for k, v in response.headers.items() if k.lower() != "content-length"},
            media_type=response.media_type,
            background=response.background,
        )

    if _is_enveloped_payload(payload):
        return JSONResponse(
            content=payload,
            status_code=response.status_code,
            headers={k: v for k, v in response.headers.items() if k.lower() != "content-length"},
            background=response.background,
        )

    if response.status_code >= 400:
        wrapped = _api_error_payload(response.status_code, payload.get("detail") if isinstance(payload, dict) else payload)
    else:
        wrapped = {"success": True, "data": payload, "error": None}
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key not in wrapped:
                    wrapped[key] = value

    return JSONResponse(
        content=wrapped,
        status_code=response.status_code,
        headers={k: v for k, v in response.headers.items() if k.lower() != "content-length"},
        background=response.background,
    )


@app.middleware("http")
async def api_response_middleware(request: Request, call_next):
    if _is_api_path(request.url.path) and request.method == "OPTIONS":
        return _apply_cors_headers(request, Response(status_code=200))

    response = await call_next(request)
    if not _is_api_path(request.url.path):
        return response

    response = await _wrap_json_response(response)
    return _apply_cors_headers(request, response)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if _is_api_path(request.url.path):
        response = JSONResponse(
            status_code=exc.status_code,
            content=_api_error_payload(exc.status_code, exc.detail),
            headers=exc.headers,
        )
        return _apply_cors_headers(request, response)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    if _is_api_path(request.url.path):
        is_sites_api = request.url.path.startswith("/api/v1/sites")
        status_code = 400 if is_sites_api else 422
        error_code = "INVALID_INPUT" if is_sites_api else "VALIDATION_ERROR"
        message = "입력값을 확인해주세요." if is_sites_api else "요청 형식이 올바르지 않습니다."
        response = JSONResponse(
            status_code=status_code,
            content=_api_error_payload(status_code, {"error": error_code, "message": message, "errors": exc.errors()}),
        )
        return _apply_cors_headers(request, response)
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled error", exc_info=exc)
    if _is_api_path(request.url.path):
        response = JSONResponse(
            status_code=500,
            content=_api_error_payload(500, {"error": "INTERNAL", "message": "서버 오류입니다. 잠시 후 다시 시도해주세요."}),
        )
        return _apply_cors_headers(request, response)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})

app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(companies_router, prefix="/api/v1")
app.include_router(sites_router, prefix="/api/v1")
app.include_router(employees_router, prefix="/api/v1")
app.include_router(attendance_router, prefix="/api/v1")
app.include_router(attendance_requests_router, prefix="/api/v1")
app.include_router(leaves_router, prefix="/api/v1")
app.include_router(schedules_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(master_tenants_router, prefix="/api/v1")
app.include_router(master_reset_router, prefix="/api/v1")
app.include_router(integrations_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "app": settings.app_name}


@app.get("/")
def root() -> dict:
    return {"message": "RG ARLS API"}


@app.on_event("startup")
def startup() -> None:
    get_pool()
    ensure_seed_admin()
