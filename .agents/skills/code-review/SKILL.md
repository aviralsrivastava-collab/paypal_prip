---
name: code-review
description: Reviews PRIP changes for correctness, architecture, security, payment safety, regression risk, and test completeness.
---
# Code Review Skill

## Review order
1. Read task/acceptance criteria and inspect the full diff.
2. Trace state transitions and trust boundaries, not just changed lines.
3. Check authorization and optimistic concurrency for correction actions.
4. Check inspection comparability and correct use of four states.
5. Check AI schema/evidence validation and confirm model cannot perform privileged actions.
6. Check payment flow: server-side verification, idempotency, timeout→UNKNOWN→reconciliation, webhook signature verification, event dedupe, environment isolation.
7. Check database transactions, constraints, migrations, audit consistency, and money precision.
8. Check frontend status honesty, Sandbox labeling, loading/error states, and no secret exposure.
9. Check tests cover happy path, invalid input, unauthorized action, stale state, duplicate, failure, and ambiguity.
10. Run relevant tests if safe; report exact results.

## Findings format
For each finding: severity (critical/high/medium/low), file/line, concrete failure scenario, impact, and recommended fix. Separate confirmed defects from questions or hardening suggestions. Do not approve solely because tests pass.
