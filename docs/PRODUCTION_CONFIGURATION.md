# PRIP Production Configuration Reference

## 1. Configuration Overview

PRIP follows 12-factor application methodology, reading configuration strictly from environment variables validated via `pydantic-settings`. In production mode (`APP_ENV=production`), the application strictly validates settings on startup and fails closed if any insecure default or unapproved environment is detected.

---

## 2. Environment Variables Specification

| Variable Name | Type | Production Requirement | Default | Description |
|---|---|---|---|---|
| `APP_ENV` | string | Mandatory (`production`) | `development` | Operating environment (`development`, `test`, `production`). |
| `DATABASE_URL` | string | Mandatory (PostgreSQL) | `sqlite:///./prip_demo.db` | Primary relational database URL. Rejects `sqlite` in production. |
| `DATABASE_POOL_SIZE` | integer | Recommended: 10-30 | `10` | SQLAlchemy connection pool size. |
| `DATABASE_MAX_OVERFLOW` | integer | Recommended: 20-50 | `20` | Max temporary connection overflow above pool size. |
| `DATABASE_POOL_TIMEOUT` | float | Recommended: 30.0 | `30.0` | Seconds to wait before raising connection timeout error. |
| `SESSION_SECRET` | string | Mandatory (High entropy) | Insecure default | Session signing key. Production fails closed on default. |
| `OIDC_ISSUER` | string | Mandatory in prod | `https://auth.prip.local` | OIDC issuer URL (`iss` claim validation). |
| `OIDC_CLIENT_ID` | string | Mandatory in prod | `prip-api` | OIDC client identifier (`aud` claim validation). |
| `OIDC_JWKS_URL` | string | Mandatory in prod | `""` | Authoritative OIDC JWKS public key endpoint (RS256/ES256 verification & key rotation). Must belong to `OIDC_ISSUER` domain authority. |
| `OIDC_JWT_SECRET` | string | Dev/Test only | Development secret | HMAC-SHA256 signing secret. Strictly rejected in production mode (`APP_ENV=production`). |
| `PAYPAL_ENVIRONMENT` | string | Strictly `sandbox` | `sandbox` | PayPal API tier. Production strictly rejects `live`. |
| `PAYPAL_BASE_URL` | string | `https://api-m.sandbox.paypal.com` | Sandbox URL | PayPal REST API endpoint. |
| `PAYPAL_CLIENT_ID` | string | Mandatory in prod | `""` | PayPal Sandbox OAuth client ID. |
| `PAYPAL_CLIENT_SECRET` | string | Mandatory in prod | `""` | PayPal Sandbox OAuth client secret. |
| `PAYPAL_WEBHOOK_ID` | string | Mandatory in prod | `WH-MOCK-SANDBOX-001`| Registered PayPal Sandbox webhook listener ID. |
| `CONTROLLED_STOREFRONT_BASE_URL` | string | Mandatory in prod | `http://localhost:3000` | Authorized storefront root for SSRF defense allowlisting. |
| `WORKER_POLL_INTERVAL_SECONDS` | float | Recommended: 5.0 | `5.0` | Background worker polling interval when queue is empty. |
| `WORKER_BATCH_SIZE` | integer | Recommended: 10 | `10` | Webhook events claimed per worker tick iteration. |
| `WORKER_LEASE_SECONDS` | integer | Recommended: 60 | `60` | Duration of distributed lease lock on webhook events. |
| `MAX_REQUEST_BODY_BYTES` | integer | Recommended: 1048576 | `1048576` (1MB) | Maximum allowed HTTP request body size (DoS protection). |

---

## 3. Startup Fail-Closed Validation Rules

The `Settings.validate_production_settings()` method is executed at application bootstrap. It enforces the following invariants:

1. **Rejection of SQLite**: If `APP_ENV=production` and `DATABASE_URL` starts with `sqlite`, startup raises `ValueError` immediately.
2. **Rejection of Default Secret**: If `SESSION_SECRET` matches the hardcoded development default, startup aborts.
3. **Rejection of PayPal Live**: If `PAYPAL_ENVIRONMENT != "sandbox"`, startup aborts to protect against unintended real-money transactions.
4. **Enforcement of OIDC Credentials**: If `OIDC_ISSUER` or `OIDC_CLIENT_ID` are missing, startup aborts.
5. **Enforcement of PayPal Sandbox Credentials**: If `PAYPAL_CLIENT_ID` or `PAYPAL_CLIENT_SECRET` are unset, startup aborts.
6. **Database Engine Fail-Closed (SEC-OPS-001)**: If PostgreSQL database engine initialization or connection fails in production, startup raises `RuntimeError` and terminates immediately. Silent SQLite fallback in production is strictly prohibited.
7. **Strict Asymmetric OIDC Verification (SEC-AUTH-001)**: In production, tokens must use RS256 or ES256 and include a valid `kid` header matching cached JWKS keys from `OIDC_JWKS_URL`. Tokens using `HS256` or `none` are rejected with HTTP 401.
8. **Mandatory Merchant Identity Claim (SEC-AUTH-001)**: Production tokens must include an explicit `merchant_id` claim. Fallback to `merchant_default` in production is disabled.
9. **No Schema Auto-Creation on Boot (SEC-OPS-002)**: `Base.metadata.create_all` is disabled on API startup in production; database migrations must be executed via `alembic upgrade head` in a separate pre-deployment job.
