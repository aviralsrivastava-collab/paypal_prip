# PRIP Repository Assessment

> Assessed from direct repository inspection on 2026-11-06. Every statement is explicitly labeled as **Observed**, **Inferred**, or **Proposed**. No absent functionality is claimed to exist, and no unrun tests are marked as passing.

---

## 1. Repository Identity

- **Repository Path / Name:** `C:\Users\HP\OneDrive\Desktop\paypal` (**Observed**)
- **Harness Subdirectory:** `C:\Users\HP\OneDrive\Desktop\paypal\PRIP_Harness_Engineering_Pack (1)\PRIP_Harness_Engineering_Pack` (**Observed**)
- **Current Git Branch and Commit:** None. Git is not initialized in this directory (`fatal: not a git repository (or any of the parent directories): .git`) (**Observed** via command output).
- **Working Tree Status:** Untracked folder containing the unzipped harness engineering pack (**Observed**).
- **Date Assessed:** 2026-11-06 (**Observed**).

---

## 2. Actual File Tree

Total files observed across the entire workspace: **37 files** (**Observed**).

```text
C:\Users\HP\OneDrive\Desktop\paypal\
└── PRIP_Harness_Engineering_Pack (1)\
    └── PRIP_Harness_Engineering_Pack\
        ├── .env.example
        ├── .gitignore
        ├── AGENTS.md
        ├── MANIFEST.md
        ├── .agents\
        │   ├── rules\
        │   │   ├── 01-project-scope.md
        │   │   ├── 02-architecture.md
        │   │   ├── 03-security-and-trust.md
        │   │   ├── 04-backend-api.md
        │   │   ├── 05-frontend.md
        │   │   ├── 06-testing-and-quality.md
        │   │   ├── 07-payments-and-webhooks.md
        │   │   └── 08-database-and-migrations.md
        │   └── skills\
        │       ├── code-review\SKILL.md
        │       ├── correction-workflow\SKILL.md
        │       ├── database-migration\SKILL.md
        │       ├── feature-implementation\SKILL.md
        │       ├── inspection-and-evidence\SKILL.md
        │       ├── paypal-integration\SKILL.md
        │       ├── repository-assessment\SKILL.md
        │       └── test-and-verify\SKILL.md
        ├── docs\
        │   ├── ACCEPTANCE_CRITERIA.md
        │   ├── ANTIGRAVITY_FIRST_PROMPT.md
        │   ├── API_CONTRACT.md
        │   ├── ARCHITECTURE.md
        │   ├── CHANGELOG_HARNESS.md
        │   ├── DATA_MODEL.md
        │   ├── DECISIONS.md
        │   ├── DEMO_RUNBOOK.md
        │   ├── IMPLEMENTATION_PLAN.md
        │   ├── PAYPAL_INTEGRATION_NOTES_TEMPLATE.md
        │   ├── PRODUCT_SPEC.md
        │   ├── README_HARNESS.md
        │   ├── REPOSITORY_ASSESSMENT_TEMPLATE.md
        │   ├── SECURITY.md
        │   └── TESTING_STRATEGY.md
        └── scripts\
            ├── harness-check.ps1
            └── verify.ps1
```

**Key Observation:** There is currently **zero application code**, **zero configuration manifests** (`package.json`, `pyproject.toml`), **zero database migration files**, and **zero test suites** (**Observed**).

---

## 3. Stack and Versions

### Observed Tooling & Runtimes
- **Node.js:** `v26.12.1` installed at `C:\Program Files\nodejs\node.exe` (**Observed**).
- **npm:** `11.20.0` available at `C:\Program Files\nodejs\npm.cmd` (**Observed**). Note: PowerShell script execution policy blocks `npm.ps1`; commands must invoke `npm.cmd` (**Observed**).
- **Git:** `2.55.0.windows.5` installed (**Observed**).
- **Python / pytest:** Windows Store execution aliases exist (`C:\Users\HP\AppData\Local\Microsoft\WindowsApps\python.exe`), but execution fails with `ApplicationFailedException: The file cannot be accessed by the system` (**Observed**). A working Python interpreter/virtual environment must be configured before backend development can proceed.
- **Lockfiles & Dependency Manifests:** None present in repository (**Observed**).

