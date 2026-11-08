# PRIP Architecture Decision Log

Record material decisions here. Each entry should include date, status, context, decision, alternatives, consequences, and evidence. Do not rewrite history silently; supersede old entries.

## ADR-001 — Modular monolith

- **Status:** Accepted as MVP target.
- **Context:** Hackathon delivery needs a complete workflow without distributed-system overhead.
- **Decision:** Use React + TypeScript UI, FastAPI backend, relational database, and clear internal domain modules.
- **Alternatives:** Microservices; serverless decomposition.
- **Consequences:** Simpler local development/testing/deployment; enforce module boundaries in code.

## ADR-002 — Seeded merchant-authorized catalog as MVP source of truth

- **Status:** Accepted.
- **Context:** A comparison is not meaningful without an authoritative source.
- **Decision:** The configured seeded catalog is authoritative for the fields checked in the controlled demo.
- **Consequences:** Do not imply production integrations or field-level authority beyond this MVP.

## ADR-003 — Deterministic inspection states

- **Status:** Accepted.
- **Decision:** Use `ISSUE_DETECTED`, `VERIFIED_NO_ISSUE`, `BLOCKED_UNKNOWN`, and `NOT_TESTED`.
- **Consequences:** Unknown/untested must never be presented as issue or clean. AI does not determine the state.

## ADR-004 — AI is explanatory, not authoritative

- **Status:** Accepted.
- **Decision:** AI returns schema-validated evidence-grounded explanation and constrained proposal only. Deterministic policy and merchant approval control actions.
- **Consequences:** No model tool access to catalog mutation, approval, payment, or capture.

## ADR-005 — Explicit correction application and reinspection

- **Status:** Accepted.
- **Context:** Approval alone does not prove a correction was applied or effective.
- **Decision:** Implement validate → apply → reinspect → audit; failure/unknown never resolves issue.

## ADR-006 — PayPal Sandbox and honest payment semantics

- **Status:** Accepted.
- **Decision:** Demonstrate Orders v2 Sandbox flow, server-side verification/capture, webhook verification, deduplication, and reconciliation. Sandbox capture is not real revenue.
- **Consequences:** No blind capture retry; ambiguous outcome becomes `UNKNOWN` until reconciled.

## ADR-007 — External Storefront Extraction Isolated Outside Database Transactions

- **Date:** 2026-11-07
- **Status:** Accepted.
- **Context:** Storefront extraction involves network latency, I/O timeouts, or potential network faults. Holding open database transactions or connection pool slots during external extraction causes connection exhaustion and contention.
- **Decision:** Perform storefront extraction and pure policy comparability checks strictly outside of any database transaction. Open `atomic_transaction` only after extraction concludes to atomically persist the `StorefrontScan`, `EvidenceItem` records, and `INSPECTION_COMPLETED` audit event.
- **Alternatives considered:** Extract within a long-lived database transaction (rejected: hazard for lock contention and timeouts); async background queues (deferred: modular monolith simplicity suffices for MVP).
- **Consequences and risks:** Minimal lock footprint; atomic consistency for persisted scan and evidence.
- **Evidence/tests:** Verified in `backend/tests/test_inspection_and_evidence.py` and `backend/services/inspection.py`.

## ADR-008 — Provider Abstraction and Deterministic Policy Validation for Advisory AI Diagnostics

