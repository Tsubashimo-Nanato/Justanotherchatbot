from __future__ import annotations

import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class AuthProxyHandler(BaseHTTPRequestHandler):
    target: str = "http://127.0.0.1:8765"
    auth_header: str = ""

    server_version = "LocalQQAgentRemoteDebug/1.0"

    def do_GET(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def do_PUT(self) -> None:
        self._proxy()

    def do_PATCH(self) -> None:
        self._proxy()

    def do_DELETE(self) -> None:
        self._proxy()

    def do_OPTIONS(self) -> None:
        self._proxy()

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))

    def _authorized(self) -> bool:
        return self.headers.get("Authorization", "") == self.auth_header

    def _send_auth_required(self) -> None:
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Local QQ Agent Debug"')
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "authentication_required"}).encode("utf-8"))

    def _proxy(self) -> None:
        if not self._authorized():
            self._send_auth_required()
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else None
        target_url = urljoin(self.target.rstrip("/") + "/", self.path.lstrip("/"))
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
        }
        request = Request(target_url, data=body, headers=headers, method=self.command)

        try:
            with urlopen(request, timeout=120, context=ssl._create_unverified_context()) as response:
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() not in HOP_BY_HOP_HEADERS:
                        self.send_header(key, value)
                self.end_headers()
                self.wfile.write(response.read())
        except HTTPError as exc:
            self.send_response(exc.code)
            for key, value in exc.headers.items():
                if key.lower() not in HOP_BY_HOP_HEADERS:
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(exc.read())
        except URLError as exc:
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            payload = {"error": "target_unavailable", "detail": str(exc.reason)}
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Basic-auth reverse proxy for the local debug UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--target", default="http://127.0.0.1:8765")
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    token = base64.b64encode(f"{args.user}:{args.password}".encode("utf-8")).decode("ascii")
    AuthProxyHandler.target = args.target
    AuthProxyHandler.auth_header = f"Basic {token}"

    server = ThreadingHTTPServer((args.host, args.port), AuthProxyHandler)
    print(f"remote debug proxy listening on http://{args.host}:{args.port} -> {args.target}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
