from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, field_errors: dict[str, str] | None = None, extra: dict | None = None):
        self.status, self.code, self.message, self.field_errors = status, code, message, field_errors
        self.extra = extra or {}  # 오류 응답에 덧붙일 값 (예: 중복 장소 정보)


def _eul_reul(word: str) -> str:
    """마지막 글자 받침이 있으면 '을', 없으면 '를'."""
    ch = word[-1] if word else "가"
    if "가" <= ch <= "힣":
        return "을" if (ord(ch) - 0xAC00) % 28 else "를"
    return "을(를)"


def not_found(what: str = "리소스") -> AppError:
    return AppError(404, "NOT_FOUND", f"{what}{_eul_reul(what)} 찾을 수 없습니다.")


def _body(code: str, message: str, field_errors: dict | None = None, extra: dict | None = None) -> dict:
    body: dict = {"code": code, "message": message}
    if field_errors:
        body["field_errors"] = field_errors
    if extra:
        body.update(extra)
    return body


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(_body(exc.code, exc.message, exc.field_errors, exc.extra), status_code=exc.status)


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields: dict[str, str] = {}
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path", "form")]
        fields[".".join(loc) or "_"] = err.get("msg", "invalid")
    return JSONResponse(_body("VALIDATION_ERROR", "입력값을 확인해 주세요.", fields), status_code=422)


async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    codes = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
    return JSONResponse(_body(codes.get(exc.status_code, "HTTP_ERROR"), str(exc.detail)), status_code=exc.status_code)


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    import logging

    logging.getLogger("app").exception("unhandled error: %s", type(exc).__name__)
    return JSONResponse(_body("INTERNAL_ERROR", "일시적인 오류가 발생했습니다."), status_code=500)
