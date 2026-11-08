# PRIP Implementation Plan and Gates

Build in dependency order. Do not start with advanced analytics or external commerce integrations.

## Phase 0 — Repository assessment

Inspect actual files, stack, versions, environment, migrations, tests, run commands, and current progress. Produce `docs/REPOSITORY_ASSESSMENT.md`. No application code changes until the assessment and plan are reviewed.

## Phase 1 — Foundation (P0)

FastAPI app, React shell, relational schema, deterministic seed data, health endpoint, demo reset safety, local run/test commands.

**Gate:** Clean setup on a fresh environment; seed and reset are deterministic and restricted to demo/test.

## Phase 2 — Controlled storefront (P0)

Seeded product pages with known mismatch and known-good variants; deterministic adapter and context.

**Gate:** Demo fixture reproducible; no arbitrary crawling or challenge bypass.

## Phase 3 — Inspection and evidence (P0)

Selected-field extraction, comparability checks, evidence references, four inspection states.

**Gate:** All four states and comparability boundary tests pass.

## Phase 4 — AI diagnosis (P0)

Structured explanation grounded in normalized facts/evidence; strict schema; no tools/authority.

**Gate:** Prompt-injection, invalid schema, unsupported evidence, and model failure are safe.

## Phase 5 — Approval and correction (P0)

Merchant authentication, approve/reject, deterministic policy, apply adapter, audit, reinspection.

**Gate:** Rejection/stale/unauthorized/out-of-bounds causes no mutation; only verified reinspection resolves.

## Phase 6 — PayPal Sandbox (P0)

Checkout preflight, local reservation, OAuth, Orders v2 create, buyer approval, server verification/capture, webhook verification.

**Gate:** Real Sandbox end-to-end order/capture and verified webhook evidence; no client-trusted status.

## Phase 7 — Reliability (P1)

Duplicate/out-of-order webhooks, timeout reconciliation, stale checkout, cancellation, reservation expiry.

**Gate:** State-machine and integration tests pass; unknown outcomes remain unknown until reconciled.

## Phase 8 — Polish and demo (P1)

Dashboard, timeline, demo reset, README, screenshots if needed, rehearsed 4–5 minute demo.

**Gate:** Acceptance criteria are evidenced and limitations are stated honestly.
