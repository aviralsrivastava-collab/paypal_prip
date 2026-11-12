# PRIP — Stage 10.1: Frontend Connectivity & PayPal Approval Flow Diagnostic Report

**Date:** 2026-11-12  
**Baseline:** Git Commit `018d8d9` (`main`)  
**Frontend:** `https://paypalprip.vercel.app` (Vercel)  
**Backend:** `https://paypal-prip.onrender.com` (Render)  
**Database:** Supabase PostgreSQL 16 (`sojoavvnsbsjdfllrtvv`, migration `012` active)  
**Status:** Investigation Complete — Diagnostics & Proposed Actions Ready (No Code Changes Applied)  

---

## 1. Executive Summary & Status Classification

| Scope Area | Status | Summary |
| :--- | :---: | :--- |
| **Frontend Connectivity** | **PASS** | Vercel `/api/*` proxy rewrite to Render functions cleanly. Live browser inspection confirms HTTP 200 OK with zero console errors. |
| **"Offline (Failed to fetch)" Root Cause** | **PASS (EXPLAINED)** | Caused by transient Render free-tier cold-start latency (30–50s spin-up) exceeding initial client timeout. Once warm, backend status settles to `healthy`. |
| **PayPal Order Capture Gate** | **PASS** | Authoritative verification that premature capture calls without buyer approval fail closed with `ORDER_NOT_APPROVED`. |
| **Order State Immutability** | **PASS** | Orders transitioning to `FAILED` cannot be captured; a fresh order is required for subsequent buyer checkout. |
| **Webhook Endpoint Routing** | **ACTION REQUIRED** | Webhook Simulator was pointed to root (`https://paypal-prip.onrender.com/`) instead of `/api/webhooks/paypal`. |
| **Webhook Signature Verification** | **PASS** | Strict 5-header asymmetric verification via official PayPal API is active and rejects unauthentic/misconfigured transmissions. |

---

## 2. Phase 1 — Frontend Connectivity Investigation