### Blueprint Target Stack (per `docs/ARCHITECTURE.md`)
- **Frontend Framework:** React + TypeScript (**Target blueprint**)
- **Backend Framework:** FastAPI (Python 3.10+) (**Target blueprint**)
- **Database / ORM:** Relational Database (e.g. SQLite for local MVP / PostgreSQL) + SQLAlchemy / Alembic (**Target blueprint**)
- **Testing Frameworks:** `pytest` (Backend), Vitest/Jest (Frontend) (**Target blueprint**)

---

## 4. Existing Implementation Map

| Domain Module | Existing Files / Paths | Actual Status | Functionality Evidence |
|---|---|---|---|
| **Catalog** | None | **Missing** | No catalog database, schemas, or seed files exist. |
| **Controlled Storefront** | None | **Missing** | No mock storefront, routes, or HTML fixtures exist. |
| **Inspection Engine** | None | **Missing** | No extraction adapter, comparability logic, or 4-state engine. |
| **Evidence Storage** | None | **Missing** | No schema or persistence for observed values or raw locators. |
| **AI Diagnosis** | None | **Missing** | No LLM provider integration, strict Pydantic schemas, or prompts. |
| **Policy Service** | None | **Missing** | No deterministic validation rules or allowlist bounds checks. |
| **Correction Engine** | None | **Missing** | No approval/rejection endpoints, apply adapter, or re-inspection trigger. |
| **Checkout Preflight** | None | **Missing** | No price/currency/availability preflight or reservation tracker. |
| **PayPal Adapter** | None | **Missing** | No Orders v2 OAuth, create-order, capture, or reconciliation logic. |
| **Webhook Receiver** | None | **Missing** | No webhook endpoint, signature verification, or inbox deduplication. |
| **Audit Trail** | None | **Missing** | No append-only audit event model or logging service. |
| **Frontend UI** | None | **Missing** | No React application, components, or screens. |

---

## 5. Existing Commands and Test Evidence

| Command | Purpose | Run? | Result | Notes |
|---|---|---|---|---|
| `git status` | Check working tree & branch | Yes | **Failed** (exit code 1) | `fatal: not a git repository (or any of the parent directories): .git` (**Observed**). |
| `powershell.exe -ExecutionPolicy Bypass -File "...\scripts\harness-check.ps1"` | Validate harness file structure & secret leakage | Yes | **Failed** (exit code 1) | Fails at line 41 (`$tracked = git ls-files 2>$null`) with terminating error because `git ls-files` outputs to stderr when `.git` is absent, triggering `$ErrorActionPreference = 'Stop'` (**Observed**). |
| `powershell.exe -ExecutionPolicy Bypass -File "...\scripts\verify.ps1"` | Run discovered test suites | Yes | **Failed** (exit code 3) | `WARNING: No configured test command was executed. Discover the actual project commands and run them manually.` Exit code 3 (**Observed**). |
| `python --version` | Check Python runtime version | Yes | **Failed** | Windows App execution alias failure: `The file cannot be accessed by the system` (**Observed**). |
| `node --version` | Check Node runtime version | Yes | **Passed** (`v26.12.1`) | Functional runtime available (**Observed**). |
| `npm.cmd --version` | Check npm package manager | Yes | **Passed** (`11.20.0`) | `npm.cmd` succeeds; `npm.ps1` blocked by PowerShell script execution policy (**Observed**). |

---

## 6. Blueprint Compliance Matrix

