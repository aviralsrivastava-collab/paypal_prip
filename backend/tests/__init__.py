"""
PRIP Backend Tests Package
==========================
Ownership:
- Unit tests for policies, schemas, and core utilities.
- Integration tests for repositories, services, and API endpoints using test database fixtures.
- Mocked adapter tests for PayPal and LLM integration boundaries.

Boundary Restrictions:
- Must NOT make outbound network calls during regular unit testing.
- Must run deterministically against disposable local test fixtures.
"""
