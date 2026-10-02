import json
import hashlib
import hmac
import math
import os
import re
import secrets
import threading
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


JSON_TYPE = "application/json; charset=utf-8"
MAX_SAFE_INTEGER = 2**53
HANDLE_RE = re.compile(r"^[a-z0-9_]{1,20}$")
REQUEST_STATUSES = {"pending", "paid", "declined", "cancelled"}


class RequestError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def validation_error(message: str) -> RequestError:
    return RequestError(422, "validation_failed", message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_string(value, field: str, *, allow_empty: bool = True, max_length=None) -> str:
    if not isinstance(value, str):
        raise validation_error(f"{field} must be a string")
    if not allow_empty and not value:
        raise validation_error(f"{field} must not be empty")
    if max_length is not None and len(value) > max_length:
        raise validation_error(f"{field} is too long")
    return value


def require_integral(value, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise validation_error(f"{field} must be an integer")
    if isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()):
        raise validation_error(f"{field} must be an integer")
    result = int(value)
    if result < minimum or result > maximum:
        raise validation_error(f"{field} is out of range")
    return result


def password_hash(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=4096, r=8, p=1, dklen=32
    )
    return f"scrypt$4096$8$1${salt.hex()}${digest.hex()}"


def password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, expected_hex = encoded.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(expected_hex)),
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


def _valid_email(email: str) -> bool:
    local, separator, domain = email.partition("@")
    return bool(local and separator and domain and "@" not in domain)


def derive_handle(email: str) -> str:
    local = email.partition("@")[0].lower()
    return re.sub(r"[^a-z0-9_]", "_", local)[:20]


def required_body_string(body: dict, field: str) -> str:
    if field not in body:
        raise validation_error(f"Missing field: {field}")
    value = body[field]
    if not isinstance(value, str):
        raise RequestError(400, "malformed_request", f"{field} must be a string")
    return value


def _require_id(value, field: str) -> str:
    return require_string(value, field, allow_empty=False, max_length=64)