- **Date:** 2026-11-07
- **Status:** Accepted.
- **Context:** Integrating AI diagnostics creates risks of prompt injection from untrusted storefront snippets, hallucinated evidence citations, and unauthorized state mutation suggestions. CI pipelines also cannot depend on external, flaky, or paid AI APIs.
- **Decision:** Decouple AI via `AIProviderInterface` with an offline deterministic `MockAIProvider` for test reproducibility and CI. Delimit untrusted storefront text in `<untrusted_storefront_content>` tags. Route all provider output through deterministic policy `validate_diagnosis_payload` to enforce evidence grounding against actual evidence IDs and reject prohibited action terms (`override inspection state`, `execute payment`, `modify catalog price`). Persist diagnoses as advisory-only records with zero execution authority.
- **Alternatives considered:** Direct OpenAI/Gemini SDK calls in service layer (rejected: breaks architecture isolation, flaky CI, secret dependency); trusting AI output schema directly without deterministic policy filters (rejected: security and integrity risk).
- **Consequences and risks:** Hermetic tests without live credentials; deterministic policy guarantees model output cannot trigger unauthorized actions or cite hallucinated facts.
- **Evidence/tests:** Verified in `backend/tests/test_diagnosis_and_ai.py` (14 tests) and architectural contract `ai-integrations-isolation`.

## ADR-009 — Controlled Remediation, Explicit Merchant Authorization & Reinspection Protocol

- **Date:** 2026-11-07
- **Status:** Accepted.
- **Context:** Moving from diagnosis to remediation introduces risk of unauthorized storefront mutations, race conditions with changing catalog/storefront versions, unhandled network timeouts, and lack of proof that a correction actually resolved the underlying discrepancy.
- **Decision:** Implement a deterministic correction workflow adhering to "AI recommends; deterministic policies validate; humans authorize; backend services execute". Proposals pin expected product and storefront versions. Approval requires server-side authenticated merchant identity and explicit confirmation (AI is prohibited from approving). External mutations occur outside database transactions. Ambiguous network outcomes transition to `RECONCILIATION_REQUIRED` (blind retries blocked). Every successful execution automatically triggers follow-up inspection to verify the result (`VERIFIED_NO_ISSUE`).
- **Alternatives considered:** Autonomous AI correction execution (rejected: dangerous, violates PRIP invariants); immediate blind retries on network timeout (rejected: violates idempotent remediation semantics).
- **Consequences and risks:** Strict human accountability; atomic append-only audit trail across all transitions (`CORRECTION_PROPOSED` through `CORRECTION_EXECUTION_SUCCEEDED`); verified discrepancy resolution.
- **Evidence/tests:** Verified in `backend/tests/test_corrections_and_remediation.py` (29 tests) and `frontend/tests/Corrections.test.tsx` (5 tests).

## ADR-010 — PayPal Sandbox Checkout, Preflight Discrepancy Gating, Server-Side Orders v2 Capture, and Cryptographic Webhook Verification

- **Date:** 2026-11-07
- **Status:** Accepted.
- **Context:** Completing the vertical slice requires demonstrating checkout while strictly preserving commerce integrity invariants: preflight discrepancy gating, server-side capture, ambiguous network outcome handling, demo inventory reservation, and cryptographic webhook authenticity.
- **Decision:**
  1. Enforce a strict preflight discrepancy gate (`validate_checkout_preflight`) that independently rereads catalog ground truth, controlled storefront price, and inspection scan. Checkout is blocked if any price mismatch or active inspection issue exists (`ISSUE_DETECTED` or `BLOCKED_UNKNOWN`).
  2. Implement `PayPalClientInterface` behind integration boundaries (`paypal-integrations-isolation`), defaulting to deterministic `MockPayPalClient` for hermetic testing and `PayPalSandboxClient` using official Orders v2 REST endpoints. Enforce sandbox domain isolation (strictly reject production URLs).
  3. All external PayPal network calls occur strictly outside database transactions. Database-backed idempotency keys and demo inventory reservations are committed atomically alongside audit events.
  4. On capture network timeout or ambiguous error, order payment status transitions to `UNKNOWN` and `reconciliation_status = RECONCILIATION_REQUIRED`. Blind retries are strictly blocked until authoritative status is reconciled from PayPal.
  5. PayPal webhooks preserve raw byte payload for cryptographic signature verification via PayPal's official REST endpoint (`POST /v1/notifications/verify-webhook-signature`). Events are deduplicated on `paypal_event_id` and idempotently drive state transitions.
