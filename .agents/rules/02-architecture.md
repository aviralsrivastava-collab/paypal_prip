---
trigger: always_on
description: PRIP modular-monolith boundaries, data flow, and dependency rules.
---
# Architecture constraints

- Use a modular monolith with the existing React + TypeScript frontend, FastAPI backend, and relational database target unless repository evidence or an approved decision changes this.
- Preserve domain boundaries: catalog, inspection, evidence, diagnosis, policy, correction, checkout, PayPal adapter, webhooks, and audit.
- Dependency direction should point toward domain/application contracts; provider SDKs, database drivers, HTTP clients, and LLM clients belong at infrastructure edges.
- The inspection/policy/correction/payment domain must not depend on frontend components.
- The LLM adapter must not be imported by policy, correction-application, or payment-capture code as an authority source.
- PayPal-specific request/response details stay behind the PayPal integration boundary.
- Avoid circular imports, hidden cross-module database writes, global mutable state, and duplicate sources of truth.
- Use explicit service interfaces and typed request/response models at module boundaries.
- Do not introduce microservices, message brokers, caches, or new infrastructure without a demonstrated requirement and user approval.
- Update `docs/ARCHITECTURE.md` and `docs/DECISIONS.md` when boundaries materially change.
