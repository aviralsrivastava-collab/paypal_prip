## Description
Provide a concise explanation of the change and the problem it solves.

## Affected Modules
- [ ] `backend/` (`api`, `core`, `models`, `schemas`, `services`, `repositories`, `integrations`, `policies`)
- [ ] `frontend/` (`components`, `pages`, `features`, `services`, `hooks`, `types`)
- [ ] `contracts/`
- [ ] `database/`
- [ ] `docs/` / `scripts/`

## Invariant and Architecture Checklist
- [ ] **Dependency Direction:** Does not violate layered architecture (no DB access from routes; services orchestrate).
- [ ] **No Client-Side Payments:** Payment status is NOT trusted from client redirects; capture is server-verified.
- [ ] **AI Boundaries:** AI is explanatory only; has no tool access to modify catalog, database, or process payments.
- [ ] **Inspection States:** Does not collapse `BLOCKED_UNKNOWN` or `NOT_TESTED` into `ISSUE_DETECTED` or `VERIFIED_NO_ISSUE`.
- [ ] **Audit Trail:** Mutating operations record an immutable audit entry with actor, timestamp, and before/after values.
- [ ] **Secrets & Security:** No secrets, tokens, or credentials are hardcoded, logged, or exposed to the frontend.

## Testing Evidence
- [ ] Unit tests added / updated
- [ ] Integration / failure tests executed
- Exact test command run and result:
```text
<paste command and test run output here>
```
