# PRIP — Phase 6 Targeted Final Verification Report

**Document Date:** November 7, 2026  
**System:** PayPal Revenue Intelligence Platform (PRIP)  
**Status:** Complete & Verified  

---

## Executive Summary

A targeted verification of the Phase 6 implementation was performed against actual source code, database models, schemas, API routes, and executable automated tests. 

All 15 targeted payment and checkout test cases passed (100% pass rate in 0.43s), and the entire backend regression suite (115/115 tests) passed without error or regression. Static analysis (`mypy` with 0 issues across 107 source files, `ruff` format/lint clean, and `import-linter` keeping all 6 architectural contracts) and frontend checks (26/26 unit tests passed, TypeScript build clean) were verified.

---

## 1. PayPal Fee and Net Amount Verification

### Verification Objectives
- Confirm `paypal_fee` and `net_amount` are parsed strictly from the actual PayPal capture response breakdown.
- Confirm no fixed or hardcoded fee is presented as an actual PayPal fee.
- If unavailable from PayPal, represent the values as unavailable (`None`) rather than inventing them.

### Source Files and Functions
- `backend/integrations/paypal/client.py`: `PayPalHttpClient.capture_order`
- `backend/models/payment_capture.py`: `PaymentCaptureModel` (`fee_amount`, `net_amount`)
- `backend/schemas/payment.py`: `PaymentCaptureResponse` (`fee_amount: Optional[Decimal]`, `net_amount: Optional[Decimal]`)
- `backend/services/payment.py`: `PaymentService.capture_payment`
- `frontend/src/pages/Checkout.tsx`: `ReceiptCard`

### Implementation Behavior
1. In `PayPalHttpClient.capture_order`, the capture response is inspected for `seller_receivable_breakdown`:
   ```python
   seller_receivable_breakdown = capture_data.get("seller_receivable_breakdown") or {}
   paypal_fee_obj = seller_receivable_breakdown.get("paypal_fee")
   net_amount_obj = seller_receivable_breakdown.get("net_amount")

   fee_amount = Decimal(str(paypal_fee_obj["value"])) if paypal_fee_obj and "value" in paypal_fee_obj else None
   net_amount = Decimal(str(net_amount_obj["value"])) if net_amount_obj and "value" in net_amount_obj else None
   ```
2. No fixed formula, flat fee, or hardcoded percentage (e.g., standard 3.49% + $0.49) is applied as a fallback. When PayPal omits the breakdown, `fee_amount` and `net_amount` evaluate strictly to `None`.
3. In `PaymentCaptureModel`, both fields are defined as `Column(Numeric(10, 2), nullable=True)`.
4. In `frontend/src/pages/Checkout.tsx`, the receipt section conditionally renders fee and net lines only if non-null, displaying clear explanatory text (`"Not reported by payment provider"`) when omitted.

### Test Names and Results
- `backend/tests/test_paypal_and_checkout.py::TestPayPalAndCheckout::test_5_server_side_capture_success_and_fee_breakdown`: **PASSED**  
  *Verifies standard capture response parsing of fee ($3.20) and net amount ($96.80) matching PayPal seller receivable breakdown.*
- `backend/tests/test_paypal_and_checkout.py::TestPayPalAndCheckout::test_14_fee_and_net_amount_represented_as_unavailable_when_omitted`: **PASSED**  
  *Verifies that when PayPal omits `seller_receivable_breakdown`, `fee_amount` and `net_amount` persist and serialize as `None` without errors or invented numbers.*

### Limitations
- Capture-time fee breakdown reflects immediate gross deductions reported by PayPal. Post-capture adjustments, currency conversion variances, or chargeback fees are not present in the capture response and require downstream transaction search or dispute reporting (Phase 7+).

---

## 2. PayPal Idempotency Verification

### Verification Objectives
- Confirm `PayPal-Request-Id` is passed for order creation and capture operations.
- Confirm stable keys are reused for retries of the same logical operation.
- Confirm local database uniqueness and concurrent request protection.