| Requirement | Target Blueprint Reference | Current Status | Evidence | Gap / Risk |
|---|---|---|---|---|
| **Seeded Catalog Authority** | `docs/PRODUCT_SPEC.md` § MVP Scope | **Missing** | No database or seed fixture. | Must create StrideX Runner `SX-001` (\$100.00 USD) seed fixture. |
| **Controlled Storefront** | `docs/PRODUCT_SPEC.md` § Demo | **Missing** | No storefront endpoint or page. | Must create controlled endpoint returning `SX-001` at \$120.00 USD. |
| **Four Inspection States** | `AGENTS.md` L25-26, `docs/ARCHITECTURE.md` | **Missing** | No state machine implemented. | Must implement `ISSUE_DETECTED`, `VERIFIED_NO_ISSUE`, `BLOCKED_UNKNOWN`, `NOT_TESTED`. |
| **Constrained AI Diagnosis** | `docs/SECURITY.md` L13-15 | **Missing** | No LLM integration. | Must ensure AI is explanatory only; zero execution or payment authority. |
| **Merchant Decision & Audit** | `docs/API_CONTRACT.md` L15-16 | **Missing** | No approve/reject routes. | Must enforce optimistic concurrency and append-only audit trail. |
| **Correction Application & Reinspection** | `AGENTS.md` L28-30 | **Missing** | No storefront mutation adapter. | Must apply only to controlled demo storefront and re-verify before resolving. |
| **Checkout Preflight & Reservation** | `docs/API_CONTRACT.md` L19 | **Missing** | No preflight endpoint. | Must re-read current price/currency/stock; short-lived demo reservation only. |
| **PayPal Orders v2 Integration** | `docs/API_CONTRACT.md` L20-21 | **Missing** | No PayPal client/adapter. | Must keep secrets server-side; isolate Sandbox environment. |
| **Server-Side Capture & Reconciliation** | `AGENTS.md` L33-34 | **Missing** | No capture logic. | Must never trust client redirect; ambiguous captures set to `UNKNOWN`. |
| **Webhook Signature Verification** | `docs/SECURITY.md` L21-24 | **Missing** | No webhook receiver. | Must verify cryptographic signature using official PayPal method. |
| **Event Deduplication & Monotonicity** | `AGENTS.md` L35 | **Missing** | No event inbox table. | Must prevent duplicate transitions and out-of-order state regression. |
| **Demo Reset & Observability** | `docs/DEMO_RUNBOOK.md` | **Missing** | No reset scripts. | Must implement deterministic reset restricted to demo/test DB. |

---

## 7. Security Observations

1. **Secret Management:**
   - No committed secrets observed in the pack (**Observed**).
   - `.env.example` has safe placeholder values (`PAYPAL_CLIENT_ID=your_sandbox_client_id`) (**Observed**).
2. **Untrusted Inputs & Prompt Injection:**
   - Storefront HTML and page text must be treated as untrusted data (**Target Security Rule**).
   - The AI component must not receive tools, database write access, or payment execution permissions. Output must be strictly validated with Pydantic schemas (**Target Security Rule**).
3. **SSRF Protections:**
   - Storefront fetching must be restricted to an explicit localhost/controlled domain allowlist to prevent arbitrary internal network probing (**Target Security Rule**).
4. **PayPal Credentials & Payments:**
   - `PAYPAL_CLIENT_SECRET` and OAuth tokens must strictly remain on the backend (**Target Security Rule**).
   - Client redirect URLs must never be treated as capture confirmation (**Target Security Rule**).
   - Webhook endpoint must preserve raw request bytes to perform PayPal HMAC signature verification (**Target Security Rule**).
5. **Windows Execution Policy:**
   - PowerShell script execution policy prevents running unsigned `.ps1` scripts like `npm.ps1` directly (**Observed**). Use `npm.cmd` or PowerShell execution bypass for legitimate developer scripts.

---

## 8. Conflicts and Assumptions

