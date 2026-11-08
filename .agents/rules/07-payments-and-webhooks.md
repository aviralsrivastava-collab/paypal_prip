---
trigger: model_decision
description: Apply when implementing, reviewing, or testing checkout, PayPal, payment state, webhook, or inventory reservation code.
---
# Payment and webhook invariants

- Verify current PayPal Orders v2 API fields, headers, idempotency support, capture behavior, OAuth flow, and webhook verification procedure against official PayPal documentation before implementation. Do not rely on memory or copy stale examples.
- Keep PayPal REST calls server-side. Store the environment, local payment attempt ID, PayPal order ID, capture ID, idempotency key, and reconciliation metadata needed for safe operations.
- Verify approved order details server-side, including expected amount, currency, purchase unit/reference, and relevant status before capture.
- Persist state transitions transactionally and enforce uniqueness for provider order IDs, capture IDs, and webhook event IDs.
- Verify webhook signature before trusting event type or resource fields. Preserve the raw request body if the official verification procedure requires it.
- A duplicate event must not cause a duplicate effective transition. Out-of-order events must not regress a terminal/stronger state without a documented provider-supported reason.
- On timeout or uncertain capture response, persist `UNKNOWN`, reconcile using PayPal's authoritative API, and only then determine whether a retry is safe.
- Do not blindly repeat capture. Use PayPal-supported idempotency only as documented; do not assume it eliminates all ambiguity.
- Sandbox and Live are separate environments. MVP configuration must be Sandbox-only unless the user explicitly approves a separate production-readiness project.
- A PRIP reservation is local demo inventory only; expiry/release must be explicit and must not imply an external stock lock.
