import json

from starlette.requests import Request
from starlette.responses import Response

from backend.api.main import security_and_tracing_middleware
from backend.core.config import get_settings
from backend.core.rate_limit import (
    InMemoryRateLimitStore,
    SharedRateLimitStore,
    classify_path,
    get_client_ip,
    is_trusted_proxy,
    reset_rate_limit_store,
)


def run_middleware(
    path: str = "/api/products",
    client_ip: str = "127.0.0.1",
    headers: dict[str, str] | None = None,
    next_response_status: int = 200,
):
    """
    Executes security_and_tracing_middleware directly without background socket loop.
    Provides fast, deterministic execution across all environments.
    """
    header_list = [(b"host", b"localhost")]
    if headers:
        for k, v in headers.items():
            header_list.append((k.lower().encode("utf-8"), v.encode("utf-8")))

    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": header_list,
        "client": (client_ip, 12345),
    }
    req = Request(scope)

    async def dummy_next(r):
        return Response("ok", status_code=next_response_status)

    coro = security_and_tracing_middleware(req, dummy_next)
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value
    raise RuntimeError("Middleware coroutine did not complete")


def test_classify_path_routing():
    """Confirms path categorization matches security tiers."""
    assert classify_path("/api/health/live") == "exempt"
    assert classify_path("/api/health/ready") == "exempt"
    assert classify_path("/docs") == "exempt"
    assert classify_path("/openapi.json") == "exempt"

    assert classify_path("/api/checkout/orders") == "sensitive"
    assert classify_path("/api/checkout/orders/ORD-1/capture") == "sensitive"
    assert classify_path("/api/webhooks/paypal") == "sensitive"
    assert classify_path("/api/corrections/1/approve") == "sensitive"

    assert classify_path("/api/products") == "default"
    assert classify_path("/api/scans") == "default"
    assert classify_path("/api/diagnoses") == "default"
    assert classify_path("/api/operations/overview") == "default"


def test_requests_within_allowed_limit():
    """Requests under the rate limit should succeed normally."""
    reset_rate_limit_store()
    for _ in range(5):
        resp = run_middleware(path="/api/products")
        assert resp.status_code == 200


def test_requests_exceeding_default_limit_returns_http_429():
    """
    Exceeding default burst limit (40 requests) triggers HTTP 429
    with Retry-After header and compliant JSON error details.
    """
    reset_rate_limit_store()
    settings = get_settings()
    burst_limit = settings.rate_limit_default_burst  # 40

    # Exhaust available tokens
    for i in range(burst_limit):
        resp = run_middleware(path="/api/products")
        assert resp.status_code == 200, f"Request {i+1} failed unexpectedly"

    # Request 41 must be rejected with HTTP 429
    resp_blocked = run_middleware(path="/api/products")
    assert resp_blocked.status_code == 429
    assert "Retry-After" in resp_blocked.headers
    assert resp_blocked.headers.get("X-RateLimit-Limit") == str(burst_limit)
    assert resp_blocked.headers.get("X-RateLimit-Remaining") == "0"

    data = json.loads(resp_blocked.body.decode("utf-8"))
    assert "Rate limit exceeded" in data["detail"]
    assert "retry_after_seconds" in data
    assert data["retry_after_seconds"] >= 1

    # Security headers must be preserved on 429 responses
    assert "X-Correlation-ID" in resp_blocked.headers
    assert resp_blocked.headers.get("X-Frame-Options") == "DENY"
    assert resp_blocked.headers.get("Content-Security-Policy") == "default-src 'self'"


def test_independent_client_identities():
    """Rate limits on client A do not affect client B when proxied with trusted headers."""
    reset_rate_limit_store()
    settings = get_settings()
    burst = settings.rate_limit_default_burst

    # Client A exhausts tokens
    for _ in range(burst):
        resp = run_middleware(
            path="/api/products",
            client_ip="127.0.0.1",
            headers={"X-Forwarded-For": "198.51.100.10"},
        )
        assert resp.status_code == 200

    # Client A is now throttled
    blocked = run_middleware(
        path="/api/products",
        client_ip="127.0.0.1",
        headers={"X-Forwarded-For": "198.51.100.10"},
    )
    assert blocked.status_code == 429

    # Client B should NOT be throttled
    client_b_resp = run_middleware(
        path="/api/products",
        client_ip="127.0.0.1",
        headers={"X-Forwarded-For": "198.51.100.20"},
    )
    assert client_b_resp.status_code == 200