1. **Harness Directory Hierarchy Conflict:**
   - **Observed:** The pack is currently nested at `C:\Users\HP\OneDrive\Desktop\paypal\PRIP_Harness_Engineering_Pack (1)\PRIP_Harness_Engineering_Pack\`.
   - **Conflict:** Antigravity agent discovery looks for `.agents/rules/` and `.agents/skills/` directly at the workspace root (`c:\Users\HP\OneDrive\Desktop\paypal`). Because of nesting, global rule scanning and always-on instructions (`AGENTS.md`) are not located at root.
   - **Proposal:** Flatten the contents of `PRIP_Harness_Engineering_Pack (1)\PRIP_Harness_Engineering_Pack\` to the workspace root once approved.
2. **`scripts/harness-check.ps1` Uninitialized Git Crash:**
   - **Observed:** Running `harness-check.ps1` on an uninitialized repository throws a fatal error because `$ErrorActionPreference = 'Stop'` aborts when `git ls-files` writes to stderr.
   - **Proposal:** Either initialize `git` in the repository (`git init`) or update `harness-check.ps1` to test for `.git` presence before calling `git ls-files`.
3. **Execution Environment Assumptions:**
   - The harness scripts assume `pytest` and `python` are available on the global PATH. In this Windows environment, standard python execution aliases fail. A dedicated virtual environment (`.venv`) or specific Python interpreter path must be established.

---

## 9. Proposed Implementation Sequence

Ordered by dependency and risk, following the gates in `docs/IMPLEMENTATION_PLAN.md`:

### Phase 0: Repository Foundation & Alignment (P0 - Immediate)
- **Goal:** Flatten harness files to the workspace root, initialize `git`, configure Python virtual environment and Node dependencies.
- **Dependencies:** User approval.
- **Verification:** `harness-check.ps1` passes with 0 missing files and 0 secret warnings.

### Phase 1: Modular Monolith Skeleton & Persistence (P0)
- **Goal:** Create FastAPI backend (`backend/`), React + TypeScript UI (`frontend/`), SQLite database with SQLAlchemy/Alembic models for products, scans, issues, approvals, and audit events.
- **Dependencies:** Phase 0.
- **Verification:** Health check endpoint returns `200 OK`; database schema initializes cleanly; deterministic reset script executes.

### Phase 2: Seeded Catalog & Controlled Storefront (P0)
- **Goal:** Seed product StrideX Runner (`SX-001`, expected \$100.00 USD). Create controlled storefront endpoint serving \$120.00 USD (deterministic mismatch).
- **Dependencies:** Phase 1.
- **Verification:** Seed script populates catalog; controlled storefront endpoint returns fixture HTML/JSON.

### Phase 3: Inspection, Comparability & Evidence Engine (P0)
- **Goal:** Implement extraction adapter, 5-point comparability gate (product, variant, market, currency, price basis), and 4-state classification (`ISSUE_DETECTED`, `VERIFIED_NO_ISSUE`, `BLOCKED_UNKNOWN`, `NOT_TESTED`).
- **Dependencies:** Phase 2.
- **Verification:** Unit tests for all 4 states; boundary tests for currency mismatch, promotion ambiguity, and network timeout.

### Phase 4: Constrained AI Diagnosis Service (P0)
- **Goal:** Implement LLM service with strict Pydantic output schema, referencing normalized evidence IDs. Zero tool execution authority.
- **Dependencies:** Phase 3.
- **Verification:** Tests for prompt-injection payloads (confirming zero unauthorized actions), schema validation rejection of hallucinations.

### Phase 5: Merchant Approval, Deterministic Policy & Reinspection (P0)
- **Goal:** Authenticated merchant approval/rejection endpoints, optimistic concurrency check, controlled storefront update adapter, append-only audit trail, and mandatory post-correction reinspection.
- **Dependencies:** Phase 4.
- **Verification:** Unit/integration tests verifying: rejection causes no update; stale version conflict blocks; reinspection failure keeps issue unresolved; successful reinspection marks resolved.

### Phase 6: Checkout Preflight & PayPal Sandbox Integration (P0)
- **Goal:** Preflight validation rereading current price/stock; short-lived local reservation; PayPal Orders v2 create-order and server-side capture endpoints.
- **Dependencies:** Phase 5.
- **Verification:** Mocked tests for decline/cancel and stale price rejection; real PayPal Sandbox integration test for order creation and capture.

### Phase 7: Webhook Signature Verification, Deduplication & Reliability (P1)
- **Goal:** Webhook endpoint verifying PayPal transmission signatures via official API; deduplicating event IDs; handling duplicate/out-of-order events; timeout reconciliation.
- **Dependencies:** Phase 6.
- **Verification:** Tests for invalid webhook signature rejection; duplicate webhook replay; capture timeout handling with reconciliation.

### Phase 8: Frontend UI, Demo Runbook & Rehearsal (P1)
- **Goal:** Build React dashboard displaying inspection states, evidence, AI explanation, merchant approve/reject button, reinspection confirmation, and PayPal checkout flow.
- **Dependencies:** Phases 1–7.
- **Verification:** Full 4–5 minute rehearsal following `docs/DEMO_RUNBOOK.md`.

---

## 10. Explicitly Unverified

The following items could not be verified and remain unvalidated:
1. **Python Environment:** Python 3 installation path and `pytest` availability on the host machine.
2. **PayPal Sandbox Credentials:** No PayPal Client ID, Secret, or Webhook ID are configured yet.
3. **External Network Access to PayPal:** Sandbox REST endpoints have not been contacted.
4. **LLM Provider API Key:** No AI provider credentials configured in `.env`.
5. **Database Engine:** No relational database is active or running.
6. **Frontend Toolchain:** Build tools (Vite/React) not yet installed or executed.
