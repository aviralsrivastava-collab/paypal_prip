# PRIP GitHub Workflow and Engineering Standards

This document establishes the Git workflow, pull request standards, and continuous integration pipeline for PRIP.

---

## 1. Branching Strategy

The repository follows a clean trunk-based development model:

- **Primary Branch:** `master` (or `main`)
  - Production-ready, stable baseline.
  - Direct pushes to `master` are reserved for initial foundation setup; feature development must occur on branches.
- **Feature Branches:** `feat/<phase>-<short-description>` (e.g. `feat/p1-catalog-model`, `feat/p2-storefront-adapter`).
- **Fix Branches:** `fix/<issue-number>-<short-description>` (e.g. `fix/harness-check-git-crash`).

---

## 2. Pull Request & Code Review Process

Every non-trivial code modification must go through a pull request adhering to `.github/PULL_REQUEST_TEMPLATE.md`.

### Mandatory Review Checklist:
1. **Scope Check:** Does the PR solve the exact problem without introducing unrelated refactors or speculative features?
2. **Layering Check:** Does the PR respect `docs/DEPENDENCY_RULES.md`? (No SQL in route handlers, no direct model exposure, no AI authority).
3. **Security Check:**
   - No hardcoded secrets, API tokens, or private keys.
   - All external input (HTML, user payload, webhooks) is validated with strict schemas.
   - PayPal operations remain strictly server-side.
4. **Test Coverage:**
   - New logic includes both positive and negative/boundary tests.
   - Exact test execution commands and observed results must be included in the PR description.
5. **Audit Trail:** Any state-mutating action includes an audit record.

---

## 3. Continuous Integration Pipeline

The automated CI workflow is defined in `.github/workflows/ci.yml` and executes on all pushes and pull requests to `master`:

### CI Job Matrix:
1. **Harness & Secret Integrity Check:**
   - Executes `scripts/harness-check.ps1`.
   - Verifies all required harness contracts, rules, and documentation exist.
   - Scans repository tree and git tracking index for committed secrets (`.env`, `*.key`, `id_rsa`).
2. **Backend Verification:**
   - Runs against Python 3.11.
   - Installs dependencies from `backend/requirements.txt` (once created).
   - Executes `pytest backend/tests` to verify unit, policy, and integration tests.
3. **Frontend Verification:**
   - Runs against Node.js 20.
   - Installs dependencies via `npm ci` in `frontend/` (once created).
   - Runs linter, type-checking (`tsc --noEmit`), and frontend unit tests.

*Note: Workflows are configured not to report false passes. When component manifests are not yet created, CI clearly logs that tests are pending rather than fabricating a passing status.*

---

## 4. Issue Management

All issues must use the official templates:
- **Bug Reports:** `.github/ISSUE_TEMPLATE/bug_report.md` (requires reproduction steps, affected module, and observed vs expected inspection/payment states).
- **Feature Requests:** `.github/ISSUE_TEMPLATE/feature_request.md` (requires alignment check with PRIP non-negotiable invariants and module ownership definitions).
