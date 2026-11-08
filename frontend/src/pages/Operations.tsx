import React, { useEffect, useState, useCallback } from 'react';
import { ApiClient } from '../services/api';
import { OperationsOverview, Order } from '../types';

export const Operations: React.FC = () => {
  const [overview, setOverview] = useState<OperationsOverview | null>(null);
  const [pendingOrders, setPendingOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const fetchOperationalData = useCallback(async () => {
    try {
      const [overviewData, pendingData] = await Promise.all([
        ApiClient.getOperationsOverview(),
        ApiClient.getPendingReconciliations(),
      ]);
      setOverview(overviewData);
      setPendingOrders(pendingData);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch operational data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOperationalData();
    const interval = setInterval(fetchOperationalData, 10000);
    return () => clearInterval(interval);
  }, [fetchOperationalData]);

  const handleReplay = async (eventId: number) => {
    setSubmitting(true);
    setActionMessage(null);
    try {
      const res = await ApiClient.replayWebhook(eventId);
      setActionMessage(`Success: Replayed event ${res.id} (${res.status}). ${res.message}`);
      await fetchOperationalData();
    } catch (err: any) {
      setError(err.message || 'Replay action failed.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReconcile = async (orderId?: string) => {
    setSubmitting(true);
    setActionMessage(null);
    try {
      const res = await ApiClient.triggerReconciliation(orderId);
      setActionMessage(`Success: Reconciled ${res.reconciled_count} order(s).`);
      await fetchOperationalData();
    } catch (err: any) {
      setError(err.message || 'Reconciliation action failed.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleWorkerTick = async () => {
    setSubmitting(true);
    setActionMessage(null);
    try {
      const res = await ApiClient.triggerWorkerTick();
      setActionMessage(`Worker pass completed. Processed ${res.processed_events} event(s).`);
      await fetchOperationalData();
    } catch (err: any) {
      setError(err.message || 'Failed to trigger worker pass.');
    } finally {
      setSubmitting(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'HEALTHY':
        return { label: 'HEALTHY', bg: '#e6f4ea', color: '#137333', border: '#ceead6' };
      case 'DELAYED':
        return { label: 'DELAYED / RETRYING', bg: '#fef7e0', color: '#b06000', border: '#feefc3' };
      case 'REQUIRES_ATTENTION':
        return { label: 'REQUIRES ATTENTION', bg: '#fce8e6', color: '#c5221f', border: '#fad2cf' };
      case 'DEAD_LETTERED':
        return { label: 'DEAD-LETTERED EVENTS', bg: '#fce8e6', color: '#a50e0e', border: '#fad2cf' };
      case 'RECONCILIATION_REQUIRED':
        return { label: 'RECONCILIATION REQUIRED', bg: '#f3e8fd', color: '#8430ce', border: '#e9d2fd' };
      default:
        return { label: status, bg: '#f1f3f4', color: '#3c4043', border: '#dadce0' };
    }
  };

  if (loading && !overview) {
    return <div style={{ padding: '2rem' }}>Loading operations dashboard...</div>;
  }

  const badge = overview ? getStatusBadge(overview.system_status) : getStatusBadge('UNKNOWN');

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      {/* Title & Status Banner */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ margin: 0, color: '#003087' }}>Operations & Resilience Dashboard</h2>
          <p style={{ margin: '4px 0 0 0', color: '#555' }}>
            Durable background processing, worker leasing, payment reconciliation, and operator recovery.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <button
            onClick={handleWorkerTick}
            disabled={submitting}
            style={{
              padding: '6px 14px',
              backgroundColor: '#0070BA',
              color: '#ffffff',
              border: 'none',
              borderRadius: '4px',
              cursor: submitting ? 'not-allowed' : 'pointer',
              fontWeight: 500,
            }}
          >
            {submitting ? 'Running...' : 'Run Worker Pass'}
          </button>
          <div
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              backgroundColor: badge.bg,
              color: badge.color,
              border: `1px solid ${badge.border}`,
              fontWeight: 'bold',
              fontSize: '0.875rem',
            }}
          >
            SYSTEM: {badge.label}
          </div>
        </div>
      </div>

      {actionMessage && (
        <div style={{ padding: '10px 16px', backgroundColor: '#e6f4ea', color: '#137333', borderRadius: '4px', marginBottom: '1rem' }}>
          {actionMessage}
        </div>
      )}

      {error && (
        <div style={{ padding: '10px 16px', backgroundColor: '#fce8e6', color: '#c5221f', borderRadius: '4px', marginBottom: '1rem' }}>
          {error}
        </div>
      )}

      {/* Metric Summary Cards */}
      {overview && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
          <div style={{ padding: '1rem', border: '1px solid #ddd', borderRadius: '6px', backgroundColor: '#fff' }}>
            <div style={{ fontSize: '0.75rem', color: '#666', fontWeight: 600 }}>WEBHOOK QUEUE</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#003087', marginTop: '4px' }}>
              {(overview.webhook_counts['PENDING'] || 0) + (overview.webhook_counts['PROCESSING'] || 0)} Pending
            </div>
            <div style={{ fontSize: '0.75rem', color: '#555', marginTop: '4px' }}>
              {overview.webhook_counts['PROCESSED'] || 0} Processed · {overview.webhook_counts['DUPLICATE_IGNORED'] || 0} Deduplicated
            </div>
          </div>

          <div style={{ padding: '1rem', border: '1px solid #ddd', borderRadius: '6px', backgroundColor: '#fff' }}>
            <div style={{ fontSize: '0.75rem', color: '#666', fontWeight: 600 }}>DEAD-LETTER QUEUE</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: overview.dead_letter_count > 0 ? '#c5221f' : '#137333', marginTop: '4px' }}>
              {overview.dead_letter_count} Events
            </div>
            <div style={{ fontSize: '0.75rem', color: '#555', marginTop: '4px' }}>
              {overview.retryable_failure_count} in exponential backoff
            </div>
          </div>

          <div style={{ padding: '1rem', border: '1px solid #ddd', borderRadius: '6px', backgroundColor: '#fff' }}>
            <div style={{ fontSize: '0.75rem', color: '#666', fontWeight: 600 }}>PENDING RECONCILIATIONS</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: overview.pending_reconciliations_count > 0 ? '#8430ce' : '#137333', marginTop: '4px' }}>
              {overview.pending_reconciliations_count} Orders
            </div>
            <div style={{ fontSize: '0.75rem', color: '#555', marginTop: '4px' }}>
              {overview.reconciliations_completed_count} completed investigations
            </div>
          </div>

          <div style={{ padding: '1rem', border: '1px solid #ddd', borderRadius: '6px', backgroundColor: '#fff' }}>
            <div style={{ fontSize: '0.75rem', color: '#666', fontWeight: 600 }}>BACKGROUND WORKERS</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: overview.stale_workers_count > 0 ? '#b06000' : '#003087', marginTop: '4px' }}>
              {overview.active_workers_count} Active
            </div>
            <div style={{ fontSize: '0.75rem', color: '#555', marginTop: '4px' }}>
              {overview.stale_workers_count} Stale heartbeat(s)
            </div>
          </div>
        </div>
      )}

      {/* Pending Reconciliations Section */}
      <div style={{ marginBottom: '2.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <h3 style={{ margin: 0, color: '#333' }}>Ambiguous Captures Requiring Reconciliation</h3>
          {pendingOrders.length > 0 && (
            <button
              onClick={() => handleReconcile()}
              disabled={submitting}
              style={{
                padding: '4px 12px',
                backgroundColor: '#8430ce',
                color: '#fff',
                border: 'none',
                borderRadius: '4px',
                cursor: submitting ? 'not-allowed' : 'pointer',
                fontSize: '0.8rem',
              }}
            >
              Reconcile All Pending
            </button>
          )}
        </div>
        {pendingOrders.length === 0 ? (
          <div style={{ padding: '1rem', backgroundColor: '#f9f9f9', border: '1px solid #eee', borderRadius: '4px', color: '#666' }}>
            No ambiguous capture outcomes detected. All payment states are cleanly resolved.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', border: '1px solid #ddd' }}>
            <thead>
              <tr style={{ backgroundColor: '#f1f3f4', textAlign: 'left', fontSize: '0.8rem' }}>
                <th style={{ padding: '8px 12px' }}>Order ID</th>
                <th style={{ padding: '8px 12px' }}>PayPal Order ID</th>
                <th style={{ padding: '8px 12px' }}>SKU</th>
                <th style={{ padding: '8px 12px' }}>Amount</th>
                <th style={{ padding: '8px 12px' }}>Payment Status</th>
                <th style={{ padding: '8px 12px' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {pendingOrders.map((ord) => (
                <tr key={ord.id} style={{ borderBottom: '1px solid #eee', fontSize: '0.85rem' }}>
                  <td style={{ padding: '8px 12px', fontFamily: 'monospace' }}>{ord.order_id}</td>
                  <td style={{ padding: '8px 12px', fontFamily: 'monospace' }}>{ord.paypal_order_id || 'N/A'}</td>
                  <td style={{ padding: '8px 12px' }}>{ord.sku}</td>
                  <td style={{ padding: '8px 12px' }}>${ord.total_amount} {ord.currency}</td>
                  <td style={{ padding: '8px 12px', color: '#b06000', fontWeight: 'bold' }}>{ord.payment_status}</td>
                  <td style={{ padding: '8px 12px' }}>
                    <button
                      onClick={() => handleReconcile(ord.order_id)}
                      disabled={submitting}
                      style={{
                        padding: '4px 10px',
                        backgroundColor: '#0070BA',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: submitting ? 'not-allowed' : 'pointer',
                        fontSize: '0.75rem',
                      }}
                    >
                      Reconcile Now
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Stuck / Dead-Letter Webhook Events Section */}
      <div style={{ marginBottom: '2.5rem' }}>
        <h3 style={{ margin: '0 0 0.75rem 0', color: '#333' }}>Stuck & Dead-Letter Webhook Notifications</h3>
        {(!overview || overview.stuck_webhooks.length === 0) ? (
          <div style={{ padding: '1rem', backgroundColor: '#f9f9f9', border: '1px solid #eee', borderRadius: '4px', color: '#666' }}>
            No stuck or dead-letter webhook events. Worker queue is operating cleanly.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', border: '1px solid #ddd' }}>
            <thead>
              <tr style={{ backgroundColor: '#f1f3f4', textAlign: 'left', fontSize: '0.8rem' }}>
                <th style={{ padding: '8px 12px' }}>Event ID</th>
                <th style={{ padding: '8px 12px' }}>Event Type</th>
                <th style={{ padding: '8px 12px' }}>Status</th>
                <th style={{ padding: '8px 12px' }}>Attempts</th>
                <th style={{ padding: '8px 12px' }}>Category</th>
                <th style={{ padding: '8px 12px' }}>Last Error</th>
                <th style={{ padding: '8px 12px' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {overview.stuck_webhooks.map((wh) => (
                <tr key={wh.id} style={{ borderBottom: '1px solid #eee', fontSize: '0.85rem' }}>
                  <td style={{ padding: '8px 12px', fontFamily: 'monospace' }}>{wh.paypal_event_id}</td>
                  <td style={{ padding: '8px 12px' }}>{wh.event_type}</td>
                  <td style={{ padding: '8px 12px', fontWeight: 'bold', color: wh.status === 'DEAD_LETTER' ? '#c5221f' : '#b06000' }}>
                    {wh.status}
                  </td>
                  <td style={{ padding: '8px 12px' }}>{wh.attempt_count} / {wh.max_attempts}</td>
                  <td style={{ padding: '8px 12px' }}>{wh.error_category || 'N/A'}</td>
                  <td style={{ padding: '8px 12px', color: '#666', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {wh.last_error || 'N/A'}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    <button
                      onClick={() => handleReplay(wh.id)}
                      disabled={submitting}
                      style={{
                        padding: '4px 10px',
                        backgroundColor: '#d93025',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: submitting ? 'not-allowed' : 'pointer',
                        fontSize: '0.75rem',
                      }}
                    >
                      Replay
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Reconciliation History Section */}
      <div style={{ marginBottom: '2.5rem' }}>
        <h3 style={{ margin: '0 0 0.75rem 0', color: '#333' }}>Recent Authoritative Reconciliation History</h3>
        {(!overview || overview.recent_reconciliations.length === 0) ? (
          <div style={{ padding: '1rem', backgroundColor: '#f9f9f9', border: '1px solid #eee', borderRadius: '4px', color: '#666' }}>
            No reconciliation history recorded yet.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', border: '1px solid #ddd' }}>
            <thead>
              <tr style={{ backgroundColor: '#f1f3f4', textAlign: 'left', fontSize: '0.8rem' }}>
                <th style={{ padding: '8px 12px' }}>Time (UTC)</th>
                <th style={{ padding: '8px 12px' }}>Order ID</th>
                <th style={{ padding: '8px 12px' }}>Outcome</th>
                <th style={{ padding: '8px 12px' }}>Local Status Before / After</th>
                <th style={{ padding: '8px 12px' }}>PayPal Provider Status</th>
                <th style={{ padding: '8px 12px' }}>Details</th>
              </tr>
            </thead>
            <tbody>
              {overview.recent_reconciliations.map((rec) => (
                <tr key={rec.id} style={{ borderBottom: '1px solid #eee', fontSize: '0.85rem' }}>
                  <td style={{ padding: '8px 12px' }}>{new Date(rec.reconciled_at).toLocaleTimeString()}</td>
                  <td style={{ padding: '8px 12px', fontFamily: 'monospace' }}>#{rec.order_id}</td>
                  <td style={{ padding: '8px 12px', fontWeight: 'bold', color: rec.outcome.includes('CAPTURED') ? '#137333' : '#333' }}>
                    {rec.outcome}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    {rec.previous_payment_status} → {rec.new_payment_status}
                  </td>
                  <td style={{ padding: '8px 12px', fontWeight: 'bold' }}>{rec.provider_status}</td>
                  <td style={{ padding: '8px 12px', color: '#555' }}>{rec.details || 'N/A'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Background Workers Section */}
      <div>
        <h3 style={{ margin: '0 0 0.75rem 0', color: '#333' }}>Background Worker Heartbeats & Leases</h3>
        {(!overview || overview.workers.length === 0) ? (
          <div style={{ padding: '1rem', backgroundColor: '#f9f9f9', border: '1px solid #eee', borderRadius: '4px', color: '#666' }}>
            No background workers currently registered. Trigger a worker pass above to initialize worker lifecycle.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', border: '1px solid #ddd' }}>
            <thead>
              <tr style={{ backgroundColor: '#f1f3f4', textAlign: 'left', fontSize: '0.8rem' }}>
                <th style={{ padding: '8px 12px' }}>Worker ID</th>
                <th style={{ padding: '8px 12px' }}>Worker Type</th>
                <th style={{ padding: '8px 12px' }}>Status</th>
                <th style={{ padding: '8px 12px' }}>Last Heartbeat</th>
                <th style={{ padding: '8px 12px' }}>Heartbeat Age</th>
                <th style={{ padding: '8px 12px' }}>Last Successful Run</th>
              </tr>
            </thead>
            <tbody>
              {overview.workers.map((w) => (
                <tr key={w.id} style={{ borderBottom: '1px solid #eee', fontSize: '0.85rem' }}>
                  <td style={{ padding: '8px 12px', fontFamily: 'monospace' }}>{w.worker_id}</td>
                  <td style={{ padding: '8px 12px' }}>{w.worker_type}</td>
                  <td style={{ padding: '8px 12px', fontWeight: 'bold', color: w.status === 'ACTIVE' ? '#137333' : '#c5221f' }}>
                    {w.status}
                  </td>
                  <td style={{ padding: '8px 12px' }}>{new Date(w.last_heartbeat_at).toLocaleTimeString()}</td>
                  <td style={{ padding: '8px 12px' }}>{w.age_seconds != null ? `${w.age_seconds}s` : 'N/A'}</td>
                  <td style={{ padding: '8px 12px' }}>
                    {w.last_successful_run_at ? new Date(w.last_successful_run_at).toLocaleTimeString() : 'None yet'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
