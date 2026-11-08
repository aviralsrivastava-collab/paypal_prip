import React, { useEffect, useState } from 'react';
import { ApiClient } from '../services/api';
import {
  CorrectionExecutionResult,
  CorrectionProposal,
  ProposalApprovalStatus,
  ProposalHistoryItem,
} from '../types';

export const Corrections: React.FC = () => {
  const [proposals, setProposals] = useState<CorrectionProposal[]>([]);
  const [selectedProposal, setSelectedProposal] = useState<CorrectionProposal | null>(null);
  const [history, setHistory] = useState<ProposalHistoryItem[]>([]);
  const [executionResult, setExecutionResult] = useState<CorrectionExecutionResult | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [loading, setLoading] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Modals & Inputs
  const [showApproveModal, setShowApproveModal] = useState<boolean>(false);
  const [approveConfirmed, setApproveConfirmed] = useState<boolean>(false);
  const [approveReason, setApproveReason] = useState<string>('');

  const [showRejectModal, setShowRejectModal] = useState<boolean>(false);
  const [rejectReason, setRejectReason] = useState<string>('');

  const [simulateTimeout, setSimulateTimeout] = useState<boolean>(false);
  const [simulateError, setSimulateError] = useState<boolean>(false);

  const loadProposals = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await ApiClient.getProposals();
      setProposals(data);
      if (data.length > 0 && !selectedProposal) {
        setSelectedProposal(data[0]);
      } else if (selectedProposal) {
        const updated = data.find((p) => p.id === selectedProposal.id);
        if (updated) setSelectedProposal(updated);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load correction proposals.');
    } finally {
      setLoading(false);
    }
  };

  const loadHistory = async (proposalId: number) => {
    try {
      const hist = await ApiClient.getProposalHistory(proposalId);
      setHistory(hist);
    } catch {
      setHistory([]);
    }
  };

  useEffect(() => {
    loadProposals();
  }, []);

  useEffect(() => {
    if (selectedProposal) {
      loadHistory(selectedProposal.id);
      setExecutionResult(null);
    }
  }, [selectedProposal?.id]);

  const handleApprove = async () => {
    if (!selectedProposal || !approveConfirmed) return;
    setActionLoading(true);
    setError(null);
    try {
      const res = await ApiClient.approveProposal(selectedProposal.id, approveReason || undefined);
      setSelectedProposal(res);
      setShowApproveModal(false);
      setApproveConfirmed(false);
      setApproveReason('');
      await loadProposals();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Approval failed.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!selectedProposal || !rejectReason.trim()) return;
    setActionLoading(true);
    setError(null);
    try {
      const res = await ApiClient.rejectProposal(selectedProposal.id, rejectReason.trim());
      setSelectedProposal(res);
      setShowRejectModal(false);
      setRejectReason('');
      await loadProposals();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Rejection failed.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleExecute = async () => {
    if (!selectedProposal) return;
    setActionLoading(true);
    setError(null);
    try {
      const result = await ApiClient.executeProposal(selectedProposal.id, {
        simulate_timeout: simulateTimeout,
        simulate_storefront_error: simulateError,
      });
      setExecutionResult(result);
      setSelectedProposal(result.proposal);
      await loadProposals();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Execution failed.');
      await loadProposals();
    } finally {
      setActionLoading(false);
    }
  };

  const handleReconcile = async () => {
    if (!selectedProposal) return;
    setActionLoading(true);
    setError(null);
    try {
      const result = await ApiClient.reconcileProposal(selectedProposal.id);
      setExecutionResult(result);
      setSelectedProposal(result.proposal);
      await loadProposals();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Reconciliation failed.');
      await loadProposals();
    } finally {
      setActionLoading(false);
    }
  };

  const getApprovalBadgeStyle = (status: ProposalApprovalStatus) => {
    switch (status) {
      case 'APPROVED':
        return { backgroundColor: '#dcfce7', color: '#166534', border: '1px solid #bbf7d0' };
      case 'REJECTED':
        return { backgroundColor: '#fee2e2', color: '#991b1b', border: '1px solid #fecaca' };
      case 'EXPIRED':
        return { backgroundColor: '#f1f5f9', color: '#64748b', border: '1px solid #cbd5e1' };
      case 'CANCELLED':
        return { backgroundColor: '#f3f4f6', color: '#4b5563', border: '1px solid #d1d5db' };
      case 'PENDING_APPROVAL':
      default:
        return { backgroundColor: '#fef3c7', color: '#92400e', border: '1px solid #fde68a' };
    }
  };

  const filteredProposals = proposals.filter((p) => {
    if (filterStatus === 'ALL') return true;
    return p.approval_status === filterStatus;
  });

  return (
    <div style={{ padding: '2rem', maxWidth: '1100px', margin: '0 auto', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      {/* Header */}
      <div style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ margin: '0 0 0.5rem', color: '#0f172a' }}>Merchant Corrections & Remediation Hub</h2>
        <p style={{ margin: 0, color: '#64748b', fontSize: '0.95rem' }}>
          Human-authorized remediation workflow: Deterministic policy checks, explicit merchant approval, safe external execution, and follow-up verification.
        </p>
      </div>

      {error && (
        <div style={{ padding: '0.85rem 1rem', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', color: '#991b1b', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
          <strong>Error: </strong> {error}
        </div>
      )}

      {/* Main Grid: Left List, Right Detail */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.6fr', gap: '1.5rem' }}>
        {/* Left Column: Proposals List */}
        <div>
          <div style={{ backgroundColor: '#fff', padding: '1rem', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <h3 style={{ margin: 0, fontSize: '0.95rem', color: '#1e293b' }}>Proposals ({filteredProposals.length})</h3>
              <button
                onClick={loadProposals}
                disabled={loading}
                style={{ fontSize: '0.8rem', padding: '0.25rem 0.6rem', border: '1px solid #cbd5e1', borderRadius: '4px', cursor: 'pointer', backgroundColor: '#f8fafc' }}
              >
                Refresh
              </button>
            </div>

            {/* Filter Tabs */}
            <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
              {['ALL', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'EXPIRED'].map((tab) => (
                <button
                  key={tab}
                  onClick={() => setFilterStatus(tab)}
                  style={{
                    padding: '0.25rem 0.55rem',
                    fontSize: '0.75rem',
                    borderRadius: '4px',
                    border: '1px solid',
                    borderColor: filterStatus === tab ? '#3b82f6' : '#e2e8f0',
                    backgroundColor: filterStatus === tab ? '#eff6ff' : '#fff',
                    color: filterStatus === tab ? '#1d4ed8' : '#64748b',
                    cursor: 'pointer',
                    fontWeight: filterStatus === tab ? 600 : 400,
                  }}
                >
                  {tab === 'PENDING_APPROVAL' ? 'Pending' : tab}
                </button>
              ))}
            </div>

            {/* List */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '550px', overflowY: 'auto' }}>
              {filteredProposals.length === 0 ? (
                <p style={{ color: '#94a3b8', fontSize: '0.85rem', textAlign: 'center', padding: '1.5rem 0' }}>
                  No proposals found matching filter.
                </p>
              ) : (
                filteredProposals.map((prop) => {
                  const badge = getApprovalBadgeStyle(prop.approval_status);
                  const isSelected = selectedProposal?.id === prop.id;
                  return (
                    <div
                      key={prop.id}
                      onClick={() => setSelectedProposal(prop)}
                      style={{
                        padding: '0.75rem',
                        borderRadius: '6px',
                        border: isSelected ? '2px solid #3b82f6' : '1px solid #e2e8f0',
                        backgroundColor: isSelected ? '#f8fafc' : '#fff',
                        cursor: 'pointer',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                        <span style={{ fontWeight: 700, fontSize: '0.85rem', color: '#1e293b' }}>
                          #{prop.id} — {prop.sku}
                        </span>
                        <span style={{ fontSize: '0.7rem', padding: '0.15rem 0.45rem', borderRadius: '4px', fontWeight: 600, ...badge }}>
                          {prop.approval_status}
                        </span>
                      </div>
                      <div style={{ fontSize: '0.8rem', color: '#475569', marginBottom: '0.25rem' }}>
                        {prop.current_value} &rarr; <strong>{prop.proposed_value} {prop.currency}</strong>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                        Created: {new Date(prop.created_at).toLocaleDateString()}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Proposal Detail, Actions & Audit */}
        <div>
          {selectedProposal ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {/* Proposal Header Card */}
              <div style={{ backgroundColor: '#fff', padding: '1.25rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                  <div>
                    <h3 style={{ margin: '0 0 0.25rem', fontSize: '1.1rem', color: '#0f172a' }}>
                      Proposal #{selectedProposal.id}: {selectedProposal.sku}
                    </h3>
                    <span style={{ fontSize: '0.85rem', color: '#64748b' }}>
                      Type: <strong>{selectedProposal.proposal_type}</strong> | Scan Ref: #{selectedProposal.scan_id}
                    </span>
                  </div>

                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <span
                      data-testid="proposal-approval-status"
                      style={{
                        padding: '0.25rem 0.65rem',
                        borderRadius: '4px',
                        fontSize: '0.8rem',
                        fontWeight: 700,
                        ...getApprovalBadgeStyle(selectedProposal.approval_status),
                      }}
                    >
                      {selectedProposal.approval_status}
                    </span>
                    <span
                      data-testid="proposal-execution-status"
                      style={{
                        padding: '0.25rem 0.65rem',
                        borderRadius: '4px',
                        fontSize: '0.8rem',
                        fontWeight: 700,
                        backgroundColor: selectedProposal.execution_status === 'SUCCEEDED' ? '#dcfce7' : selectedProposal.execution_status === 'RECONCILIATION_REQUIRED' ? '#fef3c7' : '#f1f5f9',
                        color: selectedProposal.execution_status === 'SUCCEEDED' ? '#166534' : selectedProposal.execution_status === 'RECONCILIATION_REQUIRED' ? '#92400e' : '#475569',
                        border: selectedProposal.execution_status === 'SUCCEEDED' ? '1px solid #bbf7d0' : selectedProposal.execution_status === 'RECONCILIATION_REQUIRED' ? '1px solid #fde68a' : '1px solid #cbd5e1',
                      }}
                    >
                      {selectedProposal.execution_status}
                    </span>
                  </div>
                </div>

                {/* Before / After Box */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', backgroundColor: '#f8fafc', padding: '1rem', borderRadius: '6px', border: '1px solid #e2e8f0', marginBottom: '1rem' }}>
                  <div>
                    <span style={{ fontSize: '0.75rem', color: '#64748b', display: 'block' }}>STOREFRONT (CURRENT)</span>
                    <span style={{ fontSize: '1.1rem', fontWeight: 600, color: '#dc2626' }}>
                      {selectedProposal.current_value} {selectedProposal.currency}
                    </span>
                  </div>
                  <div>
                    <span style={{ fontSize: '0.75rem', color: '#64748b', display: 'block' }}>PROPOSED TARGET</span>
                    <span style={{ fontSize: '1.1rem', fontWeight: 700, color: '#166534' }}>
                      {selectedProposal.proposed_value} {selectedProposal.currency}
                    </span>
                  </div>
                  <div>
                    <span style={{ fontSize: '0.75rem', color: '#64748b', display: 'block' }}>POLICY STATUS</span>
                    <span style={{ fontSize: '0.9rem', fontWeight: 700, color: selectedProposal.policy_validation_status === 'VALID' ? '#166534' : '#dc2626' }}>
                      {selectedProposal.policy_validation_status}
                    </span>
                  </div>
                </div>

                {/* Reason & Evidence */}
                <div style={{ marginBottom: '1rem' }}>
                  <strong style={{ fontSize: '0.85rem', color: '#334155', display: 'block', marginBottom: '0.25rem' }}>Justification Reason:</strong>
                  <p style={{ margin: 0, fontSize: '0.85rem', color: '#475569', backgroundColor: '#fff', padding: '0.5rem', borderRadius: '4px', border: '1px solid #f1f5f9' }}>
                    {selectedProposal.reason}
                  </p>
                </div>

                {selectedProposal.supporting_evidence_ids.length > 0 && (
                  <div style={{ marginBottom: '1rem' }}>
                    <strong style={{ fontSize: '0.85rem', color: '#334155', display: 'block', marginBottom: '0.25rem' }}>Grounded Evidence Citations:</strong>
                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                      {selectedProposal.supporting_evidence_ids.map((id) => (
                        <span key={id} style={{ padding: '0.15rem 0.5rem', backgroundColor: '#f1f5f9', border: '1px solid #cbd5e1', borderRadius: '4px', fontFamily: 'monospace', fontSize: '0.75rem', color: '#334155' }}>
                          Evidence #{id}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Metadata & Expiration */}
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: '#64748b', borderTop: '1px solid #f1f5f9', paddingTop: '0.75rem' }}>
                  <span>Created By: <strong>{selectedProposal.created_by}</strong></span>
                  <span>Expires: {new Date(selectedProposal.expires_at).toLocaleString()}</span>
                </div>

                {selectedProposal.approved_by && (
                  <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: '#166534' }}>
                    Approved by authorized merchant: <strong>{selectedProposal.approved_by}</strong>
                  </div>
                )}

                {selectedProposal.rejected_by && (
                  <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: '#991b1b', backgroundColor: '#fef2f2', padding: '0.5rem', borderRadius: '4px' }}>
                    <strong>Rejected by {selectedProposal.rejected_by}:</strong> {selectedProposal.rejection_reason}
                  </div>
                )}
              </div>

              {/* Action Controls Card */}
              <div style={{ backgroundColor: '#fff', padding: '1.25rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem', color: '#1e293b' }}>Merchant Governance Actions</h4>

                {/* If Pending Approval */}
                {selectedProposal.approval_status === 'PENDING_APPROVAL' && (
                  <div style={{ display: 'flex', gap: '0.75rem' }}>
                    <button
                      onClick={() => setShowApproveModal(true)}
                      style={{
                        padding: '0.55rem 1.25rem',
                        backgroundColor: '#16a34a',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '6px',
                        fontWeight: 600,
                        fontSize: '0.85rem',
                        cursor: 'pointer',
                      }}
                    >
                      Review & Authorize
                    </button>
                    <button
                      onClick={() => setShowRejectModal(true)}
                      style={{
                        padding: '0.55rem 1.25rem',
                        backgroundColor: '#dc2626',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '6px',
                        fontWeight: 600,
                        fontSize: '0.85rem',
                        cursor: 'pointer',
                      }}
                    >
                      Reject Proposal
                    </button>
                  </div>
                )}

                {/* If Approved and Not Executed */}
                {selectedProposal.approval_status === 'APPROVED' && selectedProposal.execution_status === 'NOT_STARTED' && (
                  <div>
                    <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '0.75rem' }}>
                      <label style={{ fontSize: '0.8rem', color: '#475569', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                        <input
                          type="checkbox"
                          checked={simulateTimeout}
                          onChange={(e) => setSimulateTimeout(e.target.checked)}
                        />
                        Simulate Gateway Timeout (Testing)
                      </label>
                      <label style={{ fontSize: '0.8rem', color: '#475569', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                        <input
                          type="checkbox"
                          checked={simulateError}
                          onChange={(e) => setSimulateError(e.target.checked)}
                        />
                        Simulate Gateway Error
                      </label>
                    </div>

                    <button
                      onClick={handleExecute}
                      disabled={actionLoading}
                      style={{
                        padding: '0.6rem 1.5rem',
                        backgroundColor: '#0070ba',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '6px',
                        fontWeight: 700,
                        fontSize: '0.9rem',
                        cursor: actionLoading ? 'not-allowed' : 'pointer',
                      }}
                    >
                      {actionLoading ? 'Applying to Storefront...' : 'Apply Approved Correction to Storefront'}
                    </button>
                  </div>
                )}

                {/* If Reconciliation Required */}
                {selectedProposal.execution_status === 'RECONCILIATION_REQUIRED' && (
                  <div style={{ backgroundColor: '#fffbeb', border: '1px solid #fde68a', padding: '0.85rem', borderRadius: '6px' }}>
                    <p style={{ margin: '0 0 0.5rem', color: '#92400e', fontSize: '0.85rem', fontWeight: 600 }}>
                      External Storefront Outcome Uncertain: An external timeout occurred. Blind retries are strictly blocked.
                    </p>
                    <button
                      onClick={handleReconcile}
                      disabled={actionLoading}
                      style={{
                        padding: '0.5rem 1.25rem',
                        backgroundColor: '#d97706',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '6px',
                        fontWeight: 600,
                        fontSize: '0.85rem',
                        cursor: actionLoading ? 'not-allowed' : 'pointer',
                      }}
                    >
                      {actionLoading ? 'Reconciling...' : 'Verify & Reconcile Actual Storefront State'}
                    </button>
                  </div>
                )}

                {/* Execution Success Result Banner */}
                {selectedProposal.execution_status === 'SUCCEEDED' && (
                  <div style={{ backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0', padding: '0.85rem', borderRadius: '6px' }}>
                    <p style={{ margin: '0 0 0.35rem', color: '#166534', fontSize: '0.85rem', fontWeight: 600 }}>
                      Correction successfully applied to storefront at {selectedProposal.executed_at ? new Date(selectedProposal.executed_at).toLocaleTimeString() : 'now'}.
                    </p>
                    {executionResult?.followup_scan && (
                      <p style={{ margin: 0, color: '#15803d', fontSize: '0.8rem' }}>
                        Post-remediation inspection completed: Outcome <strong>{executionResult.followup_scan.state}</strong>.
                      </p>
                    )}
                  </div>
                )}
              </div>

              {/* Audit Trail Timeline */}
              {history.length > 0 && (
                <div style={{ backgroundColor: '#fff', padding: '1.25rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem', color: '#1e293b' }}>
                    Append-Only Audit History ({history.length} events)
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {history.map((item) => (
                      <div key={item.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0.75rem', backgroundColor: '#f8fafc', borderRadius: '4px', fontSize: '0.8rem', border: '1px solid #f1f5f9' }}>
                        <div>
                          <strong style={{ color: '#0070ba' }}>{item.action}</strong>
                          <span style={{ color: '#64748b', marginLeft: '0.5rem' }}>by {item.actor_id}</span>
                          {item.details && <div style={{ color: '#475569', marginTop: '0.2rem' }}>{item.details}</div>}
                        </div>
                        <span style={{ color: '#94a3b8', whiteSpace: 'nowrap' }}>
                          {new Date(item.created_at).toLocaleTimeString()}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div style={{ backgroundColor: '#fff', padding: '3rem', borderRadius: '8px', border: '1px solid #e2e8f0', textAlign: 'center', color: '#94a3b8' }}>
              Select a correction proposal to review details and take governance action.
            </div>
          )}
        </div>
      </div>

      {/* Explicit Approval Confirmation Modal */}
      {showApproveModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', padding: '1.75rem', borderRadius: '8px', width: '480px', maxWidth: '90%' }}>
            <h3 style={{ margin: '0 0 0.75rem', color: '#0f172a' }}>Explicit Merchant Authorization</h3>
            <p style={{ fontSize: '0.85rem', color: '#475569', lineHeight: 1.5, marginBottom: '1rem' }}>
              You are authorizing the application of this price correction to the customer-facing storefront.
              This will update product <strong>{selectedProposal?.sku}</strong> from <strong>{selectedProposal?.current_value} {selectedProposal?.currency}</strong> to <strong>{selectedProposal?.proposed_value} {selectedProposal?.currency}</strong>.
            </p>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#334155', marginBottom: '0.25rem' }}>
                Optional Approval Note:
              </label>
              <input
                type="text"
                value={approveReason}
                onChange={(e) => setApproveReason(e.target.value)}
                placeholder="e.g. Authorized catalog synchronization"
                style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #cbd5e1', fontSize: '0.85rem', boxSizing: 'border-box' }}
              />
            </div>

            <div style={{ marginBottom: '1.25rem', backgroundColor: '#eff6ff', padding: '0.75rem', borderRadius: '6px', border: '1px solid #bfdbfe' }}>
              <label style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', fontSize: '0.85rem', color: '#1e40af', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  data-testid="approve-confirm-checkbox"
                  checked={approveConfirmed}
                  onChange={(e) => setApproveConfirmed(e.target.checked)}
                  style={{ marginTop: '0.2rem' }}
                />
                <span>
                  <strong>I confirm:</strong> I am an authorized merchant operator and approve this exact correction. AI recommendations cannot self-approve.
                </span>
              </label>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                onClick={() => setShowApproveModal(false)}
                style={{ padding: '0.5rem 1rem', backgroundColor: '#f1f5f9', border: '1px solid #cbd5e1', borderRadius: '4px', cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                data-testid="approve-submit-btn"
                onClick={handleApprove}
                disabled={!approveConfirmed || actionLoading}
                style={{
                  padding: '0.5rem 1.25rem',
                  backgroundColor: '#16a34a',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '4px',
                  fontWeight: 600,
                  cursor: !approveConfirmed || actionLoading ? 'not-allowed' : 'pointer',
                  opacity: !approveConfirmed || actionLoading ? 0.6 : 1,
                }}
              >
                {actionLoading ? 'Authorizing...' : 'Authorize & Approve'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rejection Modal with Mandatory Reason */}
      {showRejectModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', padding: '1.75rem', borderRadius: '8px', width: '480px', maxWidth: '90%' }}>
            <h3 style={{ margin: '0 0 0.75rem', color: '#991b1b' }}>Reject Correction Proposal</h3>
            <p style={{ fontSize: '0.85rem', color: '#475569', marginBottom: '1rem' }}>
              A substantive reason is required to reject a proposal. Rejected proposals can never be executed.
            </p>

            <div style={{ marginBottom: '1.25rem' }}>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#334155', marginBottom: '0.25rem' }}>
                Rejection Reason (Mandatory):
              </label>
              <textarea
                data-testid="reject-reason-input"
                rows={3}
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="e.g. Storefront price reflects intended promotional discount."
                style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #cbd5e1', fontSize: '0.85rem', boxSizing: 'border-box' }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                onClick={() => setShowRejectModal(false)}
                style={{ padding: '0.5rem 1rem', backgroundColor: '#f1f5f9', border: '1px solid #cbd5e1', borderRadius: '4px', cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                data-testid="reject-submit-btn"
                onClick={handleReject}
                disabled={!rejectReason.trim() || actionLoading}
                style={{
                  padding: '0.5rem 1.25rem',
                  backgroundColor: '#dc2626',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '4px',
                  fontWeight: 600,
                  cursor: !rejectReason.trim() || actionLoading ? 'not-allowed' : 'pointer',
                  opacity: !rejectReason.trim() || actionLoading ? 0.6 : 1,
                }}
              >
                {actionLoading ? 'Rejecting...' : 'Confirm Rejection'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
