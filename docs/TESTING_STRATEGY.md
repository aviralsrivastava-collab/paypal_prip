# PRIP Testing Strategy

## Test layers

1. **Unit tests** — money normalization, comparability rules, state transitions, policy validation, schema validation, idempotency decisions.
2. **Service/integration tests** — repositories, transactions, correction apply/reinspect, checkout preflight/reservation, payment state persistence, webhook inbox processing.
3. **API tests** — authentication, authorization, validation, conflict/stale-state behavior, response semantics.
4. **Frontend tests** — state rendering, approval confirmation, error/loading/unknown states, Sandbox labeling, no false success on redirect.
5. **End-to-end demo test** — seeded mismatch through verified correction and PayPal Sandbox checkout.
6. **External integration tests** — opt-in tests against PayPal Sandbox using dedicated credentials and explicit cleanup/reconciliation.

## Required acceptance scenarios

| Scenario | Expected result |
|---|---|
| Same product/variant/context; catalog USD 100, storefront USD 120 | `ISSUE_DETECTED`, expected/observed values and evidence |
| Same product/variant/context; checked values match | `VERIFIED_NO_ISSUE` |
| Ambiguous variant, unknown promotion, challenge, timeout, parse failure | `BLOCKED_UNKNOWN`, never verified issue or clean |
| No scan for current source version | `NOT_TESTED` |
| Prompt-injection-like storefront text | No privileged action; schema accepted safely or model result rejected |
| Merchant rejects correction | No storefront update; rejection audited |
| Unauthorized approval/apply | Rejected; no mutation |
| Stale or out-of-bounds proposal | Policy rejects; no update |
| Valid approval | Exact approved proposal can proceed to validation/application |
| Apply correction succeeds | Controlled storefront changes; before/after and actor audited |
| Reinspection matches | Resolve checked fields only |
| Reinspection fails/blocked | Do not resolve; show failure/unknown |
| Sandbox buyer approval and capture succeeds | Capture recorded only after trusted confirmation; IDs visible |
| Buyer cancels or payment declines | Never `CAPTURED` |
| Duplicate webhook | One effective state transition |
| Invalid webhook signature | Reject/quarantine; no trusted state mutation |
| Delayed/out-of-order webhook | Safe idempotent processing/reconciliation; no state regression |
| Capture timeout | `UNKNOWN`; reconcile before any retry |
| Price/currency/availability changes before checkout | Preflight blocks/refreshes; stale amount is not charged |
| Reservation expires | Checkout cannot proceed using expired reservation |

## Test data and determinism

Use deterministic seeded data. The principal demo fixture is StrideX Runner / `SX-001`, catalog USD 100.00, storefront USD 120.00, known same variant/market/price basis, no active promotion. Add fixtures for clean match, ambiguous variant, unknown promotion, parse failure, challenge, and timeout.

## External service discipline

- Unit tests must not require network or real PayPal credentials.
- Use fakes/mocks for deterministic state-machine tests.
- Mark real Sandbox tests explicitly and require environment configuration.
- Do not store real credentials in test fixtures or CI logs.
- Distinguish simulated webhook payload tests from verified real Sandbox webhook delivery.

## Completion evidence

For each implementation milestone, record exact commands, pass/fail counts, skipped tests and reasons, environment used, and any manual verification. A test that was not run is not passed. The full acceptance checklist lives in `docs/ACCEPTANCE_CRITERIA.md`.

## Phase 1 Automated Test Suites and Commands

### Backend Automated Test Commands
- **Unit & Integration Tests (Pytest):**
  ```powershell
  .\.venv\Scripts\pytest.exe backend/tests -v
  ```
  *Coverage:* Health check endpoint, database connectivity check, degraded state handling, atomic state mutation with audit commit, rollback on audit insertion failure, optimistic locking conflict rejection, unauthorized mutation rejection, duplicate request safety, and append-only repository enforcement.
- **Backend Linting (Ruff):**
  ```powershell
  .\.venv\Scripts\ruff.exe check backend
  ```
- **Backend Type Checking (Mypy):**
  ```powershell
  .\.venv\Scripts\mypy.exe backend
  ```
- **Backend Architecture Boundary Enforcement (Import Linter):**
  ```powershell
  .\.venv\Scripts\lint-imports.exe
  ```
  *Contracts Enforced:* Layered architecture (`api -> services -> repositories -> models -> core`), core independence, policy isolation, repository isolation.

### Frontend Automated Test Commands
- **Frontend Unit & Component Tests (Vitest):**
  ```powershell
  cd frontend; npm.cmd test
  ```
  *Coverage:* Header branding, PayPal Sandbox badge, navigation links, and full App shell view rendering.
- **Frontend Type Checking:**
  ```powershell
  cd frontend; npm.cmd run lint
  ```
- **Frontend Architecture Enforcement (Dependency Cruiser):**
  ```powershell
  cd frontend; npm.cmd run lint:arch
  ```
  *Rules Enforced:* No imports from backend code, no circular dependencies, component/page isolation.
- **Frontend Production Build:**
  ```powershell
  cd frontend; npm.cmd run build
  ```

### Cross-Cutting Repository Verification
- **Test Launcher:**
  ```powershell
  powershell.exe -ExecutionPolicy Bypass -File "scripts/verify.ps1"
  ```
- **Harness Structure & Secret Leakage Check:**
  ```powershell
  powershell.exe -ExecutionPolicy Bypass -File "scripts/harness-check.ps1"
  ```

