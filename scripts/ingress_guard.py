"""
PRIP Ingress Guard — Loopback Path & Method Filter Proxy
Listens strictly on loopback (127.0.0.1:8085).
Enforces default-deny: forwards explicitly approved read-only (GET) API routes
and the single authorized PayPal webhook ingestion endpoint (POST /api/webhooks/paypal)
to PRIP backend (127.0.0.1:8000).
Rejects ALL other mutations (checkout orders, captures, approvals, executions, resets),
unapproved webhook paths, operations, administrative, and doc routes with HTTP 403 Forbidden.
"""

import logging
import posixpath
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import List, Optional, Pattern, Tuple

logger = logging.getLogger("prip.ingress_guard")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [ingress_guard] %(message)s",
)

TARGET_HOST = "127.0.0.1"
TARGET_PORT = 8000

# Explicit allowlist of (HTTP_METHOD, compiled_regex_pattern)
# Strict default-deny: ONLY read-only GET endpoints required for dashboard and inspection view are permitted.
ALLOWLIST_RULES: List[Tuple[str, Pattern[str]]] = [
    # 1. Root & Health Check
    ("GET", re.compile(r"^/$")),
    ("GET", re.compile(r"^/api/health$")),

    # 2. Merchant-Authorized Catalog (Read-Only)
    ("GET", re.compile(r"^/api/products$")),
    ("GET", re.compile(r"^/api/products/[0-9]+$")),
    ("GET", re.compile(r"^/api/products/sku/[a-zA-Z0-9_-]+$")),

    # 3. Storefront Inspection & Structured Evidence (Read-Only)
    ("GET", re.compile(r"^/api/scans/[0-9]+$")),
    ("GET", re.compile(r"^/api/scans/[0-9]+/evidence$")),
    ("GET", re.compile(r"^/api/scans/product/[a-zA-Z0-9_-]+$")),

    # 4. Advisory AI Diagnosis (Read-Only)
    ("GET", re.compile(r"^/api/diagnoses/scan/[0-9]+$")),
    ("GET", re.compile(r"^/api/diagnoses/[0-9]+$")),

    # 5. Merchant Correction Proposals (Read-Only)
    ("GET", re.compile(r"^/api/corrections/proposals$")),
    ("GET", re.compile(r"^/api/corrections/proposals/[0-9]+$")),
    ("GET", re.compile(r"^/api/corrections/proposals/[0-9]+/history$")),

    # 6. Checkout Orders (Read-Only)
    ("GET", re.compile(r"^/api/checkout/orders$")),
    ("GET", re.compile(r"^/api/checkout/orders/[a-zA-Z0-9_-]+$")),

    # 7. Webhook Audit Events (Read-Only)
    ("GET", re.compile(r"^/api/webhooks/events$")),

    # 8. PayPal Sandbox Webhook Ingestion (Single authorized POST mutation endpoint)
    ("POST", re.compile(r"^/api/webhooks/paypal$")),
]

# Explicitly blocked prefixes (for defense-in-depth fast-rejection)
BLOCKED_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/operations",
    "/metrics",
    "/admin",
    "/debug",
)


