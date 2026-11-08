# Frontend Pages Module

## Ownership
- Top-level routable screen views:
  - `Dashboard`: Overview of discrepancies, verification states, and recent activity.
  - `CatalogView`: Authorized catalog source-of-truth records.
  - `InspectionView`: Detailed scan results, evidence breakdown, and AI explanations.
  - `CheckoutDemo`: Controlled storefront purchase flow demonstrating PayPal Sandbox.

## Boundary Restrictions
- Pages compose feature modules and presentational components.
- Must not perform direct database calls or bypass backend API services.
