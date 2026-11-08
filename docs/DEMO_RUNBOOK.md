# PRIP 4–5 Minute Demo Runbook

## Preconditions

- Resettable demo dataset is loaded.
- Catalog shows StrideX Runner, SKU `SX-001`, USD 100.00, available.
- Controlled storefront shows same product/variant/context at USD 120.00.
- No promotion is active in the seeded mismatch scenario.
- Backend, frontend, database, and controlled storefront are running.
- PayPal Sandbox credentials and webhook configuration are set server-side; never show secrets.
- A Sandbox buyer account is available and its credentials are handled privately.
- Demo UI visibly labels Sandbox.

## Run of show

| Time | Action | Judge takeaway |
|---|---|---|
| 0:00–0:30 | Show product catalog: StrideX Runner, `SX-001`, USD 100 | Merchant-authorized source of truth |
| 0:30–1:10 | Open controlled storefront at USD 120 and run inspection | Comparable, evidence-backed mismatch |
| 1:10–1:50 | Show issue evidence and AI explanation | AI explains; it does not make changes |
| 1:50–2:30 | Merchant approves; apply correction; reinspect | Merchant controls change; PRIP verifies result |
| 2:30–3:00 | Run checkout preflight and show current amount | Checkout uses current validated product facts |
| 3:00–4:15 | Complete PayPal Sandbox buyer approval and capture | Real end-to-end Sandbox payment lifecycle |
| 4:15–5:00 | Show capture ID, verified webhook event, audit timeline | Outcome is verifiable; Sandbox limitations remain clear |

## Closing statement

"PRIP detected a verified product-page mismatch against a merchant-authorized catalog, presented supporting evidence, recorded a merchant-approved correction, verified the updated storefront, and completed a PayPal Sandbox checkout with a confirmed capture. This prototype demonstrates the workflow on a controlled storefront; it does not claim universal site coverage or recovered real-world revenue."

## Failure fallback

- If inspection is blocked, show `BLOCKED_UNKNOWN`; do not relabel it as a mismatch.
- If correction application or reinspection fails, show the honest failure/unknown state; do not claim resolved.
- If PayPal capture is ambiguous, show `UNKNOWN` and explain reconciliation; do not retry blindly or claim captured.
- If webhook delivery is delayed, show provider-confirmed payment state separately from webhook processing status; do not fabricate webhook confirmation.
- Never switch to a mock and describe it as a real Sandbox event. Label mocks explicitly.

## Reset

Use only the documented demo reset command after confirming the configured database is a disposable demo database. Do not run destructive reset against a shared or production database.
