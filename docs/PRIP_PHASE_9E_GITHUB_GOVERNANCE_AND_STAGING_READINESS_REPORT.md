# PRIP — Phase 9E: GitHub Governance and Staging Readiness Report

**Date:** 2026-11-09  
**Repository:** `https://github.com/aviralsrivastava-collab/paypal_prip`  
**Base Branch:** `main`  
**Test Branch:** `phase-9e/github-governance-test`  
**Latest Successful Main Commit:** `0d39a7f`  
**Execution Outcome:** **PARTIAL — MANUAL GITHUB ADMIN ACTION REQUIRED**  

---

## 1. Repository Security and Governance Audit

An automated inspection of repository metadata and administrative permissions was executed via the GitHub REST API:

| Governance Check | Observed Value | Policy Compliance | Evidence |
| :--- | :--- | :--- | :--- |
| **Repository Visibility** | **`private`** | **COMPLIANT** | `PATCH /repos` set `private: true`, `visibility: private`. Unauthenticated API calls return `404 Not Found`. |
| **Default Branch** | **`main`** | **COMPLIANT** | `default_branch: main` confirmed via repository metadata. |
| **GitHub Actions Enabled** | **`true`** | **COMPLIANT** | `GET /actions/permissions` returns `enabled: true`, `allowed_actions: all`. |
| **CI Workflows Present** | **3 Jobs Defined** | **COMPLIANT** | `.github/workflows/ci.yml` defines Harness, Backend, and Frontend quality gates. |
| **Latest CI Run** | **`success`** | **COMPLIANT** | Run `42565424609` (commit `0d39a7f`) completed with all 3 jobs passing. |
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

### 2.2 Finding & Governance Limitation
GitHub Free individual accounts do not support branch protection or rulesets on **Private** repositories (they are supported on public repositories or private repositories under GitHub Pro, GitHub Team, or GitHub Enterprise). Per PRIP non-negotiable security rules, the repository must remain strictly Private.

### 2.3 Required Manual Administrative Actions
To activate branch protection while preserving privacy:
1. **Account Tier:** Upgrade `aviralsrivastava-collab` account to **GitHub Pro** or transfer the repository to a **GitHub Team / Organization** plan.
2. **Manual UI Configuration (Once Upgraded):**
   - Navigate to **Settings** &rarr; **Branches** &rarr; **Add branch ruleset** (or **Add branch protection rule**).
   - **Branch name pattern:** `main`
   - Check **Require a pull request before merging** (Require approvals: 1).
   - Check **Require status checks to pass before merging**:
     - `Harness & Secret Integrity Check`
     - `Backend Lint, Types, Architecture & Tests`
     - `Frontend Lint, Types, Architecture, Tests & Build`
   - Check **Require branches to be up to date before merging**.
   - Check **Do not allow bypassing the above settings**.
   - Check **Restrict deletions** and **Block force pushes**.

---

## 3. Pull-Request CI Enforcement Verification

A controlled verification was conducted using branch `phase-9e/github-governance-test` targeting `main`.

*(Pull Request results recorded in Section 7 upon remote execution)*

---

## 4. Secret Protection and Vulnerability Scanning

| Security Feature | Status | Configuration Evidence |
| :--- | :--- | :--- |
| **Dependabot Alerts** | **ENABLED** | `PUT /repos/.../vulnerability-alerts` returned `HTTP 204 No Content`. |
| **Automated Security Fixes** | **ENABLED** | `PUT /repos/.../automated-security-fixes` returned `HTTP 204 No Content`. |
| **GitHub Secret Scanning** | **PLAN RESTRICTED** | Native secret scanning API returned `422: Secret scanning is not available for this repository` (requires GitHub Advanced Security or public visibility). |
| **PRIP Active CI Secret Scanner** | **ENFORCED IN CI** | `scripts/secrets_scan.py` runs on every push and PR in the `Harness & Secret Integrity Check` job, scanning all 304 repository files for API keys, private keys, and tokens. |
| **`.env.example` Check** | **VERIFIED CLEAN** | `.env.example` contains non-secret placeholders only (`GENERATE_STRONG_RANDOM_PASSWORD`, `sb-client-id-demo`). |

