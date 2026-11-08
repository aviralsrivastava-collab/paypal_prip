# PRIP Phase 4 Completion Report: AI-Assisted Diagnosis & Explainable Intelligence

> **Milestone:** Phase 4 — AI-Assisted Diagnosis & Explainable Intelligence  
> **Status:** Completed & Fully Verified  
> **Date:** 2026-11-07  
> **Verdict:** APPROVED FOR PHASE 5 WITH DOCUMENTED LIMITATIONS  
> **Primary Scenario Diagnosed:** StrideX Runner (SKU `SX-001`), Scan #1, State `ISSUE_DETECTED`, Discrepancy +USD 20.00, Advisory AI Diagnosis Status `COMPLETED`, Grounded Evidence Citations `[#1, #2]`.

---

## 1. Executive Summary

Phase 4 introduces an explainable, evidence-grounded AI diagnostic layer to the PayPal Revenue Intelligence Platform (PRIP).
Operating strictly downstream of the deterministic inspection engine, the AI diagnostic layer analyzes completed inspection scans and structured evidence records to answer five fundamental merchant questions:
1. **What was observed?** (Authoritative catalog baseline vs controlled storefront observation)
2. **Why does an issue exist?** (Root cause analysis based on grounded evidence)
3. **Which evidence supports the diagnosis?** (Cryptographically hashed evidence IDs)
4. **What information is missing?** (Gaps, unobserved promotion terms, or comparability blockers)
5. **What actions should a human operator consider?** (Advisory recommendations requiring merchant approval)

### Mandatory Authority Boundaries
The diagnostic layer enforces non-negotiable boundaries preventing AI hallucination, prompt injection, and unauthorized actions:
- **Zero Execution Authority:** AI cannot modify catalog or storefront prices, change product availability, or initiate/capture/refund payments.
- **Deterministic State Invariance:** AI cannot alter inspection states. An AI diagnosis cannot convert `BLOCKED_UNKNOWN` to `VERIFIED_NO_ISSUE` or override deterministic comparability policies.
- **Strict Evidence Grounding:** All claims must cite observed evidence IDs. Citations of unobserved or fabricated evidence IDs are rejected by deterministic policy.
- **Storefront Input Containment:** Extracted storefront content is treated as untrusted data and strictly delimited within `<untrusted_storefront_content>` tags, neutralizing prompt injection attempts.
- **Prohibited Action Screening:** Model output proposing prohibited actions (e.g., `execute payment`, `override inspection state`, `modify catalog price`) is intercepted and rejected by deterministic policy before persistence.

---

## 2. Implemented Architecture & Components

### 2.1 Provider Abstraction Layer (`backend/integrations/ai/`)
- **`backend/integrations/ai/base.py`**:
  - `AIProviderInterface`: Abstract base class defining `generate_diagnosis(prompt_context) -> RawDiagnosisPayload`.
  - Typed error hierarchy: `AIProviderError`, `AIProviderTimeoutError`, `AIProviderRateLimitError`, `AIProviderOutageError`, `AIStructuredOutputError`.
- **`backend/integrations/ai/context.py`**:
  - `DiagnosisPromptContext`: Typed container packaging scan facts, grounded evidence records, allowed evidence ID sets, and isolated untrusted storefront snippets.
- **`backend/integrations/ai/mock_provider.py`**:
  - `MockAIProvider`: Deterministic provider for CI, automated testing, and offline development. Eliminates flaky network tests and external API key dependencies while supporting deterministic fault injection (`timeout`, `rate_limit`, `outage`, `invalid_output`, `insufficient_evidence`, `prompt_injection`).
- **`backend/integrations/ai/factory.py`**:
  - Provider factory selecting provider implementation based on `settings.ai_provider`.
- **`backend/integrations/ai/__init__.py`**:
  - Clean boundary exports ensuring external packages access only public provider contracts.

### 2.2 Deterministic Validation Policies (`backend/policies/`)
- **`backend/policies/diagnosis_validator.py`**:
  - `validate_diagnosis_payload(payload, allowed_evidence_ids)`: Deterministic policy validating:
    1. **Evidence Grounding:** Every ID in `supporting_evidence_ids` must exist in `allowed_evidence_ids`.
    2. **Prohibited Action Filter:** Screens `recommended_actions` against prohibited terms (`override state`, `override inspection state`, `execute payment`, `capture payment`, `refund payment`, `modify catalog price`, `modify database`, `bypass approval`).
    3. **Completeness & Status Integrity:** Enforces non-empty summaries and valid status mappings.

