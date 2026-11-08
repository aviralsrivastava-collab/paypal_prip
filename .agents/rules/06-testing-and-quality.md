---
trigger: always_on
description: Required test strategy, verification gates, and completion reporting.
---
# Testing and quality gates

- Every meaningful behavior change requires tests. Add regression tests for every fixed bug.
- Test deterministic policy independently from AI and external services.
- Test inspection comparability and all four inspection states.
- Test correction approval/rejection, stale proposal, out-of-bounds value, unauthorized actor, apply failure, and reinspection failure.
- Test checkout stale price/currency/availability and reservation expiry.
- Test payment cancellation/decline, duplicate webhooks, invalid signatures, out-of-order events, capture timeout, and reconciliation before retry.
- Use mocks/fakes for unit tests; use real PayPal Sandbox only for explicitly marked integration tests. Never confuse mocked webhook tests with cryptographic verification against a real Sandbox transaction.
- Do not make external network calls in ordinary unit tests. Keep integration tests opt-in and document required credentials.
- Run the narrowest relevant test first, then the full suite and static checks available in the repository.
- Do not suppress, skip, xfail, or weaken a test merely to obtain a green run without documenting the reason and obtaining approval for material coverage changes.
- Report exact commands and observed results. If a check could not run, state why; do not imply it passed.
