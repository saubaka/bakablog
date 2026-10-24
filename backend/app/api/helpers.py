"""Small helpers shared by the API modules."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from flask import Response, request
from pydantic import BaseModel

from app.errors import ApiError


def body[T: BaseModel](model: type[T]) -> T:
    """Validated JSON request body. Only application/json is accepted for these endpoints (a cross-site <form> cannot send it)."""
    data = request.get_json(silent=True)
    if data is None:
        raise ApiError(400, "bad_json", "请求内容必须是 JSON（Content-Type: application/json）。")
    return model.model_validate(data)


def query[T: BaseModel](model: type[T]) -> T:
    return model.model_validate(request.args.to_dict())


def page_info(total: int, page: int, per: int) -> dict[str, int]:
    return {"total": total, "page": page, "per": per, "pages": max(1, -(-total // per)) if per else 1}


def dumps(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")


def etag_json(data: Any, *, status: int = 200, cache: str = "no-cache") -> Response:
    """Public GET answers: a weak ETag over the body, 304 when the browser already has it."""
    payload = dumps(data)
    tag = hashlib.blake2b(payload, digest_size=10).hexdigest()
    headers = {"ETag": f'W/"{tag}"', "Cache-Control": cache}
    if status == 200 and request.if_none_match.contains_weak(tag):
        return Response(status=304, headers=headers)
    response = Response(payload, status=status, mimetype="application/json")
    response.headers.update(headers)
    return response
