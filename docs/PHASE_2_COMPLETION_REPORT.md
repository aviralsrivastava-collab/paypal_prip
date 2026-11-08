# PRIP Phase 2 Completion Report: Seeded Catalog & Controlled Storefront

> **Milestone:** Phase 2 — Seeded Catalog & Controlled Storefront  
> **Status:** Completed & Fully Verified  
> **Date:** 2026-11-07  
> **Scenario Established:** StrideX Runner (SKU `SX-001`), Catalog USD 100.00, Controlled Storefront USD 120.00, Price Discrepancy +USD 20.00.

---

## 1. Executive Summary

Phase 2 establishes the core pricing discrepancy scenario of PRIP.
The merchant-authorized catalog (`products`) acts as the authoritative source of truth, while the controlled demo storefront (`storefront_products`) serves customer-facing prices.
Both models use fixed-precision decimal arithmetic (`Decimal(10, 2)`), validate ISO currency and SKU uniqueness, and are persisted via SQLAlchemy with an Alembic migration that includes database-level immutability triggers on `audit_events`.
A dedicated seeding service and CLI script guarantee idempotent setup.
The React + TypeScript frontend catalog screen displays both values with dedicated badges and alerts when a discrepancy is detected.

All 21 backend unit tests, 6 frontend component tests, architecture linters (`import-linter` and `dependency-cruiser`), type checkers, production builds, and verification scripts pass cleanly.

---

## 2. Implemented & Modified Components

### 2.1 Backend Models & Schema (`backend/`)
- **`backend/models/product.py`**: Merchant-authorized catalog entity (`products`) with `sku` (unique, indexed), `title`, `price` (Numeric 10,2), `currency` (ISO 4217), `availability`, and `source_version`.
- **`backend/models/storefront.py`**: Controlled demo storefront entity (`storefront_products`) storing customer-facing price, currency, `url_path`, and `version`.
- **`backend/schemas/product.py`**: Strict Pydantic schemas (`ProductBase`, `ProductCreate`, `ProductResponse`, `ProductComparisonResponse`) enforcing currency allowlist (`USD`, `EUR`, `GBP`, `CAD`, `AUD`) and rejecting prices with precision exceeding 2 decimal places or non-positive values.
- **`backend/schemas/storefront.py`**: Schemas for `StorefrontProductResponse` and `StorefrontUpdatePriceRequest` with optimistic locking version checks.

### 2.2 Data Access & Services (`backend/`)
- **`backend/repositories/product.py`**: Data access layer for `products` (`get_by_sku`, `get_by_id`, `get_all`, `create`, `update`).
- **`backend/repositories/storefront.py`**: Data access layer for `storefront_products` (`get_by_sku`, `get_all`, `create`, `update_price` with version verification).
- **`backend/integrations/storefront/adapter.py`**: Controlled storefront integration adapter isolating storefront mutations from the catalog.
- **`backend/services/catalog.py`**: Orchestrates catalog queries, joins storefront comparisons, calculates discrepancies (`storefront.price - catalog.price`), and provides idempotent seed routines (`seed_initial_catalog`).
- **`backend/services/storefront.py`**: Manages storefront price modifications atomically within `atomic_transaction`, logging `STOREFRONT_PRICE_UPDATED` audit events.

### 2.3 API Routing (`backend/api/`)
- **`backend/api/products.py`**:
  - `GET /api/products`: Lists products with storefront comparison and discrepancy metrics.
  - `GET /api/products/{id}`: Returns isolated catalog product by ID.
  - `GET /api/products/sku/{sku}`: Returns comparison details for a specific SKU.
  - `POST /api/products/seed`: Seeds or resets the demo baseline via query parameter `?reset=true`.
- **`backend/api/storefront.py`**:
  - `GET /api/storefront/products/{sku}`: Fetches controlled storefront product facts.
  - `PUT /api/storefront/products/{sku}/price`: Updates customer-facing price with version checking and audit logging.
- **`backend/api/main.py`**: Mounted `products_router` and `storefront_router`.

### 2.4 Database Migrations & Seeding (`database/` & `backend/migrations/`)
- **`backend/migrations/versions/002_catalog_and_storefront.py`**: Migration creating `products` and `storefront_products` tables with unique indexes on `sku`. In SQLite, adds `BEFORE UPDATE` and `BEFORE DELETE` abort triggers on `audit_events` to enforce database-level immutability.
- **`database/seeds/catalog_seed.py`**: Standalone, idempotent CLI runner (`--reset` flag supported) and module entry point.

