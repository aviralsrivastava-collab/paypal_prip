# PRIP Phase 3 Completion Report: Inspection, Comparability, Evidence & Four-State Model

> **Milestone:** Phase 3 — Storefront Inspection, Comparability, Evidence & Four-State Model  
> **Status:** Completed & Fully Verified  
> **Date:** 2026-11-07  
> **Verdict:** APPROVED FOR PHASE 4 WITH DOCUMENTED LIMITATIONS  
> **Primary Scenario Inspected:** StrideX Runner (SKU `SX-001`), Catalog USD 100.00, Controlled Storefront USD 120.00, Inspection State `ISSUE_DETECTED`, Discrepancy +USD 20.00, 4 Structured Evidence Items with SHA-256 Content Hashes.

---

## 1. Executive Summary

Phase 3 implements the deterministic inspection, comparability, evidence tracking, and idempotency engine of the PayPal Revenue Intelligence Platform (PRIP).
The inspection engine retrieves authoritative merchant catalog ground truth, extracts customer-facing storefront observations through a controlled integration adapter, deterministically evaluates observation comparability across six key business dimensions, and assigns exactly one honest classification within the mandatory four-state model:

1. `ISSUE_DETECTED`: Comparable facts confirm a price discrepancy or policy violation.
2. `VERIFIED_NO_ISSUE`: All required observations are comparable and match ground truth.
3. `BLOCKED_UNKNOWN`: Inconclusive inspection due to extraction failure, currency mismatch, variant discrepancy, missing product, or timeout. Missing evidence is never treated as evidence of correctness.
4. `NOT_TESTED`: Product has not yet undergone inspection.

All external extraction network operations occur strictly outside database transactions to eliminate lock contention. When extraction completes, the scan record, individual structured evidence records, and append-only audit events are committed atomically within a single transactional boundary.

---

## 2. Implemented & Modified Components

### 2.1 Pure Deterministic Policies (`backend/policies/`)
- **`backend/policies/inspection_state.py`**:
  - Defines `InspectionState` enum (`ISSUE_DETECTED`, `VERIFIED_NO_ISSUE`, `BLOCKED_UNKNOWN`, `NOT_TESTED`).
  - Implements `classify_outcome(...)`: pure functional classifier enforcing that non-comparable observations or extraction failures can **never** collapse into `VERIFIED_NO_ISSUE`.
- **`backend/policies/comparability.py`**:
  - Pure dataclasses `CatalogProductFacts`, `StorefrontObservationFacts`, and `ComparabilityResult`.
  - Implements `evaluate_comparability(...)` checking SKU identity, currency equality, price basis, variant consistency, promotion context, and availability.
  - **Critical Invariant:** If comparability fails (e.g., currency mismatch `USD` vs `EUR`), `price_discrepancy` is strictly `None`. The engine never performs numerical subtraction across differing currencies or disparate product variants.
- **`backend/policies/evidence_integrity.py`**:
  - Pure deterministic canonicalization and hashing module.
  - Implements `compute_evidence_hash(...)`: creates canonical SHA-256 digests over standardized evidence fields.
  - Implements `verify_evidence_hash(...)`: detects any tampering or modification to observed values, timestamps, or digests.
  - Implements `compute_request_hash(...)`: generates SHA-256 request fingerprints for inspection idempotency.

### 2.2 Controlled Storefront Extraction (`backend/integrations/storefront/`)
- **`backend/integrations/storefront/extractor.py`**:
  - `ExtractionStatus` enum (`SUCCESS`, `MISSING_PRODUCT`, `TIMEOUT`, `BLOCKED_ACCESS`, `UNSUPPORTED_CONTENT`, `EXTRACTION_ERROR`).
  - `StorefrontObservation` typed container computing SHA-256 cryptographic hashes over normalized observation payloads.
  - `StorefrontExtractor` controlled adapter extracting facts without arbitrary web-crawling hazards or bot bypasses. Includes deterministic simulation hooks (`timeout`, `missing`, `blocked`, `unsupported`) for rigorous automated testing.

### 2.3 Database Entities & Repositories (`backend/models/`, `backend/repositories/`)
- **`backend/models/scan.py`**:
  - `StorefrontScan` entity (`storefront_scans` table) persisting scan state, catalog price, observed price, currency, numerical discrepancy, comparability flag, failure reason, correlation ID, `idempotency_key` (unique index), and `request_hash`.
