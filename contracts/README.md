# PRIP API Contracts and Specifications

## Ownership
- Formal API contracts, OpenAPI / Swagger specifications, and JSON Schemas defining data exchange formats across PRIP components.
- Canonical definitions for:
  - Inspection Scan Request/Response
  - Structured AI Diagnosis & Correction Proposal
  - Merchant Decision Payload
  - Checkout Preflight & Inventory Reservation
  - PayPal Orders v2 Request/Response Mappings
  - PayPal Webhook Event Schemas
  - Audit Event Format

## Boundary Rules
- Changes to files in this directory represent breaking contract changes and require cross-module review.
- Both `backend/schemas/` and `frontend/types/` must conform to these definitions.
