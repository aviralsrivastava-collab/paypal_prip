import ipaddress
import logging
import math
import threading
import time
from typing import Dict, Optional, Set, Tuple

from fastapi import Request, status
from fastapi.responses import JSONResponse

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

# Endpoints exempt from rate limiting (health checks, monitoring, docs)
EXEMPT_PATH_PREFIXES = (
    "/api/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/favicon.ico",
)

# Sensitive financial, mutation, or webhook endpoints with stricter limits
SENSITIVE_PATH_PREFIXES = (
    "/api/checkout",
    "/api/webhooks",
    "/api/corrections",
)


class RateLimitStore:
    """Abstract interface for rate limiter storage."""

    def consume(self, key: str, rate: float, burst: int) -> Tuple[bool, float]:
        """
        Consumes 1 token for the specified key using a token-bucket algorithm.
        Returns:
            (is_allowed: bool, retry_after_seconds: float)
        """
        raise NotImplementedError

    def reset(self) -> None:
        """Resets all rate limit state."""
        raise NotImplementedError


class InMemoryRateLimitStore(RateLimitStore):
    """
    Thread-safe, in-memory token bucket rate limiter.
    Suitable for single-replica deployments, local development, and per-replica throttling.
    NOTE: In multi-replica deployments without sticky sessions, each replica tracks tokens
    independently. Global limits require reverse proxy (Nginx limit_req) or a shared store.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key -> (tokens: float, last_updated: float)
        self._buckets: Dict[str, Tuple[float, float]] = {}

    def consume(self, key: str, rate: float, burst: int) -> Tuple[bool, float]:
        now = time.monotonic()
        with self._lock:
            tokens, last_updated = self._buckets.get(key, (float(burst), now))
            elapsed = max(0.0, now - last_updated)
            tokens = min(float(burst), tokens + elapsed * rate)

            if tokens >= 1.0:
                tokens -= 1.0
                self._buckets[key] = (tokens, now)
                return True, 0.0
            else:
                self._buckets[key] = (tokens, now)
                retry_after = (1.0 - tokens) / rate if rate > 0 else 1.0
                return False, retry_after

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


class SharedRateLimitStore(RateLimitStore):
    """
    Shared rate limit store representing coordinated multi-replica storage.
    Can wrap a shared dict/memory segment or connect to a distributed backend like Redis.
    """

    def __init__(self, backend_store: Optional[RateLimitStore] = None) -> None:
        self._store = backend_store or InMemoryRateLimitStore()

    def consume(self, key: str, rate: float, burst: int) -> Tuple[bool, float]:
        return self._store.consume(key, rate, burst)

    def reset(self) -> None:
        self._store.reset()


_global_rate_limit_store: RateLimitStore = InMemoryRateLimitStore()


def get_rate_limit_store() -> RateLimitStore:
    """Returns the active rate limiter storage instance."""
    return _global_rate_limit_store


def set_rate_limit_store(store: RateLimitStore) -> None:
    """Overrides the active rate limiter storage instance (e.g. for testing or shared store injection)."""
    global _global_rate_limit_store
    _global_rate_limit_store = store


def reset_rate_limit_store() -> None:
    """Resets the active rate limiter storage."""
    _global_rate_limit_store.reset()


def is_trusted_proxy(host: str, trusted_proxies: Set[str]) -> bool:
    """Checks whether host matches any trusted proxy IP, hostname, or CIDR network."""
    if not host:
        return False
    host_clean = host.strip()
    if host_clean.lower() in trusted_proxies:
        return True
    try:
        ip = ipaddress.ip_address(host_clean)
        for tp in trusted_proxies:
            if "/" in tp:
                try:
                    if ip in ipaddress.ip_network(tp, strict=False):
                        return True
                except ValueError:
                    continue
            else:
                try:
                    if ip == ipaddress.ip_address(tp):
                        return True
                except ValueError:
                    continue
    except ValueError:
        pass
    return False


def get_client_ip(request: Request, trusted_proxies: Set[str]) -> str:
    """
    Derives client identity safely.
    Only trusts forwarding headers (X-Forwarded-For, X-Real-IP) if the direct peer
    (request.client.host) is an explicitly configured trusted proxy.
    Otherwise, strictly uses request.client.host.
    """
    direct_host = request.client.host if request.client else "127.0.0.1"

    if is_trusted_proxy(direct_host, trusted_proxies):
        # Extract from X-Forwarded-For first
        xff = request.headers.get("x-forwarded-for")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if parts:
                return parts[0]
        # Or X-Real-IP
        x_real_ip = request.headers.get("x-real-ip")
        if x_real_ip and x_real_ip.strip():
            return x_real_ip.strip()

    return direct_host


def classify_path(path: str) -> str:
    """
    Classifies path into 'exempt', 'sensitive', or 'default'.
    Health checks and API docs are exempt from rate limiting.
    Sensitive financial/mutation endpoints receive strict limits.
    """
    norm_path = path.rstrip("/")
    if not norm_path:
        norm_path = "/"

    for prefix in EXEMPT_PATH_PREFIXES:
        if norm_path == prefix or norm_path.startswith(prefix + "/"):
            return "exempt"

    for prefix in SENSITIVE_PATH_PREFIXES:
        if norm_path == prefix or norm_path.startswith(prefix + "/"):
            return "sensitive"

    return "default"


def check_rate_limit(
    request: Request,
    store: Optional[RateLimitStore] = None,
) -> Tuple[bool, float, int]:
    """
    Evaluates rate limit for incoming request.
    Returns:
        (is_allowed: bool, retry_after: float, burst_capacity: int)
    """
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return True, 0.0, 0

    category = classify_path(request.url.path)
    if category == "exempt":
        return True, 0.0, 0

    trusted_proxies = {p.strip().lower() for p in settings.trusted_proxies.split(",") if p.strip()}
    client_ip = get_client_ip(request, trusted_proxies)

    active_store = store or get_rate_limit_store()

    if category == "sensitive":
        rate = settings.rate_limit_sensitive_rate
        burst = settings.rate_limit_sensitive_burst
        key = f"sensitive:{client_ip}"
    else:
        rate = settings.rate_limit_default_rate
        burst = settings.rate_limit_default_burst
        key = f"default:{client_ip}"

    allowed, retry_after = active_store.consume(key, rate, burst)
    return allowed, retry_after, burst


def create_rate_limit_response(retry_after: float, burst: int) -> JSONResponse:
    """Constructs a compliant HTTP 429 Too Many Requests response."""
    retry_secs = max(1, math.ceil(retry_after))
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={
            "Retry-After": str(retry_secs),
            "X-RateLimit-Limit": str(burst),
            "X-RateLimit-Remaining": "0",
        },
        content={
            "detail": "Rate limit exceeded. Please try again later.",
            "retry_after_seconds": retry_secs,
        },
    )
