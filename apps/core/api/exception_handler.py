from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler as drf_exception_handler

from .exceptions import ApiError


def error_response_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, ApiError):
        body = _shape(exc.code, str(exc.detail), exc.fields)
        if exc.retry_after is not None:
            body["retry_after"] = exc.retry_after
            response["Retry-After"] = str(exc.retry_after)
        response.data = body
        return response

    code, message, fields = _shape_default(response.data, isinstance(exc, ValidationError))
    response.data = _shape(code, message, fields)
    return response


def _shape(code: str, message: str, fields: dict) -> dict:
    return {"error": {"code": code, "message": message, "fields": fields}}


def _shape_default(detail, is_validation: bool) -> tuple[str, str, dict]:
    """Only a real ValidationError carries field errors. Other errors may send
    extra keys next to `detail` (the JWT library adds `code` and `messages`);
    those give the code and message, never fields."""
    if is_validation and isinstance(detail, dict):
        fields = {name: _as_list(value) for name, value in detail.items()}
        return "validation_error", "Validation failed.", fields
    if isinstance(detail, dict) and "detail" in detail:
        code = str(detail.get("code") or _code_of(detail["detail"]))
        return code, str(detail["detail"]), {}
    if isinstance(detail, list):
        first = detail[0] if detail else "error"
        return _code_of(first), " ".join(str(item) for item in detail), {}
    return _code_of(detail), str(detail), {}


def _as_list(value) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else [str(value)]


def _code_of(value) -> str:
    return getattr(value, "code", None) or "error"
