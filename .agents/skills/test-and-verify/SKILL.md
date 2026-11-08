---
name: test-and-verify
description: Selects and runs PRIP tests and verification gates, then reports exact evidence without overstating results.
---
# Test and Verify Skill

## Procedure
1. Inspect manifests and test configuration to discover actual commands; do not guess package manager or test runner.
2. Identify changed modules and required acceptance scenarios.
3. Run narrow unit tests first, then service/API tests, frontend checks, and full suite as appropriate.
4. Run lint/type checks/build if configured.
5. Use mocks for unit tests. Run real PayPal Sandbox tests only when explicitly configured and safe.
6. Verify database migration/reset operations only against disposable test/demo databases.
7. Capture exact command, exit code, pass/fail/skip count, and relevant output summary.
8. If tests fail, diagnose; do not hide failures, weaken assertions, or mark tests skipped to force green.
9. Update `docs/TESTING_STRATEGY.md` or assessment evidence where needed.
10. Report Passed, Failed, Not Run, and Blocked separately.

## Payment-specific verification
A mocked webhook handler test is not cryptographic signature verification. A browser return is not capture confirmation. A Sandbox capture is not real revenue. An ambiguous capture must be reconciled before retry.