### 2.5 Frontend Implementation (`frontend/`)
- **`frontend/src/types/index.ts`**: Declared `ProductComparison` and `StorefrontProduct` interfaces matching API schemas.
- **`frontend/src/services/api.ts`**: Added `getProducts()` and `seedCatalog()` client methods.
- **`frontend/src/components/PriceBadge.tsx`**: Reusable component visually distinguishing `Merchant Source of Truth` (emerald), `Storefront Customer Facing` (amber), and `Discrepancy` (red).
- **`frontend/src/pages/Catalog.tsx`**: Responsive view showing product cards, comparison badges, discrepancy state, loading spinner, error boundary with retry, and manual seed reset button.
- **`frontend/tests/Catalog.test.tsx`**: Unit tests covering loading state, successful comparison rendering with distinct badges, and error state recovery.

---

## 3. Data Flow & Architecture

```
[ Frontend: Catalog Page ]
         |
         | HTTP GET /api/products
         v
[ API: products_router ]
         |
         v
[ Service: CatalogService ]
      /           \
     v             v
[ ProductRepo ]   [ StorefrontRepo ]
     |                     |
     v                     v
( Table: products )   ( Table: storefront_products )
  USD 100.00            USD 120.00
     \                     /
      \                   /
   Calculated Discrepancy: +USD 20.00
```

- **Separation of Concerns:** Storefront mutations modify only `storefront_products`. The `products` table is the merchant-authorized ground truth and is never altered by storefront actions.
- **Fixed-Precision Monetary Calculations:** Calculations operate on Python `Decimal` objects (e.g. `Decimal("120.00") - Decimal("100.00") = Decimal("20.00")`). No floating-point inaccuracies exist.
- **Audit Integrity:** State mutations (seeding, resets, storefront updates) generate append-only audit events synchronously within `atomic_transaction`.

---

## 4. API Endpoints & Example Responses

### `GET /api/products`
```json
[
  {
    "id": 1,
    "sku": "SX-001",
    "title": "StrideX Runner",
    "description": "High-performance lightweight running shoe with responsive cushioning and breathable mesh.",
    "merchant_price": "100.00",
    "merchant_currency": "USD",
    "storefront_price": "120.00",
    "storefront_currency": "USD",
    "price_discrepancy": "+20.00",
    "has_discrepancy": true,
    "availability": "IN_STOCK",
    "source_version": 1,
    "storefront_version": 1,
    "updated_at": "2026-11-07T10:35:00.000000Z"
  }
]
```

### `GET /api/storefront/products/SX-001`
```json
{
  "id": 1,
  "sku": "SX-001",
  "title": "StrideX Runner",
  "price": "120.00",
  "currency": "USD",
  "availability": "IN_STOCK",
  "url_path": "/products/stridex-runner",
  "version": 1,
  "created_at": "2026-11-07T10:35:00.000000Z",
  "updated_at": "2026-11-07T10:35:00.000000Z"
}
```

### `PUT /api/storefront/products/SX-001/price`
Request Body:
```json
{
  "price": "100.00",
  "currency": "USD",
  "actor_id": "merchant-operator-1",
  "expected_version": 1,
  "reason": "Merchant approved alignment"
}
```
Response Body:
```json
{
  "id": 1,
  "sku": "SX-001",
  "title": "StrideX Runner",
  "price": "100.00",
  "currency": "USD",
  "availability": "IN_STOCK",
  "url_path": "/products/stridex-runner",
  "version": 2,
  "created_at": "2026-11-07T10:35:00.000000Z",
  "updated_at": "2026-11-07T10:36:00.000000Z"
}
```

---

## 5. Verification Commands and Actual Results