### 2.3 Persistence & Repositories (`backend/models/`, `backend/repositories/`, `backend/migrations/`)
- **`backend/models/diagnosis.py`**:
  - `Diagnosis` ORM model mapped to `diagnoses` table. Persists diagnosis ID, foreign key `scan_id` (with `CASCADE`), `provider`, `model`, `prompt_version`, `status` (`COMPLETED`, `INSUFFICIENT_EVIDENCE`, `FAILED`), `summary`, `likely_causes` (JSON), `supporting_evidence_ids` (JSON), `missing_information` (JSON), `recommended_actions` (JSON), `confidence_explanation`, and raw model response.
- **`backend/repositories/diagnosis.py`**:
  - `DiagnosisRepository` providing atomic creation, retrieval by ID, and listing historical diagnoses by `scan_id`.
- **`backend/migrations/versions/004_diagnoses.py`**:
  - Applied migration creating `diagnoses` table with foreign key to `storefront_scans.id` and index on `scan_id`.

### 2.4 Orchestration & API Routing (`backend/services/`, `backend/api/`)
- **`backend/services/diagnosis.py`**:
  - `DiagnosisService`:
    1. Loads completed inspection scan and associated structured evidence.
    2. Builds isolated prompt context with untrusted storefront containment.
    3. Invokes AI provider abstraction (capturing typed errors without affecting underlying scan state).
    4. Applies deterministic policy validation.
    5. Persists diagnosis record and append-only `DIAGNOSIS_COMPLETED` audit event within an atomic database transaction.
- **`backend/api/diagnoses.py`**:
  - `POST /api/diagnoses/scan/{scan_id}`: Triggers an advisory diagnosis with optional simulation mode.
  - `GET /api/diagnoses/{id}`: Retrieves specific diagnosis detail.
  - `GET /api/diagnoses/scan/{scan_id}`: Lists historical diagnoses for an inspection scan.

### 2.5 Architecture Boundaries (`.importlinter`)
- Added 5th architectural contract: `ai-integrations-isolation`.
- Forbids `backend.integrations.ai` from importing `backend.repositories`, `backend.services`, or `backend.api`.
- All 5 architectural contracts kept with 0 broken.

### 2.6 Frontend Advisory UI (`frontend/src/`)
- **`frontend/src/types/index.ts`**:
  - Defined `DiagnosisStatus` and `Diagnosis` interface.
- **`frontend/src/services/api.ts`**:
  - Added `triggerDiagnosis`, `getScanDiagnoses`, and `getDiagnosis`.
- **`frontend/src/pages/Inspection.tsx`**:
  - Integrated Advisory AI Diagnosis panel directly below Structured Evidence:
    - Prominent `Advisory Only — Human Merchant Decision Required` banner.
    - Explicit visual separation between deterministic inspection state (`ISSUE_DETECTED`) and advisory diagnosis status (`COMPLETED`).
    - Model provenance display (Provider, Model, Prompt Version).
    - Structured presentation of Summary, Likely Causes, Grounded Evidence Tags (`Evidence #1`, `Evidence #2`), Missing Information, and Advisory Recommendations (`[Advisory] ...`).
    - Fault-injection testing selector for demonstration.

---

## 3. Automated Verification & Quality Gates

### 3.1 Backend Test Suite (71 Tests Total, 14 Phase 4 Tests)
Command: `.\.venv\Scripts\pytest.exe backend/tests -v`
Result: **71 passed in 3.71s**

Phase 4 test breakdown (`backend/tests/test_diagnosis_and_ai.py`):
1. `test_1_valid_evidence_grounded_diagnosis`: Normal price discrepancy yields `COMPLETED` diagnosis with grounded evidence IDs.
2. `test_2_insufficient_evidence_when_scan_is_blocked`: `BLOCKED_UNKNOWN` scan produces `INSUFFICIENT_EVIDENCE` diagnosis noting missing data.
3. `test_3_unknown_evidence_ids_rejected`: Unobserved evidence citations rejected by deterministic policy.
4. `test_4_invalid_structured_output_rejected`: Malformed or missing JSON raises typed output error.
5. `test_5_prompt_injection_embedded_in_storefront_safely_defended`: Malicious prompts in storefront content remain delimited and neutralized.
6. `test_6_provider_timeout_handled_safely`: Timeout raises `AIProviderTimeoutError` without altering scan state.
7. `test_7_provider_rate_limit_handled_safely`: HTTP 429 raises `AIProviderRateLimitError` safely.
8. `test_8_provider_outage_handled_safely`: Service outage raises `AIProviderOutageError` safely.
9. `test_9_ai_output_attempting_to_change_inspection_state_rejected`: Model recommendations attempting to override state rejected.
10. `test_10_ai_output_attempting_to_execute_payment_rejected`: Model recommendations proposing payment actions rejected.
11. `test_11_diagnosis_retrieval_and_evidence_linkage`: Diagnosis correctly links to scan and evidence items.
12. `test_12_duplicate_diagnosis_requests`: Multiple diagnosis requests safely persist historical diagnoses.
13. `test_13_ai_failure_never_changes_inspection_state`: Invariant: provider failure leaves underlying scan completely unaltered.
14. `test_14_api_route_handlers_for_diagnoses`: Endpoints correctly handle creation, retrieval, and error status codes.

