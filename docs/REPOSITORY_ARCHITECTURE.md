# PRIP Repository Architecture

## 1. Architectural Philosophy: The Modular Monolith

The PayPal Revenue Intelligence Platform (PRIP) is built as an explicit **modular monolith**. 
Distributed architectures (microservices, service meshes, asynchronous event buses) introduce unnecessary operational friction, latency, and failure modes for a high-integrity commerce MVP. Instead, PRIP enforces domain boundaries, strict layering, and separation of concerns within a single, cohesive repository.

### Core Architectural Goals
1. **Minimizing Unintended Side Effects:** Modules interact through typed interfaces, preventing hidden coupling and ripple effects.
2. **Honest State Semantics:** Inspection, policy, and payment states are explicit, mutually exclusive, and never collapsed or guessed.
3. **Privileged Backend Boundary:** Frontend presentation components never own secrets, direct database connections, or payment capture authority.
4. **Deterministic Policy Primacy:** AI explains evidence and drafts allowlisted proposals; deterministic code enforces policies and executes mutations only upon explicit merchant authorization.

---

## 2. Top-Level Directory Taxonomy

| Directory | Responsibility | Direct Dependencies Permitted |
|---|---|---|
| `.github/` | CI/CD pipelines, issue templates, PR review guidelines. | None |
| `.agents/` | Antigravity AI rules and workflow execution skills. | Reads `docs/`, `scripts/` |
| `backend/` | FastAPI application, domain services, database persistence, and external adapters. | `contracts/`, `database/` |
| `frontend/` | React + TypeScript web application and client features. | `contracts/` (via generated or shared types) |
| `contracts/` | Canonical OpenAPI schemas, JSON schemas, and typed domain interface definitions. | None (Universal Source of Truth) |
| `database/` | Raw SQL schemas, SQLite database target, deterministic seed data, and reset utilities. | None |
| `docs/` | Architecture specs, runbooks, decision logs, and security models. | None |
| `scripts/` | Local developer verification, secret scanning, and environment setup scripts. | None |
| `tests/` | Repository-wide end-to-end integration and smoke verification suites. | `backend/`, `frontend/` |
| `infra/` | Docker configurations, local reverse proxy rules, and environment manifests. | None |

---

## 3. Backend Architecture (`backend/`)

The backend is structured into clear horizontal layers and bounded contexts:

```text
backend/
├── api/             # HTTP Routing, Request Validation, Response Serialization
├── core/            # Configuration, Security Primitives, Error Envelopes, Logging
├── models/          # SQLAlchemy Database Entity Models & Constraints
├── schemas/         # Pydantic DTOs, Enums, Decimal Money Formatting
├── services/        # Application Business Logic & Orchestration Workflows
├── repositories/    # Database Access Layer, Queries, and Transaction Boundaries
├── integrations/    # External Clients (PayPal REST SDK, LLM Client, Storefront Scraper)
├── policies/        # Pure Deterministic Validation Rules (Comparability, Bounds)
├── migrations/      # Alembic Database Migrations
└── tests/           # Backend Unit, Policy, and Service Test Suites
```

### Layered Flow of Execution:
1. **Client Request** arrives at `backend/api/`.
2. `backend/api/` validates request parameters against `backend/schemas/`.
3. `backend/api/` verifies merchant authentication and forwards the request to `backend/services/`.
4. `backend/services/` invokes `backend/policies/` for deterministic validation (e.g., verifying proposal freshness, field allowlist).
5. If external interaction is needed, `backend/services/` calls `backend/integrations/` (e.g. PayPal Orders v2).
6. State mutations are committed through `backend/repositories/` within an atomic database transaction.
7. An immutable audit record is committed to `models/audit_events`.
8. The service returns domain data to `backend/api/`, which maps it to an approved response schema.

---

## 4. Frontend Architecture (`frontend/`)

The frontend is a React + TypeScript single-page application built around domain feature modules:

```text
frontend/
├── components/      # Generic, Reusable UI Widgets (Buttons, Tables, Modals, Badges)
├── pages/           # Top-Level Routable Views (Dashboard, Catalog, Inspection, Checkout)
├── features/        # Domain Feature Slices (catalog, inspection, correction, checkout, audit)
├── services/        # Typed HTTP API Client wrappers communicating with Backend
├── hooks/           # Custom React Hooks for UI state and lifecycle
├── types/           # TypeScript Interfaces & Enums mirroring backend schemas
├── utils/           # Pure formatting and helper functions
└── tests/           # Frontend Component & Feature Unit/Integration Tests
```

---

## 5. Cross-Cutting Architectural Invariants

### 1. Database Model Isolation
Database models (`backend/models/`) are internal persistence details. They must **never** be returned directly as API responses. All API payloads must serialize through explicit Pydantic response models (`backend/schemas/`) to prevent leaking internal fields, database IDs, or sensitive relational mappings.

### 2. PayPal Integration Isolation
All PayPal REST communication, credentials (`PAYPAL_CLIENT_SECRET`), access token management, and webhook verification live strictly inside `backend/integrations/paypal/`.
- The checkout business logic (`backend/services/checkout.py`) interacts with PayPal only through high-level interfaces (`create_order`, `verify_and_capture_order`).
- The frontend receives only safe public identifiers (`order_id`) necessary to render the PayPal buttons.

### 3. AI Explanation Boundary
The LLM integration (`backend/integrations/llm/`) is strictly **explanatory**:
- The model receives normalized facts and evidence identifiers.
- The model returns strict JSON conforming to `backend/schemas/diagnosis.py`.
- The model has **zero tools** and **zero permissions** to mutate the catalog, apply corrections, approve actions, or trigger payments.

### 4. Deterministic State Machines
Inspection states are mathematically partitionable:
- `ISSUE_DETECTED`
- `VERIFIED_NO_ISSUE`
- `BLOCKED_UNKNOWN`
- `NOT_TESTED`

Neither `BLOCKED_UNKNOWN` nor `NOT_TESTED` may ever be displayed or processed as clean or as an issue.
