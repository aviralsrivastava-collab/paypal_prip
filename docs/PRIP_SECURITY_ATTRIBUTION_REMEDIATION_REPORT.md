# PRIP — Production Security Attribution & Migration Remediation Report

**Date:** 2026-11-08  
**Scope:** Remediation of Migration 009 Multi-Tenant Backfill & Strict Audit Attribution  
**Verdict:** **REMEDIATION COMPLETE — READY FOR INDEPENDENT RE-AUDIT**

---

## 1. Executive Summary

During the independent production release audit, two related security defects were identified concerning multi-tenant attribution:
1. **Migration 009 Multi-Tenant Backfill Defect:** Migration `009` applied a blanket `server_default='merchant_default'` across existing rows in `diagnoses`, `evidence_items`, `payment_captures`, and `demo_inventory_reservations` without recomputing parent entity relationships, leaving potential orphan records attributed to `merchant_default` and leaving a perpetual schema default.
2. **Audit Attribution Fallback Defect:** Audit event logging across repositories and domain services permitted implicit fallbacks to `'merchant_default'` when actor or entity merchant contexts were omitted or partially initialized, risking misattributed audit trails.

Following explicit architectural guidance, remediation was implemented via non-destructive forward migration `010_tenant_quarantine_and_audit_hardening.py` rather than altering the already-applied migration `009`. Strict fail-closed audit attribution was enforced across all repositories, services, schemas, and API boundaries.

All 186 backend tests and 30 frontend tests pass, including new migration backfill, quarantine isolation, and audit security regression test suites.

---

## 2. Defect Analysis & Migration 010 Resolution

### 2.1 Migration 009 Limitations
In migration `009_tenant_ownership_and_audit_attribution.py`, columns were added to four historical tables with `server_default='merchant_default'`. The script contained a speculative SQL update block that was wrapped in `try...except Exception: pass`, which silently skipped failures. In particular:
- On SQLite, table triggers created in migration `003` (`prevent_evidence_items_update` and `prevent_evidence_items_delete`) immediately aborted any update on `evidence_items`.
- Pre-existing records belonging to other merchants (or unlinked orphan records) were assigned to `merchant_default`.
- The permanent `server_default` on the database schema allowed future inserts to omit `merchant_id` without database-level rejection.

### 2.2 Migration 010 Architecture & Execution
Migration `010_tenant_quarantine_and_audit_hardening.py` was introduced as the new migration head (revising `009`).

Key mechanisms:
1. **Trigger Management (SQLite):** Drops `prevent_evidence_items_update` and `prevent_evidence_items_delete` prior to updating historical evidence rows, and recreates the immutable append-only triggers after schema batch alteration.
2. **Deterministic Lineage Recomputation:**
   - `diagnoses`: `merchant_id` is updated from parent `storefront_scans.merchant_id` where `diagnoses.scan_id = storefront_scans.id`.
   - `evidence_items`: `merchant_id` is updated from parent `storefront_scans.merchant_id` where `evidence_items.scan_id = storefront_scans.id`.
   - `payment_captures`: `merchant_id` is updated from parent `orders.merchant_id` where `payment_captures.order_id = orders.id`.
   - `demo_inventory_reservations`: `merchant_id` is updated from parent `orders.merchant_id` where `demo_inventory_reservations.order_id = orders.id`.
3. **Orphan Quarantine:**
   - Records whose parent scan or order does not exist or whose parent `merchant_id` is null or empty are explicitly updated to `QUARANTINED_ORPHAN`.
   - No merchant ownership is invented or assumed for orphaned records.
4. **Schema Hardening:**
   - Strips `server_default` from `merchant_id` across all four tables via Alembic `batch_alter_table` (`server_default=None`).
5. **Reversibility:**
   - Supports deterministic `downgrade()` (restoring `server_default='merchant_default'`) and re-`upgrade()`.

---

## 3. Reserved System Tenants & Tenant Isolation

Two system identifiers are reserved in `backend/core/security.py`:
- `QUARANTINED_ORPHAN`: Assigned to historical unlinked records whose tenant ownership could not be verified.
- `platform_system`: Assigned to infrastructure events (such as raw inbound webhooks, unassociated dead-letter entries, and system workers).

### Tenant Security Guards:
1. **Authentication Boundary (`security.py`):**
   - `get_current_actor` rejects tokens or headers asserting `QUARANTINED_ORPHAN` or `platform_system` with `HTTP 403 Forbidden`.
   - `require_merchant_access` rejects requests attempting to query or operate under reserved system tenant scopes.
2. **Repository Boundary:**
   - Repositories (`AuditRepository`, `DiagnosisRepository`, `EvidenceRepository`, `PaymentCaptureRepository`, `ReservationRepository`) automatically filter out `QUARANTINED_ORPHAN` records during standard merchant queries.
   - `AuditRepository.list_by_entity` and `list_by_correlation_id` exclude reserved system tenant events from merchant visibility unless explicitly requested by authorized platform tooling (`include_system=True`).

---

## 4. Strict Audit Attribution Call-Site Inventory

Silent fallbacks to `'merchant_default'` were removed across repositories, services, and schemas. Missing, empty, or whitespace-only `merchant_id` values fail closed with `ValueError`. Any discrepancy between payload `merchant_id` and service context raises `ValueError`.