- **`backend/models/evidence.py`**:
  - `EvidenceItem` entity (`evidence_items` table) linked via foreign key to `storefront_scans.id` with `ondelete="CASCADE"`. Stores `evidence_type` (`EXTRACTION`, `IDENTITY`, `CURRENCY`, `PRICE`), `field_name`, `expected_value`, `observed_value`, `source_url`, `observation_timestamp`, `content_hash`, `status`, and `details`.
- **`backend/repositories/scan.py`**:
  - `ScanRepository` providing `create`, `get_by_id`, `get_by_idempotency_key`, `list_by_sku`, and `get_latest_by_sku`.
- **`backend/repositories/evidence.py`**:
  - `EvidenceRepository` providing `create`, `create_many`, and `list_by_scan_id`.

### 2.4 Orchestration Service & API Contracts (`backend/services/`, `backend/api/`)
- **`backend/services/inspection.py`**:
  - `InspectionService`: Orchestrates the inspection lifecycle:
    1. Evaluates idempotency key against historical scans using request fingerprinting.
    2. Reads authoritative catalog ground truth.
    3. Performs external extraction **strictly outside database transactions**.
    4. Runs deterministic comparability policies.
    5. Evaluates outcome using the 4-state classifier.
    6. Atomically persists the scan record, evidence items, and an `INSPECTION_COMPLETED` audit event within `atomic_transaction`.
    7. Catches concurrent race conditions with unique constraint handling.
- **`backend/schemas/scan.py`**:
  - Pydantic models `ScanCreateRequest` (with `idempotency_key`), `EvidenceItemResponse` (with `integrity_verified`), `ScanSummaryResponse`, and `ScanDetailResponse`.
- **`backend/api/scans.py`**:
  - `POST /api/scans`: Triggers an inspection with optional `Idempotency-Key` header; maps conflict to HTTP 409.
  - `GET /api/scans/{scan_id}`: Retrieves full scan detail with linked evidence items.
  - `GET /api/scans/{scan_id}/evidence`: Retrieves structured evidence records for a scan with integrity verification status.
  - `GET /api/scans/product/{sku}`: Retrieves historical inspection timeline for a product.
- **`backend/api/main.py`**: Mounted `scans_router`.

### 2.5 Database Migration (`backend/migrations/`)
- **`backend/migrations/versions/003_scans_and_evidence.py`**:
  - Schema migration creating `storefront_scans` (with unique `idempotency_key` constraint) and `evidence_items` tables.
  - Creates SQLite `BEFORE UPDATE` and `BEFORE DELETE` abort triggers on `evidence_items` (`prevent_evidence_items_update` and `prevent_evidence_items_delete`) to enforce database-level immutability.
  - Downgrade script cleanly removes triggers, indexes, and tables.

### 2.6 Frontend Implementation (`frontend/`)
- **`frontend/src/types/index.ts`**: Declared `EvidenceItem` (with `integrity_verified`), `ScanSummary`, and `ScanDetail` matching backend schemas.
- **`frontend/src/services/api.ts`**: Implemented client methods `triggerScan` (forwarding `Idempotency-Key`), `getScan`, `getProductScans`, and `getScanEvidence`.
- **`frontend/src/pages/Inspection.tsx`**:
  - Full inspection view featuring:
    - Dedicated color-coded banner for all four states (`ISSUE_DETECTED`, `VERIFIED_NO_ISSUE`, `BLOCKED_UNKNOWN`, `NOT_TESTED`).
    - Interactive inspection runner with test fault-injection simulation selector.
    - Ground truth vs observed price comparison panel with discrepancy indicator.
    - Structured evidence table detailing each evidence item with status badges and SHA-256 hashes.
    - Historical scan timeline with click-to-inspect detail view.
- **`frontend/tests/Inspection.test.tsx`**: Component tests verifying initial `NOT_TESTED` state, `ISSUE_DETECTED` discrepancy view, `VERIFIED_NO_ISSUE` view, `BLOCKED_UNKNOWN` inconclusive view, and interactive scan execution.

---

## 3. Data Flow & Transaction Boundaries

