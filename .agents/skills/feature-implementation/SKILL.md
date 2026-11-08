---
name: feature-implementation
description: Plans and implements a bounded PRIP feature with architecture, security, tests, and acceptance criteria.
---
# Feature Implementation Skill

## Procedure
1. Read `AGENTS.md`, product spec, architecture, relevant contracts, and relevant rules.
2. Inspect current code and tests; do not scaffold duplicates.
3. Define user-visible behavior, domain state transitions, trust boundaries, API/data changes, failure cases, and acceptance criteria.
4. Produce a concise plan naming files/modules and tests. Ask before broad refactors, new infrastructure, dependency additions, destructive migrations, or scope expansion.
5. Implement the smallest complete vertical slice. Keep deterministic policy outside AI. Keep privileged operations server-side.
6. Add unit, integration, API, and UI tests appropriate to the feature, including rejection/failure/stale-state paths.
7. Run targeted tests and relevant full checks; record exact commands/results.
8. Review diff for secrets, auth gaps, unsafe state transitions, untrusted input handling, audit gaps, and unrelated changes.
9. Update docs/decision log if contracts or behavior changed.
10. Report files changed, behavior implemented, tests run/results, limitations, and next dependency.

## Stop conditions
Stop and ask if requirements conflict, the trusted source is ambiguous, a destructive data operation is needed, a production credential/environment is involved, or safe behavior cannot be established.
