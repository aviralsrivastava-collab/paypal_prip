---
trigger: glob
globs: "backend/**/*.py, **/alembic/**/*.py, **/migrations/**/*.py"
description: FastAPI backend, domain service, API validation, and persistence conventions.
---
# Backend implementation rules

- Follow the repository's existing Python version, formatter, linter, typing, and test configuration; do not guess versions.
- Keep route handlers thin: parse/validate request, authenticate/authorize, call application service, map result to response.
- Put deterministic domain rules in domain/application services, not route handlers, templates, or LLM prompts.
- Use strict Pydantic request/response schemas; reject invalid enums, extra fields where security-sensitive, malformed money, and unsupported values.
- Represent money with decimal-safe types and explicit currency; never use binary floating-point for financial calculations.
- Use database transactions for state changes that must be atomic. Enforce uniqueness/foreign-key constraints in the database where appropriate, not only in application code.
- Use optimistic concurrency/version checks for issue approval and correction application.
- Make mutation endpoints authenticated, authorized, validated, idempotent where appropriate, and auditable.
- Return stable error shapes without leaking internals. Distinguish validation, authorization, conflict/stale-state, unavailable dependency, and unknown payment outcome.
- Do not mark an issue resolved until post-correction reinspection verifies the checked fields.
- Never set payment state to `CAPTURED` from browser callback alone.
- Add tests for success and negative/failure paths for every new domain transition.
