"""
PRIP Backend Integrations Module
================================
Ownership:
- Dedicated infrastructure adapters for third-party and external services:
  - `paypal`: PayPal REST API client (OAuth token caching, Orders v2 create/capture, Webhook signature verification).
  - `llm`: Structured AI explanation client (prompt formatting, strict schema-enforced generation).
  - `storefront`: Controlled demo storefront extraction adapter.

Boundary Restrictions:
- Must NOT implement internal business authorization logic.
- Must NOT mutate internal database state directly (services coordinate state changes).
- PayPal client secrets and OAuth tokens must NEVER leave this backend module.
- AI adapter must NOT be given database access, payment execution, or correction mutation tools.
"""