| Test Category | Command | Target | Actual Result | Status |
|---|---|---|---|---|
| **Backend Unit & API Tests** | `pytest backend/tests -v` | Catalog, Storefront, Audit, Health, Architecture, Security | 30 passed in 2.54s | **PASSED** |
| **Backend Linting** | `ruff check backend` | Code standards & style | All checks passed (0 errors) | **PASSED** |
| **Backend Type Checking** | `mypy backend` | Strict static typing | Success: no issues found in 47 source files | **PASSED** |
| **Backend Architecture** | `lint-imports` | Layered contracts & component isolation | Contracts: 4 kept, 0 broken | **PASSED** |
| **Database Migrations** | `alembic upgrade head` / `downgrade base` | Reversible schema changes & triggers | Successfully upgraded and downgraded | **PASSED** |
| **Database Seeding** | `python database/seeds/catalog_seed.py` | Idempotent seed & reset | Verified seed (`+20.00` discrepancy) and safe no-op | **PASSED** |
| **Frontend Unit Tests** | `npm test` (Vitest) | Catalog, Header, App Shell, Currency Mismatch | 3 test files, 7 tests passed in 3.61s | **PASSED** |
| **Frontend Type Checking** | `npm run lint` (`tsc --noEmit`) | Strict TypeScript checks | 0 errors | **PASSED** |
| **Frontend Architecture** | `npm run lint:arch` (depcruise) | Frontend module isolation | 0 dependency violations (13 modules cruised) | **PASSED** |
| **Frontend Production Build** | `npm run build` (Vite) | Production distribution bundle | Built `dist/` bundle in 813ms | **PASSED** |
| **Repository Test Launcher** | `verify.ps1` | Discovered test suites | 2/2 suites completed (Pytest + Vitest) | **PASSED** |
| **Harness & Secret Check** | `harness-check.ps1` | Structural integrity & secret detection | Passed (0 secrets tracked) | **PASSED** |

---

## 6. Targeted Four-Point Security & Integrity Verification

This section documents the results of the Phase 2 security and integrity audit:

### 6.1 Check 1: Seed / Reset Endpoint Protection (`POST /api/products/seed`)
- **What Was Inspected:** Route handler `seed_catalog` and service `CatalogService.seed_initial_catalog`.
- **Vulnerability Identified:** The initial implementation permitted any caller to trigger `?reset=true` regardless of environment or role.
- **Remediation Implemented:**
  - Introduced `backend/core/security.py` with `require_demo_operator` dependency.
  - In production (`settings.app_env == "production"`), seeding and reset are strictly blocked with `HTTP 403 Forbidden`.
  - In development/demo, resets require `role in {"demo_operator", "merchant_admin"}`; unauthorized ordinary users are rejected with `HTTP 403 Forbidden`.
  - Authorized demo operators can safely reset the catalog in the demo environment.
- **Tests Added:** `test_seed_reset_forbidden_in_production`, `test_seed_reset_unauthorized_user_forbidden`, `test_seed_reset_allowed_for_demo_operator_in_demo_env` in `backend/tests/test_phase2_security_and_integrity.py`.

### 6.2 Check 2: Trusted Audit Actor Identity (`PUT /api/storefront/products/{sku}/price`)
- **What Was Inspected:** `StorefrontUpdatePriceRequest` and `StorefrontService.update_price`.
- **Vulnerability Identified:** The initial schema allowed a client to send an untrusted `actor_id` in the request body, allowing client impersonation in the audit trail.
- **Remediation Implemented:**
  - Server-side dependency `get_current_actor` in `backend/core/security.py` establishes the authenticated principal (`AuthenticatedActor`).
  - `StorefrontService.update_price` derives `actor_id` strictly from the server-side `trusted_actor.actor_id` context. Client-supplied body IDs are never trusted as the actor identity.
  - If a client attempts to submit a conflicting `actor_id`, the attempt is logged in the audit `details` as an untrusted override attempt.
  - In production environments, header-based simulation is disabled, returning `HTTP 401 Unauthorized`.
- **Tests Added:** `test_forged_actor_id_in_request_body_is_rejected_from_audit_trail`, `test_production_environment_rejects_unauthenticated_header_mutation` in `backend/tests/test_phase2_security_and_integrity.py`.

### 6.3 Check 3: Currency Comparability
- **What Was Inspected:** `CatalogService.list_products` and `get_product_by_sku`.
- **Vulnerability Identified:** The initial implementation subtracted storefront price from merchant price without verifying ISO currency equality, generating false numerical discrepancies across currencies.
- **Remediation Implemented:**
  - Updated `backend/schemas/product.py` to include `is_comparable: bool` and `comparability_reason: Optional[str]`.
  - If `product.currency != storefront.currency`, `is_comparable` is set to `False`, `comparability_reason` reports the exact mismatch, and `price_discrepancy` is set to `None`.
  - Updated `frontend/src/pages/Catalog.tsx` and `frontend/src/components/PriceBadge.tsx`: when currencies mismatch, the UI renders `NON-COMPARABLE (CURRENCY MISMATCH)` and suppresses numerical discrepancy calculations.
