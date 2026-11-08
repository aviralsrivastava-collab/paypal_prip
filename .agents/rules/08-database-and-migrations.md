---
trigger: model_decision
description: Apply to schema, SQL, ORM model, migration, persistence, and data-reset changes.
---
# Database and migration safety

- Inspect current schema, migration history, database engine, and deployment/reset process before changing persistence.
- Never rewrite an already-applied migration. Create a new migration with a clear forward operation and, where feasible, a safe downgrade.
- Prefer expand-and-contract for destructive/renaming changes. Do not drop columns or data in the same step that introduces a replacement unless the environment is disposable and explicitly confirmed.
- Add database constraints for uniqueness, referential integrity, non-null requirements, and valid state values where practical.
- Use transactions for multi-row state changes and audit writes that must succeed together.
- Store money using fixed-precision decimal/numeric representation plus ISO currency code. Avoid floating-point storage/calculation.
- Keep webhook event IDs, provider order IDs, capture IDs, idempotency keys, and source/proposal versions uniquely or appropriately indexed.
- Seed data must be deterministic and clearly demo-only. Reset scripts must refuse to run against a non-demo/non-test database unless the operator explicitly confirms a safe procedure.
- Test migrations against a disposable database and verify both upgrade and downgrade where supported.