def test_trusted_proxy_forwarded_for_handling():
    """Derives client IP from X-Forwarded-For only when peer host is a trusted proxy."""
    trusted_proxies = {"127.0.0.1", "10.0.0.0/8", "testclient"}

    class MockRequest:
        def __init__(self, host: str, xff: str | None = None, x_real: str | None = None):
            self.client = type("Client", (), {"host": host})()
            self.headers = {}
            if xff:
                self.headers["x-forwarded-for"] = xff
            if x_real:
                self.headers["x-real-ip"] = x_real

    # 1. Trusted proxy with X-Forwarded-For
    req1 = MockRequest(host="127.0.0.1", xff="203.0.113.50, 10.0.0.1")
    assert get_client_ip(req1, trusted_proxies) == "203.0.113.50"

    # 2. Trusted proxy with X-Real-IP
    req2 = MockRequest(host="testclient", x_real="203.0.113.99")
    assert get_client_ip(req2, trusted_proxies) == "203.0.113.99"

    # 3. Untrusted direct client attempting to spoof X-Forwarded-For
    req3 = MockRequest(host="198.51.100.77", xff="8.8.8.8")
    assert get_client_ip(req3, trusted_proxies) == "198.51.100.77"


def test_is_trusted_proxy_ip_and_cidr():
    """Validates trusted proxy IP, hostname, and CIDR subnet evaluation."""
    trusted = {"127.0.0.1", "::1", "testclient", "172.16.0.0/12"}
    assert is_trusted_proxy("127.0.0.1", trusted) is True
    assert is_trusted_proxy("testclient", trusted) is True
    assert is_trusted_proxy("172.18.0.2", trusted) is True
    assert is_trusted_proxy("8.8.8.8", trusted) is False
    assert is_trusted_proxy("", trusted) is False


def test_sensitive_endpoint_stricter_limit():
    """
    Sensitive endpoints (/api/checkout, /api/webhooks, /api/corrections)
    enforce stricter rate limits (burst=10).
    """
    reset_rate_limit_store()
    settings = get_settings()
    sensitive_burst = settings.rate_limit_sensitive_burst  # 10

    # Exhaust sensitive burst
    for i in range(sensitive_burst):
        resp = run_middleware(path="/api/checkout/orders")
        assert resp.status_code == 200, f"Request {i+1} failed"

    # 11th request must be rate limited
    resp_blocked = run_middleware(path="/api/checkout/orders")
    assert resp_blocked.status_code == 429
    assert resp_blocked.headers.get("X-RateLimit-Limit") == str(sensitive_burst)


def test_exempt_health_checks_not_rate_limited():
    """Internal health checks (/api/health/*) are exempt from throttling."""
    reset_rate_limit_store()
    # Send 50 rapid requests to health endpoints
    for _ in range(25):
        resp_live = run_middleware(path="/api/health/live")
        assert resp_live.status_code == 200
        resp_ready = run_middleware(path="/api/health/ready")
        assert resp_ready.status_code == 200


def test_multi_replica_in_memory_isolation_and_limitations():
    """
    Demonstrates multi-replica behavior with local in-memory stores.
    In the absence of a coordinated shared store or reverse proxy (Nginx limit_req),
    each application replica tracks tokens in its own process memory.
    """
    replica_1_store = InMemoryRateLimitStore()
    replica_2_store = InMemoryRateLimitStore()

    rate = 20.0
    burst = 2

    # Consume all tokens on Replica 1
    allowed1_1, _ = replica_1_store.consume("client:192.168.1.5", rate, burst)
    allowed1_2, _ = replica_1_store.consume("client:192.168.1.5", rate, burst)
    blocked1_3, retry1 = replica_1_store.consume("client:192.168.1.5", rate, burst)

    assert allowed1_1 is True
    assert allowed1_2 is True
    assert blocked1_3 is False
    assert retry1 > 0.0

    # Replica 2 still has its own available tokens for the same client
    allowed2_1, _ = replica_2_store.consume("client:192.168.1.5", rate, burst)
    assert allowed2_1 is True, "Replica 2 operates independently without a shared store"


def test_shared_store_global_enforcement():
    """
    Demonstrates coordinated multi-replica rate limiting via a shared store.
    When replicas delegate to a shared store, quotas are enforced globally.
    """
    shared_backend = InMemoryRateLimitStore()
    replica_1_proxy = SharedRateLimitStore(shared_backend)
    replica_2_proxy = SharedRateLimitStore(shared_backend)

    rate = 10.0
    burst = 2

    # Replica 1 consumes 1 token
    r1_allowed, _ = replica_1_proxy.consume("client:10.0.0.5", rate, burst)
    assert r1_allowed is True

    # Replica 2 consumes 1 token
    r2_allowed, _ = replica_2_proxy.consume("client:10.0.0.5", rate, burst)
    assert r2_allowed is True

    # Shared bucket is now exhausted: either replica will reject further requests
    r1_blocked, _ = replica_1_proxy.consume("client:10.0.0.5", rate, burst)
    r2_blocked, _ = replica_2_proxy.consume("client:10.0.0.5", rate, burst)
    assert r1_blocked is False
    assert r2_blocked is False


def test_disabled_rate_limiting_setting():
    """When rate_limit_enabled is False, rate limiting is bypassed."""
    reset_rate_limit_store()
    settings = get_settings()
    original_setting = settings.rate_limit_enabled
    try:
        settings.rate_limit_enabled = False
        # Request more than default burst without throttling
        for _ in range(50):
            resp = run_middleware(path="/api/products")
            assert resp.status_code == 200
    finally:
        settings.rate_limit_enabled = original_setting