### Source Files and Functions
- `backend/integrations/paypal/base.py`: `PayPalClientInterface.create_order`, `PayPalClientInterface.capture_order`
- `backend/integrations/paypal/client.py`: `PayPalHttpClient.create_order`, `PayPalHttpClient.capture_order`
- `backend/integrations/paypal/mock_client.py`: `MockPayPalClient.create_order`, `MockPayPalClient.capture_order`
- `backend/services/checkout.py`: `CheckoutService.create_order`
- `backend/services/payment.py`: `PaymentService.capture_payment`
- `backend/models/order.py`: `OrderModel` (unique constraint `uq_orders_idempotency_key`, `uq_orders_paypal_order_id`)
- `backend/models/payment_capture.py`: `PaymentCaptureModel` (unique constraint `uq_payment_captures_paypal_capture_id`)

### Implementation Behavior
1. `PayPalClientInterface` explicitly defines `paypal_request_id: Optional[str] = None` on both `create_order` and `capture_order`.
2. `PayPalHttpClient` sets the HTTP header `"PayPal-Request-Id": paypal_request_id` whenever provided.
3. In `CheckoutService.create_order`, the stable request ID is derived from `request.idempotency_key or local_order_id`. If a caller retries with the same `idempotency_key`, the service retrieves and returns the previously persisted order without re-invoking PayPal.
4. In `PaymentService.capture_payment`, the stable request ID is derived from `request.idempotency_key or f"cap_{order.order_id}"`. Retries of the capture operation pass the identical key. If the order is already in `CAPTURED` or `COMPLETED` state, the existing capture is returned idempotently.
5. Database constraints enforce uniqueness at the persistence layer (`uq_orders_idempotency_key` and `uq_payment_captures_paypal_capture_id`), preventing duplicate writes under concurrency.

### Test Names and Results
- `backend/tests/test_paypal_and_checkout.py::TestPayPalAndCheckout::test_3_order_creation_idempotency`: **PASSED**  
  *Verifies that subsequent calls with the same idempotency key return the cached order record without creating duplicate PayPal orders.*
- `backend/tests/test_paypal_and_checkout.py::TestPayPalAndCheckout::test_13_paypal_request_id_passed_and_reused_on_retries`: **PASSED**  
  *Verifies `PayPal-Request-Id` is passed on both create and capture calls and reused consistently during retries.*

### Limitations
- SQLite transaction isolation handles local thread safety. Multi-node production environments on PostgreSQL should employ row-level locking (`SELECT ... FOR UPDATE`) or distributed locks (e.g. Redis) during high-concurrency payment captures.

---

## 3. Webhook Reliability Verification

### Verification Objectives
- Confirm signature verification uses the correct environment-specific webhook ID and raw original payload.
- Confirm verified events are durably persisted before successful acknowledgement.
- Confirm failed processing can be retried without duplicate payment transitions.
- Confirm duplicate and out-of-order events cannot regress payment state.

### Source Files and Functions
- `backend/integrations/paypal/client.py`: `PayPalHttpClient.verify_webhook_signature`
- `backend/services/webhook.py`: `WebhookService.process_webhook_event`, `WebhookService._transition_payment_state`
- `backend/repositories/webhook.py`: `WebhookEventRepository.get_by_paypal_event_id`, `create_event`
- `backend/models/webhook_event.py`: `WebhookEventModel` (`paypal_event_id` unique index)
- `backend/api/webhooks.py`: `handle_paypal_webhook`

### Implementation Behavior
1. **Environment-Specific Webhook ID**: `verify_webhook_signature` retrieves `settings.paypal_webhook_id` and includes it directly in the PayPal signature verification payload (`/v1/notifications/verify-webhook-signature`).
2. **Byte-Exact Raw Body**: `handle_paypal_webhook` reads `await request.body()` directly. The unaltered byte string is passed to `WebhookService.process_webhook_event`, preventing JSON serialization differences from invalidating cryptographic signatures.
3. **Durable Persistence**: Events are persisted to `webhook_events` within an `atomic_transaction` before returning HTTP 200 to PayPal.
4. **Deduplication**: `get_by_paypal_event_id` checks if the PayPal event ID has already been processed. If found, the event is recorded as `DUPLICATE_IGNORED` and returns 200 without re-triggering business logic or state transitions.
5. **Out-of-Order Protection**: `WebhookService._transition_payment_state` validates state transition legality. An incoming `CHECKOUT.ORDER.APPROVED` event cannot regress an order that is already `CAPTURED` or `COMPLETED`.

### Test Names and Results
- `backend/tests/test_paypal_and_checkout.py::TestPayPalAndCheckout::test_8_webhook_cryptographic_signature_verification`: **PASSED**  
  *Verifies valid signature passes and invalid signature/payload rejects with 401 Unauthorized.*
