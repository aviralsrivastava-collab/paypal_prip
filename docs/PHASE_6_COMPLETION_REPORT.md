# PRIP Phase 6 Completion Report: PayPal Sandbox Checkout & Verification

> **Milestone:** Phase 6 — PayPal Sandbox Checkout Demo, Preflight Gating, Server-Side Capture, Webhooks & Ambiguity Reconciliation  
> **Status:** Completed & Fully Verified  
> **Date:** 2026-11-07  
> **Verdict:** APPROVED WITH DOCUMENTED LIMITATIONS  
> **Vertical Slice Delivered:** Full end-to-end commerce-integrity loop completed:
> **Detect discrepancy -> Propose advisory fix -> Authorize human correction -> Reinspect verified -> Preflight check -> PayPal Sandbox order -> Server-side capture & webhook reconciliation.**

---

## 1. Executive Summary

Phase 6 implements the final vertical slice of the PayPal Revenue Intelligence Platform (PRIP). It connects the authoritative catalog, controlled storefront, and verified inspection state to a secure, server-side PayPal Sandbox checkout.

Key governing invariants enforced:
1. **Preflight Discrepancy Gate:** Checkout is strictly blocked when an unresolved catalog/storefront price discrepancy or unverified scan exists. PRIP never silently guesses or picks a price.
2. **Server-Side Orders v2 Capture:** Payment capture occurs exclusively on the backend outside open database transactions, recording gross amounts, PayPal fees, net amounts, and payment lifecycle states.
3. **Ambiguous Outcome Reconciliation:** If a capture call times out or encounters network ambiguity, state transitions to `UNKNOWN` with `RECONCILIATION_REQUIRED`. Blind retries are strictly blocked until authoritative status is reconciled from PayPal.
4. **Cryptographic Webhook Authenticity & Deduplication:** Webhook payloads preserve exact raw request body bytes for signature verification via official PayPal documentation, deduplicate on `paypal_event_id`, and safely drive order lifecycle transitions without duplicate effects.
5. **Sandbox Isolation:** Production endpoints and live credentials are strictly rejected. The system operates in Sandbox mode only and does not claim real commercial revenue from Sandbox captures.

---

## 2. Architecture & Components Implemented

### 2.1 Database Models & Migration (`006_payment_and_orders.py`)
- **`backend/models/order.py`**:
  - `Order` entity (`orders` table): `id`, `order_id` (unique `prip_ord_...`), `paypal_order_id` (unique index), `sku`, `product_id`, `unit_price`, `currency`, `quantity`, `total_amount`, `order_status`, `payment_status`, `preflight_scan_id`, `preflight_passed`, `idempotency_key` (unique index), `correlation_id`, timestamps.
- **`backend/models/payment_capture.py`**:
  - `PaymentCapture` entity (`payment_captures` table): `id`, `order_id` (FK), `paypal_capture_id` (unique index), `status`, `amount`, `currency`, `fee_amount`, `net_amount`, `error_message`, `reconciliation_status`, `reconciled_at`, timestamps.
- **`backend/models/webhook.py`**:
  - `WebhookEvent` entity (`webhook_events` table): `id`, `paypal_event_id` (unique index), `event_type`, `resource_type`, `summary`, `status`, `raw_payload`, `transmission_id`, `processed_at`, `created_at`.
- **`backend/models/reservation.py`**:
  - `DemoInventoryReservation` entity (`demo_inventory_reservations` table): `id`, `order_id` (FK), `sku`, `quantity`, `status` (`RESERVED`, `COMMITTED`, `RELEASED`, `EXPIRED`), `expires_at`, `created_at`.
- **`backend/migrations/versions/006_payment_and_orders.py`**:
  - Alembic migration creating tables, constraints, foreign keys, and indexes. Fully applied via `alembic upgrade head`.

### 2.2 Pure Checkout Policies & State Machine (`backend/policies/checkout_policy.py`)
- **State Enums & Transitions**:
  - `OrderStatus`: `CREATED` -> `[APPROVED, CANCELLED, FAILED]` -> `[COMPLETED, CANCELLED, FAILED]`. `COMPLETED`, `CANCELLED`, `FAILED` are terminal.
  - `PaymentStatus`: `PENDING` -> `[AUTHORIZED, CAPTURED, UNKNOWN, FAILED]`.
  - `CaptureStatus`: `PENDING`, `COMPLETED`, `DECLINED`, `FAILED`, `UNKNOWN`.
  - `ReconciliationStatus`: `NOT_NEEDED`, `RECONCILIATION_REQUIRED`, `RECONCILED`.
  - `ReservationStatus`: `RESERVED` -> `COMMITTED` (on capture) or `RELEASED`/`EXPIRED`.
- **`validate_checkout_preflight(...)`**:
  - Evaluates catalog ground truth, controlled storefront price, and latest scan state.
  - Returns `PreflightPolicyResult(passed: bool, blocking_reasons: List[str])`.
  - Discrepancy (e.g. Catalog USD 100 vs Storefront USD 120) or scan state `ISSUE_DETECTED`/`BLOCKED_UNKNOWN` yields `passed=False` and blocks checkout.

