# PRIP — Stage 10.3: Correction Proposal Generation Diagnostic Report

**Date:** 2026-11-12  
**Baseline:** Git Commit `018d8d9` (`main`)  
**Frontend:** `https://paypalprip.vercel.app`  
**Backend:** `https://paypal-prip.onrender.com`  
**Database:** Supabase PostgreSQL 16 (`sojoavvnsbsjdfllrtvv`, migration `012` active)  
**Status:** Investigation Complete — No Database Mutations or Code Changes Applied (Awaiting Operator Approval)  

---

## 1. Executive Summary

| Check / Domain | Status | Key Finding |
| :--- | :---: | :--- |
| **Discrepancy Detection Workflow** | **PASS** | Inspection engine correctly detected price mismatch (Catalog USD 100.00 vs Storefront USD 120.00) and recorded Scan #1 with state `ISSUE_DETECTED` and 4 evidence items. |
| **Proposal Database State** | **VERIFIED (0 ROWS)** | Exactly **0** rows exist in `correction_proposals`. Proposals were neither expired, rejected, nor soft-deleted; none was ever created. |
| **Proposal Generation Model** | **EXPLICIT (NOT AUTOMATIC)** | Proposal creation is decoupled from inspection and AI diagnosis. PRIP invariants mandate that AI is strictly advisory and cannot autonomously create mutation proposals. |
| **Frontend Implementation Gap** | **GAP IDENTIFIED** | `ApiClient.createProposal()` is implemented in [`frontend/src/services/api.ts`](file:///c:/Users/HP/OneDrive/Desktop/paypal/frontend/src/services/api.ts#L166-L188), but **no UI component in the entire frontend (`Inspection.tsx`, `Corrections.tsx`, or `Dashboard.tsx`) ever calls it**. |
| **Corrections Hub API Handling** | **PASS** | `GET /api/corrections/proposals` returns HTTP 200 with an empty list `[]`. No backend errors are hidden; the UI honestly reports "No proposals found matching filter." |

---

## 2. Phase 1 — Backend Investigation

### 2.1 Discrepancy Detection Workflow
1. When an inspection scan runs (`POST /api/scans`), [`InspectionService.run_inspection()`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/services/inspection.py) compares catalog price against storefront observations.
2. In Supabase, **Scan #1** exists:
   - **SKU:** `SX-001`
   - **State:** `ISSUE_DETECTED`
   - **Catalog Price:** `USD 100.00`
   - **Observed Price:** `USD 120.00`
   - **Discrepancy:** `USD 20.00`
   - **Supporting Evidence Items:** 4 records (Evidence ID 1: `EXTRACTION`, ID 2: `IDENTITY`, ID 3: `CURRENCY`, ID 4: `PRICE` mismatch).
3. The inspection service records evidence and determines the 4-state outcome, but **by design does not create mutation proposals**.

### 2.2 Proposal Generation Services
- [`ProposalService.create_proposal()`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/services/proposal.py#L50-L105) handles proposal creation.
- It requires an explicit request specifying:
  - `scan_id`: Must reference a valid completed scan.
  - `sku`: Must match catalog ground-truth.
  - `proposed_value`: Must match catalog price (USD 100.00).
  - `supporting_evidence_ids`: Must belong to the scan evidence set.
  - `proposal_type`: Must be allowlisted (`PRICE_SYNCHRONIZATION`).
- When called, it deterministically validates the proposal against 12 policy rules, pins expected catalog and storefront versions, and inserts a row into `correction_proposals` with `approval_status = 'PENDING_APPROVAL'`.

### 2.3 Automatic vs. Explicit Action
- **Proposal generation is 100% EXPLICIT.**
- PRIP non-negotiable architectural invariant ([`AGENTS.md`](file:///c:/Users/HP/OneDrive/Desktop/paypal/AGENTS.md)):
  > *"AI may explain evidence and propose an allowlisted correction. AI must not approve, apply corrections, mutate catalog/storefront data, create/capture payments, or override policy."*
- Consequently:
  - Neither `InspectionService.run_inspection()` nor `DiagnosisService.diagnose_scan()` contains any code to insert into `correction_proposals`.
  - Proposal creation requires an explicit `POST /api/corrections/proposals` call.

### 2.4 Supabase Database Record Verification
A direct read-only query against the live Supabase PostgreSQL database revealed:
- `SELECT COUNT(*) FROM correction_proposals` &rarr; **0**
- `SELECT COUNT(*) FROM storefront_scans WHERE state = 'ISSUE_DETECTED'` &rarr; **3** (Scans #1, #2, #3)
- `SELECT COUNT(*) FROM diagnoses` &rarr; **1** (Diagnosis #1 on Scan #1, status `COMPLETED`)
- **Conclusion:** Proposals were never rejected or expired; no proposal has ever been created in this database.

---

## 3. Phase 2 — Frontend Investigation

### 3.1 Corrections Dashboard API Request
- In [`frontend/src/pages/Corrections.tsx`](file:///c:/Users/HP/OneDrive/Desktop/paypal/frontend/src/pages/Corrections.tsx#L31-L48), `loadProposals()` executes:
  ```typescript
  const data = await ApiClient.getProposals();
  setProposals(data);
  ```
- Probed live endpoint: `GET https://paypal-prip.onrender.com/api/corrections/proposals`
  - **HTTP Status:** `200 OK`
  - **Response:** `[]` (Empty Array)
- No error is thrown and no error is hidden. The frontend receives valid empty data.

### 3.2 Filtering, Pagination, and Refresh
- **Filtering:** Tabs (`ALL`, `PENDING_APPROVAL`, `APPROVED`, `REJECTED`, `EXPIRED`) filter the local `proposals` array. Because `proposals` is empty, all tabs display:
  `"No proposals found matching filter."`
- **Refresh Button:** Calls `loadProposals()`, cleanly issuing another `GET /api/corrections/proposals` request.

### 3.3 The Missing Frontend Link
- In [`frontend/src/services/api.ts`](file:///c:/Users/HP/OneDrive/Desktop/paypal/frontend/src/services/api.ts#L166-L188), the API helper `ApiClient.createProposal()` is fully implemented:
  ```typescript
  public static async createProposal(data: {
    scan_id: number;
    sku: string;
    proposal_type: string;
    proposed_value: string;
    currency: string;
    supporting_evidence_ids: number[];
    idempotency_key?: string;
  }): Promise<CorrectionProposal>
  ```
- However, a codebase search reveals that `ApiClient.createProposal` is **not imported or referenced anywhere in `frontend/src/pages/`**.
  - On the **Inspection page** ([`frontend/src/pages/Inspection.tsx`](file:///c:/Users/HP/OneDrive/Desktop/paypal/frontend/src/pages/Inspection.tsx)), once an issue is detected and diagnosed, the UI displays "Advisory Recommendations for Merchant" but provides no button to generate a correction proposal.
  - On the **Corrections page** ([`frontend/src/pages/Corrections.tsx`](file:///c:/Users/HP/OneDrive/Desktop/paypal/frontend/src/pages/Corrections.tsx)), there is only a proposal consumer interface (Approve, Reject, Execute, Reconcile) with no creation form.

---

## 4. Phase 3 — Root Cause

**Why does `ISSUE_DETECTED` exist while proposal count remains zero?**

1. **Architectural Separation:** In PRIP, detecting an issue (`storefront_scans`) does not automatically generate a correction proposal (`correction_proposals`). This ensures merchant governance and avoids autonomous mutations.
2. **Missing UI Trigger:** The frontend UI lacks a button or workflow step to transition an inspected discrepancy (`ISSUE_DETECTED`) into a formalized correction proposal.
3. Because no actor (merchant or script) submitted a `POST /api/corrections/proposals` request for Scan #1, the `correction_proposals` table remains empty.

---

## 5. Phase 4 — Recommendations & Proposed Action Plan

### Recommended Option A: Controlled Operator API Request (Immediate, Zero Code Changes)
To immediately populate the Corrections Hub for testing without modifying any code:
Issue an authorized `POST` request to `https://paypal-prip.onrender.com/api/corrections/proposals` linking Scan #1:

```bash
curl -X POST https://paypal-prip.onrender.com/api/corrections/proposals \
  -H "Content-Type: application/json" \
  -H "X-Actor-ID: demo-operator-1" \
  -H "X-Actor-Role: merchant_operator" \
  -H "X-Merchant-ID: merchant_default" \
  -d '{
    "scan_id": 1,
    "sku": "SX-001",
    "proposal_type": "PRICE_SYNCHRONIZATION",
    "proposed_value": 100.00,
    "currency": "USD",
    "reason": "Align controlled storefront price (120.00 USD) with merchant catalog ground truth (100.00 USD).",
    "supporting_evidence_ids": [1, 2, 3, 4],
    "expires_in_hours": 24
  }'
```

**Outcome:**
1. A valid proposal is created in `PENDING_APPROVAL` status in Supabase.
2. Navigating to `https://paypalprip.vercel.app/corrections` will immediately display Proposal #1 with:
   - Storefront USD 120.00 &rarr; Catalog Target USD 100.00
   - Policy Validation: `VALID`
   - Active "Approve Proposal" and "Reject Proposal" buttons.
3. The merchant can complete the approval, execute the correction, and verify the checkout flow.

---

### Recommended Option B: Frontend UI Link (Permanent Feature)
Add a "Generate Correction Proposal" button in [`frontend/src/pages/Inspection.tsx`](file:///c:/Users/HP/OneDrive/Desktop/paypal/frontend/src/pages/Inspection.tsx) directly below the AI Advisory Recommendations section when `currentScan.state === 'ISSUE_DETECTED'`.
- When clicked, it calls `ApiClient.createProposal(...)` using the current scan data and supporting evidence IDs, then redirects to `/corrections`.

---

## 6. Strict Safety Compliance Summary
- Catalog price was NOT modified (remains USD 100.00).
- Storefront price was NOT modified (remains USD 120.00).
- No proposals were created or approved.
- No Supabase records were inserted or updated.
- No code was modified, committed, pushed, or deployed.
