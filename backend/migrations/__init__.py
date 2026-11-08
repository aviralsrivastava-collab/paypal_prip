"""
PRIP Backend Migrations Module
==============================
Ownership:
- Alembic database migration environment and versioned revision scripts.

Boundary Restrictions:
- Migration scripts must never be altered once applied in shared/production environments.
- Must execute deterministically and support rollback where feasible.
"""