### 2.3 PayPal Integration Adapter (`backend/integrations/paypal/`)
- **Interface & Boundary (`backend/integrations/paypal/base.py`)**:
  - `PayPalClientInterface`: `create_order`, `get_order_details`, `capture_order`, `verify_webhook_signature`.
  - Typed exceptions: `PayPalError`, `PayPalApiError`, `PayPalTimeoutError`, `PayPalAuthError`.
  - Data transfer structures: `PayPalOrderResponse`, `PayPalCaptureResponse`, `PayPalWebhookVerificationResult`.
- **Mock Client (`backend/integrations/paypal/mock_client.py`)**:
  - Deterministic, hermetic mock client for automated testing and CI.
  - Shared in-memory order store simulating order creation, buyer approval, server-side capture, fee calculation ($3.49 fee), timeout fault simulation, and signature verification.
- **Sandbox Client (`backend/integrations/paypal/client.py`)**:
  - Live HTTP adapter using `httpx` against PayPal Sandbox REST endpoints (`https://api-m.sandbox.paypal.com`).
  - OAuth2 token acquisition via `client_credentials` grant with automatic token expiration caching.
  - Orders v2 `POST /v2/checkout/orders` and `POST /v2/checkout/orders/{id}/capture`.
  - Webhook verification via official PayPal endpoint `POST /v1/notifications/verify-webhook-signature`.
  - Strictly asserts that non-sandbox/production URLs are blocked.
- **Architecture Contract (`.importlinter`)**:
  - Enforces `paypal-integrations-isolation`: `backend.integrations.paypal` is forbidden from importing repositories, services, or API modules.

### 2.4 Repositories & Services (`backend/repositories/`, `backend/services/`)
- **`OrderRepository`**, **`PaymentCaptureRepository`**, **`WebhookEventRepository`**, **`ReservationRepository`**:
  - Clean persistence layers, lookups by local and provider IDs, and idempotency key uniqueness checks.
- **`CheckoutService` (`backend/services/checkout.py`)**:
  - Orchestrates preflight evaluation, idempotency resolution, external PayPal order creation outside database transactions, demo inventory reservation creation (15-min expiry), and atomic `ORDER_CREATED` audit logging.
- **`PaymentService` (`backend/services/payment.py`)**:
  - Executes server-side capture against PayPal outside DB transactions.
  - On timeout: persists `UNKNOWN` payment status, `PaymentCapture` with `reconciliation_status="RECONCILIATION_REQUIRED"`, and atomic `PAYMENT_CAPTURE_TIMEOUT` audit event.
  - On decline/error: persists `FAILED` status and `PAYMENT_CAPTURE_FAILED` audit event.
  - On success: updates payment to `CAPTURED`, order to `COMPLETED`, commits inventory reservation, persists capture with fee breakdown, and logs `PAYMENT_CAPTURED`.
  - Reconciles ambiguous orders via `get_order_details` outside DB transactions, resolving status to `CAPTURED` or `FAILED`.
- **`WebhookService` (`backend/services/webhook.py`)**:
  - Verifies cryptographic signature using raw body bytes against configured `paypal_webhook_id`.
  - Deduplicates on `paypal_event_id`; repeated events are safely ignored with audit event `WEBHOOK_DUPLICATE_IGNORED`.
  - Drives order lifecycle transitions (`CHECKOUT.ORDER.APPROVED` -> `APPROVED`, `PAYMENT.CAPTURE.COMPLETED` -> `COMPLETED`/`CAPTURED`).

### 2.5 API Endpoints (`backend/api/checkout.py`, `backend/api/webhooks.py`)
- `POST /api/checkout/preflight`: Evaluates preflight discrepancy gate.
- `POST /api/checkout/orders`: Creates order (enforcing preflight gate and idempotency).
- `POST /api/checkout/orders/{id}/capture`: Server-side capture.
- `POST /api/checkout/orders/{id}/reconcile`: Authoritative reconciliation.
- `GET /api/checkout/orders` & `GET /api/checkout/orders/{id}`: Order retrieval.
- `POST /api/webhooks/paypal`: Raw-body webhook receiver with signature verification.
- `GET /api/webhooks/events`: Lists processed webhook events.

### 2.6 Frontend Checkout Experience (`frontend/src/pages/Checkout.tsx`)
- Clear PayPal Sandbox disclaimer notice.
- Interactive preflight discrepancy gate:
  - If discrepancy exists: renders red warning banner ("Checkout Blocked: Price Mismatch Detected") and strictly disables payment button.
  - If verified clean: displays green badge ("Preflight Verified: Ground-Truth Price Synchronized") and enables payment button.
- Orders v2 flow:
  - Generates PayPal Sandbox order and displays IDs, status, and sandbox redirect link.
- Server-side capture:
  - Triggers server-side capture with simulation controls for demonstration (timeout simulation, decline simulation).
  - Displays complete capture receipt: Capture ID, status, gross amount, PayPal fee ($3.49), and net amount ($96.51).
  - When capture times out to `UNKNOWN`, surfaces warning banner and "Reconcile with PayPal" action button.

