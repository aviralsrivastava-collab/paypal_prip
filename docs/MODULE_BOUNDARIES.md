# PRIP Module Boundaries and Ownership Matrix

This document defines the strict boundaries, ownership, and prohibitions for each module in the PRIP modular monolith.

---

## 1. Backend Module Boundaries

### 1.1 `backend/api/` (API Routes & Presentation Interface)
- **Owns:** URL route definitions, HTTP method bindings, FastAPI parameter injection, dependency injection of services, HTTP status codes, error envelope formatting.
- **Must NOT:**
  - Contain business validation or calculate pricing differences.
  - Access SQLAlchemy sessions or execute SQL queries.
  - Access external APIs directly (must not call PayPal or LLM APIs).
  - Return ORM models directly.

### 1.2 `backend/core/` (Application Infrastructure Primitives)
- **Owns:** Global application configuration, environment variable parsing (`Settings`), security hashing primitives, base exception types, logging setup.
- **Must NOT:**
  - Depend on domain services, models, schemas, or routes.
  - Maintain mutable business state.

### 1.3 `backend/models/` (Database Entity Models)
- **Owns:** SQLAlchemy ORM table definitions, database constraints (foreign keys, uniqueness, check constraints, default timestamps).
- **Must NOT:**
  - Contain serialization logic for client responses.
  - Perform HTTP calls or external integrations.
  - Implement complex workflow logic.

### 1.4 `backend/schemas/` (Data Transfer Objects & Validation)
- **Owns:** Pydantic models for request bodies, query parameters, response structures, and domain enums. Decimal validation for monetary amounts.
- **Must NOT:**
  - Depend on SQLAlchemy or perform database queries.
  - Store runtime business logic or perform external side effects.

### 1.5 `backend/services/` (Domain Business Workflows)
- **Owns:** High-level orchestration of business processes:
  - Catalog inspection lifecycle.
  - Proposal generation and merchant decision enforcement.
  - Controlled correction execution and mandatory reinspection.
  - Checkout preflight and demo inventory reservations.
  - Payment capture and ambiguous state reconciliation.
  - Universal audit trail event creation.
- **Must NOT:**
  - Parse raw HTTP request headers directly (decoupled from web framework).
  - Contain raw SQL queries (must use repositories).
  - Trust client-supplied payment status.

### 1.6 `backend/repositories/` (Data Persistence Layer)
- **Owns:** Database queries, filtering, sorting, pagination, atomic transactions, row locking, session lifecycle.
- **Must NOT:**
  - Execute business rules or policy calculations.
  - Call external APIs or integrations.
  - Return unhandled database driver errors directly to the API layer.

### 1.7 `backend/integrations/` (External Provider Adapters)
- **Owns:** Low-level HTTP communication and protocol normalization with third-party providers:
  - `paypal`: OAuth token caching, Orders v2 REST client, cryptographic webhook signature verification.
  - `llm`: Prompt formatting, strict JSON schema output parsing.
  - `storefront`: Controlled demo storefront extraction adapter.
- **Must NOT:**
  - Modify database tables directly (services coordinate state changes).
  - Authorize or approve corrections (only authenticated merchants can approve).
  - Make policy determinations independently.

### 1.8 `backend/policies/` (Deterministic Business Rules)
- **Owns:** 100% deterministic, side-effect-free validation rules:
  - Comparability checks: SKU match, variant match, market match, currency match, price basis match.
  - Correction bounds: max percentage change, field allowlist check, source version currency.
  - Preflight validation: freshness checks, stock availability check.
- **Must NOT:**
  - Perform network I/O or database access.
  - Import or depend on LLM adapters or external AI providers.

---

## 2. Frontend Module Boundaries

### 2.1 `frontend/components/` (Generic UI)
- **Owns:** Dumb, presentational widgets (Button, Modal, Badge, Card, Table).
- **Must NOT:** Contain feature-specific business logic or trigger API network calls.

### 2.2 `frontend/pages/` (View Containers)
- **Owns:** Page layout structure, URL routing integration, composing features for full screen views.
- **Must NOT:** Duplicate business logic across features.

### 2.3 `frontend/features/` (Domain Feature Slices)
- **Owns:** State machines and UI flows for specific business domains (`catalog`, `inspection`, `correction`, `checkout`, `audit`).
- **Must NOT:** Directly access external APIs without going through `frontend/services`.

### 2.4 `frontend/services/` (API Client)
- **Owns:** Typed `fetch`/`axios` HTTP requests communicating with backend endpoints.
- **Must NOT:** Store private secrets or bypass backend validation.

---

## 3. Strict Module Interaction Rules

```text
[Frontend Features] ──(HTTP/JSON)──> [Backend API Routes]
                                             │
                                     (Validates Schema)
                                             │
                                             ▼
                                    [Backend Services]
                                   /         │        \
                                  /          │         \
                                 ▼           ▼          ▼
                       [Policies]    [Repositories]   [Integrations]
                       (Pure Logic)          │         (PayPal / LLM)
                                             ▼
                                        [Database]
```

1. **Routes never call Repositories directly:** All database access must flow through Services.
2. **AI never calls Services:** The LLM is invoked as a pure function adapter by Services to explain evidence; it cannot initiate workflows.
3. **Audit is Universal:** Any service mutating state (`catalog`, `storefront`, `approvals`, `payments`) must synchronously append to the audit repository in the same transaction.
