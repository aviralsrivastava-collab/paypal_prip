"""
PRIP Ingress Guard — Loopback Path & Method Filter Proxy
Listens strictly on loopback (127.0.0.1:8085).
Enforces default-deny: forwards ONLY `POST /api/webhooks/paypal` to PRIP backend (127.0.0.1:8000).
Rejects all other paths (/docs, /openapi.json, /api/operations/*, /) and non-POST methods with HTTP 403.
"""

import logging
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger("prip.ingress_guard")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [ingress_guard] %(message)s',
)

TARGET_HOST = "127.0.0.1"
TARGET_PORT = 8000
ALLOWED_PATH = "/api/webhooks/paypal"
ALLOWED_METHOD = "POST"


class IngressGuardHandler(BaseHTTPRequestHandler):
    server_version = "PRIPIngressGuard/1.0"

    def _send_forbidden(self, reason: str) -> None:
        msg = f"Forbidden: Public ingress restricted strictly to POST {ALLOWED_PATH}. Reason: {reason}\n".encode("utf-8")
        self.send_response(403)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(msg)))
        self.send_header("X-Ingress-Guard", "DENIED")
        self.end_headers()
        self.wfile.write(msg)
        logger.warning(f"BLOCKED ingress request: {self.command} {self.path} -> 403 Forbidden ({reason})")

    def do_POST(self) -> None:
        # Strip query parameters if any
        path_only = self.path.split("?")[0]
        if path_only != ALLOWED_PATH:
            self._send_forbidden(f"Path '{path_only}' is not permitted")
            return

        # Read exact raw payload bytes
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 1_048_576:  # 1MB limit
            self.send_error(413, "Payload too large (1MB limit)")
            return

        raw_body = self.rfile.read(content_length)

        # Forward to local backend
        target_url = f"http://{TARGET_HOST}:{TARGET_PORT}{ALLOWED_PATH}"
        req = urllib.request.Request(target_url, data=raw_body, method="POST")

        # Forward headers, adjusting host
        for key, val in self.headers.items():
            if key.lower() not in ("host", "content-length"):
                req.add_header(key, val)
        req.add_header("Host", f"{TARGET_HOST}:{TARGET_PORT}")
        req.add_header("X-Forwarded-For", self.client_address[0])
        req.add_header("X-Forwarded-Proto", "https")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_body = resp.read()
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ("transfer-encoding", "content-length"):
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(resp_body)))
                self.send_header("X-Ingress-Guard", "FORWARDED")
                self.end_headers()
                self.wfile.write(resp_body)
                logger.info(f"FORWARDED webhook notification -> backend status {resp.status}")
        except urllib.error.HTTPError as exc:
            err_body = exc.read()
            self.send_response(exc.code)
            for k, v in exc.headers.items():
                if k.lower() not in ("transfer-encoding", "content-length"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(err_body)))
            self.send_header("X-Ingress-Guard", "FORWARDED")
            self.end_headers()
            self.wfile.write(err_body)
            logger.info(f"FORWARDED webhook notification -> backend error status {exc.code}")
        except Exception as exc:
            logger.error(f"Failed to connect to backend at {target_url}: {exc}")
            err_msg = b"502 Bad Gateway: PRIP backend unreachable on loopback port 8000\n"
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(err_msg)))
            self.end_headers()
            self.wfile.write(err_msg)

    # Deny all other HTTP methods
    def do_GET(self) -> None:
        self._send_forbidden("GET method not allowed on public ingress")

    def do_PUT(self) -> None:
        self._send_forbidden("PUT method not allowed on public ingress")

    def do_DELETE(self) -> None:
        self._send_forbidden("DELETE method not allowed on public ingress")

    def do_PATCH(self) -> None:
        self._send_forbidden("PATCH method not allowed on public ingress")

    def do_HEAD(self) -> None:
        self._send_forbidden("HEAD method not allowed on public ingress")

    def do_OPTIONS(self) -> None:
        self._send_forbidden("OPTIONS method not allowed on public ingress")

    def log_message(self, format: str, *args: object) -> None:
        # Suppress default noisy stdio logging in favor of logger
        pass


def run_guard(host: str = "127.0.0.1", port: int = 8085) -> None:
    server = HTTPServer((host, port), IngressGuardHandler)
    logger.info(f"PRIP Ingress Guard listening on http://{host}:{port}")
    logger.info(f"Allowing strictly: POST {ALLOWED_PATH} -> http://{TARGET_HOST}:{TARGET_PORT}{ALLOWED_PATH}")
    logger.info("All other paths and methods rejected with 403 Forbidden.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Ingress Guard terminated by keyboard.")
    finally:
        server.server_close()
        logger.info("Ingress Guard stopped.")


if __name__ == "__main__":
    bind_port = 8085
    if len(sys.argv) > 1:
        try:
            bind_port = int(sys.argv[1])
        except ValueError:
            pass
    run_guard(port=bind_port)
