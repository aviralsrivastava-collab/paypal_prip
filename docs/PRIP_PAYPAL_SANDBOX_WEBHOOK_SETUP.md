# PRIP — Phase 10A: PayPal Sandbox Webhook Discovery & Setup Report

**Date:** 2026-11-09  
**Repository:** `aviralsrivastava-collab/paypal_prip`  
**Target Environment:** PayPal Developer Sandbox (`https://api-m.sandbox.paypal.com`)  
**Mode:** Read-Only Discovery & Verification Audit  
**Execution Verdict:** **PUBLIC HTTPS ENDPOINT REQUIRED**  

---

## 1. Executive Summary

A comprehensive, read-only architectural and runtime discovery of the PayPal Sandbox webhook implementation in PRIP was conducted prior to any checkout order creation.

The investigation confirms that PRIP's webhook ingestion engine is **fully implemented and operationally resilient at the codebase level**:
- Raw request bytes are strictly preserved for cryptographic signature verification.
- Official PayPal signature verification (`POST /v1/notifications/verify-webhook-signature`) is implemented with fail-closed semantics.
- Deduplication, distributed worker lease claiming, exponential backoff with jitter, out-of-order state guards, and dead-letter queue isolation are active.
- Universal append-only audit logging is enforced on all webhook transitions.

However, because the PRIP backend is currently hosted locally (`http://127.0.0.1:8000`), it **cannot receive asynchronous webhook deliveries from PayPal Sandbox servers without a publicly routable HTTPS URL and a corresponding registered `PAYPAL_WEBHOOK_ID`**.

Per the prescribed Phase 10A criteria, the execution outcome is:
# PUBLIC HTTPS ENDPOINT REQUIRED

---

## 2. Webhook Endpoint Specification & Routing

