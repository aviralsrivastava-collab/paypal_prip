# PRIP Repository Assessment

> Fill this from direct repository inspection. Label statements **Observed**, **Inferred**, or **Proposed**. Do not assume missing files or report unrun tests as passing.

## 1. Repository identity
- Repository path/name:
- Current branch and commit:
- Working tree status:
- Date assessed:

## 2. Actual file tree

Include relevant files and omit generated/vendor folders. Do not invent expected paths.

## 3. Stack and versions (Observed)
- Frontend framework/version:
- Backend framework/Python version:
- Database/ORM/migration tool:
- Package managers and lockfiles:
- Test/lint/type-check tools:
- Runtime/deployment configuration:

## 4. Existing implementation map

For each domain module, state existing paths and what they actually do: catalog, controlled storefront, inspection, evidence, diagnosis/LLM, policy, correction, checkout, PayPal, webhook, audit, frontend screens.

## 5. Existing commands and test evidence

| Command | Purpose | Run? | Result | Notes |
|---|---|---|---|---|

## 6. Blueprint compliance matrix

| Requirement | Status (implemented/partial/missing/unknown) | Evidence (file/test) | Gap/risk |
|---|---|---|---|

## 7. Security observations

Secrets handling, auth, authorization, prompt-injection boundary, SSRF controls, webhook verification, idempotency, logging/redaction, Sandbox isolation.

## 8. Conflicts and assumptions

List contradictions between code and target docs. Do not silently resolve them.

## 9. Proposed implementation sequence

Smallest safe phases with dependencies, acceptance criteria, tests, and risk.

## 10. Explicitly unverified

List everything not run, not configured, inaccessible, mocked, or awaiting credentials.
