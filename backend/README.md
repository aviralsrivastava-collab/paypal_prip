# PRIP Backend — PayPal Revenue Intelligence Platform

Modular monolith FastAPI backend for PRIP (PayPal Revenue Intelligence Platform).

## Architecture

- **`api/`**: HTTP endpoints, route handlers, and request/response coordination
- **`core/`**: Configuration, database session, logging, rate limiting, and security
- **`models/`**: SQLAlchemy ORM models
- **`schemas/`**: Pydantic models for validation and serialization
- **`services/`**: Business logic and workflow orchestration
- **`repositories/`**: Database persistence layer
- **`integrations/`**: PayPal API client, AI provider, and controlled storefront
- **`policies/`**: Deterministic verification, comparability, and bounds checking
- **`migrations/`**: Alembic database migrations
