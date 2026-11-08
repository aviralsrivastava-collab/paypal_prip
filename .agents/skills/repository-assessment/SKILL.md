---
name: repository-assessment
description: Inspects an existing PRIP repository and produces an evidence-based implementation assessment before code changes.
---
# Repository Assessment Skill

## Use when
Starting work in an unfamiliar repository, before a major milestone, or when the implementation state is uncertain.

## Procedure
1. Read root `AGENTS.md` and relevant `docs/` contracts.
2. Inspect the repository tree, Git status, manifests, lockfiles, runtime versions, configuration, migrations, tests, and README.
3. Identify actual modules for catalog, storefront, inspection, evidence, diagnosis, policy, correction, checkout, PayPal, webhooks, audit, and UI.
4. Run only safe, non-destructive discovery commands initially. Do not reset databases, install packages, deploy, or contact payment services without approval.
5. Execute existing tests only when their setup is understood and safe; record exact commands/results.
6. Compare observed implementation to product/architecture/acceptance contracts.
7. Mark each statement Observed, Inferred, or Proposed and cite file paths/line ranges where possible.
8. Write `docs/REPOSITORY_ASSESSMENT.md` using the template.
9. Propose a phased plan ordered by dependencies and risk.
10. Do not modify application code during assessment unless explicitly requested.

## Output
Actual repository map, stack/version evidence, existing commands, compliance matrix, risks, conflicts, unknowns, and proposed next step. Never claim absent functionality exists or unrun checks pass.
