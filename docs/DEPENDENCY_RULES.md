# PRIP Dependency Rules and Prohibitions

This document defines the strict import rules, permitted dependency directions, and anti-patterns to prevent architectural decay.

---

## 1. Permitted Dependency Graph

```text
Layer 0 (Infrastructure/External):   [Contracts] [Database Engine] [PayPal REST] [LLM Provider]
                                            ▲           ▲               ▲             ▲
                                            │           │               │             │
Layer 1 (Adapters/Models):           [Core] [Models] [Schemas]     [Integrations]
                                        ▲      ▲        ▲               ▲
                                        │      │        │               │
Layer 2 (Data Access):                  │   [Repositories]              │
                                        │          ▲                    │
                                        │          │                    │
Layer 3 (Domain Policies):              │   [Policies]                  │
                                        │          ▲                    │
                                        │          │                    │
Layer 4 (Application Services):         └───[Services]──────────────────┘
                                                   ▲
                                                   │
Layer 5 (API Presentation):                 [API Routes]
                                                   ▲
                                                   │ (HTTP / JSON)
Layer 6 (Client UI):                        [Frontend Services]
                                                   ▲
                                            [Frontend Features]
                                                   ▲
                                            [Frontend Pages]
```

---

## 2. Forbidden Import Matrix

| Calling Module | Forbidden Imports | Reason |
|---|---|---|
| `backend/api/` | `backend/models/`, `backend/repositories/`, `backend/integrations/` | Routes must remain thin coordinators. Must not bypass services or leak persistence. |
| `backend/policies/` | `backend/integrations/`, `backend/services/`, `backend/repositories/`, `backend/models/` | Policies must remain pure functions without network or database dependencies. |
| `backend/models/` | `backend/schemas/`, `backend/api/`, `backend/services/` | Persistence models must have zero presentation knowledge. |
| `backend/schemas/` | `backend/models/`, `backend/repositories/`, `sqlalchemy` | DTO schemas must be decoupled from ORM entities. |
| `backend/repositories/` | `backend/api/`, `backend/services/`, `backend/integrations/` | Data access must not trigger business processes or external calls. |
| `backend/integrations/` | `backend/models/`, `backend/repositories/`, `backend/api/` | External adapters must not write directly to internal persistence. |
| `frontend/` (any) | Any `backend/` Python files | Strict client/server boundary. Types must mirror `contracts/`. |

---

## 3. Communication Protocols

### 3.1 Frontend-to-Backend
- All client-server communication must occur via documented REST endpoints defined in `docs/API_CONTRACT.md` and `contracts/`.
- Content-Type must strictly be `application/json`.
- State must be represented with exact uppercase enums:
  - Inspection: `ISSUE_DETECTED`, `VERIFIED_NO_ISSUE`, `BLOCKED_UNKNOWN`, `NOT_TESTED`.
  - Payment: `PENDING`, `APPROVED`, `CAPTURED`, `DECLINED`, `UNKNOWN`.
  - Correction: `PROPOSED`, `APPROVED`, `REJECTED`, `APPLIED`, `VERIFIED`, `FAILED`.

### 3.2 Database Access Rules
1. **Repository Only:** Only classes in `backend/repositories/` may import `Session` from SQLAlchemy or execute database queries.
2. **Atomic Units of Work:** All database writes spanning multiple tables (e.g. applying a correction and writing an audit event) must be committed inside a single atomic transaction.
3. **No Dynamic SQL:** All queries must use SQLAlchemy parameterized statements or the ORM query API to prevent SQL injection.

### 3.3 Audit Trail Invariants
- The audit log is strictly **append-only**.
- Updates (`UPDATE`) and deletions (`DELETE`) on `audit_events` are strictly prohibited at the application layer.
- Every audit record must capture:
  - `actor_id` (authenticated merchant or system)
  - `action` (e.g. `CORRECTION_APPROVED`, `STOREFRONT_CORRECTED`, `PAYMENT_CAPTURED`)
  - `entity_type` & `entity_id`
  - `before_state` & `after_state` (sanitized snapshots)
  - `timestamp` (UTC ISO 8601)

---

## 4. Circular Dependency Prevention

1. **No Mutual Imports:** Services must never import other services that depend on them. Cross-domain coordination must be handled by orchestrator services or explicit command objects.
2. **Core Isolation:** `backend/core/` must never import from any other backend folder.
3. **Contracts as Ground Truth:** If two modules need shared data shapes, define the schema in `backend/schemas/` or `contracts/`, never in one of the consumer modules.

---

## 5. Automated Architecture Enforcement

Architectural invariants are not mere conventions; they are automatically enforced in CI and local test runs:

### 5.1 Backend Boundary Enforcement (`import-linter`)
- **Configuration:** `.importlinter` at the repository root.
- **Automated Contracts:**
  1. `backend-layers`: Layered architecture (`api -> services -> repositories -> models -> core`).
  2. `core-independence`: `backend.core` is forbidden from importing `services`, `repositories`, `models`, `api`, or `integrations`.
  3. `policies-independence`: `backend.policies` is forbidden from importing `integrations`, `services`, `repositories`, `models`, or `api`.
  4. `repositories-isolation`: `backend.repositories` is forbidden from importing `services`, `api`, or `integrations`.
- **Validation Command:**
  ```powershell
  .\.venv\Scripts\lint-imports.exe
  ```
- **Automated Test Coverage:**
  `backend/tests/test_architecture_boundaries.py` contains both positive tests (verifying the current codebase satisfies all contracts) and negative tests (verifying that synthetic policy or core import violations trigger test failure).

### 5.2 Frontend Boundary Enforcement (`dependency-cruiser`)
- **Configuration:** `frontend/.dependency-cruiser.cjs`.
- **Automated Rules:**
  1. `no-backend-imports`: Frontend code is strictly prohibited from importing any backend Python/files.
  2. `no-circular`: Rejects any circular import chain within `frontend/src/`.
  3. `components-do-not-import-pages`: Presentational components cannot import routable page views.
  4. `components-do-not-import-services`: Presentational components cannot import HTTP API services directly.
- **Validation Command:**
  ```powershell
  cd frontend; npm.cmd run lint:arch
  ```

---

## 6. Guide: Adding New Modules Without Breaking Architecture

When introducing new functionality in subsequent phases (e.g. Catalog in Phase 2, Inspection in Phase 3, PayPal in Phase 6):

1. **Database Entities:** Add new SQLAlchemy models to `backend/models/<domain>.py`. Register the model in `backend/models/__init__.py`. Run an Alembic migration (`alembic revision --autogenerate -m "add_<domain>_table"`). Never expose this model to API routers.
2. **API Data Transfer Objects:** Define incoming request schemas and outgoing response schemas in `backend/schemas/<domain>.py`.
3. **Persistence Access:** Create `backend/repositories/<domain>.py` exposing queries and CRUD methods. Never place business rules or external calls here.
4. **Pure Business Rules:** If domain logic requires comparability gates, bounds checks, or threshold evaluation, implement pure functions in `backend/policies/<domain>.py`. Do NOT import external APIs, databases, or LLM adapters.
5. **Application Orchestration:** Implement `backend/services/<domain>.py`. Use `atomic_transaction(session)` to wrap entity mutations and corresponding `AuditRepository.append` calls.
6. **API Route Endpoints:** Add a thin route in `backend/api/<domain>.py` injecting `db: Session = Depends(get_db)` and delegating directly to the service. Mount the router in `backend/api/main.py`.
7. **Verify Architecture Compliance:** Run `.\.venv\Scripts\lint-imports.exe` to confirm no layered boundaries or isolation rules were violated.