def build_reset_state(fixture: dict) -> dict:
    try:
        currency = require_string(fixture["currency"], "currency", allow_empty=False)
        minor_units = require_integral(fixture["minor_units"], "minor_units", 0, 3)
        users_value = fixture["users"]
    except KeyError as exc:
        raise validation_error(f"Missing field: {exc.args[0]}") from exc
    if minor_units not in {0, 2, 3}:
        raise validation_error("minor_units must be 0, 2 or 3")
    if not isinstance(users_value, list):
        raise validation_error("users must be an array")
    payments_value = fixture.get("payments", [])
    requests_value = fixture.get("requests", [])
    operators_value = fixture.get("settlement_operator_ids", [])
    if not isinstance(payments_value, list):
        raise validation_error("payments must be an array")
    if not isinstance(requests_value, list):
        raise validation_error("requests must be an array")
    if not isinstance(operators_value, list):
        raise validation_error("settlement_operator_ids must be an array")

    users = {}
    user_id_by_email = {}
    user_id_by_handle = {}
    total_seeded = 0
    for item in users_value:
        if not isinstance(item, dict):
            raise validation_error("Each user must be an object")
        try:
            user_id = _require_id(item["id"], "user.id")
            email = require_string(item["email"], "user.email", allow_empty=False)
            password = require_string(item["password"], "user.password")
            display_name = require_string(item["display_name"], "user.display_name")
            handle = require_string(item["handle"], "user.handle", allow_empty=False)
            balance = require_integral(item["balance"], "user.balance", 0, MAX_SAFE_INTEGER)
        except KeyError as exc:
            raise validation_error(f"Missing user field: {exc.args[0]}") from exc
        normalized_email = email.lower()
        if not _valid_email(email):
            raise validation_error("user.email is invalid")
        if not HANDLE_RE.fullmatch(handle):
            raise validation_error("user.handle is invalid")
        if user_id in users or normalized_email in user_id_by_email or handle in user_id_by_handle:
            raise validation_error("User ids, emails and handles must be unique")
        total_seeded += balance
        if total_seeded > MAX_SAFE_INTEGER:
            raise validation_error("Seeded balance total is out of range")
        users[user_id] = {
            "id": user_id,
            "email": email,
            "email_normalized": normalized_email,
            "password_hash": password_hash(password),
            "display_name": display_name,
            "handle": handle,
            "balance": balance,
        }
        user_id_by_email[normalized_email] = user_id
        user_id_by_handle[handle] = user_id

    created_at = utc_now()
    payments = {}
    payment_order = []
    for item in payments_value:
        if not isinstance(item, dict):
            raise validation_error("Each payment must be an object")
        try:
            payment_id = _require_id(item["id"], "payment.id")
            from_user_id = _require_id(item["from_user_id"], "payment.from_user_id")
            to_user_id = _require_id(item["to_user_id"], "payment.to_user_id")
            amount = require_integral(item["amount"], "payment.amount", 1, 1_000_000_000)
        except KeyError as exc:
            raise validation_error(f"Missing payment field: {exc.args[0]}") from exc
        note = require_string(item.get("note", ""), "payment.note", max_length=200)
        visibility = item.get("visibility", "public")
        if visibility not in {"public", "private"}:
            raise validation_error("payment.visibility is invalid")
        if payment_id in payments:
            raise validation_error("Payment ids must be unique")
        if from_user_id not in users or to_user_id not in users or from_user_id == to_user_id:
            raise validation_error("Payment users are invalid")
        payments[payment_id] = {
            "payment_id": payment_id,
            "from_user_id": from_user_id,
            "from_handle": users[from_user_id]["handle"],
            "to_user_id": to_user_id,
            "to_handle": users[to_user_id]["handle"],
            "amount": amount,
            "currency": currency,
            "note": note,
            "visibility": visibility,
            "request_id": item.get("request_id"),
            "settlement_id": item.get("settlement_id"),
            "created_at": created_at,
        }
        payment_order.append(payment_id)

    requests = {}
    request_order = []
    for item in requests_value:
        if not isinstance(item, dict):
            raise validation_error("Each request must be an object")
        try:
            request_id = _require_id(item["id"], "request.id")
            requester_id = _require_id(item["requester_id"], "request.requester_id")
            payer_id = _require_id(item["payer_id"], "request.payer_id")
            amount = require_integral(item["amount"], "request.amount", 1, 1_000_000_000)
        except KeyError as exc:
            raise validation_error(f"Missing request field: {exc.args[0]}") from exc
        note = require_string(item.get("note", ""), "request.note", max_length=200)
        status = item.get("status", "pending")
        if status not in REQUEST_STATUSES:
            raise validation_error("request.status is invalid")
        if request_id in requests:
            raise validation_error("Request ids must be unique")
        if requester_id not in users or payer_id not in users or requester_id == payer_id:
            raise validation_error("Request users are invalid")
        payment_id = item.get("payment_id")
        if payment_id is not None and not isinstance(payment_id, str):
            raise validation_error("request.payment_id is invalid")
        requests[request_id] = {
            "request_id": request_id,
            "requester_id": requester_id,
            "requester_handle": users[requester_id]["handle"],
            "payer_id": payer_id,
            "payer_handle": users[payer_id]["handle"],
            "amount": amount,
            "currency": currency,
            "note": note,
            "status": status,
            "payment_id": payment_id,
            "created_at": created_at,
        }
        request_order.append(request_id)

    operators = []
    for operator_id in operators_value:
        operator_id = _require_id(operator_id, "settlement_operator_id")
        if operator_id not in users or operator_id in operators:
            raise validation_error("settlement_operator_ids is invalid")
        operators.append(operator_id)

    return {
        "currency": currency,
        "minor_units": minor_units,
        "total_seeded": total_seeded,
        "users": users,
        "user_id_by_email": user_id_by_email,
        "user_id_by_handle": user_id_by_handle,
        "payments": payments,
        "payment_order": payment_order,
        "requests": requests,
        "request_order": request_order,
        "settlement_operator_ids": operators,
        "tokens": {},
        "idempotency": {},
    }


class StateStore:
    def __init__(self):
        self.lock = threading.RLock()
        self._state = build_reset_state({"currency": "EUR", "minor_units": 2, "users": []})

    def replace_from_fixture(self, fixture: dict) -> None:
        candidate = build_reset_state(fixture)
        with self.lock:
            self._state = candidate

    def snapshot(self) -> dict:
        with self.lock:
            return deepcopy(self._state)

    def signup(self, email: str, password: str, display_name: str) -> dict:
        normalized_email = email.lower()
        handle = derive_handle(email)
        encoded_password = password_hash(password)
        with self.lock:
            state = self._state
            if normalized_email in state["user_id_by_email"]:
                raise RequestError(409, "email_taken", "Email is already registered")
            if handle in state["user_id_by_handle"]:
                raise RequestError(409, "handle_taken", "Derived handle is already taken")
            while True:
                user_id = "u_" + secrets.token_urlsafe(18)
                if user_id not in state["users"]:
                    break
            user = {
                "id": user_id,
                "email": email,
                "email_normalized": normalized_email,
                "password_hash": encoded_password,
                "display_name": display_name,
                "handle": handle,
                "balance": 0,
            }
            state["users"][user_id] = user
            state["user_id_by_email"][normalized_email] = user_id
            state["user_id_by_handle"][handle] = user_id
            token = self._new_token(state)
            state["tokens"][token] = user_id
            return {"user_id": user_id, "display_name": display_name, "token": token}

    def login(self, email: str, password: str) -> dict:
        normalized_email = email.lower()
        with self.lock:
            state = self._state
            user_id = state["user_id_by_email"].get(normalized_email)
            user = state["users"].get(user_id) if user_id is not None else None
            encoded_password = user["password_hash"] if user is not None else None
        if encoded_password is None or not password_matches(password, encoded_password):
            raise RequestError(401, "unauthenticated", "Invalid email or password")
        with self.lock:
            state = self._state
            current = state["users"].get(user_id)
            if current is None or current["password_hash"] != encoded_password:
                raise RequestError(401, "unauthenticated", "Invalid email or password")
            token = self._new_token(state)
            state["tokens"][token] = user_id
            return {
                "user_id": user_id,
                "display_name": current["display_name"],
                "token": token,
            }

    def authenticate(self, token: str) -> dict:
        with self.lock:
            state = self._state
            user_id = state["tokens"].get(token)
            user = state["users"].get(user_id) if user_id is not None else None
            if user is None:
                raise RequestError(401, "unauthenticated", "Invalid bearer token")
            return {
                "user_id": user_id,
                "display_name": user["display_name"],
                "handle": user["handle"],
                "balance": user["balance"],
                "currency": state["currency"],
                "minor_units": state["minor_units"],
            }

    @staticmethod
    def _new_token(state: dict) -> str:
        while True:
            token = secrets.token_urlsafe(32)
            if token not in state["tokens"]:
                return token