- **Alternatives considered:** Client-side PayPal button capture (rejected: untrusted, cannot enforce preflight discrepancy gate or fee breakdown); blind retries on capture timeout (rejected: severe financial hazard); local cert verification without provider API (rejected: complex crypto wheels, fragile local trust store).
- **Consequences and risks:** Guaranteed integrity gating before order creation; complete trace of fees, net amounts, and reconciliation status; Sandbox isolation prevents accidental live transaction attempts.
- **Evidence/tests:** Verified in `backend/tests/test_paypal_and_checkout.py` (12 tests), `frontend/tests/Checkout.test.tsx` (6 tests), Alembic migration `006_payment_and_orders.py`, and architectural contract `paypal-integrations-isolation`.

## ADR-011 — Production Hardening, Multi-Merchant Isolation, OIDC JWT Authentication, and Standalone Worker Resilience

- **Date:** 2026-11-08
- **Status:** Accepted.
- **Context:** Transitioning PRIP from demo MVP to production readiness requires resolving single-tenant data assumptions, eliminating demo authentication headers in production, securing API endpoints with rate and size guards, isolating background webhook execution in a dedicated process, and strictly preventing accidental PayPal Live deployment.
- **Decision:**
  1. Multi-merchant isolation: Add indexed `merchant_id` to all business entities (`Product`, `Order`, `StorefrontScan`, `CorrectionProposal`, `WebhookEvent`, `PaymentReconciliation`, `AuditEvent`) via migration `008_multi_merchant_and_production_hardening`. Enforce `require_merchant_access` across all read/write endpoints.
  2. Production OIDC authentication: Require genuine OIDC Bearer tokens in production (`app_env == "production"`); fail closed (HTTP 401) on missing tokens or demo header simulation attempts. Validate signature, `exp`, `iss`, `aud`, and extract `sub` and `merchant_id`.
  3. Database production readiness: Target PostgreSQL 16 with connection pooling (`pool_size=10`, `max_overflow=20`, `pool_timeout=30s`, `pool_pre_ping=True`). Startup fails closed if production uses SQLite or default session secrets.
  4. Standalone background worker: Introduce `backend/worker.py` running in a dedicated container (`infra/Dockerfile.worker`) with distributed leasing, exponential backoff, dead-lettering, heartbeat tracking, and graceful signal handling (`SIGINT`/`SIGTERM`).
  5. Security and observability: Add security headers (CSP, HSTS, X-Content-Type-Options, X-Frame-Options), 1MB body limit (HTTP 413), SSRF private IP/cloud metadata blocking on storefront extraction, and structured JSON logging with automatic secret masking.
  6. Non-negotiable Sandbox isolation: `validate_production_settings()` strictly fails closed if `PAYPAL_ENVIRONMENT != "sandbox"`.
- **Alternatives considered:** Multi-database per tenant (rejected: operational overhead too high for MVP); in-process FastAPI background tasks (rejected: worker crashes kill the web server).
- **Consequences and risks:** Production-grade security boundary; robust data isolation; strictly zero real-money exposure.
- **Evidence/tests:** Verified in `backend/tests/test_production_hardening.py` (34 tests) and full regression suite (171 tests total).

## ADR-012 — Migration 010 Tenant Quarantine, Backfill Integrity, and Strict Audit Attribution

