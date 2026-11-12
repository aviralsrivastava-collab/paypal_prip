# PRIP — Stage 10.4: Controlled Correction Proposal Creation Report

**Date:** 2026-11-12  
**Baseline:** Git Commit `018d8d9` (`main`)  
**Frontend:** `https://paypalprip.vercel.app` (Vercel)  
**Backend:** `https://paypal-prip.onrender.com` (Render)  
**Database:** Supabase PostgreSQL 16 (`sojoavvnsbsjdfllrtvv`, migration `012` active)  
**Status:** SUCCESS — Exactly One Correction Proposal Created in `PENDING_APPROVAL` Status  

---

## 1. Executive Summary

In accordance with Stage 10.4 instructions, all 5 safety preconditions were authoritatively validated before executing an explicit `POST /api/corrections/proposals` request against the live Render backend.

Exactly **one** correction proposal has been created and verified:
- **Proposal ID:** `1`
- **Product SKU:** `SX-001` (StrideX Runner)
- **Referenced Scan:** Scan `#1` (`ISSUE_DETECTED`)
- **Current Storefront Value:** `USD 120.00`
- **Proposed Target Value:** `USD 100.00`
- **Proposal Type:** `PRICE_SYNCHRONIZATION`
- **Policy Validation Status:** `VALID` (Passed all 12 deterministic validation policies)
- **Approval Status:** `PENDING_APPROVAL` (Awaiting explicit human merchant authorization)
- **Execution Status:** `NOT_STARTED`
- **Created By:** `demo-operator-1`
- **Expires At:** `2026-11-13T07:05:18.249485Z` (24-hour expiration window)

---

## 2. Precondition Verification Evidence

Prior to submitting the creation request, the following 5 preconditions were strictly checked against the live system:

| # | Precondition | Observed Evidence | Result |
| :---: | :--- | :--- | :---: |
| **1** | Authenticated Merchant Identity | `actor_id="demo-operator-1"`, `role="merchant_operator"`, `merchant_id="merchant_default"` | **PASS** |
| **2** | Scan #1 Exists and Active | Direct DB query: `id=1`, `sku='SX-001'`, `state='ISSUE_DETECTED'`, `catalog_price=100.00`, `observed_price=120.00` | **PASS** |
| **3** | Four Supporting Evidence Records Exist | `evidence_items` query confirmed 4 records: ID 1 (`EXTRACTION`), ID 2 (`IDENTITY`), ID 3 (`CURRENCY`), ID 4 (`PRICE` mismatch `100.00` vs `120.00`) | **PASS** |
| **4** | Zero Prior Proposals for Scan #1 | Direct DB query confirmed `0` proposals existed for Scan #1 and total proposals in table = `0` | **PASS** |
| **5** | Catalog Ground-Truth Price at USD 100.00 | Direct DB query confirmed `products` row for `SX-001` has `price=100.00`, `currency='USD'` | **PASS** |

---

## 3. Submission Details

- **Endpoint:** `POST https://paypal-prip.onrender.com/api/corrections/proposals`
- **Headers:**
  - `Content-Type: application/json`
  - `X-Actor-ID: demo-operator-1`
  - `X-Actor-Role: merchant_operator`
  - `X-Merchant-ID: merchant_default`
  - `Origin: https://paypalprip.vercel.app`
- **Request Payload:**
  ```json
  {
    "scan_id": 1,
    "sku": "SX-001",
    "proposal_type": "PRICE_SYNCHRONIZATION",
    "proposed_value": 100.00,
    "currency": "USD",
    "reason": "Align controlled storefront price (120.00 USD) with merchant catalog ground truth (100.00 USD).",
    "supporting_evidence_ids": [1, 2, 3, 4],
    "expires_in_hours": 24
  }
  ```
- **Observed Response (HTTP 201 Created):**
  ```json
  {
    "id": 1,
    "merchant_id": "merchant_default",
    "scan_id": 1,
    "diagnosis_id": null,
    "product_id": 1,
    "sku": "SX-001",
    "proposal_type": "PRICE_SYNCHRONIZATION",
    "current_value": "120.00",
    "proposed_value": "100.00",
    "currency": "USD",
    "reason": "Align controlled storefront price (120.00 USD) with merchant catalog ground truth (100.00 USD).",
    "supporting_evidence_ids": [1, 2, 3, 4],
    "policy_validation_status": "VALID",
    "approval_status": "PENDING_APPROVAL",
    "execution_status": "NOT_STARTED",
    "created_at": "2026-11-12T07:05:18.249485Z",
    "updated_at": "2026-11-12T07:05:18.249485Z",
    "expires_at": "2026-11-13T07:05:18.249485Z",
    "created_by": "demo-operator-1",
    "approved_by": null,
    "rejected_by": null,
    "rejection_reason": null,
    "executed_at": null,
    "expected_catalog_version": 1,
    "expected_storefront_version": 1,
    "idempotency_key": null,
    "execution_error": null,
    "execution_correlation_id": null,
    "is_expired": false
  }
  ```

---

## 4. Post-Creation Verification

1. **API List Verification (`GET /api/corrections/proposals`):**
   - **Status:** `200 OK`
   - **Proposals Count:** `1`
   - **Verified Proposal #1:** SKU `SX-001`, proposed value `100.00 USD`, status `PENDING_APPROVAL`.
2. **Direct Supabase Database Record Verification:**
   ```text
   (1, 1, 'SX-001', Decimal('100.00'), 'USD', 'PENDING_APPROVAL', 'NOT_STARTED', 'VALID')
   ```
3. **Frontend Visibility:**
   - Navigating to the live Corrections Hub at [`https://paypalprip.vercel.app/corrections`](https://paypalprip.vercel.app/corrections) now renders Proposal #1 with before/after price cards (`USD 120.00` &rarr; `USD 100.00`), policy validation `VALID`, and the merchant review controls.

---

## 5. Safety Invariants Enforced
- **Single Proposal:** Exactly one proposal created (total rows = 1).
- **No Premature Approval:** `approved_by` is `null`; `approval_status` is strictly `PENDING_APPROVAL`.
- **No Storefront Mutation:** Storefront price remains `USD 120.00`; `executed_at` is `null`.
- **No Checkout Bypass:** Checkout preflight continues to block `SX-001` until correction execution and reinspection complete.
- **No Code Changes:** No application files modified; no git commits or pushes executed.
