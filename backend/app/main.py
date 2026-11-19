import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.errors import AppError, app_error_handler, http_error_handler, unhandled_error_handler, validation_error_handler
from app.routers import auth, friends, users

logging.basicConfig(level=logging.INFO)

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(title="Photo Globe API", version="0.1.0", openapi_url=f"{API_PREFIX}/openapi.json", docs_url=f"{API_PREFIX}/docs")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    @app.middleware("http")
    async def reject_nul_in_url(request, call_next):
        raw = request.scope.get("raw_path", b"") + b"?" + request.scope.get("query_string", b"")
        if b"%00" in raw or b"\x00" in raw or "\x00" in request.url.path:
            return JSONResponse({"code": "VALIDATION_ERROR", "message": "허용되지 않는 문자가 포함되어 있습니다."}, status_code=422)
        return await call_next(request)

    for r in (auth.router, users.router, friends.router):
        app.include_router(r, prefix=API_PREFIX)

    @app.get(f"{API_PREFIX}/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
