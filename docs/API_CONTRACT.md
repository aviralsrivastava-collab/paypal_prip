# PRIP API Contract

The following is the target API surface from the solution blueprint. It is a contract to implement and verify, not a claim that endpoints currently exist. Confirm actual route prefix, authentication mechanism, response envelopes, and versioning from the repository before coding.

## Target endpoints

| Method | Path | Purpose | Critical controls |
|---|---|---|---|
| GET | `/api/products` | List seeded/catalog products | Auth as appropriate; pagination if needed |
| GET | `/api/products/{id}` | Product detail | Do not expose internal secrets |
| POST | `/api/scans` | Start controlled inspection | Validate product/source version; rate limit |
| GET | `/api/scans/{id}` | Scan status/result | Distinguish all four inspection states |
| GET | `/api/issues` | List findings | Filter by state; never mislabel unknown as issue |
| GET | `/api/issues/{id}` | Issue, diagnosis, evidence | Evidence IDs and context checks visible |
| POST | `/api/issues/{id}/approve` | Approve exact proposal version | Authenticated merchant; optimistic concurrency; audit |
| POST | `/api/issues/{id}/reject` | Reject exact proposal version | Authenticated merchant; no mutation; audit |
| POST | `/api/corrections/{id}/apply` | Apply approved correction | Revalidate actor, approval, versions, bounds, allowlist |
| POST | `/api/corrections/{id}/verify` | Trigger/retrieve reinspection | Resolve only verified checked fields |
| POST | `/api/checkout/preflight` | Validate current state/create or refresh local reservation | Reread current price/currency/availability; stale state blocks |
| POST | `/api/payments/paypal/order` | Create PayPal order | Backend only; validated preflight; idempotency |
| POST | `/api/payments/paypal/{order_id}/capture` | Verify approval and capture safely | Server-side verification; ambiguity → UNKNOWN/reconcile |
| POST | `/api/webhooks/paypal` | Receive PayPal webhook | Verify signature before trusted processing; dedupe |
| GET | `/api/payments/{id}` | Payment status and provider references | Server-derived state; Sandbox label |
| GET | `/api/audit?entity_id={id}` | Audit timeline | Authorization and safe redaction |

## API design requirements

- Use strict typed request/response schemas and stable error formats.
- Mutating endpoints require authentication, authorization, validation, and audit events.
- Approval and correction use issue/proposal/source version or equivalent optimistic concurrency tokens.
- Never accept client-supplied payment status as authoritative.
- Money fields must be decimal-safe and include currency.
- Distinguish validation errors, unauthenticated/unauthorized requests, stale-state conflicts, policy rejection, dependency failure, and ambiguous payment outcome.
- Do not return stack traces, tokens, secrets, raw credentials, or unnecessary sensitive data.
- Define idempotency semantics for retryable mutations; persist keys and outcomes where appropriate.
- Keep webhook endpoint response behavior aligned with current PayPal delivery/verification requirements.

## Required response semantics

Inspection result includes state, checked fields, comparability checks, evidence references, inspected context/time, and reason when blocked. Correction result distinguishes proposal, approval, application, and verification. Payment response distinguishes local attempt, PayPal order, buyer approval, capture pending, captured, declined/cancelled, unknown, and refunded/reversed.
