# PRIP — Independent Production Release-Readiness Audit Report

**Document Version:** 1.0.0  
**Audit Date:** 2026-11-08  
**Auditor:** Independent Principal Security & Architecture Auditor  
**Scope:** Full-repository review of PRIP (PayPal Revenue Intelligence Platform) Phases 1–8  
**Audit Classification:** READ-ONLY Verification  
**Final Release Verdict:** **`NOT APPROVED FOR PRODUCTION RELEASE`**

---

## 1. Executive Summary & Release Verdict

An independent, rigorous, read-only production release-readiness audit was conducted across the PayPal Revenue Intelligence Platform (PRIP) codebase, database migrations, configuration profiles, security controls, automated test suites, and container infrastructure.

PRIP delivers an exceptional MVP vertical slice for discrepancy detection, deterministic policy-grounded human corrections, and PayPal Sandbox Orders v2 checkout preflight gating. The test suites (171 backend pytest tests, 30 frontend vitest tests), linters (`ruff`), static type checkers (`mypy`), and architectural boundary verifications (`import-linter`, `dependency-cruiser`) all pass with zero errors.

However, an in-depth audit of security perimeters and multi-tenant isolation identified critical vulnerabilities and architectural blockers that preclude authorization for production deployment:

1. **Broken Object Level Authorization (BOLA / IDOR) Across Core State Mutations**:
   While `merchant_id` was added to primary tables in migration 008, critical state-mutating endpoints—including correction proposal approval (`POST /api/corrections/proposals/{id}/approve`), rejection (`POST /api/corrections/proposals/{id}/reject`), cancellation (`POST /api/corrections/proposals/{id}/cancel`), execution (`POST /api/corrections/proposals/{id}/execute`), PayPal order capture (`POST /api/checkout/orders/{id}/capture`), order reconciliation (`POST /api/checkout/orders/{id}/reconcile`), and storefront price updates (`PUT /api/storefront/products/{sku}/price`)—**fail to verify that the authenticated actor's `merchant_id` matches the target entity's `merchant_id`**. An authenticated actor from Merchant A can approve, reject, execute, or cancel Merchant B's corrections, capture Merchant B's payments, and alter Merchant B's storefront pricing.
2. **Unauthenticated & Unscoped AI Diagnostic Endpoints**:
   `GET /api/diagnoses/{diagnosis_id}` and `GET /api/diagnoses/scan/{scan_id}` completely lack authentication dependencies (`Depends(get_current_actor)`) and tenancy filters, exposing proprietary discrepancy analyses to unauthenticated callers. Furthermore, `POST /api/diagnoses/scan/{scan_id}` fails to enforce that the caller belongs to the tenant owning the scan, and the `diagnoses` database table lacks a `merchant_id` foreign/tenant key.
3. **Incomplete Enterprise OIDC Implementation**:
   Token validation in `backend/core/security.py` strictly mandates symmetric HMAC-SHA256 (`HS256`) using a local shared secret. It lacks dynamic JSON Web Key Set (JWKS) discovery, asymmetric key verification (RS256/ES256), and cryptographic key rotation required by standard enterprise Identity Providers (Okta, Auth0, Azure AD, Keycloak). Additionally, JWTs missing the `merchant_id` claim default to `"merchant_default"` rather than failing closed.
4. **Commingled Audit Trail**:
   `AuditEventCreate` and `AuditRepository.append` do not accept or persist `merchant_id`, causing all application and worker audit records to fall back to `"merchant_default"`. Compliance audits cannot be verified on a per-tenant boundary.
5. **Database Engine Fallback & Startup Race Hazards**:
   `backend/core/database.py` catches database initialization exceptions and silently falls back to local SQLite, violating production fail-closed invariants. In addition, `backend/api/main.py` executes `Base.metadata.create_all()` on FastAPI startup, introducing DDL race conditions in multi-replica container environments.

