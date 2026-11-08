---
name: paypal-integration
description: Implements and reviews PRIP PayPal Sandbox OAuth, Orders v2, capture, webhook verification, idempotency, and reconciliation.
---
# PayPal Integration Skill

## Mandatory preflight research
1. Consult current official PayPal documentation for REST OAuth, Orders v2 create/get/capture, idempotency, webhook registration/events, and signature verification.
2. Verify exact endpoint, request fields, headers, response semantics, and environment URLs. Record links/date in `docs/PAYPAL_INTEGRATION_NOTES.md`.
3. Do not assume idempotency guarantees or event ordering beyond current official docs.

## Implementation boundaries
- All PayPal REST operations and secrets stay backend-side.
- Use Sandbox by default; isolate Sandbox and Live credentials/configuration.
- Create order only after server-side checkout preflight.
- Persist local payment attempt and idempotency metadata before/around provider operations using safe transaction boundaries.
- Verify approved order server-side and compare expected amount, currency, and local purchase reference before capture.
- Do not trust browser query parameters or redirect as proof of capture.
- Verify webhook signature before trusting payload; use correct environment-specific webhook ID.
- Deduplicate event IDs and process idempotently; guard against out-of-order state regression.
- Capture timeout/ambiguous response → persist `UNKNOWN` → query/reconcile provider state → retry only when proven safe under documented semantics.
- Do not collect/store card numbers or CVV.

## Required tests
- OAuth failure/expired token handling without secret leakage.
- Create order success/failure and idempotency behavior.
- Buyer cancellation/decline.
- Amount/currency/order mismatch before capture.
- Capture success and denial.
- Capture timeout with reconciliation; no blind retry.
- Valid and invalid webhook signature.
- Duplicate, delayed, and out-of-order webhook events.
- Sandbox/Live configuration isolation.

## Evidence/reporting
Distinguish mocked tests, PayPal webhook simulator, real Sandbox buyer approval/capture, and verified webhook delivery. Never report a mock as a real transaction.
