# First Antigravity Prompt — Harness Installation and Repository Assessment

Copy this prompt into Antigravity after placing the harness pack in the actual PRIP repository.

---

You are working on PRIP — PayPal Revenue Intelligence Platform. Before implementing application features, establish an evidence-based understanding of this repository and reconcile the harness with the real codebase.

Read these files first:
- `AGENTS.md`
- `docs/README_HARNESS.md`
- `docs/PRODUCT_SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/DATA_MODEL.md`
- `docs/API_CONTRACT.md`
- `docs/SECURITY.md`
- `docs/TESTING_STRATEGY.md`
- `docs/ACCEPTANCE_CRITERIA.md`
- all applicable `.agents/rules/*.md`

Then inspect the repository without changing application code:

1. Report the actual repository tree, current Git branch/commit, and working-tree status.
2. Identify the real frontend/backend stack, exact versions, package managers, lockfiles, database, ORM, migration tool, test/lint/type-check commands, and runtime configuration from files and command output.
3. Map existing implementation to PRIP domains: catalog, controlled storefront, inspection, evidence, diagnosis/LLM, deterministic policy, correction, audit, checkout, PayPal, webhooks, and frontend screens.
4. Identify existing APIs, data models, migrations, seed/reset scripts, authentication, authorization, and environment-variable usage.
5. Compare actual implementation with the target contracts and `docs/ACCEPTANCE_CRITERIA.md`.
6. Identify security gaps, especially prompt injection, SSRF, unauthorized correction, stale approvals, secret exposure, webhook verification, duplicate events, capture timeout/reconciliation, and Sandbox/Live separation.
7. Discover test commands from the actual manifests. Run only safe checks that do not mutate shared data or contact external payment services. Record exact commands and results.
8. Create `docs/REPOSITORY_ASSESSMENT.md` using `docs/REPOSITORY_ASSESSMENT_TEMPLATE.md`.
9. Mark every conclusion as **Observed**, **Inferred**, or **Proposed**. Cite exact repository paths and line numbers where possible.
10. Propose a phased implementation plan ordered by dependencies and risk. Identify the smallest complete vertical slice and the tests required at each phase.

Strict constraints:
- Do not invent files, endpoints, fields, dependencies, test results, or implemented functionality.
- Do not overwrite existing project files or restructure the repository during this assessment.
- Do not install packages, run destructive migrations/resets, deploy, use production credentials, or call PayPal without explicit approval.
- Do not start building features yet.
- If the actual repository differs from the target docs, report the discrepancy and recommend a minimal reconciliation instead of silently forcing the target structure.

Finish with: (a) what is already implemented and evidenced, (b) what is missing, (c) what is risky, (d) what remains unknown, and (e) the single safest next implementation task.
