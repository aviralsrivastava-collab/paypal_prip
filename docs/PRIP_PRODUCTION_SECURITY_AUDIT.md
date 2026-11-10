# PRIP — Production Security Architecture & Pre-Deployment Audit

**Document Version:** 1.0  
**Target Environment:** Free-Tier Production (Vercel Frontend + Render FastAPI + Neon PostgreSQL + Google OIDC)  
**Security Status:** PENDING AUTHORIZATION — PRE-DEPLOYMENT AUDIT COMPLETE

---

## 1. Executive Summary

This security audit evaluates the PRIP codebase for public demonstration readiness under a zero-cost, free-tier architecture. It assesses authentication boundaries, tenant isolation, secret management, database fail-closed mechanisms, and payment safety.

---

## 2. Critical Findings & Required Adaptations

### Finding 1: Google OIDC Issuer vs. JWKS Authority Domain Discrepancy
* **Issue:** In [`backend/core/security.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/core/security.py#L204-L211):
  ```python
  if settings.oidc_jwks_url and settings.oidc_issuer:
      parsed_jwks = urlparse(settings.oidc_jwks_url)
      parsed_issuer = urlparse(settings.oidc_issuer)
      if parsed_jwks.netloc.lower() != parsed_issuer.netloc.lower():
          raise HTTPException(
              status_code=status.HTTP_401_UNAUTHORIZED,
              detail="Security violation: Configured JWKS URL does not belong to trusted OIDC issuer authority.",
          )
  ```
* **Impact on Google OIDC:** Google hosts its authentication authority on `https://accounts.google.com`, but serves public JWKS certificates from `https://www.googleapis.com/oauth2/v3/certs`. Because their hostnames differ (`accounts.google.com` vs `www.googleapis.com`), PRIP's strict domain-matching guard will reject authentic Google JWKS keys.
* **Remediation:** Permit Google's verified signing endpoint by allowing `www.googleapis.com` when the configured issuer is `https://accounts.google.com`, or verify against Google's OpenID Connect discovery specification.

---

### Finding 2: Identity-to-Merchant Mapping for Public OIDC Providers
* **Issue:** Standard Google ID tokens contain `sub`, `email`, `email_verified`, `name`, but **no custom `merchant_id` claim**.
  In production, [`backend/core/security.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/core/security.py#L306-L310) strictly asserts:
  ```python
  if is_production and not merchant_id:
      raise HTTPException(
          status_code=status.HTTP_401_UNAUTHORIZED,
          detail="Missing required merchant identity claim ('merchant_id') in production token.",
      )
  ```
* **Remediation:** Implement server-side mapping in PRIP that maps the verified Google user email (e.g. `operator@gmail.com`) to a designated merchant tenant (e.g. `merchant_default`). Client-supplied headers like `X-Merchant-ID` must remain strictly disallowed for identity resolution.

---

### Finding 3: Frontend OIDC Authentication Absence
* **Issue:** The React frontend at `https://paypalprip.vercel.app` contains zero login buttons, token handling, or session storage. It currently sends unauthenticated fetch requests expecting the development fallback.
* **Remediation:** Integrate a lightweight OAuth 2.0 PKCE flow in the frontend header that prompts the merchant operator to sign in with Google, captures the ID token, and includes `Authorization: Bearer <id_token>` in all `ApiClient` requests.

---

### Finding 4: PostgreSQL Dialect Scheme Normalization
* **Issue:** Managed cloud providers like Neon supply connection strings starting with `postgresql://` or `postgres://`. SQLAlchemy 2.0 defaults to the uninstalled `psycopg2` driver unless explicitly prefixed with `postgresql+psycopg://`.
* **Remediation:** Automatically normalize `postgres://` or `postgresql://` to `postgresql+psycopg://` in `backend/core/database.py` and `backend/migrations/env.py`.

---

## 3. Security Invariant Verification Matrix

| Invariant | Code Verification | Production Enforcement |
| :--- | :--- | :--- |
| **No Anonymous Operator Access** | `backend/core/security.py` | In `APP_ENV=production`, missing Bearer token raises `HTTP 401`. |
| **No Client Header Impersonation** | `backend/core/security.py` | `X-Merchant-ID` is ignored when Bearer JWT is validated; identity is derived from cryptographically verified claims. |
| **Strict Multi-Merchant Isolation** | `backend/services/*` | Repository queries filter by `merchant_id`; `require_merchant_access` throws `HTTP 403` on cross-tenant mismatch. |
| **Fail-Closed Database** | `backend/core/database.py` | SQLite is prohibited in production; engine throws `RuntimeError` if PostgreSQL is unavailable. |
| **PayPal Sandbox Isolation** | `backend/core/config.py` | `paypal_environment: "sandbox"`. Production live payments are permanently blocked in MVP. |
| **Cryptographic Webhook Signatures** | `backend/services/webhook.py` | Verifies raw-body signature using PayPal SDK cert and transmission headers before persisting or processing. |
| **Append-Only Universal Audit** | `backend/services/audit.py` | Every proposal, approval, rejection, correction execution, and webhook event writes an immutable audit record. |
| **SSRF Prevention** | `backend/core/config.py` | Controlled storefront fetchers only contact URLs matching `controlled_storefront_base_url`. |

---

## 4. Production Security Recommendations

1. **Keep `APP_ENV=production` on Render:** Never set `APP_ENV=development` on any public deployment.
2. **Generate Strong Session Secret:** Use a cryptographically secure 64-character hex string for `SESSION_SECRET` (Render generates this automatically via Blueprint).
3. **Keep Database Credentials Isolated:** Neon connection strings must be entered strictly in Render's private environment variables; never add them to Git, frontend variables, or documentation.
4. **CORS Allowlist Lock:** `CORS_ALLOWED_ORIGINS` must contain strictly `https://paypalprip.vercel.app` (no `*` wildcards with credentials).
