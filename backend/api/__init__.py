"""
PRIP Backend API Module
=======================
Ownership:
- HTTP route definitions (FastAPI routers).
- Request validation and parameter parsing.
- Authentication and authorization verification.
- Mapping domain results and exceptions to standard HTTP response schemas and status codes.

Boundary Restrictions:
- Must NOT implement business rules or domain policies.
- Must NOT execute direct SQL queries or manipulate database models.
- Must delegate all operations to application services.
"""