---

## 5. Staging Documentation Review

A cross-document review of `docs/PRIP_STAGING_HOST_REQUIREMENTS.md`, `docs/PRIP_STAGING_SETUP_RUNBOOK.md`, `docs/PRIP_PHASE_9C_BLOCKED_TEST_REGISTER.md`, and `docs/PRODUCTION_DEPLOYMENT_RUNBOOK.md` confirmed alignment across all core architecture specifications:

1. **Alembic Migration Head:** All runbooks specify `011_revalidate_parent_tenant_ownership`.
2. **Database Engine:** PostgreSQL 16+ is universally required; SQLite is strictly rejected in staging/production environments (`backend/core/config.py`).
3. **Container Infrastructure:** Docker Engine 24+ and Compose v2.20+ with multi-stage non-root container builds.
4. **Independent Background Worker:** Separation of API and polling worker with distributed database row locks (`SKIP LOCKED`).
5. **Nginx Rate Limiting:** Synchronized limits (20 req/s baseline, 40 burst; 5 req/s sensitive, 10 burst).
6. **OIDC/JWKS Verification:** Dynamic key retrieval via `OIDC_JWKS_URL` enforcing RS256/ES256 asymmetric signatures.
7. **PayPal Sandbox Invariant:** `PAYPAL_ENVIRONMENT=sandbox` strictly required; production live payments fail closed.
8. **Health Probes:** Distinct `/api/health/live`, `/api/health/ready`, `/nginx-health` probes documented and implemented.

---

## 6. Staging Host Execution Checklist (12 Gates)

The following checklist must be executed once the dedicated staging host is provisioned:

| Gate | Validation Target | Target Infrastructure | Execution Command |
| :--- | :--- | :--- | :--- |
| **GATE-01** | Multi-container Compose startup | Staging Host (Docker Engine) | `docker compose --env-file .env.staging -f infra/docker-compose.yml up -d` |
| **GATE-02** | PostgreSQL 16 fresh migration (001–011) | Staging PostgreSQL | `docker compose ... run --rm migration alembic upgrade head` |
| **GATE-03** | Existing database upgrade & downgrade | Staging PostgreSQL | `docker compose ... run --rm migration alembic downgrade 006 && alembic upgrade head` |
| **GATE-04** | PostgreSQL multi-tenant isolation & quarantine | Staging PostgreSQL | `docker compose ... exec backend pytest backend/tests/test_migration_009_multi_tenant_backfill.py -v` |
| **GATE-05** | Multi-worker `SKIP LOCKED` concurrency | 2+ Worker Containers | Run 2 concurrent worker instances; verify zero duplicate claims |
| **GATE-06** | Worker crash recovery & dead-lettering | Staging Containers | Terminate active worker container mid-batch; verify lease reclamation |
| **GATE-07** | Nginx rate limiting enforcement | Staging Nginx Proxy | Send 45 rapid HTTP requests; verify HTTP 429 after 40 burst allowance |
| **GATE-08** | X-Forwarded-For anti-spoofing | Staging Nginx Proxy | Send client-forged `X-Forwarded-For`; verify Nginx overwrites with `$remote_addr` |
| **GATE-09** | Multi-replica rate-limiting consistency | Multi-replica Backend | Send burst traffic distributed across 2 backend replicas |
| **GATE-10** | External OIDC / JWKS key rotation | External IdP (Auth0/Okta) | Rotate signing key on IdP; verify backend refetches keys without downtime |
| **GATE-11** | PayPal Sandbox OAuth & Orders v2 | PayPal Sandbox API | Initiate preflight checkout on StrideX Runner; create Sandbox order |
| **GATE-12** | Real Sandbox Webhook Signature Verification | PayPal Sandbox Webhooks | Capture order in Sandbox; receive and cryptographically verify webhook payload |

---

## 7. Pull Request Results and Final Verdict

*(Populated upon PR creation and CI verification)*
