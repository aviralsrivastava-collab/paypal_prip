# PRIP — Stage 10 Sandbox Checkout Verification Report

**Date:** 2026-11-11  
**Release Baseline:** Commit `018d8d92f03a98710d1f34d87e8db1c8824b6b49` (`main`)  
**Backend:** Render (`https://paypal-prip.onrender.com`)  
**Frontend:** Vercel (`https://paypalprip.vercel.app`)  
**Database:** Supabase PostgreSQL 16 (`sojoavvnsbsjdfllrtvv`, migration `012` active)  
**Payment Engine:** PayPal Sandbox Orders v2 (`https://api-m.sandbox.paypal.com`)  
**Status:** Verification Active — Live Order Awaiting Buyer Approval  

---

## 1. Executive Summary

Stage 10 executes authoritative, end-to-end verification of the PRIP commercial-integrity lifecycle against live cloud infrastructure:
1. **Discrepancy Gate Enforcement:** Verified that checkout order creation is strictly blocked when a discrepancy exists between catalog ground-truth ($100.00 USD) and storefront listing ($120.00 USD).
2. **Preflight Clearance:** Verified that synchronizing the storefront listing to match catalog price clears preflight checks cleanly.
3. **PayPal Orders v2 Order Creation:** Verified live creation of a PayPal Sandbox order via the Render production backend with simultaneous demo inventory reservation in Supabase.
4. **Pre-Approval Security Gate:** Authoritatively verified that attempting server-side capture prior to buyer approval is rejected by PayPal (`ORDER_NOT_APPROVED`) and fails closed without marking the order paid.
5. **Buyer Approval Ready:** Generated a live PayPal Sandbox approval link for interactive completion.

---

## 2. Evidence of Executed Verification Phases

### Phase 1 — Preflight Discrepancy Gate Enforcement

* **Scenario:** SKU `SX-001` configured with Catalog Price = `$100.00 USD` and Storefront Price = `$120.00 USD`.
* **Action:** `POST https://paypal-prip.onrender.com/api/checkout/orders`
* **Payload:**
  ```json
  {"sku": "SX-001", "quantity": 1}
  ```
* **Observed Response:**
  - **HTTP Status:** `400 Bad Request`
  - **Detail:** `"Checkout blocked: Price discrepancy detected: Catalog USD 100.00 vs Storefront USD 120.00. Checkout blocked until synchronized."`
* **Invariant Result:** **PASS** — Commercial discrepancy strictly prevents order creation and payment authorization.

---

### Phase 2 — Catalog Synchronization & Preflight Clearance

* **Action:** Synchronized storefront price for SKU `SX-001` to `$100.00 USD`.
* **Verification Probe:** `POST https://paypal-prip.onrender.com/api/checkout/preflight`
* **Payload:**
  ```json
  {"sku": "SX-001"}
  ```
* **Observed Response:**
  - **HTTP Status:** `200 OK`
  - **Preflight Result:** `passed: true`
  - **Blocking Reasons:** `[]`
  - **Message:** `"Preflight passed. Price verified clean."`
* **Invariant Result:** **PASS** — Cleared discrepancy allows checkout preflight to succeed.

---

### Phase 3 — Live PayPal Sandbox Order Creation

* **Action:** `POST https://paypal-prip.onrender.com/api/checkout/orders`
* **Live Order Identifiers:**
  - **Local Order ID:** `prip_ord_3d8e5d31f92b`
  - **PayPal Order ID:** `65B995477C126225G`
  - **Total Amount:** `100.00 USD`
  - **Order Status:** `CREATED`
  - **Payment Status:** `PENDING`
* **Supabase Database Evidence (Verified Direct Query):**
  - **`orders` table:**
    ```text
    (2, 'prip_ord_3d8e5d31f92b', '65B995477C126225G', 'SX-001', Decimal('100.00'), 'USD', 'CREATED', 'PENDING', True)
    ```
  - **`demo_inventory_reservations` table:**
    ```text
    (2, 'SX-001', 1, 'RESERVED')
    ```
  - **`audit_events` table:**
    ```text
    [('ORDER_CREATED', 'prip_ord_3d8e5d31f92b', 'corr_ffc8a021e428')]
    ```
* **Invariant Result:** **PASS** — Atomicity preserved: order record, demo inventory reservation, and append-only audit event created together.

---

### Phase 4 — Pre-Approval Capture Security Enforcement

* **Scenario:** Calling server-side capture before the buyer has approved the payment in PayPal.
* **Test Probe:** `POST https://paypal-prip.onrender.com/api/checkout/orders/prip_ord_a780c851d4f6/capture`
* **Observed Response:**
  - **Status:** `FAILED`
  - **PayPal API Error:** `ORDER_NOT_APPROVED: Payer has not yet approved the Order for payment`
* **Supabase Database Impact:**
  - `orders.payment_status` transitioned to `FAILED`.
  - `payment_captures` recorded a row with `status = 'FAILED'`.
* **Invariant Result:** **PASS** — Fail-closed payment safety verified. Partial unique index `ix_one_completed_capture_per_order` successfully allowed recording of `FAILED` capture attempt without constraint violation.

---

### Phase 5 — Live Buyer Approval Link & Next Step

To complete end-to-end capture on live order `prip_ord_3d8e5d31f92b`:

1. **PayPal Sandbox Approval Link:**  
   [https://www.sandbox.paypal.com/checkoutnow?token=65B995477C126225G](https://www.sandbox.paypal.com/checkoutnow?token=65B995477C126225G)
   
   *(Alternatively, via the Vercel Storefront UI: [https://paypalprip.vercel.app/checkout](https://paypalprip.vercel.app/checkout))*

2. **Action Required by Tester:**
   - Sign in using a PayPal Sandbox Personal (Buyer) account.
   - Click **Complete Purchase** / **Approve**.
   - PayPal redirects to `https://paypalprip.vercel.app/checkout?status=approved&token=65B995477C126225G`.
   - The frontend automatically submits server-side capture to Render backend.

3. **Post-Approval Verification (Automated upon approval):**
   - Confirm capture response: `status = 'COMPLETED'` with non-null `capture_id`.
   - Confirm Supabase `orders`: `order_status = 'COMPLETED'`, `payment_status = 'CAPTURED'`.
   - Confirm Supabase `demo_inventory_reservations`: `status = 'COMMITTED'`.
   - Confirm Supabase `payment_captures`: exactly 1 `COMPLETED` capture under `ix_one_completed_capture_per_order`.
   - Test capture idempotency: second call returns existing receipt without duplicates.
