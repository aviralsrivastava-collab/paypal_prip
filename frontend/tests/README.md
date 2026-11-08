# Frontend Tests Module

## Ownership
- Unit tests for utility functions, custom hooks, and presentational components.
- Integration tests for feature workflows and page views using mock API servers (MSW / Vitest).
- Visual and accessibility compliance tests.

## Boundary Restrictions
- Must not make live network calls during automated testing.
- Must test all 4 inspection states and explicit error boundaries.
