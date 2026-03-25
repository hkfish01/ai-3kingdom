import json
from urllib import error, request

from ..config import settings
from ..errors import AppError


def post_json(url: str, payload: dict, token: str = "") -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {"raw": raw}
            return resp.status, body
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise AppError("INVALID_REQUEST", f"Central request failed: {exc.code} {detail}", status_code=502) from exc
    except error.URLError as exc:
        raise AppError("INVALID_REQUEST", f"Central request unreachable: {exc.reason}", status_code=502) from exc


def get_json(url: str, token: str = "") -> tuple[int, dict]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {"raw": raw}
            return resp.status, body
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise AppError("INVALID_REQUEST", f"Central request failed: {exc.code} {detail}", status_code=502) from exc
    except error.URLError as exc:
        raise AppError("INVALID_REQUEST", f"Central request unreachable: {exc.reason}", status_code=502) from exc