- **Cases Tested:**
  - Case 1 (USD 100 vs USD 120): `is_comparable=True`, `discrepancy=+20.00`.
  - Case 2 (USD 100 vs EUR 120): `is_comparable=False`, `discrepancy=None`, reason logged.
  - Case 3 (GBP 100 vs GBP 100): `is_comparable=True`, `discrepancy=+0.00`.
- **Tests Added:** `test_case_1_matching_currency_discrepancy_calculated`, `test_case_2_differing_currencies_explicitly_non_comparable`, `test_case_3_matching_gbp_clean_no_discrepancy` in `backend/tests/test_phase2_security_and_integrity.py`, and component test in `frontend/tests/Catalog.test.tsx`.

### 6.4 Check 4: SQLite Audit Immutability Triggers
- **What Was Inspected:** Alembic migration `002_catalog_and_storefront.py` and `backend/migrations/env.py`.
- **Remediation Implemented:**
  - Corrected `env.py` to respect dynamic database URLs passed during programmatic test execution.
  - Verified on a disposable test database (`tmp_path / "disposable_audit_trigger_test.db"`):
    1. Migration `002` installs triggers `prevent_audit_events_update` and `prevent_audit_events_delete`.
    2. SQL `INSERT` into `audit_events` succeeds.
    3. Direct SQL `UPDATE` fails with abort error: `'audit_events is append-only: updates are prohibited'`.
    4. Direct SQL `DELETE` fails with abort error: `'audit_events is append-only: deletions are prohibited'`.
    5. Migration downgrade to `001_initial` cleanly drops the triggers.
- **Tests Added:** `test_triggers_prevent_sql_update_and_delete_on_disposable_database` in `backend/tests/test_phase2_security_and_integrity.py`.

---

## 7. Confirmation of Phase 1 Invariants

- **All Phase 1 Checks Pass:** Health endpoint checks, atomic transaction rollbacks, optimistic concurrency locking on `demo_states`, and append-only repository operations remain completely intact and passing.
- **Layering & Isolation Preserved:** `backend.core` remains independent, `backend.repositories` does not import services or integrations, and frontend components do not import backend code or pages.
- **Database-Level Audit Security:** Alembic migration `002` closed the limitation identified in Phase 1 by adding SQLite abort triggers preventing raw SQL updates or deletes on `audit_events`.

---

## 8. Known Limitations & Production Readiness Notice

1. **Authentication Scope:** The current implementation provides server-side actor identity resolution with role-based checks for local/demo environments (`AuthenticatedActor`). Full enterprise OAuth 2.0 / JWT session authentication is intentionally deferred and not implemented in this hackathon MVP. Mutation endpoints are explicitly restricted from production use.
2. **Remote GitHub CI:** Code has not been pushed to a remote GitHub repository (local branch `master` remains uncommitted pending user approval).

---

## 9. Final Phase 2 Acceptance Verdict

**Verdict:** **APPROVED FOR PHASE 3 WITH DOCUMENTED LIMITATIONS**

*Justification:* All four targeted security and integrity checks have been implemented, tested, and verified with automated test suites. The catalog ground truth and controlled demo storefront are decoupled, fixed-precision arithmetic and currency comparability are strictly enforced, audit records are protected at both the application and database levels, and the catalog screen provides honest visual feedback for both discrepancy and non-comparable states.

---

## 10. Next Milestone: Phase 3 — Inspection, Comparability, Evidence & Four-State Model

When approved, Phase 3 will implement:
- Controlled storefront extraction adapter (simulated scraper).
- Explicit 4-state inspection engine (`ISSUE_DETECTED`, `VERIFIED_NO_ISSUE`, `BLOCKED_UNKNOWN`, `NOT_TESTED`).
- Structured immutable evidence items (`evidence_items` table).
- Inspection scan lifecycle API (`POST /api/scans`, `GET /api/scans/{id}`).
