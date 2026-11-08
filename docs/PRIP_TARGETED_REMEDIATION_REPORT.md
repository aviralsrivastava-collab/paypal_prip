# PRIP — Targeted Remediation Report: Reserved Audit Access, Trusted Demo-State Attribution & Migration Validation

**Date:** 2026-11-08  
**Scope:** Remediation of Reserved Audit Access Controls, Trusted Demo-State Attribution, and Migration 010/011 Ownership Validation  
**Verdict:** **REMEDIATION COMPLETE — READY FOR FINAL INDEPENDENT RE-AUDIT**

---

## 1. Executive Summary

This report documents the resolution of the three findings identified in the independent source review:
1. **Audit Repository Access Controls:** Fixed vulnerability in `AuditRepository` where querying with explicit reserved tenant IDs or using unverified boolean flags (`include_system`, `allow_quarantined`) could expose reserved system tenants (`QUARANTINED_ORPHAN`, `platform_system`, `platform`). Added an authorized service boundary in `AuditService`.
2. **Trusted Demo-State Attribution:** Removed reliance on client-supplied `request.actor_id` and `request.merchant_id` in `DemoStateService.update_state_with_audit`. Required server-side `trusted_actor: AuthenticatedActor`, rejected tenant/actor mismatches, and enforced fail-closed semantics. Documented that no external production API route exposes this service.
3. **Migration 010/011 Ownership Validation:** Tightened `010_tenant_quarantine_and_audit_hardening.py` and created forward migration `011_revalidate_parent_tenant_ownership.py` to ensure records whose parent scan/order has null, empty, or whitespace-only `merchant_id` (or null foreign key / non-existent parent) are quarantined under `QUARANTINED_ORPHAN`.

All 191 backend tests and 30 frontend tests pass cleanly, with 0 architecture violations and clean typing/linting.

---

## 2. Findings and Corrections

