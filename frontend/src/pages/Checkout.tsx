import React, { useEffect, useState } from 'react';
import { ApiClient } from '../services/api';
import { Order, PaymentCapture, PreflightResult } from '../types';

export const Checkout: React.FC = () => {
  const [sku, setSku] = useState('SX-001');
  const [preflight, setPreflight] = useState<PreflightResult | null>(null);
  const [loadingPreflight, setLoadingPreflight] = useState(false);
  const [preflightError, setPreflightError] = useState<string | null>(null);

  const [activeOrder, setActiveOrder] = useState<Order | null>(null);
  const [creatingOrder, setCreatingOrder] = useState(false);
  const [orderError, setOrderError] = useState<string | null>(null);

  const [captureResult, setCaptureResult] = useState<PaymentCapture | null>(null);
  const [capturing, setCapturing] = useState(false);
  const [captureError, setCaptureError] = useState<string | null>(null);

  const [simulateTimeout, setSimulateTimeout] = useState(false);
  const [simulateDecline, setSimulateDecline] = useState(false);

  const [reconciling, setReconciling] = useState(false);
  const [reconcileMessage, setReconcileMessage] = useState<string | null>(null);

  // Run preflight check on mount or when sku changes
  const runPreflight = async (targetSku = sku) => {
    setLoadingPreflight(true);
    setPreflightError(null);
    setCaptureResult(null);
    setActiveOrder(null);
    setReconcileMessage(null);
    try {
      const res = await ApiClient.checkPreflight(targetSku);
      setPreflight(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Preflight check failed';
      setPreflightError(msg);
    } finally {
      setLoadingPreflight(false);
    }
  };

  useEffect(() => {
    runPreflight();
  }, []);

  const handleCreateOrder = async () => {
    setCreatingOrder(true);
    setOrderError(null);
    try {
      const order = await ApiClient.createOrder(sku, 1);
      setActiveOrder(order);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create order';
      setOrderError(msg);
    } finally {
      setCreatingOrder(false);
    }
  };

  const handleCaptureOrder = async () => {
    if (!activeOrder) return;
    setCapturing(true);
    setCaptureError(null);
    setReconcileMessage(null);
    try {
      const capture = await ApiClient.captureOrder(activeOrder.order_id, {
        simulateTimeout,
        simulateDecline,
      });
      setCaptureResult(capture);
      // Refresh order state
      const updatedOrder = await ApiClient.getOrder(activeOrder.order_id);
      setActiveOrder(updatedOrder);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to capture payment';
      setCaptureError(msg);
    } finally {
      setCapturing(false);
    }
  };

  const handleReconcileOrder = async () => {
    if (!activeOrder) return;
    setReconciling(true);
    setReconcileMessage(null);
    try {
      const result = await ApiClient.reconcileOrder(activeOrder.order_id);
      setReconcileMessage(result.message);
      // Refresh order and capture state
      const updatedOrder = await ApiClient.getOrder(activeOrder.order_id);
      setActiveOrder(updatedOrder);
      if (captureResult) {
        setCaptureResult({
          ...captureResult,
          status: result.payment_status,
          reconciliation_status: result.reconciliation_status,
        });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to reconcile payment';
      setCaptureError(msg);
    } finally {
      setReconciling(false);
    }
  };

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '2rem', fontFamily: 'system-ui, sans-serif' }}>
      <h2>PayPal Sandbox Checkout Demo</h2>
      <p style={{ color: '#555' }}>
        Verifies discrepancy gating, server-side Orders v2 capture, timeout reconciliation, and audit integrity.
      </p>

      {/* Mandatory Sandbox Invariant Notice */}
      <div
        role="alert"
        style={{
          padding: '1rem',
          border: '1px solid #ffd700',
          backgroundColor: '#fffdf0',
          borderRadius: '6px',
          marginBottom: '1.5rem',
        }}
      >
        <p style={{ margin: 0 }}>
          <strong>PayPal Sandbox Environment:</strong> Sandbox captures are demo simulations and do not represent real
          commercial revenue or conversion lift. Live credentials are never used.
        </p>
      </div>

      {/* Preflight Check Card */}
      <div
        style={{
          border: '1px solid #e0e0e0',
          borderRadius: '8px',
          padding: '1.5rem',
          backgroundColor: '#ffffff',
          boxShadow: '0 2px 4px rgba(0,0,0,0.05)',
          marginBottom: '1.5rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0 }}>1. Checkout Preflight Discrepancy Gate</h3>
          <button
            onClick={() => runPreflight()}
            disabled={loadingPreflight}
            style={{
              padding: '0.4rem 0.8rem',
              backgroundColor: '#0070ba',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            {loadingPreflight ? 'Checking...' : 'Re-check Preflight'}
          </button>
        </div>

        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.9rem', color: '#666', marginBottom: '0.2rem' }}>
            Product SKU:
          </label>
          <input
            type="text"
            value={sku}
            onChange={(e) => setSku(e.target.value)}
            style={{ padding: '0.4rem', border: '1px solid #ccc', borderRadius: '4px', width: '200px' }}
          />
        </div>

        {preflightError && (
          <div style={{ padding: '0.8rem', backgroundColor: '#ffebee', color: '#c62828', borderRadius: '4px', marginBottom: '1rem' }}>
            {preflightError}
          </div>
        )}

        {preflight && (
          <div>
            <div style={{ display: 'flex', gap: '2rem', marginBottom: '1rem', fontSize: '0.95rem' }}>
              <div>
                <strong>Catalog Ground-Truth:</strong>{' '}
                <span>{preflight.catalog_price ? `${preflight.currency} ${preflight.catalog_price}` : 'Not found'}</span>
              </div>
              <div>
                <strong>Controlled Storefront:</strong>{' '}
                <span>{preflight.storefront_price ? `${preflight.currency} ${preflight.storefront_price}` : 'Not found'}</span>
              </div>
              {preflight.scan_state && (
                <div>
                  <strong>Latest Inspection:</strong>{' '}
                  <span
                    style={{
                      fontWeight: 'bold',
                      color: preflight.scan_state === 'VERIFIED_NO_ISSUE' ? '#2e7d32' : '#c62828',
                    }}
                  >
                    {preflight.scan_state}
                  </span>
                </div>
              )}
            </div>

            {preflight.passed ? (
              <div
                style={{
                  padding: '1rem',
                  backgroundColor: '#e8f5e9',
                  border: '1px solid #a5d6a7',
                  borderRadius: '6px',
                  color: '#2e7d32',
                }}
              >
                <strong>Preflight Verified: Ground-Truth Price Synchronized</strong>
                <p style={{ margin: '0.5rem 0 0', fontSize: '0.9rem' }}>
                  Catalog and Storefront prices match ({preflight.currency} {preflight.catalog_price}). Checkout is
                  permitted.
                </p>
              </div>
            ) : (
              <div
                style={{
                  padding: '1rem',
                  backgroundColor: '#ffebee',
                  border: '1px solid #ef9a9a',
                  borderRadius: '6px',
                  color: '#c62828',
                }}
              >
                <strong>Checkout Blocked: Price Mismatch Detected</strong>
                <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.2rem', fontSize: '0.9rem' }}>
                  {preflight.blocking_reasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
                <p style={{ margin: '0.5rem 0 0', fontSize: '0.85rem', color: '#555' }}>
                  Tip: Use the <strong>Corrections</strong> dashboard to review, approve, and apply price synchronization
                  before checkout.
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Order Creation & Approval Card */}
      <div
        style={{
          border: '1px solid #e0e0e0',
          borderRadius: '8px',
          padding: '1.5rem',
          backgroundColor: '#ffffff',
          boxShadow: '0 2px 4px rgba(0,0,0,0.05)',
          marginBottom: '1.5rem',
          opacity: preflight?.passed ? 1 : 0.6,
        }}
      >
        <h3 style={{ margin: '0 0 1rem 0' }}>2. PayPal Sandbox Order</h3>

        {orderError && (
          <div style={{ padding: '0.8rem', backgroundColor: '#ffebee', color: '#c62828', borderRadius: '4px', marginBottom: '1rem' }}>
            {orderError}
          </div>
        )}

        {!activeOrder ? (
          <div>
            <p style={{ fontSize: '0.9rem', color: '#666', marginBottom: '1rem' }}>
              Creates an order using PayPal Orders v2 (intent: CAPTURE) and reserves demo inventory.
            </p>
            <button
              onClick={handleCreateOrder}
              disabled={!preflight?.passed || creatingOrder}
              style={{
                padding: '0.6rem 1.2rem',
                backgroundColor: preflight?.passed ? '#0070ba' : '#cccccc',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: preflight?.passed ? 'pointer' : 'not-allowed',
                fontWeight: 'bold',
              }}
            >
              {creatingOrder ? 'Creating Order...' : 'Pay with PayPal Sandbox'}
            </button>
          </div>
        ) : (
          <div style={{ backgroundColor: '#f9f9f9', padding: '1rem', borderRadius: '6px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.8rem', fontSize: '0.9rem' }}>
              <div>
                <strong>Local Order ID:</strong> {activeOrder.order_id}
              </div>
              <div>
                <strong>PayPal Order ID:</strong> {activeOrder.paypal_order_id || 'N/A'}
              </div>
              <div>
                <strong>Total Amount:</strong> {activeOrder.currency} {activeOrder.total_amount}
              </div>
              <div>
                <strong>Order Status:</strong>{' '}
                <span style={{ fontWeight: 'bold', color: activeOrder.order_status === 'COMPLETED' ? '#2e7d32' : '#0070ba' }}>
                  {activeOrder.order_status}
                </span>
              </div>
              <div>
                <strong>Payment Status:</strong>{' '}
                <span
                  style={{
                    fontWeight: 'bold',
                    color:
                      activeOrder.payment_status === 'CAPTURED'
                        ? '#2e7d32'
                        : activeOrder.payment_status === 'UNKNOWN'
                        ? '#f57c00'
                        : '#0070ba',
                  }}
                >
                  {activeOrder.payment_status}
                </span>
              </div>
            </div>

            {activeOrder.approve_url && (
              <div style={{ marginTop: '0.8rem', fontSize: '0.85rem', color: '#666' }}>
                <strong>Sandbox Redirect:</strong> <code>{activeOrder.approve_url}</code>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Server-Side Capture Card */}
      {activeOrder && (
        <div
          style={{
            border: '1px solid #e0e0e0',
            borderRadius: '8px',
            padding: '1.5rem',
            backgroundColor: '#ffffff',
            boxShadow: '0 2px 4px rgba(0,0,0,0.05)',
            marginBottom: '1.5rem',
          }}
        >
          <h3 style={{ margin: '0 0 1rem 0' }}>3. Server-Side Capture & Verification</h3>

          {captureError && (
            <div style={{ padding: '0.8rem', backgroundColor: '#ffebee', color: '#c62828', borderRadius: '4px', marginBottom: '1rem' }}>
              {captureError}
            </div>
          )}

          {reconcileMessage && (
            <div style={{ padding: '0.8rem', backgroundColor: '#e3f2fd', color: '#1565c0', borderRadius: '4px', marginBottom: '1rem' }}>
              {reconcileMessage}
            </div>
          )}

          {/* Simulation Controls for Evaluation */}
          <div
            style={{
              padding: '0.8rem',
              backgroundColor: '#f5f5f5',
              borderRadius: '6px',
              marginBottom: '1rem',
              fontSize: '0.85rem',
            }}
          >
            <strong>Demo Simulation Toggles:</strong>
            <div style={{ display: 'flex', gap: '1.5rem', marginTop: '0.4rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={simulateTimeout}
                  onChange={(e) => setSimulateTimeout(e.target.checked)}
                />
                Simulate Capture Timeout (UNKNOWN state)
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={simulateDecline}
                  onChange={(e) => setSimulateDecline(e.target.checked)}
                />
                Simulate Buyer Decline
              </label>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
            <button
              onClick={handleCaptureOrder}
              disabled={capturing || activeOrder.payment_status === 'CAPTURED'}
              style={{
                padding: '0.6rem 1.2rem',
                backgroundColor: activeOrder.payment_status === 'CAPTURED' ? '#4caf50' : '#0070ba',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: activeOrder.payment_status === 'CAPTURED' ? 'default' : 'pointer',
                fontWeight: 'bold',
              }}
            >
              {capturing
                ? 'Capturing...'
                : activeOrder.payment_status === 'CAPTURED'
                ? 'Captured Successfully'
                : 'Execute Server-Side Capture'}
            </button>

            {/* Reconciliation button when UNKNOWN state occurs */}
            {(activeOrder.payment_status === 'UNKNOWN' ||
              captureResult?.reconciliation_status === 'RECONCILIATION_REQUIRED') && (
              <button
                onClick={handleReconcileOrder}
                disabled={reconciling}
                style={{
                  padding: '0.6rem 1.2rem',
                  backgroundColor: '#f57c00',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontWeight: 'bold',
                }}
              >
                {reconciling ? 'Reconciling...' : 'Reconcile with PayPal'}
              </button>
            )}
          </div>

          {/* Capture Result Details */}
          {captureResult && (
            <div
              style={{
                marginTop: '1.5rem',
                padding: '1rem',
                backgroundColor:
                  captureResult.status === 'COMPLETED'
                    ? '#e8f5e9'
                    : captureResult.status === 'UNKNOWN'
                    ? '#fff8e1'
                    : '#ffebee',
                border:
                  captureResult.status === 'COMPLETED'
                    ? '1px solid #a5d6a7'
                    : captureResult.status === 'UNKNOWN'
                    ? '1px solid #ffe082'
                    : '1px solid #ef9a9a',
                borderRadius: '6px',
              }}
            >
              <h4 style={{ margin: '0 0 0.5rem 0' }}>Capture Receipt</h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.5rem', fontSize: '0.9rem' }}>
                <div>
                  <strong>Capture ID:</strong> {captureResult.capture_id || 'N/A'}
                </div>
                <div>
                  <strong>Capture Status:</strong> {captureResult.status}
                </div>
                <div>
                  <strong>Gross Amount:</strong> {captureResult.currency} {captureResult.amount}
                </div>
                {captureResult.fee_amount && (
                  <div>
                    <strong>PayPal Fee:</strong> {captureResult.currency} {captureResult.fee_amount}
                  </div>
                )}
                {captureResult.net_amount && (
                  <div>
                    <strong>Net Received:</strong> {captureResult.currency} {captureResult.net_amount}
                  </div>
                )}
                <div>
                  <strong>Reconciliation:</strong> {captureResult.reconciliation_status}
                </div>
              </div>
              {captureResult.error_message && (
                <p style={{ margin: '0.5rem 0 0', color: '#c62828', fontSize: '0.85rem' }}>
                  <strong>Note:</strong> {captureResult.error_message}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
