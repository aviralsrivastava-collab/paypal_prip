# Frontend Types Module

## Ownership
- TypeScript type definitions, interfaces, and enums representing backend domain contracts:
  - Inspection states: `ISSUE_DETECTED`, `VERIFIED_NO_ISSUE`, `BLOCKED_UNKNOWN`, `NOT_TESTED`.
  - Payment states: `PENDING`, `APPROVED`, `CAPTURED`, `DECLINED`, `UNKNOWN`.
  - Correction statuses: `PROPOSED`, `APPROVED`, `REJECTED`, `APPLIED`, `VERIFIED`, `FAILED`.
  - Product, Scan, Evidence, Issue, and Audit models.

## Boundary Restrictions
- Must mirror the backend Pydantic schemas in `backend/schemas/` and `contracts/`.
- Must not invent undocumented fields or divergent status representations.