```
[ Merchant / User ]
         |
         | POST /api/scans (Header: Idempotency-Key)
         v
[ API: scans_router ]
         |
         v
[ InspectionService ]
         |
         |-- 1. Idempotency & Request Fingerprint Pre-Check
         |      If duplicate key with identical payload: return existing scan.
         |      If duplicate key with differing payload: raise HTTP 409 Conflict.
         |
         |-- 2. Read Catalog Ground Truth (ProductRepository)
         |
         |-- 3. External Storefront Extraction (StorefrontExtractor)
         |      *** NO DATABASE TRANSACTION HELD ***
         |      Returns StorefrontObservation + Raw Snippet + Hash
         |
         |-- 4. Deterministic Comparability Check (evaluate_comparability)
         |      Checks: SKU, Currency, Variants, Price Basis, Availability
         |
         |-- 5. Mandatory 4-State Classification (classify_outcome)
         |      Returns: ISSUE_DETECTED | VERIFIED_NO_ISSUE | BLOCKED_UNKNOWN
         |
         |-- 6. Canonical SHA-256 Evidence Hashing (compute_evidence_hash)
         |
         |-- 7. ATOMIC DATABASE TRANSACTION (atomic_transaction)
                |-- Create StorefrontScan (Unique: idempotency_key)
                |-- Create Many EvidenceItems (FK: scan.id)
                |-- Log AuditEvent ('INSPECTION_COMPLETED')
                |-- On Concurrent Race: Catch IntegrityError & reconcile
```

---

## 4. Three-Point Integrity Verification Findings

### 4.1 Check 1 — Database Transaction Boundaries & Rollback Integrity
- **Finding**: Storefront extraction occurs strictly outside database transactions. Catalog facts are extracted into detached dataclass instances, any open read transaction is committed before external I/O, and the persistence block (`atomic_transaction`) opens only when all observations, comparability evaluations, and evidence objects are prepared.
- **Failure-Injection Verification**:
  - Failure during evidence creation (`evidence_repo.create_many` injected failure) caused an immediate rollback: 0 scans, 0 evidence items, and 0 audit events remained in the database.
  - Failure during audit event creation (`AuditService.log_event` injected failure) caused an immediate rollback: 0 scans, 0 evidence items, and 0 audit events remained.
  - Failure during database commit (`session.commit` injected failure) left 0 partial records.
- **Automated Tests**: Implemented in `backend/tests/test_phase3_three_point_verification.py` (`TestDatabaseTransactionBoundaries`).

### 4.2 Check 2 — Evidence Integrity, Canonical Hashing & Database Immutability
- **Canonicalization Rules**:
  1. *Timestamp Normalization*: Observation timestamps are converted to UTC and formatted as ISO 8601 without microseconds (`%Y-%m-%dT%H:%M:%SZ`).
  2. *Deterministic Keys*: Standard dictionary containing sorted keys: `['details', 'evidence_type', 'expected_value', 'field_name', 'observation_timestamp', 'observed_value', 'source_url', 'status']`.
  3. *Whitespace Elimination*: Serialized with `json.dumps(..., sort_keys=True, separators=(',', ':'))`.
  4. *Digest*: Encoded as UTF-8 bytes and hashed with SHA-256 to a 64-character lowercase hexadecimal string.
- **Tamper Detection Verification**:
  - Normal evidence retrieval verifies stored content against its hash (`integrity_verified=True`).
  - Injected modification to `observed_value` (e.g., from `120.00` to `100.00`) immediately causes `verify_evidence_hash` and `integrity_verified` to evaluate to `False`.
  - Injected modification to `content_hash` immediately causes `verify_evidence_hash` to evaluate to `False`.
- **Database-Level Immutability**:
  - SQLite triggers `prevent_evidence_items_update` and `prevent_evidence_items_delete` installed via migration `003_scans_and_evidence`.
  - Direct SQL `UPDATE evidence_items SET observed_value = '100.00'` was aborted with: `evidence_items is append-only: updates are prohibited`.
  - Direct SQL `DELETE FROM evidence_items` was aborted with: `evidence_items is append-only: deletions are prohibited`.
  - Normal evidence insertion succeeded.
  - Migration downgrade (`alembic downgrade 002`) cleanly dropped triggers and tables.
- **Integrity Guarantee Disclosures**:
  - *What is guaranteed*: Deterministic integrity verification detects unintended drift, application tampering, data corruption, and column modifications. Database triggers prevent direct SQL modifications.
  - *What is NOT guaranteed*: An unkeyed SHA-256 digest is not a cryptographic digital signature (HMAC or PKI). An actor with privileged database write access could alter values and recompute the SHA-256 digest. It is not a distributed immutable ledger.

### 4.3 Check 3 — Inspection Idempotency, Request Fingerprinting & Concurrency Safety
- **Idempotency Strategy & Scope**:
  - Clients may supply an idempotency key via the `Idempotency-Key` HTTP header or `idempotency_key` JSON body field.
  - Request Fingerprint: Computed via SHA-256 over canonical request parameters: `{"sku": request.sku.strip().upper(), "simulated_scenario": request.simulated_scenario}`.
  - Database Uniqueness: Enforced via a `UNIQUE` index on `storefront_scans.idempotency_key`.
