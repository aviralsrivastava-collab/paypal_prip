"""
PRIP Backend Core Module
========================
Ownership:
- Environment configuration and settings loading (`pydantic-settings`).
- Security helpers (token hashing, constant-time comparisons).
- Application-wide exception definitions and structured error formats.
- Logging and telemetry configuration.

Boundary Restrictions:
- Must NOT import or depend on domain services, repositories, or API routes.
- Must remain pure infrastructure and configuration primitives.
"""
