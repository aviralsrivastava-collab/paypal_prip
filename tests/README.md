# PRIP End-to-End & Cross-Module Tests

## Ownership
- Repository-level end-to-end integration and smoke test suites.
- Automated verification of the full vertical slice:
  1. Inspect seeded product StrideX Runner (`SX-001`, catalog $100 vs storefront $120).
  2. Verify 4-state engine returns `ISSUE_DETECTED` with evidence.
  3. Verify structured AI diagnosis returns valid schema proposal.
  4. Execute merchant approval and apply correction to demo storefront.
  5. Verify post-correction reinspection returns `VERIFIED_NO_ISSUE`.
  6. Execute checkout preflight and verify current price and availability.
  7. Exercise PayPal Sandbox Orders v2 lifecycle with server capture and webhook handling.

## Boundary Rules
- Real Sandbox credentials must be opt-in via environment variables.
- Standard continuous integration runs must use mock/fake external adapters without live internet dependency.
