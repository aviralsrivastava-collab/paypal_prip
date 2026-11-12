import sys
import types
import uuid
from pathlib import Path
from typing import Any

# If 'backend' is not in sys.modules (e.g. deployed with root: "backend"),
# bind the current package directory to the 'backend' namespace.
if "backend" not in sys.modules:
    try:
        import backend  # noqa: F401
    except ModuleNotFoundError:
        _backend_dir = str(Path(__file__).resolve().parent.parent)
        _backend_mod = types.ModuleType("backend")
        _backend_mod.__path__ = [_backend_dir]
        _backend_mod.__file__ = str(Path(_backend_dir) / "__init__.py")
        sys.modules["backend"] = _backend_mod

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Ensure models are imported so Base metadata is populated
import backend.models  # noqa: F401
from backend.api.auth import router as auth_router
from backend.api.chat import router as ai_router
from backend.api.checkout import router as checkout_router
from backend.api.corrections import router as corrections_router
from backend.api.diagnoses import router as diagnoses_router
from backend.api.health import router as health_router
from backend.api.operations import router as operations_router
from backend.api.products import router as products_router
from backend.api.scans import router as scans_router
from backend.api.storefront import router as storefront_router
from backend.api.webhooks import router as webhooks_router
from backend.core.config import get_settings
from backend.core.database import Base, engine
from backend.core.logging import correlation_id_ctx, merchant_id_ctx
from backend.core.rate_limit import check_rate_limit, create_rate_limit_response

settings = get_settings()

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}


def apply_security_headers(headers: Any, correlation_id: str) -> Any:
    """Applies mandatory production security and tracing headers to response headers."""
    headers["X-Correlation-ID"] = correlation_id
    headers.update(SECURITY_HEADERS)
    return headers


def validate_request_size(content_length: int | None, max_bytes: int = 1_048_576) -> bool:
    """Returns False if request body exceeds maximum allowed size (1MB)."""
    if content_length is not None and content_length > max_bytes:
        return False
    return True


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="PRIP — PayPal Revenue Intelligence Platform Backend API",
)


@app.middleware("http")
async def security_and_tracing_middleware(request: Request, call_next):
    # 1. Max request body size guard (1MB limit)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if not validate_request_size(int(content_length), settings.max_request_body_bytes):
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "Request body exceeds maximum allowed size (1MB)."},
                )
        except ValueError:
            pass

    # 2. Correlation ID & Tenancy Context
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    token_cid = correlation_id_ctx.set(correlation_id)
    merchant_id = request.headers.get("X-Merchant-ID") or "merchant_default"
    token_mid = merchant_id_ctx.set(merchant_id)

    request.state.correlation_id = correlation_id
    request.state.merchant_id = merchant_id

    # 3. Rate limiting guard (GAP-01)
    allowed, retry_after, burst = check_rate_limit(request)
    if not allowed:
        try:
            response = create_rate_limit_response(retry_after, burst)
            apply_security_headers(response.headers, correlation_id)
            return response
        finally:
            correlation_id_ctx.reset(token_cid)
            merchant_id_ctx.reset(token_mid)

    try:
        response = await call_next(request)
    finally:
        correlation_id_ctx.reset(token_cid)
        merchant_id_ctx.reset(token_mid)

    # 4. Security headers enforcement
    apply_security_headers(response.headers, correlation_id)
    return response


# CORS middleware for local frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(health_router, prefix="/api")
app.include_router(auth_router)
app.include_router(ai_router)
app.include_router(products_router)
app.include_router(storefront_router)
app.include_router(scans_router)
app.include_router(diagnoses_router)
app.include_router(corrections_router)
app.include_router(checkout_router)
app.include_router(webhooks_router)
app.include_router(operations_router)


@app.get("/", tags=["Root"])
def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "online",
        "docs_url": "/docs",
        "health_url": "/api/health",
        "webhook_url": "/api/webhooks/paypal",
    }


@app.post("/", tags=["Root"])
def root_post():
    """
    Diagnostic handler for webhooks mistakenly sent to the root URL.
    Returns HTTP 400 with actionable instructions to register '/api/webhooks/paypal'.
    """
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "INCORRECT_WEBHOOK_URL",
            "message": "PayPal webhook notifications must be delivered to '/api/webhooks/paypal', not root '/'.",
            "registered_webhook_endpoint": "/api/webhooks/paypal",
        },
    )


@app.on_event("startup")
def startup_event():
    """Create tables on startup ONLY in development/testing. Production relies strictly on Alembic migrations."""
    if settings.app_env.lower() != "production":
        Base.metadata.create_all(bind=engine)
