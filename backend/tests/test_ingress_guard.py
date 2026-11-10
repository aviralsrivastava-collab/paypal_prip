"""
Unit and Integration Tests for PRIP Ingress Guard (scripts/ingress_guard.py).
Verification:
1. Explicit allowlist enforcement: ONLY permitted read-only (GET) routes and the single
   authorized PayPal Sandbox webhook endpoint (POST /api/webhooks/paypal) are allowed.
2. All other mutation endpoints (POST/PUT/DELETE/PATCH) remain strictly rejected with 403 Forbidden:
   - Payment creation, capture, reconcile, preflight
   - Correction creation, approve, reject, cancel, execute, reconcile
   - Catalog seed, storefront price update
   - Inspection triggers, AI diagnosis triggers
   - Unapproved webhook methods (GET/PUT/DELETE /api/webhooks/paypal) and unapproved webhook paths
3. Preservation and forwarding of raw request payload and PayPal signature headers:
   - PAYPAL-AUTH-ALGO
   - PAYPAL-CERT-URL
   - PAYPAL-TRANSMISSION-ID
   - PAYPAL-TRANSMISSION-SIG
   - PAYPAL-TRANSMISSION-TIME
4. All operations, worker, replay, docs, admin, and metrics routes return 403 Forbidden.
5. Path traversal, null bytes, double slashes, and encoded bypass defenses return 403.
6. Backend authorization verification: spoofed merchant headers, unauthenticated access,
   and cross-tenant isolation enforcement.
"""

import io
from typing import Any, Tuple, cast
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from scripts.ingress_guard import (
    IngressGuardHandler,
    is_request_allowed,
    validate_and_normalize_path,
)

from backend.core.config import get_settings
from backend.core.security import (
    AuthenticatedActor,
    create_jwt_token,
    get_current_actor,
    require_merchant_access,
)


class TestIngressGuardAllowlistMatching:
    """Verifies that ONLY the explicitly approved read-only routes and POST /api/webhooks/paypal are permitted."""

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/"),
            ("GET", "/api/health"),
            ("GET", "/api/products"),
            ("GET", "/api/products/1"),
            ("GET", "/api/products/sku/SX-001"),
            ("GET", "/api/scans/1"),
            ("GET", "/api/scans/1/evidence"),
            ("GET", "/api/scans/product/SX-001"),
            ("GET", "/api/diagnoses/scan/1"),
            ("GET", "/api/diagnoses/1"),
            ("GET", "/api/corrections/proposals"),
            ("GET", "/api/corrections/proposals/1"),
            ("GET", "/api/corrections/proposals/1/history"),
            ("GET", "/api/checkout/orders"),
            ("GET", "/api/checkout/orders/ORD-12345"),
            ("GET", "/api/webhooks/events"),
            ("POST", "/api/webhooks/paypal"),  # Authorized webhook ingestion
            ("OPTIONS", "/api/products"),
            ("OPTIONS", "/api/health"),
            ("OPTIONS", "/api/checkout/orders"),
            ("OPTIONS", "/api/webhooks/paypal"),
        ],
    )
    def test_approved_requests_allowed(self, method: str, path: str):
        assert is_request_allowed(method, path) is True

    @pytest.mark.parametrize(
        "method,path",
        [
            # Blocked payment mutations
            ("POST", "/api/checkout/orders"),
            ("POST", "/api/checkout/orders/ORD-12345/capture"),
            ("POST", "/api/checkout/orders/ORD-12345/reconcile"),
            ("POST", "/api/checkout/preflight"),
            # Blocked correction mutations
            ("POST", "/api/corrections/proposals"),
            ("POST", "/api/corrections/proposals/1/approve"),
            ("POST", "/api/corrections/proposals/1/reject"),
            ("POST", "/api/corrections/proposals/1/cancel"),
            ("POST", "/api/corrections/proposals/1/execute"),
            ("POST", "/api/corrections/proposals/1/reconcile"),
            # Blocked catalog and storefront mutations
            ("POST", "/api/products/seed"),
            ("PUT", "/api/storefront/products/SX-001/price"),
            # Blocked inspection and diagnosis triggers
            ("POST", "/api/scans"),
            ("POST", "/api/diagnoses/scan/1"),
            # Blocked unapproved webhook methods & paths
            ("GET", "/api/webhooks/paypal"),
            ("PUT", "/api/webhooks/paypal"),
            ("DELETE", "/api/webhooks/paypal"),
            ("PATCH", "/api/webhooks/paypal"),
            ("POST", "/api/webhooks/other"),
            ("POST", "/api/webhooks/paypal/fake"),
            ("POST", "/api/webhooks/events"),
            ("POST", "/api/webhooks"),
            ("POST", "/api/webhooks/stripe"),
            # Blocked documentation & schema
            ("GET", "/docs"),
            ("GET", "/redoc"),
            ("GET", "/openapi.json"),
            ("OPTIONS", "/docs"),
            # Blocked operations, replay, and worker endpoints
            ("GET", "/api/operations/overview"),
            ("GET", "/api/operations/webhooks/stuck"),
            ("POST", "/api/operations/webhooks/1/replay"),
            ("GET", "/api/operations/reconciliations/pending"),
            ("GET", "/api/operations/reconciliations/history"),
            ("POST", "/api/operations/reconciliations/trigger"),
            ("GET", "/api/operations/workers"),
            ("POST", "/api/operations/workers/tick"),
            ("OPTIONS", "/api/operations/overview"),
            # Blocked admin, metrics, debugging
            ("GET", "/admin"),
            ("GET", "/metrics"),
            ("GET", "/debug"),
            ("GET", "/database"),
            # Unapproved methods on existing GET routes
            ("DELETE", "/api/products/1"),
            ("PATCH", "/api/products/1"),
            ("DELETE", "/api/checkout/orders/ORD-12345"),
        ],
    )
    def test_all_mutations_and_unapproved_routes_blocked(self, method: str, path: str):
        assert is_request_allowed(method, path) is False