def validate_and_normalize_path(raw_url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Validates, sanitizes, and normalizes the request URI against path traversal,
    encoded bypasses, null bytes, and protocol exploits.
    Returns (normalized_path, query_string, error_message).
    """
    if not raw_url:
        return None, None, "Empty request URI"

    if "\x00" in raw_url or "%00" in raw_url.lower():
        return None, None, "Null byte detected in request URI"

    # Reject scheme-relative (//example.com) or multiple leading slashes
    if raw_url.startswith("//"):
        return None, None, "Invalid path: leading double slashes detected"

    parsed = urllib.parse.urlsplit(raw_url)
    if parsed.netloc:
        return None, None, "Invalid request URI: absolute URI or netloc not allowed"

    raw_path = parsed.path
    if not raw_path.startswith("/"):
        return None, None, "Path must start with '/'"

    # Check for direct or unencoded traversal sequences
    if ".." in raw_path or "//" in raw_path:
        return None, None, "Directory traversal or double slashes detected"

    # Decode and check again
    unquoted = urllib.parse.unquote(raw_path)
    if ".." in unquoted or "//" in unquoted or "\x00" in unquoted:
        return None, None, "Encoded directory traversal or invalid sequence detected"

    normalized = posixpath.normpath(unquoted)
    if normalized != unquoted:
        return None, None, "Path normalization mismatch"

    return normalized, parsed.query, None


def is_request_allowed(method: str, path: str) -> bool:
    """Checks method and path against explicit allowlist rules."""
    # Fast reject known blocked administrative / doc prefixes
    if any(path == p or path.startswith(f"{p}/") for p in BLOCKED_PREFIXES):
        return False

    # CORS Preflight OPTIONS: allow if path matches any valid endpoint
    if method == "OPTIONS":
        return any(pattern.match(path) for _, pattern in ALLOWLIST_RULES)

    # Standard method check
    return any(m == method and pattern.match(path) for m, pattern in ALLOWLIST_RULES)


class IngressGuardHandler(BaseHTTPRequestHandler):
    server_version = "PRIPIngressGuard/2.1-WebhookEnabled"

    def _send_forbidden(self, reason: str) -> None:
        msg = f"Forbidden: Public ingress restricted by allowlist. Reason: {reason}\n".encode("utf-8")
        self.send_response(403)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(msg)))
        self.send_header("X-Ingress-Guard", "DENIED")
        self.end_headers()
        self.wfile.write(msg)
        logger.warning(f"BLOCKED ingress request: {self.command} {self.path} -> 403 Forbidden ({reason})")

    def handle_request(self) -> None:
        method = self.command

        # Validate Host header against CRLF injection
        host_header = self.headers.get("Host", "")
        if not host_header or "\r" in host_header or "\n" in host_header:
            self._send_forbidden("Invalid or missing Host header")
            return

        # Sanitize and normalize path
        path, query, err = validate_and_normalize_path(self.path)
        if err or not path:
            self._send_forbidden(err or "Invalid path")
            return

        # Check against allowlist
        if not is_request_allowed(method, path):
            self._send_forbidden(f"Endpoint '{method} {path}' is not permitted on public ingress")
            return

        # Read request body if present
        content_length_str = self.headers.get("Content-Length", "0")
        try:
            content_length = int(content_length_str)
        except ValueError:
            self.send_error(400, "Invalid Content-Length header")
            return

        if content_length > 1_048_576:  # 1MB limit
            self.send_error(413, "Payload too large (1MB limit)")
            return

        body: Optional[bytes] = None
        if content_length > 0:
            body = self.rfile.read(content_length)

        # Build backend destination URL (loopback port 8000)
        target_path = f"{path}?{query}" if query else path
        target_url = f"http://{TARGET_HOST}:{TARGET_PORT}{target_path}"

        req = urllib.request.Request(target_url, data=body, method=method)

        # Forward headers, adjusting Host and adding standard proxy headers
        hop_by_hop = {
            "host",
            "content-length",
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "transfer-encoding",
            "upgrade",
        }
        for key, val in self.headers.items():
            if key.lower() not in hop_by_hop:
                req.add_header(key, val)

        req.add_header("Host", f"{TARGET_HOST}:{TARGET_PORT}")
        req.add_header("X-Forwarded-For", self.client_address[0])
        req.add_header("X-Forwarded-Proto", "https")
        req.add_header("X-Forwarded-Host", host_header)

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
                logger.info(f"FORWARDED: {method} {path} -> backend status {resp.status}")
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
            logger.info(f"FORWARDED: {method} {path} -> backend error status {exc.code}")
        except Exception as exc:
            logger.error(f"Failed to connect to backend at {target_url}: {exc}")
            err_msg = b"502 Bad Gateway: PRIP backend unreachable on loopback port 8000\n"
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(err_msg)))
            self.end_headers()
            self.wfile.write(err_msg)

    def do_GET(self) -> None:
        self.handle_request()

    def do_POST(self) -> None:
        self.handle_request()

    def do_PUT(self) -> None:
        self.handle_request()

    def do_OPTIONS(self) -> None:
        self.handle_request()

    def do_HEAD(self) -> None:
        self.handle_request()

    def do_DELETE(self) -> None:
        self._send_forbidden("DELETE method not allowed on public ingress")

    def do_PATCH(self) -> None:
        self._send_forbidden("PATCH method not allowed on public ingress")

    def log_message(self, format: str, *args: object) -> None:
        pass


def run_guard(host: str = "127.0.0.1", port: int = 8085) -> None:
    server = HTTPServer((host, port), IngressGuardHandler)
    logger.info(f"PRIP Ingress Guard listening on http://{host}:{port}")
    logger.info(f"Forwarding authorized read-only requests and POST /api/webhooks/paypal strictly to http://{TARGET_HOST}:{TARGET_PORT}")
    logger.info("All other mutations, operations, admin, and docs rejected with 403 Forbidden.")
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