### Release Verdict
```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║                    NOT APPROVED FOR PRODUCTION RELEASE                       ║
║                                                                              ║
║   Critical multi-tenant authorization gaps (IDOR/BOLA) and enterprise OIDC   ║
║   deficiencies must be remediated and verified before production deployment. ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## 2. Audit Baseline & Repository Provenance

- **Repository Root:** `c:\Users\HP\OneDrive\Desktop\paypal`
- **Active Git Branch:** `master` (working tree cleanly inspected)
- **Architecture Structure:** Modular monolith adhering to 10 top-level directories:
  - `.github/`, `.agents/`, `backend/`, `frontend/`, `contracts/`, `database/`, `docs/`, `scripts/`, `tests/`, `infra/`
- **Reviewed Architectural Records:**
  - `docs/ARCHITECTURE.md`, `docs/PRODUCT_SPEC.md`, `docs/DECISIONS.md` (ADR-001 through ADR-011)
  - Completion Reports: Phase 1 through Phase 8 (`docs/PHASE_*_COMPLETION_REPORT.md`)
  - Operational Runbooks: `docs/PRODUCTION_DEPLOYMENT_RUNBOOK.md`, `docs/DISASTER_RECOVERY_RUNBOOK.md`, `docs/OPERATIONS_RUNBOOK.md`, `docs/SECURITY_THREAT_MODEL.md`

---

## 3. Automated Quality Gate & Verification Results

The automated quality gates were executed locally in a strictly read-only mode. All automated checks succeeded:

| Gate | Tool | Command / Target | Result | Evidence / Details |
| :--- | :--- | :--- | :---: | :--- |
| **Backend Unit & Regression** | `pytest` | `pytest -q` (171 tests) | **PASSED** | 171 passed in 10.67s |
| **Frontend Unit & Component** | `vitest` | `npm test -- --run` (30 tests) | **PASSED** | 30 passed in 8.81s |
| **Backend Python Linter** | `ruff` | `ruff check backend` | **PASSED** | All checks passed, 0 errors |
| **Backend Static Type Checker** | `mypy` | `mypy backend` | **PASSED** | Success: 0 issues in 121 source files |
| **Backend Architecture Contracts** | `import-linter` | `lint-imports` | **PASSED** | 6 of 6 layer contracts kept |
| **Frontend Architecture Boundary** | `dependency-cruiser`| `npm run lint:arch` | **PASSED** | 0 dependency violations found |
| **Frontend Production Build** | `vite` | `npm run build` | **PASSED** | `dist/assets/index-q6sv_1Dn.js` (238.63 kB) |
| **Repository Harness Check** | PowerShell | `scripts/harness-check.ps1` | **PASSED** | Structural verification clean |

---

## 4. Findings Classification Matrix

Findings are classified into six severity categories:
- **CRITICAL**: Immediate security or integrity vulnerability requiring remediation prior to production.
- **HIGH**: Material defect, missing security control, or architecture gap that introduces significant operational or compliance risk.
- **MEDIUM**: Defensive inconsistency, reliability shortcoming, or operational fragility.
- **LOW**: Minor optimization or code hygiene improvement.
- **VERIFIED**: Invariant or security feature verified as correctly implemented.
- **NOT VERIFIED**: Component or capability documented or simulated, but not executed against live production infrastructure.

### Summary of Findings Count
- **CRITICAL:** 1
- **HIGH:** 2
- **MEDIUM:** 3
- **LOW:** 2
- **VERIFIED:** 11
- **NOT VERIFIED:** 3

---

### Detailed Findings

#### Finding SEC-TENANT-001 — Broken Object Level Authorization (BOLA/IDOR) on Core State Mutations
- **Severity:** `CRITICAL`
- **Location:**
  - `backend/api/corrections.py` (lines 106–220)
  - `backend/services/proposal.py` (lines 198–370)
  - `backend/services/remediation.py` (lines 47–85)
  - `backend/api/checkout.py` (lines 76–134)
  - `backend/services/payment.py` (lines 62–105, 317–365)
  - `backend/api/storefront.py` (lines 30–51)
  - `backend/services/storefront.py` (lines 34–98)
- **Description:**
  Migration 008 introduced `merchant_id` to `products`, `orders`, `storefront_products`, `storefront_scans`, `correction_proposals`, and `payment_reconciliations`. However, the route handlers and underlying service methods do not verify tenant ownership on write operations. Specifically:
  1. `POST /api/corrections/proposals/{proposal_id}/approve`: Resolves `proposal` by ID and executes approval without asserting `current_actor.merchant_id == proposal.merchant_id`.
  2. `POST /api/corrections/proposals/{proposal_id}/reject`: Does not assert `current_actor.merchant_id == proposal.merchant_id`.
  3. `POST /api/corrections/proposals/{proposal_id}/cancel`: Does not assert `current_actor.merchant_id == proposal.merchant_id`.
  4. `POST /api/corrections/proposals/{proposal_id}/execute`: Calls `RemediationService.execute_correction()`, which does not assert `current_actor.merchant_id == proposal.merchant_id`.
  5. `POST /api/checkout/orders/{order_id}/capture`: Calls `PaymentService.capture_payment()`, resolving the order by ID without checking `order.merchant_id == current_actor.merchant_id`.
  6. `POST /api/checkout/orders/{order_id}/reconcile`: Calls `PaymentService.reconcile_payment()`, resolving the order by ID without checking `order.merchant_id == current_actor.merchant_id`.
  7. `PUT /api/storefront/products/{sku}/price`: Calls `StorefrontService.update_price()`, which updates `StorefrontProduct` without validating `storefront_product.merchant_id == current_actor.merchant_id`.
- **Security Impact:**
  An authenticated merchant user belonging to Merchant A can execute or cancel Merchant B's correction proposals, capture Merchant B's orders, trigger payment reconciliations on Merchant B's transactions, and mutate Merchant B's storefront prices.
- **Required Remediation:**
  Enforce `require_merchant_access(current_actor, entity.merchant_id)` immediately after fetching the entity in both the API route handlers and service layers before executing state transitions.

---

#### Finding SEC-AUTH-001 — OIDC Token Validation Lacks RS256/JWKS Discovery & Asymmetric Key Rotation
- **Severity:** `HIGH`
- **Location:** `backend/core/security.py` (lines 68–175), `backend/core/config.py` (lines 20–25)
- **Description:**
  `verify_oidc_token` in `backend/core/security.py` strictly validates only symmetric HMAC-SHA256 (`HS256`) signatures using a single pre-shared secret (`settings.oidc_jwt_secret`). It explicitly rejects any algorithm other than `HS256` (lines 92–96). While `oidc_jwks_url` exists in `backend/core/config.py`, there is no HTTP client, JWKS discovery fetcher, caching layer, or RS256 asymmetric signature verification logic. Furthermore, if a validated JWT does not supply a `merchant_id` claim, `get_current_actor` defaults the actor context to `"merchant_default"` (line 205) rather than failing closed.
- **Security Impact:**
  Standard enterprise Identity Providers (Auth0, Okta, Keycloak, Azure AD, Google Workspace) issue RS256/ES256 asymmetric signatures rotated dynamically via JWKS endpoints. PRIP cannot federate with standard enterprise IdPs in its current state. Defaulting missing `merchant_id` claims to `"merchant_default"` creates tenancy confusion if tokens lack explicit tenant metadata.
- **Required Remediation:**
  1. Integrate `python-jose` or `PyJWT` with cryptography backends to support RS256 asymmetric validation via cached JWKS retrieval.
  2. Implement `kid` (Key ID) header lookup with background JWKS key refresh.
  3. Fail closed (HTTP 401/403) when an enterprise production JWT lacks an explicit `merchant_id` claim.

---

#### Finding SEC-TENANT-002 — Unauthenticated & Cross-Tenant Exposure of AI Diagnoses
- **Severity:** `HIGH`
- **Location:** `backend/api/diagnoses.py` (lines 21–96), `backend/models/diagnosis.py` (lines 10–40)
- **Description:**
  `GET /api/diagnoses/{diagnosis_id}` and `GET /api/diagnoses/scan/{scan_id}` do not include `current_actor: AuthenticatedActor = Depends(get_current_actor)` and contain zero tenancy checks. Any unauthenticated caller can query and view all diagnostic analyses. Furthermore, `POST /api/diagnoses/scan/{scan_id}` accepts `current_actor` but does not verify that `current_actor.merchant_id == scan.merchant_id`. Finally, the `diagnoses` table was omitted from migration 008 and lacks a `merchant_id` column.
- **Security Impact:**
  Unauthenticated information disclosure of catalog discrepancies, extraction snippets, pricing differentials, and AI remediation recommendations. Cross-tenant leakage of diagnostic reports.
- **Required Remediation:**
  1. Add `merchant_id` column and index to `diagnoses` table via Alembic migration.
  2. Require `current_actor = Depends(get_current_actor)` on all diagnosis endpoints.
  3. Validate `require_merchant_access(current_actor, scan.merchant_id)` prior to generating or returning diagnosis data.

---

#### Finding SEC-TENANT-003 — Commingled Audit Trail Lacking Per-Tenant Scoping
- **Severity:** `MEDIUM`
- **Location:** `backend/schemas/audit.py` (lines 7–18), `backend/repositories/audit.py` (lines 17–55)
- **Description:**
  Migration 008 added `merchant_id` with `server_default="merchant_default"` to the `audit_events` table. However, `AuditEventCreate` lacks a `merchant_id` field, and `AuditRepository.append` does not assign `merchant_id`. Consequently, all audit logs generated by services and workers are persisted with the default `"merchant_default"` tenant ID. Furthermore, `AuditRepository.list_by_entity` and `AuditRepository.list_by_correlation_id` do not accept or filter by `merchant_id`.
- **Security Impact:**
  Audit logs are commingled across all merchants, preventing legally defensible, per-tenant compliance reporting.
- **Required Remediation:**
  Add `merchant_id: str` to `AuditEventCreate`, propagate `current_actor.merchant_id` through all `AuditService.log_event()` invocations, and enforce tenant filtering on audit retrieval queries.

---

#### Finding SEC-TENANT-004 — Cross-Tenant Visibility on Operational Management Endpoints
- **Severity:** `MEDIUM`
- **Location:** `backend/api/operations.py` (lines 38–200)
- **Description:**
  Endpoints `/api/operations/overview`, `/api/operations/webhooks/stuck`, `/api/operations/reconciliations/pending`, and `/api/operations/reconciliations/history` enforce `require_operator_role` (accepting any user with `merchant_admin`). However, the database queries in `WebhookEventRepository` and `PaymentReconciliationRepository` execute global queries without filtering by `current_actor.merchant_id`.
- **Security Impact:**
  A merchant administrator from Tenant A can view queue depths, webhook failures, and pending payment reconciliations belonging to Tenant B.
- **Required Remediation:**
  Scope all operational query repositories by `merchant_id`, or restrict operational endpoints strictly to platform superadministrators (`role == "superadmin"`).

---

#### Finding SEC-OPS-001 — Silent Database Engine Fallback to SQLite on Initialization Error
- **Severity:** `MEDIUM`
- **Location:** `backend/core/database.py` (lines 35–39)
- **Description:**
  `backend/core/database.py` wraps engine creation in a broad exception handler:
  ```python
  try:
      engine = create_app_engine(settings.database_url)
  except Exception:
      engine = create_engine("sqlite:///./prip_demo.db", connect_args={"check_same_thread": False})
  ```
  If connection pooling or PostgreSQL driver initialization fails during production startup, the process silently falls back to local SQLite instead of terminating immediately.
- **Security Impact:**
  Undermines `validate_production_settings()`, which strictly rejects SQLite in production. A production service could run against an ephemeral SQLite database without alerting operators.
- **Required Remediation:**
  Remove the silent fallback in non-development environments; raise the exception and terminate the process if `settings.app_env.lower() == "production"`.

---

#### Finding SEC-OPS-002 — `create_all` Executed on FastAPI Application Startup
- **Severity:** `MEDIUM`
- **Location:** `backend/api/main.py` (lines 114–117)
- **Description:**
  `Base.metadata.create_all(bind=engine)` is invoked unconditionally within `@app.on_event("startup")`.
- **Security Impact:**
  In a production cluster running multiple backend replicas, concurrent execution of `create_all()` causes DDL race conditions, table locks, and bypasses Alembic schema version tracking.
- **Required Remediation:**
  Remove `create_all()` from `backend/api/main.py`. Ensure schema creation and updates are executed solely via the dedicated migration job (`infra/docker-compose.yml` `migration` container running `alembic upgrade head`).

---

#### Finding SEC-SSRF-001 — Storefront Extraction URL Validation Lacks DNS Resolution & Transport Pinning
- **Severity:** `LOW / INFORMATIONAL`
- **Location:** `backend/integrations/storefront/extractor.py` (lines 14–71)
- **Description:**
  `is_safe_storefront_url` inspects URL schemes, strings, and IP address literals to reject private/loopback/cloud metadata ranges. However, it does not resolve domain names to IP addresses prior to validation if `allowed_base` is unconfigured, which would leave the system vulnerable to DNS rebinding or redirect bypass.
- **Mitigation Status:**
  Currently mitigated: `StorefrontExtractor.extract_from_storefront` reads directly from the controlled demo database (`StorefrontRepository(session).get_by_sku(sku)`) and does not issue outbound HTTP network requests. If outbound HTTP requests are introduced in the future, socket-level IP pinning and HTTP client redirect restrictions must be enforced.

---

#### Finding OPS-CONCURR-001 — Webhook Queue Worker Uses Optimistic Updates Instead of `SKIP LOCKED`
- **Severity:** `LOW`
- **Location:** `backend/repositories/webhook.py` (lines 56–115)
- **Description:**
  `claim_eligible_event` selects the first eligible row (`SELECT ... LIMIT 1`) and executes a conditional update (`UPDATE ... WHERE id = candidate_id AND status = candidate_status`). Under high worker concurrency on PostgreSQL, multiple workers select the same candidate row, causing row lock contention where only one worker succeeds and others receive `rowcount = 0`.
- **Impact:**
  Safe from duplicate execution, but causes contention under high concurrency.
- **Required Remediation:**
  Update PostgreSQL query dialect to use `SELECT ... FOR UPDATE SKIP LOCKED` when running on PostgreSQL engines.

---

### Verified Controls (Passing Audited Invariants)

| Control ID | Domain | Verified Invariant | Code Evidence |
| :--- | :--- | :--- | :--- |
| **VERIFIED-PAY-001** | Payments | Decimal arithmetic & accurate fee parsing | `backend/integrations/paypal/client.py` lines 242–246; fees/net amounts parsed directly from PayPal capture `seller_receivable_breakdown` without hardcoded fees. |
| **VERIFIED-PAY-002** | Payments | Remote idempotency via `PayPal-Request-Id` | `backend/integrations/paypal/client.py` lines 124, 210; client passes header for order creation and capture. |
| **VERIFIED-PAY-003** | Payments | Ambiguous capture transitions to `UNKNOWN` | `backend/services/payment.py` lines 112–165; timeouts transition payment status to `UNKNOWN` with `reconciliation_status = RECONCILIATION_REQUIRED`; blind retries are blocked. |
| **VERIFIED-PAY-004** | Checkout | Preflight discrepancy gating | `backend/policies/checkout_policy.py` lines 145–205; preflight rereads catalog price, storefront price, and inspection state; blocks checkout if prices differ or issues are unresolved. |
| **VERIFIED-PAY-005** | Webhooks | Raw cryptographic signature verification | `backend/api/webhooks.py` lines 27–29 & `backend/services/webhook.py` lines 53–64; raw body bytes preserved and verified against PayPal's official REST endpoint. |
| **VERIFIED-PAY-006** | Payments | Sandbox isolation & live credential rejection | `backend/core/config.py` lines 72–76 & `backend/integrations/paypal/client.py` lines 35–39; strictly rejects `PAYPAL_ENVIRONMENT != "sandbox"`. |
| **VERIFIED-DATA-001** | Privacy | Zero PAN / CVV persistence | Verified across all models and repositories; PRIP never collects, transmits, or persists credit card numbers or security codes. |
| **VERIFIED-DATA-002** | Observability | Automated secret & token log masking | `backend/core/logging.py` lines 13–35; `MaskingFormatter` strips passwords, client secrets, and bearer tokens from logs. |
| **VERIFIED-SEC-001** | HTTP | Request size guards & security headers | `backend/api/main.py` lines 24–45, 57–66; enforces 1MB body limit (HTTP 413) and CSP, HSTS, X-Frame-Options (`DENY`), and X-Content-Type-Options (`nosniff`). |
| **VERIFIED-INFRA-001**| Containers | Non-root users & network segregation | `infra/Dockerfile.backend` (lines 19–30; `appuser` UID 10001) & `infra/docker-compose.yml` (`prip-internal` bridge isolates PostgreSQL). |
| **VERIFIED-TEST-001** | Quality | Regression & architectural test integrity | 171 backend tests pass, 30 frontend tests pass, 6/6 architectural layer contracts kept (`import-linter`). |

---

### Items Not Verified (Simulated or Mapped to MVP Boundaries)

| Item ID | Description | Reason Not Verified in Local Read-Only Audit |
| :--- | :--- | :--- |
| **NOT-VERIFIED-001** | Live PostgreSQL 16 Cluster Concurrency | Local tests run against in-process SQLite. PostgreSQL connection pooling and concurrency lock behavior were audited via source code and configuration, but not executed against a distributed PostgreSQL cluster. |
| **NOT-VERIFIED-002** | Live PayPal Sandbox API Network Roundtrip | Automated tests use `MockPayPalClient` for hermetic CI. Live network roundtrips to `api-m.sandbox.paypal.com` were verified in Phase 6/7 testing but not re-triggered during this read-only audit. |
| **NOT-VERIFIED-003** | Live Enterprise IdP Federation | OIDC verification was validated using locally signed HS256 tokens; live federation with external Okta/Auth0 JWKS endpoints was not executed. |

---

## 5. Traceability Matrix against Non-Negotiable Invariants & ADRs

| Reference | Mandated Invariant | Audit Finding / Status | Compliance |
| :--- | :--- | :--- | :---: |
| **`AGENTS.md`** | Seeded catalog is MVP source of truth | Verified: Catalog records drive inspection expected values. | **COMPLIANT** |
| **`AGENTS.md`** | 4-state inspection model (`ISSUE_DETECTED`, `VERIFIED_NO_ISSUE`, `BLOCKED_UNKNOWN`, `NOT_TESTED`) | Verified: Engine preserves exact states; unknown never collapses into clean. | **COMPLIANT** |
| **`AGENTS.md`** | AI is strictly explanatory; cannot mutate state or approve | Verified: AI output policy-validated; zero mutation or payment authority. | **COMPLIANT** |
| **`AGENTS.md`** | Multi-merchant tenant isolation | **FAILED: BOLA/IDOR on approve/reject/execute/capture/reconcile (SEC-TENANT-001).** | **NON-COMPLIANT** |
| **`AGENTS.md`** | PayPal Sandbox is not real revenue | Verified: No claims of recovered revenue; capture tracked honestly. | **COMPLIANT** |
| **`AGENTS.md`** | Raw body cryptographic webhook verification | Verified: Exact raw request body passed to PayPal verification endpoint. | **COMPLIANT** |
| **`AGENTS.md`** | Ambiguous captures transition to `UNKNOWN` | Verified: Ambiguous captures set `UNKNOWN`; reconciliation required. | **COMPLIANT** |
| **ADR-001** | Modular monolith with clean domain boundaries | Verified: 6/6 `import-linter` architectural contracts kept. | **COMPLIANT** |
| **ADR-007** | Storefront extraction outside DB transactions | Verified: Extraction finishes prior to `atomic_transaction` opening. | **COMPLIANT** |
| **ADR-009** | Human-authorized corrections & reinspection | Verified: Approvals require merchant actor; automatic post-apply reinspection. | **COMPLIANT** |
| **ADR-010** | Preflight discrepancy gate blocks checkout | Verified: Checkout preflight independently rereads catalog and storefront. | **COMPLIANT** |
| **ADR-011** | Production OIDC & Multi-Merchant Hardening | **FAILED: Missing RS256/JWKS (SEC-AUTH-001) & Cross-tenant BOLA (SEC-TENANT-001).** | **NON-COMPLIANT** |

---

## 6. Remediation Roadmap & Blocking Items Checklist

To achieve a production-ready status (`PRODUCTION RELEASE APPROVED`), the engineering team must complete the following remediation steps in order:

### Phase A: Remediate Broken Object Level Authorization (Blocking)
- [x] Add `require_merchant_access(current_actor, proposal.merchant_id)` to `approve_proposal`, `reject_proposal`, `cancel_proposal`, and `execute_correction` in `backend/api/corrections.py`, `backend/services/proposal.py`, and `backend/services/remediation.py`. (Remediated: SEC-TENANT-001)
- [x] Add `require_merchant_access(current_actor, order.merchant_id)` to `capture_order` and `reconcile_order` in `backend/api/checkout.py` and `backend/services/payment.py`. (Remediated: SEC-TENANT-001)
- [x] Add `require_merchant_access(current_actor, storefront_product.merchant_id)` to `update_storefront_price` in `backend/api/storefront.py` and `backend/services/storefront.py`. (Remediated: SEC-TENANT-001)
- [x] Write automated regression tests asserting HTTP 403 Forbidden when Tenant A attempts to approve, reject, execute, or cancel Tenant B's proposal, or capture/reconcile Tenant B's order. (Remediated: `backend/tests/test_security_remediation.py`)

### Phase B: Secure AI Diagnoses & Database Schema (Blocking)
- [x] Create Alembic migration `009_tenant_ownership_and_audit_attribution.py` adding `merchant_id` to `diagnoses`, `evidence_items`, `payment_captures`, and `demo_inventory_reservations`. (Remediated: SEC-TENANT-002)
- [x] Require `current_actor: AuthenticatedActor = Depends(get_current_actor)` on `GET /api/diagnoses/{id}` and `GET /api/diagnoses/scan/{scan_id}` in `backend/api/diagnoses.py`. (Remediated: SEC-TENANT-002)
- [x] Assert `require_merchant_access(current_actor, scan.merchant_id)` on all diagnosis operations. (Remediated: SEC-TENANT-002)

### Phase C: Implement Enterprise OIDC JWKS & RS256 Token Verification (Blocking)
- [x] Replace custom HMAC-SHA256 signature logic with `pyjwt[crypto]` with cryptography support. (Remediated: SEC-AUTH-001)
- [x] Implement dynamic JWKS key discovery and caching using `settings.oidc_jwks_url`, supporting RS256/ES256 and key rotation. (Remediated: SEC-AUTH-001)
- [x] Enforce that tokens without an explicit `merchant_id` claim fail closed with HTTP 401 Unauthorized in production environments. (Remediated: SEC-AUTH-001)

### Phase D: Operational & Database Hardening (Required)
- [x] Remove `Base.metadata.create_all(bind=engine)` from `backend/api/main.py` startup event in production. (Remediated: SEC-OPS-002)
- [x] Remove silent SQLite fallback in `backend/core/database.py` when `settings.app_env.lower() == "production"`. (Remediated: SEC-OPS-001)
- [x] Add `merchant_id` to `AuditEventCreate` and `AuditRepository.append` to prevent audit log commingling. (Remediated: SEC-TENANT-003)
- [x] Filter operational metrics and queues in `backend/api/operations.py` by `current_actor.merchant_id`. (Remediated: SEC-TENANT-004)

---

## 7. Final Formal Verdict Statement

Based on the evidence discovered during this independent read-only audit:

The PayPal Revenue Intelligence Platform (PRIP) demonstrates exemplary engineering craftsmanship in its domain models, test coverage, static analysis, PayPal Orders v2 integration, and deterministic state transitions. 

However, because the audited baseline contained multi-tenant authorization gaps, exposed AI diagnoses unauthenticated, commingles audit events, and lacked dynamic JWKS discovery, the initial audit verdict was:

**`NOT APPROVED FOR PRODUCTION RELEASE`**

### Post-Audit Remediation Sprint Status (2026-11-08)
All findings (`SEC-TENANT-001`, `SEC-TENANT-002`, `SEC-AUTH-001`, `SEC-TENANT-003`, `SEC-TENANT-004`, `SEC-OPS-001`, `SEC-OPS-002`) have been fully remediated in the Production Security Remediation Sprint.
Verification evidence is documented in `docs/PRIP_SECURITY_REMEDIATION_REPORT.md` and confirmed by 179 passing backend tests (including `backend/tests/test_security_remediation.py`), 30 frontend vitest tests, strict mypy typing, ruff linting, and import-linter contract compliance.

The codebase is submitted for independent re-audit under status:
**`REMEDIATION COMPLETE — READY FOR INDEPENDENT RE-AUDIT`**
