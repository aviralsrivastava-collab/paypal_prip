# Frontend Services Module

## Ownership
- Typed HTTP API client wrappers for backend endpoints (`/api/products`, `/api/scans`, `/api/issues`, `/api/corrections`, `/api/checkout`, `/api/payments`).
- Request serialization, response parsing, and error status handling.

## Boundary Restrictions
- Must communicate strictly via HTTP/HTTPS with the FastAPI backend.
- Must NEVER embed PayPal client secrets, webhook secrets, or private keys.
- Must treat all incoming data from external sources as untrusted until schema-validated.
