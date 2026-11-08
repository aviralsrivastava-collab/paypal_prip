import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Operations } from '../src/pages/Operations';
import { ApiClient } from '../src/services/api';

describe('Operations Page Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockOverview = {
    system_status: 'HEALTHY' as const,
    webhook_counts: { PENDING: 0, PROCESSED: 12, DUPLICATE_IGNORED: 2 },
    dead_letter_count: 0,
    retryable_failure_count: 0,
    pending_reconciliations_count: 0,
    reconciliations_completed_count: 4,
    active_workers_count: 1,
    stale_workers_count: 0,
    workers: [
      {
        id: 1,
        worker_id: 'wh_worker_main',
        worker_type: 'WEBHOOK_PROCESSOR',
        status: 'ACTIVE',
        last_heartbeat_at: new Date().toISOString(),
        last_successful_run_at: new Date().toISOString(),
        age_seconds: 5.2,
      },
    ],
    recent_reconciliations: [
      {
        id: 1,
        order_id: 101,
        paypal_order_id: 'PAYPAL-ORD-101',
        paypal_capture_id: 'CAP-101',
        outcome: 'RESOLVED_CAPTURED',
        previous_payment_status: 'UNKNOWN',
        new_payment_status: 'CAPTURED',
        provider_status: 'COMPLETED',
        details: 'Reconciliation resolved status to CAPTURED based on PayPal records.',
        actor_id: 'MERCHANT',
        actor_type: 'MERCHANT',
        reconciled_at: new Date().toISOString(),
      },
    ],
    stuck_webhooks: [],
  };

  it('renders loading state initially', () => {
    vi.spyOn(ApiClient, 'getOperationsOverview').mockImplementation(() => new Promise(() => {}));
    vi.spyOn(ApiClient, 'getPendingReconciliations').mockImplementation(() => new Promise(() => {}));

    render(<Operations />);
    expect(screen.getByText(/loading operations dashboard/i)).toBeInTheDocument();
  });

  it('renders healthy operational status badge and metric cards', async () => {
    vi.spyOn(ApiClient, 'getOperationsOverview').mockResolvedValue(mockOverview);
    vi.spyOn(ApiClient, 'getPendingReconciliations').mockResolvedValue([]);

    render(<Operations />);

    await waitFor(() => {
      expect(screen.getByText(/operations & resilience dashboard/i)).toBeInTheDocument();
    });

    expect(screen.getByText('SYSTEM: HEALTHY')).toBeInTheDocument();
    expect(screen.getByText('WEBHOOK QUEUE')).toBeInTheDocument();
    expect(screen.getByText('DEAD-LETTER QUEUE')).toBeInTheDocument();
    expect(screen.getByText('PENDING RECONCILIATIONS')).toBeInTheDocument();
    expect(screen.getByText('BACKGROUND WORKERS')).toBeInTheDocument();
  });

  it('renders stuck webhooks and triggers replay action', async () => {
    const overviewWithStuck = {
      ...mockOverview,
      system_status: 'DEAD_LETTERED' as const,
      dead_letter_count: 1,
      stuck_webhooks: [
        {
          id: 42,
          paypal_event_id: 'WH-DEAD-LETTER-001',
          event_type: 'CHECKOUT.ORDER.APPROVED',
          resource_type: 'order',
          status: 'DEAD_LETTER',
          attempt_count: 5,
          max_attempts: 5,
          error_category: 'ORDER_NOT_FOUND',
          last_error: 'Order SX-999 not found in local catalog',
          last_attempt_at: new Date().toISOString(),
          next_retry_at: null,
          created_at: new Date().toISOString(),
        },
      ],
    };

    vi.spyOn(ApiClient, 'getOperationsOverview').mockResolvedValue(overviewWithStuck);
    vi.spyOn(ApiClient, 'getPendingReconciliations').mockResolvedValue([]);
    const replaySpy = vi.spyOn(ApiClient, 'replayWebhook').mockResolvedValue({
      id: 42,
      status: 'PROCESSED',
      message: 'Replay successful',
    });

    render(<Operations />);

    await waitFor(() => {
      expect(screen.getByText('WH-DEAD-LETTER-001')).toBeInTheDocument();
    });

    expect(screen.getByText('SYSTEM: DEAD-LETTERED EVENTS')).toBeInTheDocument();
    expect(screen.getByText('ORDER_NOT_FOUND')).toBeInTheDocument();

    const replayBtn = screen.getByRole('button', { name: /replay/i });
    fireEvent.click(replayBtn);

    await waitFor(() => {
      expect(replaySpy).toHaveBeenCalledWith(42);
    });
  });

  it('renders pending reconciliations and triggers reconciliation action', async () => {
    const overviewWithRecon = {
      ...mockOverview,
      system_status: 'RECONCILIATION_REQUIRED' as const,
      pending_reconciliations_count: 1,
    };

    const mockPendingOrder = {
      id: 1,
      order_id: 'prip_ord_test123',
      paypal_order_id: 'PAYPAL-ORD-TEST',
      sku: 'SX-001',
      unit_price: '100.00',
      currency: 'USD',
      quantity: 1,
      total_amount: '100.00',
      order_status: 'CREATED',
      payment_status: 'UNKNOWN',
      preflight_passed: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    vi.spyOn(ApiClient, 'getOperationsOverview').mockResolvedValue(overviewWithRecon);
    vi.spyOn(ApiClient, 'getPendingReconciliations').mockResolvedValue([mockPendingOrder]);
    const reconSpy = vi.spyOn(ApiClient, 'triggerReconciliation').mockResolvedValue({
      reconciled_count: 1,
      results: [],
    });

    render(<Operations />);

    await waitFor(() => {
      expect(screen.getByText('prip_ord_test123')).toBeInTheDocument();
    });

    expect(screen.getByText('SYSTEM: RECONCILIATION REQUIRED')).toBeInTheDocument();

    const reconBtn = screen.getByRole('button', { name: /reconcile now/i });
    fireEvent.click(reconBtn);

    await waitFor(() => {
      expect(reconSpy).toHaveBeenCalledWith('prip_ord_test123');
    });
  });
});
