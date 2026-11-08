# PRIP Data Model Contract

This is a logical model, not a claim that these tables already exist. Inspect the actual database and migration history before implementing. Choose concrete column types and naming consistently with the selected database/ORM.

## Entities

### products
Merchant-authorized catalog record. Suggested attributes: internal ID, SKU, title, selected variant identity, expected price as fixed-precision decimal, ISO currency, availability, configured market/customer context, price basis, promotion context, selected attributes, source version, created/updated timestamps.

### storefront_scans
One inspection attempt. Attributes: product ID, variant ID, source version, URL/controlled page identifier, inspected timestamp, inspection method, parser/version metadata, comparison context, result state, failure reason/category, correlation ID.

### evidence_items
Evidence associated with a scan. Attributes: scan ID, evidence type, field name, normalized value, raw/displayed value where safe, source locator/reference, observed timestamp, extraction metadata, content hash where useful. Avoid storing unnecessary full page content or personal data.

### issues
A verified issue or reviewable finding. Attributes: product ID, scan ID, issue category, state, expected/observed normalized values, evidence references, context checks, source/proposal version, created/resolved timestamps. Unknown/not-tested outcomes should remain scan states, not be fabricated as verified issues.

### merchant_approvals
Decision record bound to exact issue/proposal version. Attributes: issue ID, proposal ID/version, authenticated actor ID, decision (`APPROVED`/`REJECTED`), reason, timestamp, request/correlation ID.

### correction_actions
Correction proposal/application record. Attributes: issue ID, field allowlisted, proposed value, currency if monetary, before value, after value, source version, status, approval reference, applied timestamp, adapter result, verification scan ID/result. Never treat approval as applied or verified.

### inventory_reservations
PRIP-local demo inventory reservation. Attributes: product/variant, quantity, expiry, state, checkout attempt ID. Explicitly does not represent external merchant stock locking.

### payment_orders
Local payment attempt and PayPal order mapping. Attributes: local ID, reservation ID, environment, provider, PayPal order ID, expected amount/currency, idempotency key, state, timestamps, last reconciliation result. Enforce unique provider order IDs within environment.

### payment_captures
Capture records. Attributes: payment order ID, PayPal capture ID, amount/currency, provider status, raw/normalized reference as appropriate, confirmed timestamp. Enforce uniqueness for provider capture IDs within environment.

### webhook_events
Provider event inbox. Attributes: provider, environment, provider event ID, event type, received timestamp, signature verification result, processing state, payload hash/reference, processed timestamp/error. Enforce unique event ID within environment/provider. Store payload only as needed and protect it.

### audit_events
Append-only application audit record. Attributes: actor type/ID, action, entity type/ID, timestamp, correlation ID, before/after references or safe snapshots, outcome, reason. Never include secrets or card data.

## Data integrity rules

- Use fixed-precision decimal/numeric for money; pair amount with ISO currency.
- Use explicit version numbers/ETags or equivalent optimistic concurrency for source records, issues, and correction proposals.
- Use database uniqueness and foreign keys for critical relationships.
- Use transactions for correction application + audit and payment-state persistence + related audit where consistency requires it.
- Webhook event processing must be idempotent.
- Preserve evidence/audit traceability; do not silently overwrite historical scan observations.
- Keep demo seed/reset operations deterministic and restricted to demo/test environments.
