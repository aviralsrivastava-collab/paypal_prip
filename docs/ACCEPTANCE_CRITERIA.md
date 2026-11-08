# PRIP Definition of Done and Acceptance Criteria

## Product and inspection

- [ ] Judge can understand problem/product promise in under one minute.
- [ ] Seeded catalog is explicitly identified as MVP source of truth.
- [ ] StrideX Runner / SKU `SX-001` fixture has catalog USD 100.00 and controlled storefront USD 120.00.
- [ ] Comparability requires same product, variant, market/customer context, currency, and price basis; promotion context is considered where relevant.
- [ ] Verified mismatch produces `ISSUE_DETECTED` with evidence.
- [ ] Matching checked fields produce `VERIFIED_NO_ISSUE` only for inspected context.
- [ ] Timeout/challenge/parse failure/ambiguous context produces `BLOCKED_UNKNOWN`.
- [ ] No scan for current source version produces `NOT_TESTED`.

## AI and correction

- [ ] AI explanation is structured, schema-validated, and grounded in evidence IDs.
- [ ] AI has no privileged mutation or payment authority.
- [ ] Merchant identity is authenticated for decisions.
- [ ] Approve/reject binds to exact proposal/source version and is audited.
- [ ] Rejection, stale approval, unauthorized action, or out-of-bounds proposal causes no storefront mutation.
- [ ] Valid approved correction applies only to controlled demo storefront.
- [ ] Before/after values, actor, timestamp, and action ID are auditable.
- [ ] Reinspection verifies the same context and resolves only checked fields.
- [ ] Failed/blocked reinspection never marks issue resolved.

## Checkout and PayPal

- [ ] Checkout preflight rereads current product/variant/price/currency/availability.
- [ ] Stale or inconsistent product data blocks or refreshes checkout.
- [ ] PRIP-local reservation is short-lived and clearly not external stock locking.
- [ ] Backend creates PayPal Sandbox Orders v2 order.
- [ ] Buyer approval is verified server-side before capture.
- [ ] `CAPTURED` requires trusted provider confirmation or reconciliation.
- [ ] Cancellation/decline never becomes `CAPTURED`.
- [ ] Webhook signature verification is implemented using current official PayPal procedure.
- [ ] Duplicate event IDs cause one effective state transition.
- [ ] Invalid signature causes no trusted payment mutation.
- [ ] Out-of-order events do not incorrectly regress payment state.
- [ ] Capture timeout becomes `UNKNOWN` and is reconciled before retry.
- [ ] Every payment record and UI outcome clearly identifies Sandbox.
- [ ] No claim of recovered real revenue or production payment processing.

## Engineering and demo

- [ ] Setup, environment variables, architecture, tests, reset, and demo steps are documented.
- [ ] No secrets are committed or exposed in frontend bundle/logs.
- [ ] Migrations and reset procedure are safe for their intended environment.
- [ ] Relevant automated tests pass; skipped/unavailable checks are disclosed.
- [ ] Four-to-five-minute demo is rehearsed and reproducible.
- [ ] Remaining limitations are stated honestly.

A checked box requires observable evidence. Do not check a criterion because code appears to implement it; run the relevant test or manual verification and record the evidence.