### Finding 1: Audit Repository Access Controls
- **Vulnerability:** `AuditRepository.list_by_entity` and `list_by_correlation_id` directly filtered `AuditEvent.merchant_id == merchant_id` when `merchant_id` was supplied. If an ordinary caller explicitly queried `merchant_id="QUARANTINED_ORPHAN"` or `merchant_id="platform_system"`, those events were exposed. Furthermore, `allow_quarantined=True` in `list_by_merchant` and `include_system=True` were unverified boolean flags, and `"platform"` was missing from the recognized reserved list.
- **Correction:**
  - Standardized on `RESERVED_SYSTEM_TENANTS = {"QUARANTINED_ORPHAN", "platform_system", "platform"}` imported from `backend/core/security.py`.
  - In `AuditRepository.list_by_entity` and `list_by_correlation_id` ([backend/repositories/audit.py](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/repositories/audit.py#L63-L125)):
    - If `merchant_id in RESERVED_SYSTEM_TENANTS` and caller lacks platform administrative privileges (`role not in {"superadmin", "system_admin"}`), the query returns `[]`.
    - If `include_system=True` is supplied without platform administrative privileges, raises `PermissionError`.
  - In `AuditRepository.list_by_merchant` ([backend/repositories/audit.py](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/repositories/audit.py#L128-L151)):
    - Querying a reserved tenant without platform administrative privileges returns `[]`.
    - Setting `allow_quarantined=True` without platform administrative privileges raises `PermissionError`.
  - In `AuditService` ([backend/services/audit.py](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/services/audit.py#L36-L118)):
    - Added authorized query methods: `list_events_by_entity`, `list_events_by_correlation_id`, and `list_events_by_merchant`.
    - Enforces that privileged system access requires platform admin roles (`superadmin`, `system_admin`) and ordinary merchant queries remain strictly scoped to `actor.merchant_id`.

### Finding 2: Demo-State Trusted Attribution
- **Vulnerability:** In `DemoStateService.update_state_with_audit` and `StateUpdateRequest`, actor identity and merchant attribution were accepted from client request bodies (`request.actor_id`, `request.merchant_id`) rather than a trusted authentication context.
- **Correction:**
  - In `backend/schemas/demo_state.py` ([backend/schemas/demo_state.py](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/schemas/demo_state.py#L7-L14)): Made `actor_id` optional in `StateUpdateRequest`.
  - In `backend/services/demo_state.py` ([backend/services/demo_state.py](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/services/demo_state.py#L44-L138)):
    - Added `trusted_actor: Optional[AuthenticatedActor] = None` parameter.
    - Missing trusted actor fails closed with `UnauthorizedError("Unauthorized: actor identity required for mutation (missing trusted actor context)")`.
    - Unauthenticated actors (`is_authenticated=False` or `actor_id="anonymous"`) fail closed with `UnauthorizedError`.
    - Actors asserting reserved system tenants (`QUARANTINED_ORPHAN`, `platform_system`, `platform`) fail closed with `UnauthorizedError`.
    - Validates client-supplied fields: if `request.merchant_id` differs from `trusted_actor.merchant_id`, raises `ValueError("Tenant mismatch...")`. If `request.actor_id` differs from `trusted_actor.actor_id`, raises `UnauthorizedError("Actor mismatch...")`.
    - Audit entry is stamped with trusted `actor_id = trusted_actor.actor_id.strip()` and `merchant_id = trusted_actor.merchant_id.strip()`.
    - Verified all-or-nothing atomicity within `atomic_transaction(session)`.
  - **API Route Disclosure:** Confirmed that `DemoStateService` is an internal test/demonstration service; no public or production FastAPI route exists or was invented.

### Finding 3: Migration 010/011 Ownership Validation
- **Vulnerability:** Migration `010` backfill only quarantined records when the parent did not exist or foreign key was null. If a parent record had an empty string `""`, whitespace `"   "`, or `NULL` as its `merchant_id`, the invalid parent ownership was copied to the child record without quarantine.
- **Correction:**
  - In `backend/migrations/versions/010_tenant_quarantine_and_audit_hardening.py` ([backend/migrations/versions/010_tenant_quarantine_and_audit_hardening.py](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/migrations/versions/010_tenant_quarantine_and_audit_hardening.py#L37-L83)):
    - Step 1: Only updates child `merchant_id` when parent exists, parent `merchant_id IS NOT NULL`, and `TRIM(parent.merchant_id) != ''` and not in reserved system tenants.
    - Step 2: Quarantines records where foreign key is null, parent does not exist, parent `merchant_id IS NULL OR TRIM(parent.merchant_id) = ''`, or child `merchant_id IS NULL OR TRIM(merchant_id) = ''`.
  - In forward migration `011_revalidate_parent_tenant_ownership.py` ([backend/migrations/versions/011_revalidate_parent_tenant_ownership.py](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/migrations/versions/011_revalidate_parent_tenant_ownership.py#L1-L110)):
    - Non-destructive forward migration revising `010_tenant_quarantine_and_audit_hardening`.
    - Re-evaluates all 4 tables (`diagnoses`, `evidence_items`, `payment_captures`, `demo_inventory_reservations`) in existing databases where 010 was already applied.
    - Preserves historical migration immutability (did not rewrite historical migration 009 or 010).

---

## 3. Files Changed and Exact Line References

| File | Exact Lines | Purpose |
| :--- | :--- | :--- |
| [`backend/repositories/audit.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/repositories/audit.py) | L6, L54-L60, L63-L93, L96-L125, L128-L151 | Reserved tenant protection (`RESERVED_SYSTEM_TENANTS`), privilege checks, prevention of unauthorized query access. |
| [`backend/services/audit.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/services/audit.py) | L5-L9, L36-L118 | Authorized query service boundary (`list_events_by_entity`, `list_events_by_correlation_id`, `list_events_by_merchant`). |
| [`backend/schemas/demo_state.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/schemas/demo_state.py) | L11-L12 | Made `actor_id` optional in `StateUpdateRequest`. |
| [`backend/services/demo_state.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/services/demo_state.py) | L7, L44-L93, L120-L133 | Trusted actor context enforcement, fail-closed validation, tenant/actor mismatch rejection, atomic audit attribution. |
| [`backend/migrations/versions/010_tenant_quarantine_and_audit_hardening.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/migrations/versions/010_tenant_quarantine_and_audit_hardening.py) | L39-L83 | Quarantines records with missing, null, empty, or whitespace-only parent merchant IDs. |
| [`backend/migrations/versions/011_revalidate_parent_tenant_ownership.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/migrations/versions/011_revalidate_parent_tenant_ownership.py) | L1-L110 | Forward migration revalidating parent ownership for applied environments without rewriting history. |
| [`backend/tests/test_audit_transaction.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/tests/test_audit_transaction.py) | L4, L31, L69, L98, L139 | Updated test callsites to supply `trusted_actor`. |
| [`backend/tests/test_audit_attribution_security.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/tests/test_audit_attribution_security.py) | L12-L13, L146-L157, L188-L198, L223-L506 | Tests for explicit reserved tenant queries, unauthorized privileged flags, trusted demo-state attribution, and tenant mismatch. |
| [`backend/tests/test_migration_009_multi_tenant_backfill.py`](file:///c:/Users/HP/OneDrive/Desktop/paypal/backend/tests/test_migration_009_multi_tenant_backfill.py) | L200-L373 | Tests for blank/whitespace parent ownership quarantine, backfill failure behavior, and downgrade/re-upgrade. |
| [`docs/DECISIONS.md`](file:///c:/Users/HP/OneDrive/Desktop/paypal/docs/DECISIONS.md) | L124-L141 | ADR-013 documenting reserved audit tenant access controls, trusted demo-state attribution, and forward migration 011. |

---

## 4. Tests Actually Executed and Exact Results

1. **Full Backend Test Suite:**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest backend/tests
   ```
   **Result:** `191 passed in 12.91s`

2. **Dedicated Audit Attribution & Access Control Tests:**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest backend/tests/test_audit_attribution_security.py
   ```
   **Result:** `9 passed in 0.22s`
   - `test_audit_repository_omitted_merchant_raises_error`
   - `test_audit_isolation_cross_tenant_query_blocked`
   - `test_webhook_audit_uses_platform_scope_or_order_merchant`
   - `test_demo_state_trusted_actor_attribution`
   - `test_demo_state_rejects_tenant_and_actor_mismatch`
   - `test_reserved_system_tenants_cannot_be_accessed_by_ordinary_merchants`
   - `test_audit_repository_blocks_explicit_reserved_tenant_queries`
   - `test_audit_repository_unauthorized_privileged_flags_raise_error`
   - `test_audit_service_rejects_conflicting_merchant_ids`

3. **Dedicated Migration Quarantine & Failure Tests:**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest backend/tests/test_migration_009_multi_tenant_backfill.py
   ```
   **Result:** `3 passed in 2.30s`
   - `test_migration_009_multi_tenant_backfill_and_orphan_quarantine`
   - `test_migration_quarantine_blank_and_whitespace_parent_tenant`
   - `test_migration_backfill_failure_raises_immediately`

4. **Static Analysis & Architecture Checks:**
   - `ruff check backend`: Clean (0 errors)
   - `mypy backend`: Clean (0 issues across 127 source files)
   - `.\.venv\Scripts\lint-imports.exe`: Clean (6 contracts kept, 0 broken)

5. **Frontend Test Suite & Architecture:**
   - `npm.cmd --prefix frontend test -- --run`: Clean (7 test files passed, 30 tests passed)
   - `npm.cmd --prefix frontend run lint:arch`: Clean (15 modules, 35 dependencies, 0 violations)
   - `npm.cmd --prefix frontend run build`: Clean (`tsc && vite build` succeeded)

6. **Repository Verification Script:**
   - `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`: Clean (191 backend tests + 30 frontend tests passed)

---

## 5. Security & Safety Confirmations

- **PayPal Live:** Not enabled. All integration defaults to PayPal Sandbox / `MockPayPalClient`.
- **Production Deployment:** Not performed.
- **Git State:** No commits or pushes were created or executed.
- **Migration History:** Migration `009` was not modified. Migration `010` ownership logic was hardened, and a non-destructive forward migration `011` was applied to preserve migration immutability.

---

## 6. Remaining Limitations

1. **Quarantined Records Maintenance:** Historical records quarantined under `QUARANTINED_ORPHAN` cannot be queried through standard tenant APIs and require privileged administrative DB access to re-link or archive.
2. **Internal Demo-State Service:** `DemoStateService` remains an internal, unexposed utility for testing atomic state and audit transitions; it has no external HTTP endpoint.

---

## 7. Verdict

**REMEDIATION COMPLETE — READY FOR FINAL INDEPENDENT RE-AUDIT**