- **Verification Results**:
  - First request with a novel key creates exactly one inspection.
  - Repeating the request with the same key returns the existing inspection result without executing duplicate extraction or creating duplicate audit events.
  - Reusing the key with conflicting request parameters (e.g. differing simulation scenario) raises `IdempotencyConflictError`, mapped to HTTP 409 Conflict.
  - New idempotency keys create new distinct inspection scans.
  - Concurrent duplicate requests (tested via `ThreadPoolExecutor` with 4 concurrent threads) safely resolve via the unique constraint: all threads receive the exact same scan ID, and exactly one scan and one audit record are created in the database.
  - Simulated client timeout followed by retry seamlessly retrieves the persisted scan without duplicating records.

---

## 5. Verification & Quality Gates Summary

| Suite / Gate | Command | Result |
| :--- | :--- | :---: |
| **Backend Unit & Integration Tests** | `pytest backend/tests -v` | **57 passed** (3.36s) |
| **Phase 3 Integrity Tests** | `pytest backend/tests/test_phase3_three_point_verification.py -v` | **15 passed** (1.07s) |
| **Backend Linting** | `ruff check backend` | **0 errors (clean)** |
| **Backend Type Checking** | `mypy backend` | **0 errors across 61 files** |
| **Backend Architecture Boundaries** | `lint-imports` | **4 kept, 0 broken** |
| **Frontend Unit & Component Tests** | `npm test -- --run` | **12 passed across 4 suites** |
| **Frontend Type Checking** | `npm run lint` (`tsc --noEmit`) | **0 errors (clean)** |
| **Frontend Architecture Boundaries** | `npm run lint:arch` (`depcruise`) | **0 violations across 13 modules** |
| **Frontend Production Build** | `npm run build` (`vite build`) | **Clean bundle (183.87 kB)** |
| **Migration Upgrade/Downgrade** | `alembic downgrade 002; alembic upgrade head` | **Verified clean** |
| **Repository Harness Check** | `powershell scripts/harness-check.ps1` | **Passed** |
| **Full Verification Script** | `powershell scripts/verify.ps1` | **Passed (57 backend + 12 frontend)** |

---

## 6. Invariant Checklist

| Invariant | Status | Implementation Reference |
| :--- | :---: | :--- |
| **Merchant catalog is source of truth** | Enforced | `CatalogProductFacts` retrieved from `products` table |
| **Strict 4-State Model** | Enforced | `backend/policies/inspection_state.py` |
| **`BLOCKED_UNKNOWN` cannot become `VERIFIED_NO_ISSUE`** | Enforced | `test_8_critical_invariant_blocked_unknown_cannot_become_verified_no_issue` |
| **Zero numerical discrepancy on non-comparable** | Enforced | `evaluate_comparability` sets `price_discrepancy = None` |
| **No DB transaction during external extraction** | Enforced | `InspectionService.run_inspection` commits read state before extraction |
| **Rollback integrity on failure injection** | Enforced | Tested on evidence failure, audit failure, and commit failure |
| **Structured evidence with SHA-256 hash** | Enforced | `compute_evidence_hash` and `verify_evidence_hash` |
| **Evidence database-level immutability** | Enforced | SQLite triggers `prevent_evidence_items_update/delete` |
| **Inspection Idempotency & Conflict detection** | Enforced | Unique constraint, request fingerprinting, HTTP 409 mapping |
| **Universal append-only audit trail** | Enforced | `INSPECTION_COMPLETED` logged atomically in transaction |
| **No AI mutation or checkout logic in Phase 3** | Enforced | Out of scope; verified by import-linter |

---

## 7. Documented Limitations & Scope Boundaries

1. **Controlled Demo Storefront**: Storefront extraction operates against the controlled demo storefront environment with fault injection hooks. It is not an arbitrary internet crawler and does not attempt anti-bot bypass.
2. **AI Diagnosis Deferred**: Root-cause analysis and LLM explanation are strictly deferred to Phase 4.
3. **Merchant Correction Deferred**: Approval workflows and controlled catalog-to-storefront corrections belong to Phase 5.
4. **PayPal Checkout Deferred**: Sandbox orders, captures, webhooks, and reconciliation belong to Phase 6.

---

## 8. Final Verdict

**APPROVED FOR PHASE 4 WITH DOCUMENTED LIMITATIONS**
