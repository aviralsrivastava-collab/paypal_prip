---
name: correction-workflow
description: Implements PRIP merchant approval, deterministic policy validation, controlled correction, audit, and reinspection.
---
# Correction Workflow Skill

## Procedure
1. Read issue, evidence, source version, proposal version, allowed field/value constraints.
2. Ensure merchant identity is authenticated and authorized.
3. Bind approval/rejection to exact proposal and source version; use optimistic concurrency.
4. On rejection, record actor/time/reason and ensure no storefront mutation.
5. Before apply, revalidate issue state, evidence freshness, source version, approval, field allowlist, value format, currency, configured bounds, and actor authorization.
6. Apply only through controlled storefront adapter; never let LLM or frontend write directly.
7. Record before/after values and action ID in audit trail.
8. Reinspect the same product and comparable context.
9. Resolve only if inspected fields now match; otherwise retain unresolved/failure/unknown state.
10. Test rejected, unauthorized, stale, out-of-bounds, adapter failure, successful apply, and blocked/failed reinspection.

## Stop conditions
If source-of-truth authority, actor authorization, evidence freshness, or safe bounds are unknown, fail closed and ask for clarification rather than mutating.
