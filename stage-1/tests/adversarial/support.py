"""Black-box HTTP helpers shared by the adversarial tests."""

from __future__ import annotations

import json
import os
import random
import threading
import urllib.error
import urllib.request
import unittest
import uuid
from dataclasses import dataclass
from datetime import datetime
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
    extra_headers: dict[str, str] | None = None,
    timeout: float = 5.0,
) -> Response:
    base_url = os.environ["BASE_URL"].rstrip("/")
    headers = {"Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if key is not None:
        headers["Idempotency-Key"] = key
    if extra_headers:
        headers.update(extra_headers)
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


PASSWORD = "correct horse"
BASE_USERS = [
    {"id": "u_ada", "email": "ada@example.com", "password": PASSWORD,
     "display_name": "Ada", "handle": "ada", "balance": 10000},
    {"id": "u_bob", "email": "bob@example.com", "password": PASSWORD,
     "display_name": "Bob", "handle": "bob", "balance": 5000},
    {"id": "u_cy", "email": "cy@example.com", "password": PASSWORD,
     "display_name": "Cy", "handle": "cy", "balance": 2500},
    {"id": "u_dee", "email": "dee@example.com", "password": PASSWORD,
     "display_name": "Dee", "handle": "dee", "balance": 1000},
]


def fixture(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "currency": "EUR",
        "minor_units": 2,
        "users": [dict(user) for user in BASE_USERS],
        "payments": [],
        "requests": [],
        "settlement_operator_ids": ["u_ada"],
    }
    value.update(overrides)
    return value


def error_code(response: Response) -> str | None:
    if not isinstance(response.body, dict):
        return None
    error = response.body.get("error")
    return error.get("code") if isinstance(error, dict) else None


def assert_rfc3339_with_offset(test: unittest.TestCase, value: Any) -> None:
    test.assertIsInstance(value, str)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    test.assertIsNotNone(parsed.utcoffset(), value)


class ApiTestCase(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.seed = int(os.environ.get("ADVERSARIAL_SEED", "1"))
        self.random = random.Random(self.seed + sum(map(ord, self.id())))
        self.reset()
        self.tokens = {user["handle"]: self.login(user["email"], user["password"])
                       for user in BASE_USERS}

    def reset(self, value: dict[str, Any] | None = None) -> Response:
        response = request("POST", "/_test/reset", fixture() if value is None else value, timeout=10)
        self.assertEqual(204, response.status, response.body)
        self.assertIsNone(response.body)
        return response

    def login(self, email: str, password: str = PASSWORD) -> str:
        response = request("POST", "/auth/login", {"email": email, "password": password})
        self.assertEqual(200, response.status, response.body)
        self.assertIsInstance(response.body.get("token"), str)
        return response.body["token"]

    def key(self, prefix: str = "k") -> str:
        return f"{prefix}-{uuid.UUID(int=self.random.getrandbits(128))}"

    def assert_error(self, response: Response, status: int, code: str) -> None:
        self.assertEqual(status, response.status, response.body)
        self.assertEqual(code, error_code(response), response.body)
        self.assertIsInstance(response.body["error"].get("message"), str)

    def post(self, path: str, body: Any, handle: str = "ada", key: str | None = None,
             **kwargs: Any) -> Response:
        return request("POST", path, body, token=self.tokens[handle], key=key, **kwargs)

    def get(self, path: str, handle: str = "ada", **kwargs: Any) -> Response:
        return request("GET", path, token=self.tokens[handle], **kwargs)

    def balances(self) -> dict[str, int]:
        result = {}
        for handle in self.tokens:
            response = self.get("/me", handle)
            self.assertEqual(200, response.status, response.body)
            result[handle] = response.body["balance"]
        return result

    def concurrent(self, count: int, operation: Any) -> list[Response]:
        from concurrent.futures import ThreadPoolExecutor

        barrier = threading.Barrier(count)

        def invoke(index: int) -> Response:
            barrier.wait(timeout=5)
            return operation(index)

        with ThreadPoolExecutor(max_workers=count) as pool:
            return list(pool.map(invoke, range(count)))