### 2.1 Configuration Audit
- **Vercel Routing:** [`vercel.json`](file:///c:/Users/HP/OneDrive/Desktop/paypal/vercel.json#L6-L15) defines:
  ```json
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://paypal-prip.onrender.com/api/:path*"
    },
    {
      "source": "/(.*)",
      "destination": "/index.html"
    }
  ]
  ```
- **Client Base URL:** In the deployed bundle (`index-CM5H3Kin.js`), `ApiClient.getBaseUrl()` returns `"/api"`.
  Browser requests target `https://paypalprip.vercel.app/api/*` (same-origin), which Vercel proxies directly to Render.
- **CORS & Headers:**
  - `OPTIONS /api/health` returns `200 OK` with `Access-Control-Allow-Origin: https://paypalprip.vercel.app` and `Access-Control-Allow-Credentials: true`.
  - `GET /api/health` returns `200 OK` with full health payload.
  - Security headers present: `X-Correlation-Id`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'self'`.

### 2.2 Root Cause of `Backend Status: Offline (Failed to fetch)`
1. **Cold Start Latency:** Render free-tier web services spin down after 15 minutes of inactivity. When a browser loads `https://paypalprip.vercel.app` after an idle period, the initial container boot takes 30 to 50 seconds.
2. **Proxy / Fetch Timeout:** The browser `fetch('/api/health')` or Vercel proxy rewrite times out while Render is booting. The browser JavaScript runtime captures this as `TypeError: Failed to fetch`.
3. **No Automatic Backoff/Retry:** [`frontend/src/pages/Dashboard.tsx`](file:///c:/Users/HP/OneDrive/Desktop/paypal/frontend/src/pages/Dashboard.tsx#L10-L26) executes `checkHealth()` only once on mount (`useEffect(..., [])`). When the first request fails, the UI remains pinned to `Backend Status: Offline (Failed to fetch)` until the user manually clicks "Retry Connection".
4. **Settled State Evidence:** Live browser inspection of `https://paypalprip.vercel.app` after container warm-up showed:
   - Status: `healthy`
   - Database Connected: `Yes`
   - Environment: `development`
   - Version: `0.1.0`
   - Console Errors: `0`
   - Response Latency: `427.6 ms`

---

## 3. Phase 2 — PayPal Order Lifecycle & Trace

### 3.1 Trace of All Supabase Database Orders

#### Order 1: `prip_ord_a780c851d4f6` (PayPal ID: `14Y270278H021861C`)
- **Created At:** `2026-11-11 16:17:43 UTC`
- **SKU & Amount:** `SX-001`, `100.00 USD`
- **Order Status:** `FAILED`
- **Payment Status:** `FAILED`
- **Capture Attempt:** `2026-11-11 16:18:52 UTC`
- **PayPal Response:**
  ```text
  PayPal API Error [422] CAPTURE_FAILED: {"name":"UNPROCESSABLE_ENTITY","details":[{"issue":"ORDER_NOT_APPROVED","description":"Payer has not yet approved the Order for payment. Please redirect the payer to the 'rel':'approve' url returned as part of the HATEOAS links within the Create Order call or provide a valid payment_source in the request."}],"debug_id":"ca58e9d82796f"}
  ```
- **Root Cause of `ORDER_NOT_APPROVED`:** A capture request was intentionally sent during Stage 10 testing *before* buyer approval to verify pre-approval safety. As expected, PayPal rejected premature capture.
- **State Impact:** In accordance with [`backend/services/payment.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/services/payment.py#L116-L120) (`validate_payment_transition`), transitioning to `FAILED` is terminal. The order cannot be re-captured.

#### Order 2: `prip_ord_3d8e5d31f92b` (PayPal ID: `65B995477C126225G`)
- **Created At:** `2026-11-11 16:22:58 UTC`
- **SKU & Amount:** `SX-001`, `100.00 USD`
- **Order Status:** `CREATED`
- **Payment Status:** `PENDING`
- **Preflight Passed:** `True`
- **Demo Reservation:** `(2, 'SX-001', 1, 'RESERVED')`
- **Approval URL:** `https://www.sandbox.paypal.com/checkoutnow?token=65B995477C126225G`
- **Payer Status:** Not yet approved (`Payer: None`)
- **Capture Attempt:** None (Clean)

### 3.2 Frontend Redirect & Return Handling
- **Order Creation & Redirect:** In [`frontend/src/pages/Checkout.tsx`](file:///c:/Users/HP/OneDrive/Desktop/paypal/frontend/src/pages/Checkout.tsx#L85-L98), clicking "Pay with PayPal Sandbox" creates the order and redirects the browser via `window.location.href = order.approve_url`.
- **Return URL Processing:** On return from PayPal, the URL contains `?status=approved&token=<paypal_order_id>`. Lines 57–74 extract `token`, clear query params, and execute `ApiClient.captureOrder(token)`.
- **Backend Resolution:** [`backend/api/checkout.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/api/checkout.py#L101-L105) accepts both local order ID and PayPal order ID, resolving the correct database record.

---

## 4. Phase 3 — Webhook Configuration & Simulator Analysis

### 4.1 Registered Endpoint vs Simulator Root POST
- **Authoritative Webhook Endpoint:**  
  `https://paypal-prip.onrender.com/api/webhooks/paypal`
- **Root Diagnostic Handler:** [`backend/api/main.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/api/main.py#L150-L163) handles requests mistakenly sent to `POST /`:
  ```json
  {
    "error": "INCORRECT_WEBHOOK_URL",
    "message": "PayPal webhook notifications must be delivered to '/api/webhooks/paypal', not root '/'.",
    "registered_webhook_endpoint": "/api/webhooks/paypal"
  }
  ```
- **Finding:** The PayPal Webhook Simulator was configured with `https://paypal-prip.onrender.com/`. When triggered, Render returned HTTP 400 with the diagnostic message. The URL in the PayPal Webhook Simulator must be set to `https://paypal-prip.onrender.com/api/webhooks/paypal`.

### 4.2 Signature Verification & Security Constraints
- **Signature Verification:** [`backend/integrations/paypal/client.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/integrations/paypal/client.py#L260-L330) verifies all 5 PayPal signature headers (`paypal-transmission-id`, `paypal-transmission-time`, `paypal-cert-url`, `paypal-auth-algo`, `paypal-transmission-sig`) by invoking PayPal's `/v1/notifications/verify-webhook-signature` API.
- **Simulator Handling:** PayPal Simulator events send mock headers and simulated IDs. If the Webhook ID in the payload does not match Render's `PAYPAL_WEBHOOK_ID` (`4F133799HS024162A`), PayPal's verification API returns `FAILURE` and PRIP correctly rejects the payload.
- **Policy Enforcement:** Simulator events must **never** be treated as real money or valid checkout captures.

---

## 5. Exact Proposed Corrections (Awaiting Approval)

No application code or cloud configuration was changed during this investigation.

### Proposal 1: Frontend Health-Check Auto-Retry & Warmup Indicator
- **File:** `frontend/src/pages/Dashboard.tsx`
- **Change:** Add an automatic retry loop (up to 3 attempts with 5s backoff) when the initial health check returns `Failed to fetch`, and display a "Waking up backend server..." status instead of immediate "Offline".

### Proposal 2: Correct PayPal Webhook Simulator URL in Dashboard
- **Configuration:** In PayPal Developer Dashboard → Testing Tools → Webhook Simulator:
  - Update **Webhook URL** to: `https://paypal-prip.onrender.com/api/webhooks/paypal`
  - Select registered Webhook ID: `4F133799HS024162A`

### Proposal 3: Clear Buyer Flow for Order `65B995477C126225G`
- **Execution:** Open `https://www.sandbox.paypal.com/checkoutnow?token=65B995477C126225G` in a browser with a PayPal Sandbox Personal Buyer account, complete purchase, and allow the frontend to execute capture upon redirect.

---

## 6. Required Tests After Corrections

1. **Cold-Start Resilience Test:** Verify that `Dashboard.tsx` smoothly transitions from "Waking up backend..." to "healthy" without showing a hard offline error.
2. **Authorized Buyer Approval Test:** Confirm that approving order `65B995477C126225G` in PayPal Sandbox triggers server-side capture returning HTTP 200 with `status: "COMPLETED"`.
3. **Database Capture Verification:** Verify in Supabase that `payment_captures` contains exactly 1 completed capture and `demo_inventory_reservations` is marked `COMMITTED`.
4. **Idempotency Gate Test:** Re-trigger capture on `65B995477C126225G` and confirm the existing completed capture is returned without inserting duplicate rows (enforced by `ix_one_completed_capture_per_order`).

---

## 7. Outstanding Risks

1. **Free-Tier Render Inactivity Sleep:** If the live demo is inactive for >15 minutes, the first page load will take ~30–50s.
2. **Sandbox Buyer Balance:** Sandbox personal buyer accounts must have sufficient virtual funds; otherwise PayPal will return payment decline.
3. **Terminal FAILED State:** Order 1 (`prip_ord_a780c851d4f6`) cannot be reused for checkout since its state is permanently `FAILED`. Order 2 (`prip_ord_3d8e5d31f92b`) must be used.
