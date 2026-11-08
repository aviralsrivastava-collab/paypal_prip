---
name: database-migration
description: Designs and validates safe PRIP schema changes, migrations, seed data, and demo resets.
---
# Database Migration Skill

## Procedure
1. Inspect database engine, ORM, migration tool, schema, migration history, and environment configuration.
2. Identify data compatibility, uniqueness, foreign keys, transaction requirements, and rollback risks.
3. Use decimal-safe money fields with explicit currency.
4. Add uniqueness for provider order/capture/event identifiers and appropriate idempotency constraints.
5. Use expand-and-contract for destructive/renaming changes; never rewrite an applied migration.
6. Create deterministic demo seed data and safe reset safeguards.
7. Test upgrade and downgrade on disposable database; verify existing data compatibility where relevant.
8. Confirm reset cannot target production/shared database by default.
9. Document migration and operational steps.
10. Report exact DB and migration test evidence.

## Stop conditions
Do not run destructive migration/reset on an unknown or shared database. Ask for explicit confirmation and a verified backup/restore plan where data loss is possible.
