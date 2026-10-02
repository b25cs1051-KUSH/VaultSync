import json
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8080")
PASSWORD = "correct horse"


def request(method, path, body=None, token=None, key=None, raw=None):
    data = raw if raw is not None else (
        json.dumps(body, separators=(",", ":")).encode() if body is not None else None
    )
    headers = {}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if key is not None:
        headers["Idempotency-Key"] = key
    call = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        response = urllib.request.urlopen(call, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    try:
        payload = response.read()
        return response.status, json.loads(payload) if payload else None
    finally:
        response.close()


def main():
    fixture = {
        "currency": "EUR",
        "minor_units": 2,
        "users": [
            {
                "id": "u_ada",
                "email": "ada@example.com",
                "password": PASSWORD,
                "display_name": "Ada",
                "handle": "ada",
                "balance": 10000,
            },
            {
                "id": "u_bob",
                "email": "bob@example.com",
                "password": PASSWORD,
                "display_name": "Bob",
                "handle": "bob",
                "balance": 2500,
            },
        ],
    }
    assert request("POST", "/_test/reset", fixture)[0] == 204
    ada = request("POST", "/auth/login", {"email": "ada@example.com", "password": PASSWORD})[1]["token"]
    bob = request("POST", "/auth/login", {"email": "bob@example.com", "password": PASSWORD})[1]["token"]

    def send(index):
        raw = (
            b'{"to_handle":"bob","amount":10}'
            if index % 2
            else b'{ "amount": 10.0, "to_handle": "bob" }'
        )
        return request("POST", "/payments", token=ada, key="burst", raw=raw)

    with ThreadPoolExecutor(max_workers=50) as pool:
        responses = list(pool.map(send, range(50)))
    assert sum(status == 201 for status, _ in responses) == 1, responses
    assert sum(status == 200 for status, _ in responses) == 49, responses
    assert len({json.dumps(body, sort_keys=True) for _, body in responses}) == 1
    assert request("GET", "/me", token=ada)[1]["balance"] == 9990
    assert request("GET", "/me", token=bob)[1]["balance"] == 2510

    status, body = request(
        "POST", "/payments", {"to_handle": 7, "amount": True}, ada, "burst"
    )
    assert (status, body["error"]["code"]) == (409, "idempotency_key_reuse")
    assert request(
        "POST", "/payments", {"to_handle": "missing", "amount": 1}, ada, "retry"
    )[0] == 404
    assert request(
        "POST", "/payments", {"to_handle": "bob", "amount": 1}, ada, "retry"
    )[0] == 201
    assert request(
        "POST", "/payments", {"to_handle": "ada", "amount": 1}, bob, "burst"
    )[0] == 201
    assert request("POST", "/payments", {"to_handle": "bob", "amount": 1}, ada)[0] == 400
    assert request(
        "POST", "/payments", {"to_handle": "bob", "amount": 1}, ada, "x" * 256
    )[0] == 422
    print("HTTP_IDEMPOTENCY_OK one_201=1 replays=49 balances=9990,2510")


if __name__ == "__main__":
    main()
