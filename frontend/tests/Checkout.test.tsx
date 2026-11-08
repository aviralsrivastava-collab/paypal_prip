import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Checkout } from '../src/pages/Checkout';
import { ApiClient } from '../src/services/api';
import { Order, PaymentCapture, PreflightResult, ReconciliationResult } from '../src/types';

describe('Checkout Page Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockBlockedPreflight: PreflightResult = {
    passed: false,
    sku: 'SX-001',
    catalog_price: '100.00',
    storefront_price: '120.00',
    currency: 'USD',
    scan_id: 1,
    scan_state: 'ISSUE_DETECTED',
    blocking_reasons: [
      'Price discrepancy detected: Catalog USD 100.00 vs Storefront USD 120.00. Checkout blocked until synchronized.',
    ],
    message: 'Price discrepancy detected. Checkout blocked.',
  };

  const mockCleanPreflight: PreflightResult = {
    passed: true,
    sku: 'SX-001',
    catalog_price: '100.00',
    storefront_price: '100.00',
    currency: 'USD',
    scan_id: 2,
    scan_state: 'VERIFIED_NO_ISSUE',
    blocking_reasons: [],
    message: 'Preflight passed. Price verified clean.',
  };

  const mockCreatedOrder: Order = {
    id: 1,
    order_id: 'prip_ord_12345678',
    paypal_order_id: 'MOCK-ORD-ABC12345',
    sku: 'SX-001',
    unit_price: '100.00',
    currency: 'USD',
    quantity: 1,
    total_amount: '100.00',
    order_status: 'CREATED',
    payment_status: 'PENDING',
    preflight_passed: true,
    approve_url: 'https://www.sandbox.paypal.com/checkoutnow?token=MOCK-ORD-ABC12345',
    created_at: '2026-11-07T12:00:00Z',
    updated_at: '2026-11-07T12:00:00Z',
  };

  const mockCaptureResult: PaymentCapture = {
    capture_id: 'CAP-MOCK-998877',
    order_id: 'prip_ord_12345678',
    paypal_order_id: 'MOCK-ORD-ABC12345',
    status: 'COMPLETED',
    amount: '100.00',
    currency: 'USD',
    fee_amount: '3.49',
    net_amount: '96.51',
    reconciliation_status: 'NOT_NEEDED',
    created_at: '2026-11-07T12:01:00Z',
  };

  const mockTimeoutCapture: PaymentCapture = {
    capture_id: null,
    order_id: 'prip_ord_12345678',
    paypal_order_id: 'MOCK-ORD-ABC12345',
    status: 'UNKNOWN',
    amount: '100.00',
    currency: 'USD',
    fee_amount: null,
    net_amount: null,
    reconciliation_status: 'RECONCILIATION_REQUIRED',
    error_message: 'Capture timed out. Ambiguous outcome persisted as UNKNOWN.',
    created_at: '2026-11-07T12:01:00Z',
  };

  const mockReconcileResult: ReconciliationResult = {
    order_id: 'prip_ord_12345678',
    paypal_order_id: 'MOCK-ORD-ABC12345',
    order_status: 'COMPLETED',
    payment_status: 'CAPTURED',
    reconciliation_status: 'RECONCILED',
    message: 'Reconciliation resolved status to CAPTURED based on PayPal records.',
  };

  it('renders PayPal Sandbox notice and preflight card', async () => {
    vi.spyOn(ApiClient, 'checkPreflight').mockResolvedValue(mockBlockedPreflight);

    render(<Checkout />);

    expect(screen.getByText(/PayPal Sandbox Checkout Demo/i)).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(/PayPal Sandbox Environment/i);
    expect(screen.getByText(/1\. Checkout Preflight Discrepancy Gate/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/Checkout Blocked: Price Mismatch Detected/i)).toBeInTheDocument();
    });
  });

  it('disables checkout button when preflight is blocked', async () => {
    vi.spyOn(ApiClient, 'checkPreflight').mockResolvedValue(mockBlockedPreflight);

    render(<Checkout />);

    await waitFor(() => {
      expect(screen.getByText(/Checkout Blocked: Price Mismatch Detected/i)).toBeInTheDocument();
    });

    const payButton = screen.getByRole('button', { name: /Pay with PayPal Sandbox/i });
    expect(payButton).toBeDisabled();
  });

  it('enables checkout button when preflight is clean and verified', async () => {
    vi.spyOn(ApiClient, 'checkPreflight').mockResolvedValue(mockCleanPreflight);

    render(<Checkout />);

    await waitFor(() => {
      expect(screen.getByText(/Preflight Verified: Ground-Truth Price Synchronized/i)).toBeInTheDocument();
    });

    const payButton = screen.getByRole('button', { name: /Pay with PayPal Sandbox/i });
    expect(payButton).not.toBeDisabled();
  });

  it('creates order and transitions to capture section', async () => {
    vi.spyOn(ApiClient, 'checkPreflight').mockResolvedValue(mockCleanPreflight);
    vi.spyOn(ApiClient, 'createOrder').mockResolvedValue(mockCreatedOrder);

    render(<Checkout />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Pay with PayPal Sandbox/i })).not.toBeDisabled();
    });

    fireEvent.click(screen.getByRole('button', { name: /Pay with PayPal Sandbox/i }));

    await waitFor(() => {
      expect(screen.getByText(/Local Order ID:/i)).toBeInTheDocument();
      expect(screen.getByText(/prip_ord_12345678/i)).toBeInTheDocument();
      expect(screen.getByText(/3\. Server-Side Capture & Verification/i)).toBeInTheDocument();
    });
  });

  it('executes server-side capture and renders fee breakdown', async () => {
    vi.spyOn(ApiClient, 'checkPreflight').mockResolvedValue(mockCleanPreflight);
    vi.spyOn(ApiClient, 'createOrder').mockResolvedValue(mockCreatedOrder);
    vi.spyOn(ApiClient, 'captureOrder').mockResolvedValue(mockCaptureResult);
    vi.spyOn(ApiClient, 'getOrder').mockResolvedValue({
      ...mockCreatedOrder,
      order_status: 'COMPLETED',
      payment_status: 'CAPTURED',
    });

    render(<Checkout />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Pay with PayPal Sandbox/i })).not.toBeDisabled();
    });

    fireEvent.click(screen.getByRole('button', { name: /Pay with PayPal Sandbox/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Execute Server-Side Capture/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Execute Server-Side Capture/i }));

    await waitFor(() => {
      expect(screen.getByText(/Capture Receipt/i)).toBeInTheDocument();
      expect(screen.getByText(/CAP-MOCK-998877/i)).toBeInTheDocument();
      expect(screen.getByText(/PayPal Fee:/i)).toBeInTheDocument();
      expect(screen.getByText(/Net Received:/i)).toBeInTheDocument();
    });
  });

  it('handles capture timeout, transitions to UNKNOWN, and allows reconciliation', async () => {
    vi.spyOn(ApiClient, 'checkPreflight').mockResolvedValue(mockCleanPreflight);
    vi.spyOn(ApiClient, 'createOrder').mockResolvedValue(mockCreatedOrder);
    vi.spyOn(ApiClient, 'captureOrder').mockResolvedValue(mockTimeoutCapture);
    vi.spyOn(ApiClient, 'getOrder').mockResolvedValue({
      ...mockCreatedOrder,
      payment_status: 'UNKNOWN',
    });
    vi.spyOn(ApiClient, 'reconcileOrder').mockResolvedValue(mockReconcileResult);

    render(<Checkout />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Pay with PayPal Sandbox/i })).not.toBeDisabled();
    });

    fireEvent.click(screen.getByRole('button', { name: /Pay with PayPal Sandbox/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Execute Server-Side Capture/i })).toBeInTheDocument();
    });

    // Execute capture that times out
    fireEvent.click(screen.getByRole('button', { name: /Execute Server-Side Capture/i }));

    await waitFor(() => {
      expect(screen.getByText(/Capture Receipt/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Reconcile with PayPal/i })).toBeInTheDocument();
    });

    // Click reconciliation
    fireEvent.click(screen.getByRole('button', { name: /Reconcile with PayPal/i }));

    await waitFor(() => {
      expect(screen.getByText(/Reconciliation resolved status to CAPTURED based on PayPal records/i)).toBeInTheDocument();
    });
  });
});
