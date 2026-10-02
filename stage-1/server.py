import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


JSON_TYPE = "application/json; charset=utf-8"


class RequestError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


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

    def do_GET(self) -> None:
        if self._path() == "/health":
            self._send_json(200, {"status": "ok"})
            return
        self._send_error(404, "not_found", "No such resource")

    def do_POST(self) -> None:
        try:
            if self._path() == "/_test/reset":
                self._read_json_object()
                self._send_error(422, "validation_failed", "Reset is not configured")
                return
            self._send_error(404, "not_found", "No such resource")
        except RequestError as exc:
            self._send_error(exc.status, exc.code, exc.message)


def main() -> None:
    raw_port = os.environ.get("PORT", "8080")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise SystemExit("PORT must be an integer") from exc
    server = ThreadingHTTPServer(("0.0.0.0", port), PocketfulHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
