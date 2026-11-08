# PRIP Harness Engineering Pack

This pack contains repository instructions, Antigravity rules and skills, technical contracts, verification guidance, and safe local scripts for the PRIP hackathon MVP.

## Installation

1. Open the actual PRIP repository in Antigravity.
2. Back up or commit the current repository state before adding harness files.
3. Extract/copy the contents of this pack into the repository root, preserving the `.agents/` directory and paths.
4. Do not overwrite existing project documentation or configuration without comparing it first. Merge useful content and retain repository-specific facts.
5. Ask Antigravity to inspect the repository and reconcile the harness against the real codebase before implementation.
6. Review the resulting diff. Commit the harness as a separate, reviewable change.

## Important scope note

The pack defines target contracts from the PRIP final solution blueprint. It does not claim that the application, database, API, PayPal integration, authentication, or tests already exist. The agent must inspect the repository and mark each capability as implemented, tested, mocked, or planned.

## Antigravity compatibility

- Root `AGENTS.md` is an always-on instruction file.
- `.agents/rules/*.md` use supported YAML `trigger` frontmatter.
- `.agents/skills/<skill-name>/SKILL.md` are on-demand procedures.
- Rules are deliberately flat directly under `.agents/rules/` because Antigravity's rule discovery scans immediate Markdown children.
- This pack uses Skills, not legacy Workflows.

## Suggested first Antigravity task

"Read `AGENTS.md`, `docs/README_HARNESS.md`, and all PRIP docs. Inspect the current repository without changing application code. Produce `docs/REPOSITORY_ASSESSMENT.md` containing the actual tree, stack/version evidence, existing modules, tests, commands, missing capabilities, conflicts with target contracts, and a phased implementation plan. Label every statement as observed, inferred, or proposed. Do not invent files or claim tests pass."

## Suggested implementation order

1. Repository assessment and foundation.
2. Seeded catalog and controlled storefront.
3. Inspection, comparability, evidence, and four-state model.
4. Structured AI diagnosis with no action authority.
5. Merchant approval, deterministic policy, correction application, audit, and reinspection.
6. Checkout preflight and local demo reservation.
7. PayPal Sandbox order, buyer approval, capture, webhook verification, idempotency, and reconciliation.
8. UI polish, demo reset, README, and rehearsed demo.

## Verification

Run `scripts/harness-check.ps1` to check pack structure and obvious secret-file hazards. It is not a substitute for application tests, security review, or PayPal Sandbox verification. See `docs/TESTING_STRATEGY.md`.
