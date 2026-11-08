# Frontend Features Module

## Ownership
- Domain-driven vertical feature slices:
  - `catalog`: Product list view, detail view, authority indicators.
  - `inspection`: Scan initiation, 4-state status indicators (`ISSUE_DETECTED`, `VERIFIED_NO_ISSUE`, `BLOCKED_UNKNOWN`, `NOT_TESTED`), evidence drawer.
  - `diagnosis`: AI explanation renderer, proposed correction diff viewer.
  - `correction`: Merchant approval/rejection action dialog, apply progress, reinspection status.
  - `checkout`: Preflight summary, PayPal Sandbox smart payment buttons, capture feedback.
  - `audit`: Chronological event timeline viewer.

## Boundary Restrictions
- Feature modules communicate with the backend exclusively via `frontend/services`.
- State must be scoped to the feature lifecycle.