### 3.2 Backend Code Quality & Architecture Checks
- **Ruff:** `.\.venv\Scripts\ruff.exe check backend` -> **All checks passed!**
- **Mypy:** `.\.venv\Scripts\mypy.exe backend` -> **Success: no issues found in 74 source files**
- **Import-Linter:** `.\.venv\Scripts\lint-imports.exe` -> **Contracts: 5 kept, 0 broken**

### 3.3 Frontend Verification (15 Tests Total)
Command: `cd frontend; npm.cmd test -- --run`
Result: **15 passed in 4.62s**
- Added 3 targeted Phase 4 tests in `frontend/tests/Inspection.test.tsx`:
  - `renders advisory AI diagnosis panel with clear separation from inspection state`
  - `triggers advisory AI diagnosis on user button click`
  - `displays AI diagnostic error without altering inspection state banner`
- **Frontend Typecheck:** `npm.cmd run lint` -> `tsc --noEmit` passed cleanly.
- **Frontend Architecture:** `npm.cmd run lint:arch` -> `depcruise` passed with 0 violations.
- **Frontend Production Build:** `npm.cmd run build` -> built cleanly in 893ms.

### 3.4 Repository Verification Scripts
- `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` -> **Passed cleanly (all tests pass)**.
- `powershell -ExecutionPolicy Bypass -File scripts/harness-check.ps1` -> **Passed cleanly**.

---

## 4. Invariant Compliance Checklist

| Invariant | Status | Verification Evidence |
|---|---|---|
| AI is strictly advisory and explanatory | Compliant | Enforced in `backend/policies/diagnosis_validator.py` and UI disclaimer banner |
| AI cannot alter inspection state | Compliant | Verified by `test_9_ai_output_attempting_to_change_inspection_state_rejected` and `test_13_ai_failure_never_changes_inspection_state` |
| AI cannot execute, capture, or refund payments | Compliant | Verified by `test_10_ai_output_attempting_to_execute_payment_rejected` |
| Factual claims grounded in observed evidence | Compliant | Verified by `test_3_unknown_evidence_ids_rejected` |
| Untrusted storefront content isolated | Compliant | Storefront text delimited in `<untrusted_storefront_content>`; verified by `test_5_prompt_injection_embedded_in_storefront_safely_defended` |
| Provider failure isolates scan state | Compliant | Fault injection tests (6, 7, 8, 13) confirm scan state remains intact |
| Append-only audit logging | Compliant | `DIAGNOSIS_COMPLETED` audit event logged atomically with diagnosis record |
| No external network calls in CI | Compliant | Hermetic `MockAIProvider` used for deterministic testing |

---

## 5. Documented Limitations & Phase 5 Preconditions

1. **Advisory Scope Only:** The AI diagnosis produces recommendations for merchant consideration. It cannot approve corrections or modify storefront data. Phase 5 will implement the merchant approval workflow, deterministic policy enforcement, controlled correction, and mandatory post-correction reinspection.
2. **Mock AI Provider Default:** The MVP uses `MockAIProvider` to guarantee hermetic CI runs and deterministic testing without exposing API keys or incurring external latency. Integrating a live LLM provider in production requires configuring merchant-managed API keys via environment variables.
3. **No Payment Integration in Phase 4:** PayPal Sandbox checkout, payment capture, and webhook reconciliation remain deferred to Phase 6.

---

## 6. Phase Acceptance Verdict

**APPROVED FOR PHASE 5 WITH DOCUMENTED LIMITATIONS**  
All Phase 4 acceptance criteria, architectural boundaries, prompt defenses, deterministic policies, automated tests, and quality gates are satisfied.