STORE = StateStore()


class PocketfulHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        return

    def _send_json(self, status: int, value) -> None:
        payload = json.dumps(
            value, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", JSON_TYPE)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_error(self, status: int, code: str, message: str) -> None:
        self._send_json(status, {"error": {"code": code, "message": message}})

    def _read_json_object(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise RequestError(400, "malformed_request", "Invalid content length") from exc
        if length < 0 or length > 16 * 1024 * 1024:
            raise RequestError(400, "malformed_request", "Invalid content length")
        try:
            raw = self.rfile.read(length)
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RequestError(400, "malformed_request", "Request body is not valid JSON") from exc
        if not isinstance(value, dict):
            raise RequestError(400, "malformed_request", "Request body must be a JSON object")
        return value

    def _path(self) -> str:
        return urlsplit(self.path).path

    def _authenticated_user(self) -> dict:
        authorization = self.headers.get("Authorization")
        if authorization is None:
            raise RequestError(401, "unauthenticated", "Bearer token is required")
        parts = authorization.split(" ")
        if len(parts) != 2 or parts[0] != "Bearer" or not parts[1]:
            raise RequestError(401, "unauthenticated", "Bearer token is malformed")
        return STORE.authenticate(parts[1])

    def _validate_auth_body(self, body: dict) -> tuple[str, str, str | None]:
        email = required_body_string(body, "email")
        password = required_body_string(body, "password")
        if not _valid_email(email):
            raise validation_error("email must have the form local@domain")
        if len(password) < 8:
            raise validation_error("password must be at least 8 characters")
        display_name = None
        if self._path() == "/auth/signup":
            display_name = required_body_string(body, "display_name")
        return email, password, display_name

    def do_GET(self) -> None:
        try:
            path = self._path()
            if path == "/health":
                self._send_json(200, {"status": "ok"})
                return
            if path == "/_test/export":
                self._send_error(404, "not_found", "No such resource")
                return
            user = self._authenticated_user()
            if path == "/me":
                self._send_json(200, user)
                return
            self._send_error(404, "not_found", "No such resource")
        except RequestError as exc:
            self._send_error(exc.status, exc.code, exc.message)

    def do_POST(self) -> None:
        try:
            path = self._path()
            if path == "/_test/reset":
                fixture = self._read_json_object()
                STORE.replace_from_fixture(fixture)
                self._send_empty(204)
                return
            if path in {"/auth/signup", "/auth/login"}:
                body = self._read_json_object()
                email, password, display_name = self._validate_auth_body(body)
                if path == "/auth/signup":
                    self._send_json(201, STORE.signup(email, password, display_name))
                else:
                    self._send_json(200, STORE.login(email, password))
                return
            if path == "/_test/import":
                self._send_error(404, "not_found", "No such resource")
                return
            self._authenticated_user()
            self._send_error(404, "not_found", "No such resource")
        except RequestError as exc:
            self._send_error(exc.status, exc.code, exc.message)


class PocketfulHTTPServer(ThreadingHTTPServer):
    # The default socketserver backlog is only five. Bursts at the documented
    # 50-request concurrency limit can otherwise be dropped before a worker
    # thread is created, especially while reset workers hash passwords.
    request_queue_size = 128
    daemon_threads = True


def main() -> None:
    raw_port = os.environ.get("PORT", "8080")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise SystemExit("PORT must be an integer") from exc
    server = PocketfulHTTPServer(("0.0.0.0", port), PocketfulHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