The exact endpoint path, HTTP method, and router configuration were verified from [`backend/api/webhooks.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/api/webhooks.py#L11-L45) and [`backend/api/main.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/api/main.py#L123):

| Attribute | Configured Specification |
| :--- | :--- |
| **HTTP Method** | `POST` |
| **Full URL Path** | `/api/webhooks/paypal` |
| **Router Prefix** | `prefix="/api/webhooks"` (in [`backend/api/webhooks.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/api/webhooks.py#L11)) |
| **Route Path** | `@router.post("/paypal")` (in [`backend/api/webhooks.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/api/webhooks.py#L14)) |
| **Application Mount** | `app.include_router(webhooks_router)` (in [`backend/api/main.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/api/main.py#L123)) |
| **Request Size Limit** | 1 MB enforced by `validate_request_size` in HTTP middleware |
| **Authentication Barrier** | Public listener with cryptographic PayPal transmission header verification |
| **Response Format** | `{"status": "ok", "event_id": str, "event_type": str, "processing_status": str}` |

---

## 3. Raw Request Body Preservation

Cryptographic signature verification requires that the payload verified by PayPal matches the raw byte stream transmitted over HTTP byte-for-byte. Any premature JSON parsing, whitespace alteration, or serialization normalization breaks signature hashes.

Verification of [`backend/api/webhooks.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/api/webhooks.py#L27-L33):
```python
raw_bytes = await request.body()
raw_body = raw_bytes.decode("utf-8")
headers = dict(request.headers)

service = WebhookService(db)
event_resp = service.process_webhook(headers=headers, raw_body=raw_body)
```
- **Byte Integrity:** The raw byte array is captured directly from ASGI `request.body()`.
- **Decoding:** Decoded as UTF-8 string without JSON normalization before verification.
- **Header Forwarding:** Transmission headers (`paypal-transmission-id`, `paypal-transmission-time`, `paypal-cert-url`, `paypal-auth-algo`, `paypal-transmission-sig`) are extracted directly from HTTP headers and forwarded untouched.

---

## 4. Cryptographic Signature Verification & Webhook ID

Signature verification is delegated to the official PayPal REST verification endpoint via [`backend/integrations/paypal/client.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/integrations/paypal/client.py#L259-L299) and [`backend/services/webhook.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/services/webhook.py#L53-L64):

1. **Verification Request:**
   - **Endpoint:** `POST https://api-m.sandbox.paypal.com/v1/notifications/verify-webhook-signature`
   - **Authorization:** `Bearer <oauth_token>` acquired via client credentials grant.
   - **Verification Payload:**
     - `transmission_id`: value of `paypal-transmission-id` header
     - `transmission_time`: value of `paypal-transmission-time` header
     - `cert_url`: value of `paypal-cert-url` header
     - `auth_algo`: value of `paypal-auth-algo` header
     - `transmission_sig`: value of `paypal-transmission-sig` header
     - `webhook_id`: configured `PAYPAL_WEBHOOK_ID`
     - `webhook_event`: JSON parsed object of `raw_body`
2. **Fail-Closed Semantics:** If PayPal returns any status other than `verification_status: "SUCCESS"` (or non-200 HTTP status), `verify_webhook_signature` returns `False`, raising a `ValueError("Cryptographic webhook signature verification failed.")` which yields HTTP 400.
3. **Webhook ID Configuration:**
   - Loaded by `Settings.paypal_webhook_id` in [`backend/core/config.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/core/config.py#L31).
   - In `.env.example`, defaults to `WH-MOCK-SANDBOX-001`.
   - In current local `.env`, remains set to `WH-MOCK-SANDBOX-001` (mock default).
   - **Required Action:** Once the webhook URL is registered in the PayPal Developer Dashboard, the resulting `WEBHOOK-ID` must be configured in `.env`.

---

## 5. Supported Event Types & Ingestion Pipeline

PRIP supports discrete commerce and payment lifecycle events in [`backend/services/webhook_worker.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/services/webhook_worker.py#L106-L201):

| PayPal Event Type | Trigger & Business Action | Monotonic State Guard | Inventory Action |
| :--- | :--- | :--- | :--- |
| **`CHECKOUT.ORDER.APPROVED`** | Buyer approved checkout session on PayPal. | Transitions order from `CREATED` to `APPROVED`. Safely ignored if order is already `CAPTURED` or `COMPLETED`. | None |
| **`PAYMENT.CAPTURE.COMPLETED`** | Asynchronous payment capture succeeded. | Transitions payment status to `CAPTURED`, order to `COMPLETED`. | Commits demo inventory reservation (`ReservationStatus.COMMITTED`). |
| **`PAYMENT.CAPTURE.DENIED`** | Payment rejected or denied by PayPal risk/processor. | Transitions payment status to `FAILED`, order to `FAILED`. | Releases demo inventory reservation (`ReservationStatus.RELEASED`). |
| **`PAYMENT.CAPTURE.DECLINED`** | Instrument declined. | Transitions payment status to `FAILED`, order to `FAILED`. | Releases demo inventory reservation (`ReservationStatus.RELEASED`). |
| **Other Event Types** | Informational notifications. | Durably recorded and marked `PROCESSED` without mutating order/payment state. | None |

---

## 6. Deduplication, Worker Processing & Resilience Architecture

The ingestion and worker architecture separates durable receipt from business execution to prevent duplicate transactions and tolerate crashes:

```
[ PayPal Cloud ]
       │
       ▼ (HTTP POST /api/webhooks/paypal)
┌────────────────────────────────────────────────────────┐
│ FastAPI Webhook Listener                              │
│ - Raw byte preservation                                │
│ - Cryptographic signature check against PayPal Sandbox │
│ - Deduplication on unique `paypal_event_id`            │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼ (Atomic DB Transaction)
┌────────────────────────────────────────────────────────┐
│ `webhook_events` Table (Inbox Pattern)                 │
│ - Status: PENDING                                      │
│ - Raw payload stored                                   │
│ - Universal audit event: WEBHOOK_RECEIVED              │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼ (Lease Claiming / Worker)
┌────────────────────────────────────────────────────────┐
│ `WebhookWorkerService`                                 │
│ - Atomic lease claim (SKIP LOCKED or atomic update)    │
│ - Monotonic state transitions (Order & Capture)        │
│ - Commits/releases local demo reservations             │
│ - Exponential backoff + jitter on failure              │
│ - Dead-letter isolation after 5 attempts               │
│ - Operator manual replay API                           │
└────────────────────────────────────────────────────────┘
```

### Key Resilience Guarantees

1. **Deduplication:**
   - Table `webhook_events` enforces a `UNIQUE` constraint on `paypal_event_id`.
   - Duplicate events are detected via `get_by_paypal_event_id()`, generate audit log `WEBHOOK_DUPLICATE_IGNORED`, and return HTTP 200 with status `DUPLICATE` without reprocessing.
2. **Out-of-Order Delivery Protection:**
   - If an approval event (`CHECKOUT.ORDER.APPROVED`) arrives after a capture completed event, the worker checks `order.order_status == OrderStatus.CREATED.value`. Since status is already `COMPLETED`, it will not overwrite or regress state.
3. **Distributed Lease Locking:**
   - Workers claim events via `claim_eligible_event(worker_id, lease_seconds=60)`.
   - On PostgreSQL, uses `SELECT FOR UPDATE SKIP LOCKED` for scale without contention.
   - On SQLite, uses atomic conditional `UPDATE` matching expected candidate state.
   - Crashed worker recovery: expired leases (`processing_lease_expires_at < now`) are automatically reclaimed by surviving workers.
4. **Retry Backoff & Dead-Letter Handling:**
   - Failures calculate bounded exponential backoff with jitter: `min(300, 1.0 * 2^(attempt-1)) + Uniform(-jitter, +jitter)`.
   - Event status moves to `RETRYABLE_FAILURE` with updated `next_retry_at`.
   - After 5 failed attempts (`max_attempts=5`), status transitions to `DEAD_LETTER`.
   - Errors are categorized into `INVALID_PAYLOAD`, `ORDER_NOT_FOUND`, `NETWORK_ERROR`, or `UNHANDLED_EXCEPTION`.
   - Operators can inspect dead-lettered events via `GET /api/operations/webhooks/stuck` and trigger idempotent replay via `POST /api/operations/webhooks/{id}/replay`.

---

## 7. Public Reachability & HTTPS Assessment

PayPal Sandbox webhook delivery requires a publicly routable, valid HTTPS endpoint:

1. **Current Localhost State:**
   - The backend runs on `http://127.0.0.1:8000`.
   - PayPal Sandbox servers cannot reach RFC 1918 private IP addresses or `localhost`.
   - Direct webhook delivery from PayPal will fail with connection timeout or DNS resolution failure.
2. **Public Reachability Requirement:**
   - A secure public HTTPS reverse proxy or tunnel (such as ngrok, Cloudflare Tunnel, or deployment to a dedicated staging environment) is required.
   - Target URL format: `https://<public-domain>/api/webhooks/paypal`.
3. **Security Boundary Enforcement:**
   - Any public reverse proxy or tunnel must route **exclusively** to the backend API port (8000).
   - Under no circumstances may internal databases (PostgreSQL port 5432, SQLite files), admin interfaces, or diagnostic tooling be exposed to the public internet.

---

## 8. Required Environment Variables

To activate live PayPal Sandbox webhook verification and event ingestion, the following environment variables must be configured in the backend environment:

| Variable Name | Required Value / Description | Sensitive? |
| :--- | :--- | :--- |
| **`PAYPAL_CLIENT_TYPE`** | `sandbox` (activates `PayPalSandboxClient`) | No |
| **`PAYPAL_ENVIRONMENT`** | `sandbox` (strictly fails closed if `live`) | No |
| **`PAYPAL_BASE_URL`** | `https://api-m.sandbox.paypal.com` | No |
| **`PAYPAL_CLIENT_ID`** | PayPal Developer Sandbox App Client ID | Sensitive (unlogged) |
| **`PAYPAL_CLIENT_SECRET`** | PayPal Developer Sandbox App Client Secret | Highly Sensitive (unlogged) |
| **`PAYPAL_WEBHOOK_ID`** | Webhook ID obtained from PayPal Developer Dashboard | Sensitive (unlogged) |
| **`WORKER_POLL_INTERVAL_SECONDS`** | Polling interval for background worker (default: `5.0`) | No |
| **`WORKER_BATCH_SIZE`** | Webhook event batch size per worker tick (default: `10`) | No |
| **`WORKER_LEASE_SECONDS`** | Lock lease duration for worker processing (default: `60`) | No |

*Note: In accordance with security rules, no credential values or tokens are stored in this report or exposed in Git.*

---

## 9. Verification of Strict Limits

During this discovery phase:
- **No webhook registrations were created, modified, or deleted** on PayPal.
- **No checkout orders were created.**
- **No payments were captured or refunded.**
- **No storefront prices or catalog records were modified.**
- **No database records were mutated.**
- **No Git commits or pushes were made.**

---

## 10. Recommended Next Steps for Phase 10A Checkout Test

1. **Expose Secure HTTPS Webhook Tunnel:**
   - Establish an HTTPS tunnel pointing exclusively to local port 8000:
     `ngrok http 8000` or `cloudflared tunnel --url http://localhost:8000`
2. **Register Webhook in PayPal Developer Dashboard:**
   - In PayPal Developer Dashboard -> App Settings -> Add Webhook:
     - Webhook URL: `https://<public-tunnel-domain>/api/webhooks/paypal`
     - Subscribed Events:
       - `Checkout order approved`
       - `Payment capture completed`
       - `Payment capture denied`
       - `Payment capture declined`
3. **Configure `PAYPAL_WEBHOOK_ID` in `.env`:**
   - Add the resulting Webhook ID to `.env`:
     `PAYPAL_WEBHOOK_ID=<paypal-webhook-id>`
4. **Proceed to Controlled End-to-End Sandbox Checkout:**
   - Execute preflight check, create PayPal Sandbox order, complete buyer approval flow, capture payment, and verify asynchronous webhook delivery and audit logging.
