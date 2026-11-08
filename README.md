# PRIP — PayPal Revenue Intelligence Platform

> **Tagline:** Detect the discrepancy. Approve the correction. Verify the checkout.

PRIP is a merchant-facing commerce-integrity platform MVP designed to detect evidence-backed discrepancies between a merchant-authorized catalog and a customer-facing storefront, explain findings with constrained AI, require authenticated merchant approval, apply policy-validated corrections to a controlled storefront, reinspect the result, and verify checkout via the PayPal Sandbox API.

---

## 1. Non-Negotiable Product Invariants

1. **Authorized Catalog Authority:** The seeded merchant catalog is the source of truth for configured fields.
2. **Honest 4-State Inspection Engine:**
   - `ISSUE_DETECTED`: Completed inspection verified an evidence-backed discrepancy.
   - `VERIFIED_NO_ISSUE`: Completed inspection confirmed selected fields matched in context.
   - `BLOCKED_UNKNOWN`: Inspection could not reliably complete (timeout, challenge, ambiguous variant).
   - `NOT_TESTED`: No inspection exists for current product/source version.
   *Neither unknown nor untested may ever be presented or treated as clean.*
3. **Constrained AI Role:** AI explains verified findings and drafts allowlisted proposals. AI has **zero authority** to approve, mutate data, or execute payments.
4. **Mandatory Merchant Sign-off:** Corrections strictly require authenticated merchant approval for the exact proposal version.
5. **Reinspection Requirement:** Issues are resolved **only** after post-correction reinspection verifies the corrected fields.
6. **Checkout Preflight & Reservation:** Preflight re-reads current price, currency, and availability before payment; local reservations do not claim external stock locking.
7. **PayPal Sandbox Invariants:** Real capture requires server-side provider confirmation or reconciliation. Browser redirects or client statuses are never trusted as capture.

---

## 2. Repository Structure

PRIP is built as an explicit modular monolith organized into 10 top-level directories:

```text
prip/
├── .github/         # CI/CD workflows, issue templates, PR template
├── .agents/         # Antigravity rules and execution skills
├── backend/         # FastAPI backend modular architecture
│   ├── api/         # HTTP routes and request/response coordination
│   ├── core/        # Settings, configuration, logging, exceptions
│   ├── models/      # SQLAlchemy database entity models
│   ├── schemas/     # Pydantic validation schemas & DTOs
│   ├── services/    # Business logic & workflow orchestration
│   ├── repositories/# Database persistence & transaction management
│   ├── integrations/# External adapters (PayPal REST, LLM, Storefront)
│   ├── policies/    # Deterministic validation rules (comparability, bounds)
│   ├── migrations/  # Alembic schema migrations
│   └── tests/       # Backend unit, policy, and service test suites
├── frontend/        # React + TypeScript single-page application
│   ├── components/  # Reusable UI widgets
│   ├── pages/       # Screen views (Dashboard, Catalog, Inspection, Checkout)
│   ├── features/    # Domain feature slices (catalog, inspection, correction, checkout)
│   ├── services/    # Typed API client
│   ├── hooks/       # Custom React hooks
│   ├── types/       # TypeScript contract interfaces
│   ├── utils/       # Formatting and helper utilities
│   └── tests/       # Frontend component & feature tests
├── contracts/       # Canonical OpenAPI & JSON schemas
├── database/        # Seed data fixtures, SQLite target, reset utilities
├── docs/            # Architecture specifications, runbooks, decision logs
├── scripts/         # Local verification and secret scanning scripts
├── tests/           # Cross-module end-to-end integration tests
└── infra/           # Local development container and proxy configurations
```

---

## 3. Architecture & Standards Documentation

- [Repository Architecture](file:///docs/REPOSITORY_ARCHITECTURE.md): Modular monolith layers, component interactions, and execution flow.
- [Module Boundaries](file:///docs/MODULE_BOUNDARIES.md): Ownership definitions and strict restrictions for each module.
- [Dependency Rules](file:///docs/DEPENDENCY_RULES.md): Allowed import directions, communication protocols, and circular dependency prevention.
- [GitHub Workflow](file:///docs/GITHUB_WORKFLOW.md): Branching strategy, PR checklist, and CI automation.
- [Product Specification](file:///docs/PRODUCT_SPEC.md): MVP problem statement, seeded demo scenario (StrideX Runner `SX-001`), and claims policy.
- [Security Model](file:///docs/SECURITY.md): Threat matrix, prompt injection defenses, SSRF mitigations, and PayPal verification rules.

---

## 4. Verification and Foundation Checks

Run the automated harness structure and secret detection validation:

```powershell
powershell.exe -ExecutionPolicy Bypass -File "scripts/harness-check.ps1"
```

To run discovered test suites:
```powershell
powershell.exe -ExecutionPolicy Bypass -File "scripts/verify.ps1"
```
