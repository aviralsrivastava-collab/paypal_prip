# PRIP PayPal Sandbox Verification & Isolation Guide

## 1. Non-Negotiable Sandbox Policy

PRIP is an MVP designed strictly for merchant decision intelligence and demonstration of discrepancy remediation.
**This application does NOT authorize or support PayPal Live payments or real-money processing.**

### Fail-Closed Safeguard:
In `backend/core/config.py`:
```python
if self.paypal_environment.lower() != "sandbox":
    raise ValueError(
        "PRIP MVP strictly rejects PayPal Live environments. "
        "paypal_environment must be configured as 'sandbox'."
    )
```
Any attempt to deploy or configure PRIP with `PAYPAL_ENVIRONMENT=live` causes the application process to fail closed with a fatal startup error.

---

## 2. Sandbox Verification Workflow

### Step 1: Provisioning Sandbox Accounts
1. Log in to the [PayPal Developer Dashboard](https://developer.paypal.com/dashboard/).
2. Navigate to **Testing Tools > Sandbox Accounts**.
3. Create two accounts:
   - **Business Account**: Merchant receiver account (connects to PRIP).
   - **Personal Account**: Buyer account with test card and balance.

### Step 2: Registering Orders v2 Application
1. In **Apps & Credentials**, create a new REST API app in **Sandbox** mode.
2. Note the `Client ID` and `Secret`.
3. Set in `.env`:
   ```bash
   PAYPAL_CLIENT_ID=sb-client-id...
   PAYPAL_CLIENT_SECRET=sb-client-secret...
   PAYPAL_ENVIRONMENT=sandbox
   ```

### Step 3: Webhook Registration
1. In the app settings, add a webhook targeting:
   `https://<YOUR_DOMAIN>/api/webhooks/paypal`
2. Subscribe to events:
   - `CHECKOUT.ORDER.APPROVED`
   - `PAYMENT.CAPTURE.COMPLETED`
   - `PAYMENT.CAPTURE.DENIED`
3. Copy the generated `Webhook ID` to `PAYPAL_WEBHOOK_ID`.

---

## 3. Discrepancy Gate Verification

1. When a discrepancy exists (e.g. Catalog USD 100.00 vs Storefront USD 120.00):
   - Initiating checkout `POST /api/checkout/orders` is blocked by preflight:
     `{"detail": "Checkout blocked: UNRESOLVED_DISCREPANCY: Storefront price (120.00 USD) does not match catalog price (100.00 USD)."}`
2. After merchant approves proposal and executes correction:
   - Storefront price synchronizes to USD 100.00.
   - Preflight passes.
   - Order creation succeeds and returns PayPal Sandbox approval URL.

---

## 4. Sandbox Integrity Statement

- PayPal Sandbox captures represent simulated test transactions only.
- Under no circumstances should test transaction volumes, captured amounts, or fees in sandbox be claimed as recovered merchant revenue or proven causal conversion lift.
