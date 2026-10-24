"""One error shape for the whole API: {"error": {"code", "message", "fields"?}} with the right HTTP status."""
from __future__ import annotations

import logging

from flask import Flask, Response, jsonify, request
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)

_STATUS_CODES = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed", 409: "conflict",
    413: "too_large", 415: "unsupported_media_type", 422: "invalid", 429: "rate_limited", 500: "server_error",
}
_STATUS_MESSAGES = {
    400: "请求格式不对。", 401: "需要先登录。", 403: "没有权限做这件事。", 404: "没有找到。", 405: "这个地址不支持这种请求。",
    409: "和现有内容冲突。", 413: "上传的内容太大了。", 415: "不支持这种文件。", 422: "提交的内容有问题。",
    429: "操作太频繁了，请稍后再试。", 500: "服务器出错了，过一会儿再试试。",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str | None = None, message: str | None = None, *, fields: dict | None = None,
                 headers: dict | None = None, extra: dict | None = None):
        super().__init__(message or code or str(status))
        self.status = status
        self.code = code or _STATUS_CODES.get(status, "error")
        self.message = message or _STATUS_MESSAGES.get(status, "出错了。")
        self.fields = fields
        self.headers = headers or {}
        self.extra = extra or {}


def error_response(status: int, code: str | None = None, message: str | None = None, *, fields: dict | None = None,
                   headers: dict | None = None, extra: dict | None = None) -> Response:
    body: dict = {"code": code or _STATUS_CODES.get(status, "error"), "message": message or _STATUS_MESSAGES.get(status, "出错了。")}
    if fields:
        body["fields"] = fields
    if extra:
        body.update(extra)
    response = jsonify({"error": body})
    response.status_code = status
    for key, value in (headers or {}).items():
        response.headers[key] = value
    return response


def friendly_validation(exc: ValidationError) -> dict[str, str]:
    """pydantic errors -> {"field.path": "短句"} for the forms."""
    out: dict[str, str] = {}
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"] if p not in ("body", "query"))
        ctx = err.get("ctx") or {}
        kind = err["type"]
        if kind == "missing":
            msg = "必填"
        elif kind == "string_too_long":
            msg = f"最多 {ctx.get('max_length')} 个字符"
        elif kind == "string_too_short":
            msg = "不能为空" if ctx.get("min_length") == 1 else f"至少 {ctx.get('min_length')} 个字符"
        elif kind in ("int_parsing", "int_from_float", "float_parsing"):
            msg = "需要一个数字"
        elif kind == "bool_parsing":
            msg = "需要 true 或 false"
        elif kind == "extra_forbidden":
            msg = "不认识这个字段"
        elif kind == "literal_error":
            expected = ctx.get("expected", "")
            msg = f"只能是 {expected}".replace("'", "")
        elif kind in ("greater_than_equal", "greater_than"):
            msg = f"不能小于 {ctx.get('ge', ctx.get('gt'))}"
        elif kind in ("less_than_equal", "less_than"):
            msg = f"不能大于 {ctx.get('le', ctx.get('lt'))}"
        elif kind == "value_error":
            msg = str(ctx.get("error", err["msg"])).removeprefix("Value error, ")
        elif kind == "too_long":
            msg = f"最多 {ctx.get('max_length')} 项"
        elif kind in ("dict_type", "list_type", "model_type"):
            msg = "格式不对"
        else:
            msg = err["msg"].removeprefix("Value error, ")
        out.setdefault(loc or "_", msg)
    return out


def wants_json() -> bool:
    return request.path.startswith("/api/") or request.path in ("/api",)


def register(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError):
        return error_response(exc.status, exc.code, exc.message, fields=exc.fields, headers=exc.headers, extra=exc.extra)

    @app.errorhandler(ValidationError)
    def _validation(exc: ValidationError):
        return error_response(422, "invalid", "提交的内容有问题。", fields=friendly_validation(exc))

    @app.errorhandler(HTTPException)
    def _http(exc: HTTPException):
        status = exc.code or 500
        if wants_json() or status != 404:
            return error_response(status, headers={k: v for k, v in exc.get_headers() if k.lower() == "allow"})
        from app.seo.spa import not_found_page  # HTML routes: the Vue app draws the 404 page

        return not_found_page()

    @app.errorhandler(IntegrityError)
    def _integrity(exc: IntegrityError):
        log.warning("integrity error on %s %s: %s", request.method, request.path, str(exc.orig)[:200])
        return error_response(409, "conflict", "和现有内容冲突，可能刚刚被别处改过，请刷新后再试。")

    @app.errorhandler(OperationalError)
    def _operational(exc: OperationalError):
        if "locked" in str(exc.orig).lower() or "busy" in str(exc.orig).lower():
            log.warning("database busy on %s %s", request.method, request.path)
            return error_response(503, "busy", "服务器正忙，请稍后重试。", headers={"Retry-After": "1"})
        return _unexpected(exc)

    @app.errorhandler(Exception)
    def _unexpected(exc: Exception):
        log.exception("unhandled error on %s %s", request.method, request.path)
        if wants_json():
            return error_response(500)
        from app.seo.spa import server_error_page

        return server_error_page()