class TestPathSanitizationAndNormalization:
    """Verifies path traversal, encoding, and injection defenses."""

    def test_clean_path_accepted(self):
        norm, query, err = validate_and_normalize_path("/api/health")
        assert err is None
        assert norm == "/api/health"
        assert query == ""

    def test_query_string_preserved(self):
        norm, query, err = validate_and_normalize_path("/api/products?limit=10&page=1")
        assert err is None
        assert norm == "/api/products"
        assert query == "limit=10&page=1"

    def test_null_byte_rejected(self):
        norm, query, err = validate_and_normalize_path("/api/products%00/secret")
        assert err is not None
        assert "Null byte" in err
        assert norm is None

    def test_path_traversal_double_dot_rejected(self):
        norm, query, err = validate_and_normalize_path("/api/products/../../docs")
        assert err is not None
        assert "Directory traversal" in err

    def test_encoded_traversal_rejected(self):
        norm, query, err = validate_and_normalize_path("/api/products/%2e%2e/%2e%2e/docs")
        assert err is not None
        assert "traversal" in err

    def test_double_slashes_rejected(self):
        norm, query, err = validate_and_normalize_path("//docs")
        assert err is not None
        assert "slashes" in err

    def test_absolute_uri_netloc_rejected(self):
        norm, query, err = validate_and_normalize_path("http://evil.com/docs")
        assert err is not None
        assert "absolute URI" in err


class DummySocket:
    """Minimal mock socket for in-memory BaseHTTPRequestHandler testing."""

    def __init__(self, request_bytes: bytes):
        self._rfile = io.BytesIO(request_bytes)
        self._wfile = io.BytesIO()

    def makefile(self, mode: str = "r", buffering: int = -1) -> io.BytesIO:
        if "r" in mode:
            return self._rfile
        return self._wfile

    def sendall(self, data: bytes) -> None:
        self._wfile.write(data)

    def close(self) -> None:
        pass


def run_handler_with_request(raw_request_bytes: bytes) -> Tuple[int, bytes]:
    """Runs IngressGuardHandler with simulated raw HTTP request bytes and returns (status_code, response_bytes)."""
    sock = DummySocket(raw_request_bytes)
    server = MagicMock()
    server.server_name = "127.0.0.1"
    server.server_port = 8085

    handler = IngressGuardHandler(
        request=cast(Any, sock),
        client_address=("127.0.0.1", 54321),
        server=server,
    )
    raw_output = sock._wfile.getvalue()
    status_code = handler._last_response_code if hasattr(handler, "_last_response_code") else 200
    first_line = raw_output.split(b"\r\n")[0]
    if b" " in first_line:
        parts = first_line.split(b" ")
        if len(parts) >= 2 and parts[1].isdigit():
            status_code = int(parts[1])
    return status_code, raw_output


