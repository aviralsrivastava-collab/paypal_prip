---
trigger: glob
globs: "frontend/**/*.ts, frontend/**/*.tsx, frontend/**/*.js, frontend/**/*.jsx, frontend/**/*.css, frontend/**/*.scss"
description: React and TypeScript UI boundaries, status semantics, and payment UX.
---
# Frontend rules

- Follow the existing component system, routing, state management, formatting, and test conventions; inspect before adding dependencies.
- The frontend is a presentation/client layer, not a security boundary. Never embed PayPal client secrets, OAuth tokens, webhook secrets, or privileged policy logic.
- Do not let the browser directly mutate catalog/storefront data or capture PayPal orders. Call authenticated backend endpoints.
- Render inspection states distinctly: `ISSUE_DETECTED`, `VERIFIED_NO_ISSUE`, `BLOCKED_UNKNOWN`, `NOT_TESTED`. Never visually equate unknown/untested with clean.
- Show expected and observed values, comparison context, timestamps, evidence references, and relevant limitations.
- Clearly distinguish proposal, merchant approval, applied correction, and verified correction. Approval alone is not resolution.
- Show payment states honestly, including `UNKNOWN`, `CAPTURE_PENDING`, `DECLINED/CANCELLED`, and `CAPTURED`. Browser redirect is not capture confirmation.
- Label every payment flow and record as PayPal Sandbox in the MVP. Never label Sandbox capture as revenue recovered.
- Explain that PRIP-local reservation does not lock external merchant inventory.
- Include loading, empty, validation, authorization, stale-data, dependency-failure, and retry/reconciliation states. Do not silently swallow errors.
- Prevent double-submit on user actions, but do not rely on UI disabling as the only idempotency control.
- Use accessible labels, keyboard interaction, focus management, and readable status text; do not communicate state by color alone.