- **Date:** 2026-11-08
- **Status:** Accepted.
- **Context:** Following the independent production release audit, migration `009` was identified as having used a blanket `server_default='merchant_default'` across historical rows in `diagnoses`, `evidence_items`, `payment_captures`, and `demo_inventory_reservations` without verifying parent lineage, leaving potential orphan data erroneously attributed. Additionally, audit logging allowed silent fallbacks to `'merchant_default'` when actor or entity merchant context was omitted.
- **Decision:**
  1. Introduce non-destructive forward migration `010_tenant_quarantine_and_audit_hardening.py` rather than rewriting historical migration `009`.
  2. Recalculate historical merchant ownership for `diagnoses` and `evidence_items` from parent `storefront_scans`.
  3. Recalculate historical merchant ownership for `payment_captures` and `demo_inventory_reservations` from parent `orders`.
  4. Detect unlinked or orphaned historical records whose parent ownership cannot be established and reassign them to the immutable reserved quarantine tenant `QUARANTINED_ORPHAN` (do not invent merchant attribution).
  5. Drop the temporary `server_default` on `merchant_id` across all four tables so new rows must provide explicit merchant context.
  6. On SQLite, drop existing immutable triggers on `evidence_items` prior to backfill and recreate them after table batch alteration.
  7. Enforce strict, fail-closed audit attribution in `AuditRepository.append` and `AuditService.log_event`: reject missing or blank `merchant_id` with `ValueError`; reject conflicts between event payloads and service context.
  8. Reserve `QUARANTINED_ORPHAN` and `platform_system` as system tenant identifiers in `security.py`, blocking ordinary merchants from authenticating as or querying them.
  9. Webhook ingress and unassociated infrastructure events record `merchant_id = "platform_system"`.
- **Alternatives considered:** Re-running or modifying migration `009` directly in-place (rejected: corrupts applied migration state in environments that already ran 009); deleting unlinked orphan records (rejected: violates audit/forensic data retention invariants).
- **Consequences and risks:** Guaranteed tenant data isolation; deterministic upgrade, downgrade, and re-upgrade paths; no silent default attribution fallbacks.
- **Evidence/tests:** Verified in `backend/tests/test_migration_009_multi_tenant_backfill.py` and `backend/tests/test_audit_attribution_security.py`.

## ADR-013 — Reserved Audit Tenant Access Control, Trusted Demo-State Attribution & Forward Migration 011

- **Date:** 2026-11-08
- **Status:** Accepted.
- **Context:** An independent source review identified that:
  1. `AuditRepository` read methods could return reserved system tenant records (`QUARANTINED_ORPHAN`, `platform_system`, `platform`) if a reserved merchant ID was explicitly queried or if boolean flags (`include_system`, `allow_quarantined`) were passed without checking caller authorization.
  2. `DemoStateService.update_state_with_audit` trusted client-supplied `request.actor_id` and `request.merchant_id` instead of enforcing trusted authenticated actor context.
  3. Migration 010 did not quarantine records whose parent scans or orders had empty, whitespace-only, or null `merchant_id`.
- **Decision:**
  1. In `AuditRepository`: consistently recognize all `RESERVED_SYSTEM_TENANTS` (`QUARANTINED_ORPHAN`, `platform_system`, `platform`). Ordinary merchant queries cannot expose reserved tenants even when explicitly requested. Treating `include_system` or `allow_quarantined` without a platform admin actor raises `PermissionError`.
  2. Establish `AuditService` query methods (`list_events_by_entity`, `list_events_by_correlation_id`, `list_events_by_merchant`) as the authorized service boundary.
  3. In `DemoStateService`: require explicit `trusted_actor: AuthenticatedActor`. Fail closed on missing/unauthenticated actor. Reject tenant or actor mismatch against client requests.
  4. In Migration 010 and new forward migration `011_revalidate_parent_tenant_ownership.py`: quarantine records where parent does not exist, foreign key is null, or parent `merchant_id` is null, empty, or whitespace-only. Prevent invalid parent ownership from propagating to child records.
- **Alternatives considered:** Omitting forward migration and assuming fresh database setups (rejected: violates Alembic migration immutability rules).
- **Consequences and risks:** Guaranteed multi-tenant isolation across audit and state mutation; non-destructive forward migration.
- **Evidence/tests:** Verified in `backend/tests/test_audit_attribution_security.py` (9 tests) and `backend/tests/test_migration_009_multi_tenant_backfill.py` (3 tests).

## Future decision template

### ADR-NNN — Title
- **Date:** YYYY-MM-DD
- **Status:** Proposed / Accepted / Superseded / Rejected
- **Context:**
- **Decision:**
- **Alternatives considered:**
- **Consequences and risks:**
- **Evidence/tests:**
