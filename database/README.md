# PRIP Database Module

## Ownership
- Database initialization scripts, schema DDL, and SQLite demo database storage.
- Deterministic demo seed fixtures (`seeds/`):
  - Authorized catalog product: StrideX Runner (`SX-001`, expected $100.00 USD).
  - Clean comparison fixtures and edge-case test records.
- Deterministic database reset script ensuring clean state before test runs or demo presentations.

## Boundary Rules
- Reset scripts must refuse to execute on non-demo / production databases.
- Real customer data or live payment tokens must NEVER be stored here.