---

## 3. Verification & Quality Gates

### 3.1 Automated Test Execution Results

| Test Suite | Files | Tests | Result | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Backend Pytest** | 10 | **112** | **100% Passed (112/112)** | Includes 12 new Phase 6 checkout/paypal/webhook integration tests. Execution time: 7.33s. |
| **Frontend Vitest** | 6 | **26** | **100% Passed (26/26)** | Includes 6 new Phase 6 Checkout page tests. Execution time: 6.49s. |
| **Verification Launcher (`verify.ps1`)** | All | **138** | **100% Passed** | Runs pytest and vitest discovery manifests cleanly. |
| **Harness Structure Check (`harness-check.ps1`)** | Docs / Rules | N/A | **Passed** | Confirms required rules, specs, and secret isolation. |

### 3.2 Code Quality & Architectural Integrity
- **Ruff Check:** Passed with 0 errors (`ruff check backend`).
- **Mypy Type Checking:** Strict static typing passed with 0 errors across 107 source files (`mypy backend`).
- **Import-Linter:** 6 architectural contracts kept, 0 broken (`lint_imports`):
  1. `Backend Layered Architecture`: KEPT
  2. `Core Infrastructure Independence`: KEPT
  3. `Pure Policy Independence`: KEPT
  4. `Repositories Isolation`: KEPT
  5. `AI Integrations Isolation`: KEPT
  6. `PayPal Integrations Isolation`: KEPT
- **Frontend TypeScript Linting:** Passed cleanly (`tsc --noEmit`).
- **Frontend Architecture Linting:** Passed with 0 violations (`depcruise --config .dependency-cruiser.cjs src`).
- **Frontend Vite Build:** Production build generated successfully (`vite build` in 1.08s).

---

## 4. Requirement Verification Matrix

| Requirement | Implementation Evidence | Test Coverage |
| :--- | :--- | :--- |
| **1. Payment State Machine** | `backend/policies/checkout_policy.py`: `OrderStatus`, `PaymentStatus`, `CaptureStatus`, `ReconciliationStatus`. | `TestPayPalAndCheckout::test_5`, `test_6`, `test_7` |
| **2. PayPal Webhook Signature** | Preserves raw request body bytes; calls `verify_webhook_signature` against official PayPal specs. | `TestPayPalAndCheckout::test_8` |
| **3. Block Preflight on Discrepancy** | `validate_checkout_preflight` blocks if catalog != storefront or scan is `ISSUE_DETECTED`. Never picks price silently. | `TestPayPalAndCheckout::test_1`, `test_2`, `Checkout.test.tsx` |
| **4. Database Idempotency** | Unique indexes on `orders.idempotency_key`, `orders.paypal_order_id`, and `webhook_events.paypal_event_id`. | `TestPayPalAndCheckout::test_3`, `test_9` |
| **5. Atomic State & Audit** | `atomic_transaction` context wraps all state transitions alongside append-only audit events. | `TestPayPalAndCheckout::test_5`, `test_10` |
| **6. External Calls Outside DB TX** | PayPal REST calls occur before or outside `with atomic_transaction(...)` blocks in services. | Verified in `checkout.py`, `payment.py`, `webhook.py` |
| **7. Sandbox-Only Environment** | `paypal_environment="sandbox"`; non-sandbox URLs raise `PayPalError` immediately. | `TestPayPalAndCheckout::test_11` |
| **8. Deterministic Mock CI** | `MockPayPalClient` with shared state runs hermetically offline in automated test suites without live keys. | All 12 backend test cases and 6 frontend test cases |
| **9. No Refunds or Subscriptions** | Out-of-scope capabilities omitted from schemas, models, and endpoints. | Maintained in Phase 6 scope boundary |
| **10. No Live Credentials** | Live credentials strictly excluded; defaults to mock in dev/test. | Verified in `config.py` and `.importlinter` |

---

## 5. Documented Limitations & Scope Boundaries

1. **Sandbox Demonstration:** All transactions are executed against the PayPal Sandbox or deterministic mock provider. Captured funds represent simulated test authorizations, not real commercial revenue or conversion lift.
2. **Demo Inventory Reservation:** PRIP's demo inventory reservation protects only the controlled demo catalog (`SX-001`), not external merchant warehouse systems.
3. **No Refunds / Payouts / Subscriptions:** Phase 6 implements checkout, preflight gating, capture, webhook verification, and reconciliation. Post-order dispute, refund, and subscription operations are intentionally omitted from MVP.
4. **Single-Storefront Demo Scope:** Operates on the controlled demo storefront and seeded catalog; multi-tenant merchant storefront crawling is not included.

---

## 6. Conclusion & Status

Phase 6 successfully delivers the full end-to-end PRIP product promise:
> **Detect the discrepancy. Approve the correction. Verify the checkout.**

The implementation satisfies all architectural contracts, security invariants, testing requirements, and quality standards.
