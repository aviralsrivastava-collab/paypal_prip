# PRIP — Phase 9E: GitHub Governance and Staging Readiness Report

**Date:** 2026-11-09  
**Repository:** `https://github.com/aviralsrivastava-collab/paypal_prip`  
**Target Branch:** `main`  
**Test PR:** [#1](https://github.com/aviralsrivastava-collab/paypal_prip/pull/1)  
**Execution Outcome:** **PARTIAL — MANUAL GITHUB ADMIN ACTION REQUIRED**  

---

## 1. Repository Security and Governance Audit

An automated inspection of repository metadata and administrative permissions was executed via the GitHub REST API:

| Governance Check | Observed Value | Policy Compliance | Evidence |
| :--- | :--- | :--- | :--- |
| **Repository Visibility** | **`private`** | **COMPLIANT** | `PATCH /repos` verified `private: true`, `visibility: private`. Unauthenticated API calls return `404 Not Found`. |
| **Default Branch** | **`main`** | **COMPLIANT** | Confirmed via `GET /repos/aviralsrivastava-collab/paypal_prip` (`default_branch: main`). |
| **GitHub Actions Enabled** | **`true`** | **COMPLIANT** | Confirmed via `GET /actions/permissions` (`enabled: true`, `allowed_actions: all`). |
| **CI Workflows Present** | **3 Jobs Defined** | **COMPLIANT** | `.github/workflows/ci.yml` defines Harness, Backend, and Frontend quality gates. |
| **Latest Main CI Run** | **`success`** | **COMPLIANT** | Run [42565424609](https://github.com/aviralsrivastava-collab/paypal_prip/actions/runs/42565424609) (commit `0d39a7f`) passed all 3 jobs. |
| **Collaborators & Access** | **1 Admin** | **COMPLIANT** | `aviralsrivastava-collab` holds sole admin role (`permissions: {admin: true}`). Zero unexpected users. |

---

## 2. Branch Protection and Ruleset Investigation

Administrative calls were made to configure branch protection and rulesets for `main`:

### 2.1 API Configuration Attempts
1. **Classic Branch Protection (`PUT /repos/.../branches/main/protection`):**
   - **Payload:** Enforced PR reviews, dismiss stale reviews, strict status checks (`Harness & Secret Integrity Check`, `Backend Lint, Types, Architecture & Tests`, `Frontend Lint, Types, Architecture, Tests & Build`), no force-pushes, no deletions, enforce admins.
   - **Response:** `HTTP 403 Forbidden`
   - **Message:** `"Upgrade to GitHub Pro or make this repository public to enable this feature."`
2. **Repository Rulesets (`POST /repos/.../rulesets`):**
   - **Payload:** Active branch rule targeting `~DEFAULT_BRANCH`, blocking deletion, non-fast-forward pushes, requiring PR and status checks.
   - **Response:** `HTTP 403 Forbidden`
   - **Message:** `"Upgrade to GitHub Pro or make this repository public to enable this feature."`

### 2.2 Finding & Plan Constraint
On GitHub's personal Free tier, branch protection and repository rulesets are only available on public repositories. For private repositories, GitHub restricts these governance features to **GitHub Pro**, **GitHub Team**, or **GitHub Enterprise Cloud** plans.
Because PRIP security invariants strictly mandate that the repository remain **Private**, branch protection cannot be enabled automatically via API under the current personal Free plan without account plan elevation.

### 2.3 Required Manual Administrative Actions
To activate branch protection while preserving strict repository privacy:
1. **Account Tier Upgrade:** Upgrade the account `aviralsrivastava-collab` to **GitHub Pro** or transfer the repository into a **GitHub Team / Organization** workspace.
2. **Manual UI Configuration Instructions:**
   - Navigate to `https://github.com/aviralsrivastava-collab/paypal_prip/settings/branches`.
   - Click **Add branch ruleset** (or **Add branch protection rule**).
   - Set **Ruleset Name / Branch pattern:** `main`.
   - Under **Enforcement status**, select **Active**.
   - Under **Target branches**, select **Default branch**.
   - Enable **Restrict deletions**.
   - Enable **Block force pushes**.
   - Enable **Require a pull request before merging**:
     - Set **Required approvals:** `1` (or `0` if single-maintainer workflow).
     - Check **Dismiss stale pull request approvals when new commits are pushed**.
     - Check **Require conversation resolution before merging**.
   - Enable **Require status checks to pass before merging**:
     - Check **Require branches to be up to date before merging**.
     - Add exact check names:
       1. `Harness & Secret Integrity Check`
       2. `Backend Lint, Types, Architecture & Tests`
       3. `Frontend Lint, Types, Architecture, Tests & Build`
   - Under **Bypass list**, ensure zero bypass roles or teams are permitted.
   - Click **Create / Save changes**.

---

## 3. Pull-Request CI Enforcement Verification

A controlled end-to-end pull request cycle was executed using branch `phase-9e/github-governance-test`:

- **Pull Request:** [#1](https://github.com/aviralsrivastava-collab/paypal_prip/pull/1) (`docs: Phase 9E GitHub governance and staging readiness report`)
- **Base Branch:** `main`
- **Head Branch:** `phase-9e/github-governance-test` (Commit `c78c410`)
- **Workflow Run:** [42566899033](https://github.com/aviralsrivastava-collab/paypal_prip/actions/runs/42566899033) (Trigger: `pull_request`)

### Job Execution Results

| Job Name | Runner OS | Status | Conclusion | Duration |
| :--- | :--- | :--- | :--- | :--- |
| **Harness & Secret Integrity Check** | `windows-latest` | `completed` | **`success`** | ~20s |
| **Backend Lint, Types, Architecture & Tests** | `ubuntu-latest` | `completed` | **`success`** | ~25s |
| **Frontend Lint, Types, Architecture, Tests & Build** | `ubuntu-latest` | `completed` | **`success`** | ~33s |

### Mergeability Progression
- When checks were executing: PR mergeable state reported `unstable` (`mergeable: true`).
- Once all 3 CI jobs passed: PR mergeable state cleanly transitioned to `clean` (`mergeable: true`).
- Following successful verification, PR #1 was closed without merging, and the remote test branch was deleted cleanly per repository hygiene rules.

---

## 4. Secret Protection and Vulnerability Scanning

| Security Capability | Configuration Status | Evidence |
| :--- | :--- | :--- |
| **Dependabot Alerts** | **ENABLED** | `PUT /repos/.../vulnerability-alerts` returned `HTTP 204 No Content`. |
| **Automated Security Fixes** | **ENABLED** | `PUT /repos/.../automated-security-fixes` returned `HTTP 204 No Content`. |
| **Native Secret Scanning** | **PLAN RESTRICTED** | Native secret scanning returned `HTTP 422` (restricted on private repositories on Free plan; requires Advanced Security). |
| **Active PRIP Secret Scanner** | **ENFORCED IN CI** | `scripts/secrets_scan.py` executes on every push and PR in CI, auditing all repository files for private keys, PayPal tokens, AWS keys, and connection strings. |
| **`.env.example` Check** | **CLEAN (Placeholders Only)** | Audited `.env.example`; contains only generic templates (`GENERATE_STRONG_RANDOM_PASSWORD`, `sb-client-id-demo`). |

---

## 5. Staging Documentation Review

A comprehensive alignment review across all staging and production runbooks confirmed technical consistency:
- `docs/PRIP_STAGING_HOST_REQUIREMENTS.md`
- `docs/PRIP_STAGING_SETUP_RUNBOOK.md`
- `docs/PRIP_PHASE_9C_BLOCKED_TEST_REGISTER.md`
- `docs/PRODUCTION_DEPLOYMENT_RUNBOOK.md`

### Invariant Alignment Checklist
1. **Alembic Migration Head:** All documents agree on `011_revalidate_parent_tenant_ownership`.
2. **Database Engine:** PostgreSQL 16+ is universally required; SQLite fallback is strictly blocked in staging/production mode (`backend/core/config.py`).
3. **Container Infrastructure:** Standardized on Docker Engine 24+ and Docker Compose v2.20+ with non-root containers.
4. **Independent Worker Separation:** Dedicated worker process with distributed `SKIP LOCKED` database concurrency.
5. **Nginx Rate Limiting:** Coordinated baseline (20 rps / 40 burst) and sensitive endpoints (5 rps / 10 burst).
6. **OIDC/JWKS Verification:** Mandatory asymmetric RS256/ES256 verification via `OIDC_JWKS_URL`.
7. **PayPal Sandbox Exclusivity:** `PAYPAL_ENVIRONMENT=sandbox` strictly enforced; `live` raises `ValueError`.
8. **Health Probes:** Granular probes implemented at `/api/health/live`, `/api/health/ready`, and `/nginx-health`.

---

## 6. Staging Host Execution Checklist (12 Gates)

The following checklist must be executed once the dedicated staging host is provisioned:

| Gate | Validation Target | Target Infrastructure | Execution Command | Local vs External |
| :--- | :--- | :--- | :--- | :--- |
| **GATE-01** | Multi-container Compose startup | Staging Host (Docker Engine) | `docker compose --env-file .env.staging -f infra/docker-compose.yml up -d` | External Staging |
| **GATE-02** | PostgreSQL 16 fresh migration (001–011) | Staging PostgreSQL | `docker compose ... run --rm migration alembic upgrade head` | External Staging |
| **GATE-03** | Existing database upgrade & downgrade | Staging PostgreSQL | `docker compose ... run --rm migration alembic downgrade 006 && alembic upgrade head` | External Staging |
| **GATE-04** | PostgreSQL multi-tenant isolation & quarantine | Staging PostgreSQL | `docker compose ... exec backend pytest backend/tests/test_migration_009_multi_tenant_backfill.py -v` | External Staging |
| **GATE-05** | Multi-worker `SKIP LOCKED` concurrency | 2+ Worker Containers | Launch 2 concurrent workers; verify zero duplicate claims | External Staging |
| **GATE-06** | Worker crash recovery & dead-lettering | Staging Containers | Kill worker container mid-batch; verify lease reclamation | External Staging |
| **GATE-07** | Nginx rate limiting enforcement | Staging Nginx Proxy | Send 45 rapid HTTP requests; verify HTTP 429 after 40 burst allowance | External Staging |
| **GATE-08** | X-Forwarded-For anti-spoofing | Staging Nginx Proxy | Send client-forged `X-Forwarded-For`; verify Nginx overwrites with `$remote_addr` | External Staging |
| **GATE-09** | Multi-replica rate-limiting consistency | Multi-replica Backend | Send burst traffic distributed across 2 backend replicas | External Staging |
| **GATE-10** | External OIDC / JWKS key rotation | External IdP (Auth0/Okta) | Rotate signing key on IdP; verify backend refetches keys without downtime | External IdP |
| **GATE-11** | PayPal Sandbox OAuth & Orders v2 | PayPal Sandbox API | Initiate preflight checkout on StrideX Runner; create Sandbox order | External PayPal Sandbox |
| **GATE-12** | Real Sandbox Webhook Signature Verification | PayPal Sandbox Webhooks | Capture order in Sandbox; receive and cryptographically verify webhook payload | External PayPal Sandbox |

---

## 7. Outstanding Infrastructure Requirements

The following requirements remain outstanding until a dedicated staging host is provisioned:
1. **Linux / WSL2 Host:** Minimum 2 vCPU cores, 4 GB RAM, and 20 GB SSD storage running Ubuntu 22.04/24.04 or Debian 12.
2. **Container Engine:** Docker Engine 24+ and Docker Compose v2.20+.
3. **External Connectivity:** Outbound TCP port 443 egress to `api-m.sandbox.paypal.com` and the configured OIDC issuer JWKS endpoint.

---

## 8. Final Verdict

# `PARTIAL — MANUAL GITHUB ADMIN ACTION REQUIRED`

The repository is private, clean, and has all 3 CI workflows passing on both `push` and `pull_request` events. Due to GitHub Free plan limitations on private repositories, branch protection cannot be activated via the API and requires upgrading the account to GitHub Pro/Team or manual UI configuration.
