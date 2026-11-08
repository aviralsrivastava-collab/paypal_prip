# PRIP Production Release Checklist

## 1. Automated Verification Gates

- [x] **Backend Static Checks**:
  - `ruff check backend` passes with zero errors.
  - `mypy backend` passes with zero type errors.
  - `lint-imports` passes with zero boundary violations.
- [x] **Backend Automated Tests**:
  - All 137 Phase 1–7 regression tests passing.
  - All 34 Phase 8 production hardening tests passing.
- [x] **Frontend Checks**:
  - `npm run lint` passes without warnings.
  - `npm run lint:arch` passes architectural import boundaries.
  - `npm test` passes all Vitest unit and integration specs.
  - `npm run build` generates clean production distribution bundle.

---

## 2. Security & Compliance Gates

- [x] **No Real Money / Sandbox Strictly Enforced**:
  - `PAYPAL_ENVIRONMENT` must be `sandbox`.
  - Config fails closed if `live` is attempted.
- [x] **Zero Secret Leaks**:
  - Git history and repository contain zero credentials or private tokens.
  - `.env` files are ignored in `.gitignore`.
  - Structured logs automatically mask credentials, Bearer tokens, and sensitive keys.
- [x] **OIDC Production Authentication**:
  - Simulation headers (`X-Actor-ID`, `X-Actor-Role`) are strictly blocked in production.
  - Bearer tokens are cryptographically verified for signature, expiry, issuer, and audience.
- [x] **Multi-Merchant Tenancy Isolation**:
  - All entities (`Product`, `Order`, `StorefrontScan`, `CorrectionProposal`, `WebhookEvent`, `PaymentReconciliation`, `AuditEvent`) carry indexed `merchant_id`.
  - Cross-tenant access is rejected with HTTP 403 Forbidden.
- [x] **SSRF Defense**:
  - Storefront extraction validates URL scheme, blocks cloud metadata (`169.254.169.254`), and rejects private RFC1918 subnets.
- [x] **API Boundary Protection**:
  - Security headers present on all responses (CSP, HSTS, X-Content-Type-Options, X-Frame-Options).
  - 1MB max request body limit strictly enforced with HTTP 413.

---

## 3. Database & Operations Gates

- [x] **PostgreSQL Production Configuration**:
  - SQLite rejected when `APP_ENV=production`.
  - Connection pooling configured (`pool_size`, `max_overflow`, `pool_pre_ping=True`).
- [x] **Schema Migration Integrity**:
  - Alembic migration `008_multi_merchant_and_production_hardening` verified for both `upgrade` and `downgrade`.
- [x] **Operational Resilience**:
  - Standalone background worker (`backend.worker`) verified with graceful shutdown, distributed lease recovery, and periodic heartbeats.
  - Liveness (`/api/health/live`) and readiness (`/api/health/ready`) probes operational.