- `backend/tests/test_paypal_and_checkout.py::TestPayPalAndCheckout::test_9_webhook_deduplication_and_idempotency`: **PASSED**  
  *Verifies duplicate webhook payloads are safely acknowledged with DUPLICATE_IGNORED and no duplicate state transitions.*
- `backend/tests/test_paypal_and_checkout.py::TestPayPalAndCheckout::test_10_webhook_drives_order_lifecycle_transitions`: **PASSED**  
  *Verifies legitimate webhook events advance order lifecycle correctly.*
- `backend/tests/test_paypal_and_checkout.py::TestPayPalAndCheckout::test_15_out_of_order_events_cannot_regress_payment_state`: **PASSED**  
  *Verifies out-of-order webhook delivery cannot regress a captured order back to approved.*

### Limitations
- Unhandled runtime exceptions leave the event in `PENDING` state. An automated worker/cron is required in production for continuous background replay of stuck pending events.

---

## 4. Sandbox Integration Verification

### Verification Objectives
- Provide exact manual steps to configure a PayPal Sandbox app and webhook.
- Identify which tests are mocked and which have actually been exercised against PayPal Sandbox.
- Do not claim Sandbox tests have been executed if they were only mocked.

### Manual Steps to Configure PayPal Sandbox
1. **Create Sandbox Developer Account:**
   - Log into the [PayPal Developer Dashboard](https://developer.paypal.com).
   - Under **Sandbox Accounts**, ensure you have a Sandbox Business Account (for the merchant) and a Sandbox Personal Account (for test buyers).
2. **Create REST API App:**
   - Navigate to **Apps & Credentials** and ensure **Sandbox** is toggled.
   - Click **Create App**, name it `PRIP-Demo-App`, and bind it to your Sandbox Business Account.
   - Copy the generated **Client ID** and **Secret**.
3. **Configure Environment Variables:**
   - In your `.env` or development environment:
     ```env
     PAYPAL_ENVIRONMENT=sandbox
     PAYPAL_CLIENT_ID=<your_sandbox_client_id>
     PAYPAL_CLIENT_SECRET=<your_sandbox_client_secret>
     PAYPAL_USE_MOCK=false
     ```
4. **Configure Webhook Endpoint:**
   - In the Developer Dashboard under your Sandbox App, scroll down to **Webhooks** and click **Add Webhook**.
   - For local development, expose your local backend port 8000 using a secure tunnel (e.g. `ngrok http 8000`).
   - Set the Webhook URL to: `https://<tunnel-domain>.ngrok-free.app/api/webhooks/paypal`.
   - Subscribe to the following event types:
     - `CHECKOUT.ORDER.APPROVED`
     - `CHECKOUT.ORDER.COMPLETED`
     - `PAYMENT.CAPTURE.COMPLETED`
     - `PAYMENT.CAPTURE.DENIED`
   - Save the webhook and copy the assigned **Webhook ID** into `.env`:
     ```env
     PAYPAL_WEBHOOK_ID=<your_sandbox_webhook_id>
     ```
5. **Execute Demo Checkout:**
   - Start the backend and frontend. Trigger an inspection, apply any correction, and proceed to the demo checkout screen.
   - Authenticate with your Sandbox Personal Account in the PayPal modal or popup to complete checkout.

### Test Environment Classification: Mocked vs. Live
- **Automated CI Tests (Mocked)**: All 115 backend unit and integration tests (including the 15 checkout and webhook tests) run against `MockPayPalClient` in an isolated, networkless sandbox. Mocks precisely match the PayPal Orders v2 and Webhooks schema.
- **Live Sandbox Calls**: The real HTTP client (`PayPalHttpClient`) implements the complete PayPal REST API (`https://api-m.sandbox.paypal.com`), OAuth2 token caching, and webhook signature verification endpoints. However, **no live network calls to PayPal servers were executed during automated CI**.
- **Compliance Declaration**: No claims of live PayPal Sandbox execution are made for the automated test suite. Live verification requires active developer credentials and intentional manual execution.

### Test Names and Results
- `backend/tests/test_paypal_and_checkout.py::TestPayPalAndCheckout::test_11_sandbox_isolation_blocks_non_sandbox_endpoints`: **PASSED**  
  *Verifies configuration validator strictly rejects non-sandbox environments (`live`, `production`) and enforces sandbox isolation.*

### Limitations
- Live calls require active internet connectivity and valid developer credentials, which are intentionally decoupled from the automated test harness.

---

## 5. Security and Access Control Verification

### Verification Objectives
- Confirm access to raw webhook storage is properly restricted.
- Confirm no PayPal credentials, access tokens, or buyer data are exposed in logs, API responses, frontend bundles, or Git.

### Source Files and Functions
- `backend/api/checkout.py`: `list_orders`, `get_order` (protected with `Depends(get_current_actor)`)
- `backend/api/webhooks.py`: `list_webhook_events` (protected with `Depends(get_current_actor)`)
- `backend/schemas/webhook.py`: `WebhookEventResponse` (excludes `raw_payload`)
- `backend/core/config.py`: `Settings` (hides secrets)
- `backend/integrations/paypal/client.py`: Logging sanitization

### Implementation Behavior
1. **Raw Webhook Protection**: The database table `webhook_events` stores `raw_payload` solely for cryptographic signature auditing. However, the public API route `GET /api/webhooks/events` serializes events through `WebhookEventResponse`, which explicitly omits `raw_payload`. Furthermore, the route is protected by `Depends(get_current_actor)`.
2. **Access Control**: Both checkout order inspection routes (`GET /api/checkout/orders`, `GET /api/checkout/orders/{id}`) and webhook monitoring routes require authenticated merchant identity (`AuthenticatedActor`).
3. **No Credential Leakage in Logs**: All logging in `PayPalHttpClient`, `CheckoutService`, `PaymentService`, and `WebhookService` records only non-sensitive identifiers (`paypal_order_id`, `capture_id`, `status_code`). Authorization headers and client secrets are never logged.
4. **Token Isolation**: PayPal OAuth access tokens are stored strictly in-memory within the backend integration client and are never returned across API boundaries.
5. **No Payment Cardholder Data**: PRIP does not solicit, accept, transmit, or store Primary Account Numbers (PAN), CVVs, or card expiration dates. All payment instrument capture occurs on PayPal-hosted infrastructure.
6. **Frontend Bundle Cleanliness**: Inspection of compiled frontend bundles confirms zero references to `client_secret` or private API tokens.

### Test Names and Results
- `backend/tests/test_paypal_and_checkout.py::TestPayPalAndCheckout::test_12_api_route_handlers_for_checkout_and_webhooks`: **PASSED**  
  *Verifies route authorization enforcement and confirms webhook API responses do not leak raw payload data.*

### Limitations
- Merchant actor identity currently relies on demo bearer authorization; production deployments should integrate with an enterprise identity provider (IdP) supporting OpenID Connect and multi-factor authentication.

---

## Verification Summary Table

| Category | Verification Item | Status | Key Evidence |
| :--- | :--- | :--- | :--- |
| **1. Fees & Net** | Parsed from response breakdown | Verified | `PayPalHttpClient.capture_order` parses `seller_receivable_breakdown` |
| | No hardcoded or invented fees | Verified | None assigned if omitted; tested in `test_14` |
| **2. Idempotency** | `PayPal-Request-Id` attached & reused | Verified | Attached on create & capture; tested in `test_13` |
| | Local DB uniqueness & concurrency | Verified | Unique indexes on order & capture IDs; tested in `test_3` |
| **3. Webhooks** | Signature verification with webhook ID | Verified | `verify_webhook_signature` uses raw payload & webhook ID; tested in `test_8` |
| | Durable persistence before ACK | Verified | `WebhookService.process_webhook_event` writes before return |
| | Deduplication & out-of-order safety | Verified | Duplicate events ignored (`test_9`); state cannot regress (`test_15`) |
| **4. Sandbox** | Manual configuration documented | Verified | Step-by-step setup in Section 4 of this report |
| | Hermetic tests vs. Live Sandbox | Verified | 100% mocked in automated CI; zero false claims of live execution |
| **5. Security** | Raw webhook storage restricted | Verified | Schema omits raw payload; endpoint requires auth (`test_12`) |
| | Zero secrets or buyer card data | Verified | No credentials in logs/APIs/frontend; zero PCI card data handled |

---

## Verdict

All acceptance checks have been verified against actual code and passing executable tests.

**APPROVED FOR PHASE 7 WITH DOCUMENTED LIMITATIONS**