class TestIngressGuardHandlerExecution:
    """Executes IngressGuardHandler in memory to verify exact HTTP responses, headers, and forwarding."""

    def test_blocked_mutation_returns_403_and_security_headers(self):
        req = (
            b"POST /api/checkout/orders HTTP/1.1\r\n"
            b"Host: 127.0.0.1:8085\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )
        code, resp = run_handler_with_request(req)
        assert code == 403
        assert b"X-Ingress-Guard: DENIED" in resp
        assert b"Forbidden: Public ingress restricted by allowlist" in resp

    def test_blocked_unapproved_webhook_returns_403(self):
        req = (
            b"POST /api/webhooks/other HTTP/1.1\r\n"
            b"Host: 127.0.0.1:8085\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )
        code, resp = run_handler_with_request(req)
        assert code == 403
        assert b"X-Ingress-Guard: DENIED" in resp

        req_get_wh = (
            b"GET /api/webhooks/paypal HTTP/1.1\r\n"
            b"Host: 127.0.0.1:8085\r\n"
            b"\r\n"
        )
        code, resp = run_handler_with_request(req_get_wh)
        assert code == 403
        assert b"X-Ingress-Guard: DENIED" in resp

    def test_blocked_docs_returns_403(self):
        req = (
            b"GET /docs HTTP/1.1\r\n"
            b"Host: 127.0.0.1:8085\r\n"
            b"\r\n"
        )
        code, resp = run_handler_with_request(req)
        assert code == 403
        assert b"X-Ingress-Guard: DENIED" in resp

    @patch("urllib.request.urlopen")
    def test_get_health_forwarded(self, mock_urlopen: MagicMock):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.read.return_value = b'{"status":"healthy"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        req = (
            b"GET /api/health HTTP/1.1\r\n"
            b"Host: 127.0.0.1:8085\r\n"
            b"Authorization: Bearer test-token\r\n"
            b"X-Merchant-Id: merchant-123\r\n"
            b"\r\n"
        )
        code, resp = run_handler_with_request(req)
        assert code == 200
        assert b"X-Ingress-Guard: FORWARDED" in resp
        assert b'{"status":"healthy"}' in resp

        forwarded_req = mock_urlopen.call_args[0][0]
        assert forwarded_req.full_url == "http://127.0.0.1:8000/api/health"
        assert forwarded_req.headers.get("Host") == "127.0.0.1:8000"
        assert forwarded_req.headers.get("Authorization") == "Bearer test-token"
        assert forwarded_req.headers.get("X-merchant-id") == "merchant-123"
        assert forwarded_req.headers.get("X-forwarded-proto") == "https"

    @patch("urllib.request.urlopen")
    def test_paypal_webhook_post_forwards_with_signature_headers_and_body(self, mock_urlopen: MagicMock):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.read.return_value = b'{"status":"SUCCESS","id":"WH-123"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        payload = b'{"id":"WH-123","event_type":"PAYMENT.CAPTURE.COMPLETED"}'
        req = (
            b"POST /api/webhooks/paypal HTTP/1.1\r\n"
            b"Host: 127.0.0.1:8085\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(payload)).encode("ascii") + b"\r\n"
            b"PAYPAL-AUTH-ALGO: SHA256withRSA\r\n"
            b"PAYPAL-CERT-URL: https://api.sandbox.paypal.com/v1/notifications/certs/CERT-123\r\n"
            b"PAYPAL-TRANSMISSION-ID: trans-98765\r\n"
            b"PAYPAL-TRANSMISSION-SIG: sig-abcdef123456\r\n"
            b"PAYPAL-TRANSMISSION-TIME: 2026-11-10T14:00:00Z\r\n"
            b"\r\n"
            + payload
        )
        code, resp = run_handler_with_request(req)
        assert code == 200
        assert b"X-Ingress-Guard: FORWARDED" in resp
        assert b'{"status":"SUCCESS","id":"WH-123"}' in resp

        forwarded_req = mock_urlopen.call_args[0][0]
        assert forwarded_req.full_url == "http://127.0.0.1:8000/api/webhooks/paypal"
        assert forwarded_req.get_method() == "POST"
        assert forwarded_req.data == payload
        # Verify PayPal signature headers forwarded exactly
        assert forwarded_req.headers.get("Paypal-auth-algo") == "SHA256withRSA"
        assert forwarded_req.headers.get("Paypal-cert-url") == "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-123"
        assert forwarded_req.headers.get("Paypal-transmission-id") == "trans-98765"
        assert forwarded_req.headers.get("Paypal-transmission-sig") == "sig-abcdef123456"
        assert forwarded_req.headers.get("Paypal-transmission-time") == "2026-11-10T14:00:00Z"
        assert forwarded_req.headers.get("Host") == "127.0.0.1:8000"

    @patch("urllib.request.urlopen")
    def test_options_cors_preflight_forwarded(self, mock_urlopen: MagicMock):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {
            "Access-Control-Allow-Origin": "https://paypalprip.vercel.app",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
        mock_resp.read.return_value = b""
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        req = (
            b"OPTIONS /api/products HTTP/1.1\r\n"
            b"Host: 127.0.0.1:8085\r\n"
            b"Origin: https://paypalprip.vercel.app\r\n"
            b"Access-Control-Request-Method: GET\r\n"
            b"\r\n"
        )
        code, resp = run_handler_with_request(req)
        assert code == 200
        assert b"X-Ingress-Guard: FORWARDED" in resp
        forwarded_req = mock_urlopen.call_args[0][0]
        assert forwarded_req.get_method() == "OPTIONS"


class TestBackendAuthorizationAndTenantSecurity:
    """Verifies that backend authentication, authorization, and tenant isolation remain airtight."""

    def test_spoofed_merchant_header_does_not_override_jwt_claims(self):
        """When a valid JWT is presented, the authenticated actor's merchant_id is derived from token claims, NOT client headers."""
        import time
        token = create_jwt_token({
            "sub": "user_genuine",
            "merchant_id": "merchant_alpha",
            "role": "merchant_operator",
            "actor_type": "merchant",
            "exp": int(time.time()) + 3600,
        })
        actor = get_current_actor(
            authorization=f"Bearer {token}",
            x_merchant_id="merchant_spoofed_victim",
        )
        assert actor.merchant_id == "merchant_alpha"
        assert actor.merchant_id != "merchant_spoofed_victim"

    def test_cross_tenant_access_blocked_by_guard(self):
        """Actors cannot access or mutate resources belonging to another merchant tenant."""
        alpha_actor = AuthenticatedActor(
            actor_id="user_alpha",
            role="merchant_operator",
            merchant_id="tenant_alpha",
        )
        with pytest.raises(HTTPException) as exc_info:
            require_merchant_access(alpha_actor, "tenant_beta")
        assert exc_info.value.status_code == 403
        assert "not authorized to access or mutate merchant 'tenant_beta'" in exc_info.value.detail

    def test_reserved_system_tenant_claim_blocked(self):
        """Non-system callers attempting to claim reserved platform/system tenant are rejected with 403."""
        with pytest.raises(HTTPException) as exc_info:
            get_current_actor(
                authorization=None,
                x_actor_id="attacker",
                x_actor_role="merchant_operator",
                x_merchant_id="platform_system",
            )
        assert exc_info.value.status_code == 403
        assert "reserved non-merchant identity" in exc_info.value.detail

    def test_production_mode_strictly_rejects_unauthenticated_requests(self, monkeypatch: pytest.MonkeyPatch):
        """In production (APP_ENV=production), missing Bearer token immediately raises HTTP 401."""
        settings = get_settings()
        monkeypatch.setattr(settings, "app_env", "production")
        with pytest.raises(HTTPException) as exc_info:
            get_current_actor(authorization=None)
        assert exc_info.value.status_code == 401
        assert "Production authentication token required" in exc_info.value.detail

    def test_cors_preflight_on_fastapi_backend(self):
        """Settings explicitly authorize Vercel frontend without wildcards."""
        settings = get_settings()
        assert "https://paypalprip.vercel.app" in settings.cors_origins_list
        assert "*" not in settings.cors_origins_list
# ok
