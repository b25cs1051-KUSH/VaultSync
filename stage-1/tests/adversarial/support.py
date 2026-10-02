"""Black-box HTTP helpers shared by the adversarial tests."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Response:
    status: int
    body: Any
    headers: Any


def request(
    method: str,
    path: str,
    body: Any = None,
    *,
    token: str | None = None,
    key: str | None = None,
    raw_body: bytes | None = None,
    timeout: float = 5.0,
) -> Response:
    base_url = os.environ["BASE_URL"].rstrip("/")
    headers = {"Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if key is not None:
        headers["Idempotency-Key"] = key
    data = raw_body
    if body is not None:
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
    try:
        response = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    payload = response.read()
    parsed = None if not payload else json.loads(payload.decode("utf-8"))
    return Response(response.status, parsed, response.headers)