| Domain / Call-Site | Event Type | Attribution Source | Fallback Policy |
| :--- | :--- | :--- | :--- |
| **Inspection** (`inspection.py`) | `INSPECTION_COMPLETED` | `trusted_actor.merchant_id` | Fail closed (`ValueError` if missing) |
| **Diagnosis** (`proposal.py`) | `DIAGNOSIS_GENERATED` | `scan.merchant_id` (persisted parent) | Validated against actor tenancy |
| **Proposal** (`proposal.py`) | `CORRECTION_PROPOSED` | `trusted_actor.merchant_id` | Validated against scan tenancy |
| **Proposal Review** (`proposal.py`) | `CORRECTION_APPROVED`<br>`CORRECTION_REJECTED` | `trusted_actor.merchant_id` | Validated against proposal tenancy |
| **Proposal Execution** (`proposal.py`) | `CORRECTION_EXECUTION_STARTED`<br>`CORRECTION_EXECUTION_SUCCEEDED`<br>`CORRECTION_EXECUTION_FAILED`<br>`CORRECTION_REINSPECTION_SUCCEEDED`<br>`CORRECTION_REINSPECTION_FAILED` | `trusted_actor.merchant_id` | Validated against proposal tenancy |
| **Checkout Preflight & Order** (`checkout.py`) | `ORDER_CREATED` | Explicit `actor.merchant_id` or catalog `product.merchant_id` | Rejects cross-tenant mismatches; fails closed if unresolvable |
| **Payment Capture** (`checkout.py`) | `PAYMENT_CAPTURED` | Parent `order.merchant_id` | Fail closed if missing |
| **Payment Reconciliation** (`checkout.py`) | `RECONCILIATION_ATTEMPTED` | Parent `order.merchant_id` | Fail closed if missing |
| **Inbound Webhook Intake** (`webhook.py`) | `WEBHOOK_RECEIVED`<br>`WEBHOOK_DUPLICATE_IGNORED` | `platform_system` | Fixed infrastructure scope |
| **Webhook Worker** (`webhook_worker.py`) | `WEBHOOK_PROCESSING_FAILED`<br>`WEBHOOK_DEAD_LETTERED`<br>`WEBHOOK_REPLAY_REQUESTED` | Linked `order.merchant_id` if identified, else `platform_system` | Explicit attribution |
| **Demo State Mutation** (`demo_state.py`) | `STATE_MUTATED`<br>`STATE_RESET` | `trusted_actor.merchant_id` or explicit `request.merchant_id` | Fail closed (`ValueError` if missing) |

---

## 5. Verification Commands and Test Results

### 5.1 Test Execution Summary
All automated checks were executed and verified against the repository:

1. **Full Backend Test Suite:**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest backend/tests
   ```
   **Result:** `186 passed in 16.38s`

2. **Dedicated Migration 010 Backfill & Quarantine Test:**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest backend/tests/test_migration_009_multi_tenant_backfill.py
   ```
   **Result:** `4 passed`
   - `test_migration_010_multi_tenant_backfill_and_orphan_quarantine`: Verified scan-to-diagnosis, scan-to-evidence, order-to-capture, order-to-reservation backfill, orphan quarantine under `QUARANTINED_ORPHAN`, and server default removal.
   - `test_migration_010_downgrade_and_reupgrade`: Verified full rollback to `009` and clean re-upgrade to `010`.
   - `test_migration_010_evidence_items_sqlite_triggers`: Verified drop and re-creation of immutable triggers.
   - `test_migration_010_quarantined_orphan_isolation`: Verified quarantined records are excluded from normal queries.

3. **Dedicated Audit Attribution Security Test:**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest backend/tests/test_audit_attribution_security.py
   ```
   **Result:** `6 passed`
   - `test_audit_repository_omitted_merchant_raises_error`: Verified omitted/blank `merchant_id` raises `ValueError`.
   - `test_audit_isolation_cross_tenant_query_blocked`: Verified cross-tenant audit log query isolation.
   - `test_webhook_audit_uses_platform_scope_or_order_merchant`: Verified `platform_system` scoping on unlinked webhook ingestion and order-merchant scoping on linked captures.
   - `test_demo_state_audit_requires_explicit_merchant`: Verified demo state mutation rejects missing merchant attribution.
   - `test_reserved_system_tenants_cannot_be_accessed_by_ordinary_merchants`: Verified HTTP 403 on attempted authentication or querying under `QUARANTINED_ORPHAN` / `platform_system`.
   - `test_audit_service_rejects_conflicting_merchant_ids`: Verified `ValueError` on conflicting merchant IDs.

4. **Code Quality, Static Typing & Architecture:**
   - `ruff check backend`: 0 errors
   - `mypy backend`: 0 issues in 126 source files
   - `lint-imports`: 6 contracts kept, 0 broken
   - `frontend test`: 7 test files, 30 tests passed
   - `frontend lint:arch`: 15 modules, 35 dependencies, 0 violations
   - `frontend build`: Build succeeded (`tsc && vite build`)
   - `scripts/verify.ps1`: All suites passed (186 backend + 30 frontend)
   - `scripts/harness-check.ps1`: Harness check passed

---

## 6. Documented Limitations & Operational Risks

1. **Orphan Inspection & Remediation:** Quarantined orphan records under `QUARANTINED_ORPHAN` remain stored in the database for forensic preservation. They are inaccessible via standard merchant APIs and can only be inspected via privileged administrative database tooling.
2. **PayPal Sandbox Boundary:** Real money processing and live credentials remain strictly prohibited; sandbox configuration and mock clients remain the active enforcement.
3. **SQLite vs PostgreSQL DDL Triggers:** On SQLite, Alembic batch table operations require manual trigger recreation. In PostgreSQL, standard constraints and column alteration operate natively without dropping triggers.

---

## 7. Final Verdict

**REMEDIATION COMPLETE — READY FOR INDEPENDENT RE-AUDIT**
