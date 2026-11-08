# PRIP Architecture Contract

## Architectural style

Use a modular monolith for the hackathon MVP. Target stack in the blueprint: React + TypeScript UI, FastAPI backend, relational database. Confirm actual versions and libraries from repository manifests before coding; do not invent version pins.

## Logical modules

1. **Catalog** — merchant-authorized seeded product data and source versions.
2. **Controlled storefront** — deterministic demo pages/data; no arbitrary-site crawling.
3. **Inspection** — extraction adapter, comparability checks, classification, scan lifecycle.
4. **Evidence** — immutable or append-only references to observed values, timestamps, source/context, parser version.
5. **Diagnosis** — LLM adapter that receives normalized facts/evidence references and returns strict structured explanation.
6. **Policy** — deterministic validation of issue state, evidence, source version, allowed fields, bounds, currency, and authorization.
7. **Correction** — merchant decision, apply through controlled-storefront adapter, before/after record, reinspection trigger/result.
8. **Checkout** — current-state preflight, local demo reservation, payment attempt state machine.
9. **PayPal adapter** — OAuth, Orders v2 create/get/capture, provider response normalization, reconciliation.
10. **Webhook** — raw request handling as required, signature verification, event deduplication, safe state transition.
11. **Audit** — actor, action, entity, timestamp, request/correlation ID, before/after references, outcome.

## Dependency direction

Presentation → API/application services → domain policy/contracts → repository/provider interfaces. Infrastructure adapters implement interfaces at the edge. Domain policy must not call the LLM or PayPal SDK. The LLM must not have direct DB/payment/catalog tools. The frontend must never own privileged secrets or payment capture.

## Core data flow

Catalog source + controlled storefront observation → comparability gate → inspection state + evidence → AI explanation/proposal → strict schema validation → merchant approval → deterministic policy revalidation → controlled correction → reinspection → checkout preflight → PayPal order/approval/capture → verified webhook/reconciliation → audit/dashboard.

## Suggested repository mapping

Adapt to the existing repository rather than forcing these exact paths:

- `backend/` — FastAPI app and domain/application/infrastructure modules.
- `frontend/` — React + TypeScript app.
- `tests/` — unit, integration, and end-to-end tests.
- `scripts/` — safe local development, reset, and verification commands.
- `docs/` — product, architecture, contracts, runbooks, decisions.

## State ownership

- Inspection state is produced by deterministic inspection/comparability logic, not by AI.
- Correction state is produced by policy/application service and audit evidence.
- Payment state is produced by server-side PayPal responses, verified webhooks, and reconciliation—not browser claims.
- Audit events record material transitions and their actors/outcomes.

## Cross-cutting concerns

Authentication/authorization; schema validation; structured errors; transaction boundaries; optimistic concurrency; idempotency; audit; observability; rate limiting; secrets management; Sandbox/Live isolation; reproducible demo reset.

## Failure boundaries

- Extraction timeout/challenge/parse failure → `BLOCKED_UNKNOWN`.
- Missing scan for current source version → `NOT_TESTED`.
- Invalid/stale correction → no mutation; audit rejection.
- Correction apply failure → unresolved failure state.
- Reinspection unknown/failure → not resolved.
- Checkout stale state → block/refresh; no stale charge.
- Capture ambiguity → `UNKNOWN`, reconcile before retry.
- Invalid webhook signature → reject/quarantine; no trusted payment mutation.
