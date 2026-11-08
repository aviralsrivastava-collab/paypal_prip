import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Corrections } from '../src/pages/Corrections';
import { ApiClient } from '../src/services/api';
import { CorrectionExecutionResult, CorrectionProposal, ProposalHistoryItem } from '../src/types';

describe('Corrections Page Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockPendingProposal: CorrectionProposal = {
    id: 1,
    scan_id: 1,
    diagnosis_id: 10,
    product_id: 1,
    sku: 'SX-001',
    proposal_type: 'PRICE_SYNCHRONIZATION',
    current_value: '120.00',
    proposed_value: '100.00',
    currency: 'USD',
    reason: 'Align storefront price with catalog ground truth',
    supporting_evidence_ids: [1, 2],
    policy_validation_status: 'VALID',
    approval_status: 'PENDING_APPROVAL',
    execution_status: 'NOT_STARTED',
    created_at: '2026-11-07T12:00:00Z',
    updated_at: '2026-11-07T12:00:00Z',
    expires_at: '2026-11-08T12:00:00Z',
    created_by: 'system_diagnosis',
    expected_catalog_version: 1,
    expected_storefront_version: 1,
    idempotency_key: 'prop-1-key',
  };

  const mockApprovedProposal: CorrectionProposal = {
    ...mockPendingProposal,
    approval_status: 'APPROVED',
    approved_by: 'merchant-jane',
  };

  const mockHistory: ProposalHistoryItem[] = [
    {
      id: 1,
      action: 'CORRECTION_PROPOSED',
      actor_id: 'system_diagnosis',
      actor_type: 'system',
      created_at: '2026-11-07T12:00:00Z',
      details: 'Correction proposed',
    },
    {
      id: 2,
      action: 'CORRECTION_VALIDATED',
      actor_id: 'policy_engine',
      actor_type: 'system',
      created_at: '2026-11-07T12:00:01Z',
      details: 'Deterministic policy validation passed',
    },
  ];

  it('renders proposals list and detailed before/after comparison', async () => {
    vi.spyOn(ApiClient, 'getProposals').mockResolvedValue([mockPendingProposal]);
    vi.spyOn(ApiClient, 'getProposalHistory').mockResolvedValue(mockHistory);

    render(<Corrections />);

    await waitFor(() => {
      expect(screen.getByText('Merchant Corrections & Remediation Hub')).toBeInTheDocument();
      expect(screen.getByText('#1 — SX-001')).toBeInTheDocument();
    });

    expect(screen.getAllByText(/120\.00/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/100\.00/).length).toBeGreaterThan(0);
    expect(screen.getByTestId('proposal-approval-status')).toHaveTextContent('PENDING_APPROVAL');
    expect(screen.getByTestId('proposal-execution-status')).toHaveTextContent('NOT_STARTED');
    expect(screen.getByText('Evidence #1')).toBeInTheDocument();
  });

  it('requires explicit confirmation checkbox before approval button is enabled', async () => {
    vi.spyOn(ApiClient, 'getProposals').mockResolvedValue([mockPendingProposal]);
    vi.spyOn(ApiClient, 'getProposalHistory').mockResolvedValue(mockHistory);

    render(<Corrections />);

    await waitFor(() => {
      expect(screen.getByText('Review & Authorize')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Review & Authorize'));

    await waitFor(() => {
      expect(screen.getByText('Explicit Merchant Authorization')).toBeInTheDocument();
    });

    const submitBtn = screen.getByTestId('approve-submit-btn');
    expect(submitBtn).toBeDisabled();

    // Check confirmation checkbox
    const confirmCheckbox = screen.getByTestId('approve-confirm-checkbox');
    fireEvent.click(confirmCheckbox);

    await waitFor(() => {
      expect(screen.getByTestId('approve-submit-btn')).not.toBeDisabled();
    });
  });

  it('successfully approves a proposal when authorized', async () => {
    vi.spyOn(ApiClient, 'getProposals')
      .mockResolvedValueOnce([mockPendingProposal])
      .mockResolvedValue([mockApprovedProposal]);
    vi.spyOn(ApiClient, 'getProposalHistory').mockResolvedValue(mockHistory);
    const approveSpy = vi.spyOn(ApiClient, 'approveProposal').mockResolvedValue(mockApprovedProposal);

    render(<Corrections />);

    await waitFor(() => {
      expect(screen.getByText('Review & Authorize')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Review & Authorize'));

    await waitFor(() => {
      expect(screen.getByTestId('approve-confirm-checkbox')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('approve-confirm-checkbox'));

    await waitFor(() => {
      expect(screen.getByTestId('approve-submit-btn')).not.toBeDisabled();
    });

    fireEvent.click(screen.getByTestId('approve-submit-btn'));

    await waitFor(() => {
      expect(approveSpy).toHaveBeenCalledWith(1, undefined);
    });

    await waitFor(() => {
      expect(screen.getByTestId('proposal-approval-status')).toHaveTextContent('APPROVED');
    });
  });

  it('requires mandatory rejection reason before rejection is submitted', async () => {
    vi.spyOn(ApiClient, 'getProposals').mockResolvedValue([mockPendingProposal]);
    vi.spyOn(ApiClient, 'getProposalHistory').mockResolvedValue(mockHistory);

    render(<Corrections />);

    await waitFor(() => {
      expect(screen.getByText('Reject Proposal')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Reject Proposal'));

    await waitFor(() => {
      expect(screen.getByText(/A substantive reason is required to reject a proposal/i)).toBeInTheDocument();
    });

    const rejectSubmitBtn = screen.getByTestId('reject-submit-btn');
    expect(rejectSubmitBtn).toBeDisabled();

    const reasonInput = screen.getByTestId('reject-reason-input');
    fireEvent.change(reasonInput, { target: { value: 'Deliberate promotion for holiday sale.' } });

    await waitFor(() => {
      expect(screen.getByTestId('reject-submit-btn')).not.toBeDisabled();
    });
  });

  it('executes approved proposal and displays execution success and reinspection state', async () => {
    const execResult: CorrectionExecutionResult = {
      proposal: {
        ...mockApprovedProposal,
        execution_status: 'SUCCEEDED',
        executed_at: '2026-11-07T12:05:00Z',
      },
      followup_scan: {
        id: 2,
        product_id: 1,
        sku: 'SX-001',
        source_version: 1,
        state: 'VERIFIED_NO_ISSUE',
        is_comparable: true,
        catalog_price: '100.00',
        observed_price: '100.00',
        currency: 'USD',
        discrepancy_amount: null,
        url: '/products/sx-001',
        correlation_id: 'reinspect-1',
        comparability_reasons: [],
        evidence_items: [],
        created_at: '2026-11-07T12:05:01Z',
      },
    };

    vi.spyOn(ApiClient, 'getProposals')
      .mockResolvedValueOnce([mockApprovedProposal])
      .mockResolvedValue([execResult.proposal]);
    vi.spyOn(ApiClient, 'getProposalHistory').mockResolvedValue(mockHistory);

    const execSpy = vi.spyOn(ApiClient, 'executeProposal').mockResolvedValue(execResult);

    render(<Corrections />);

    await waitFor(() => {
      expect(screen.getByText('Apply Approved Correction to Storefront')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Apply Approved Correction to Storefront'));

    await waitFor(() => {
      expect(execSpy).toHaveBeenCalledWith(1, { simulate_timeout: false, simulate_storefront_error: false });
    });

    await waitFor(() => {
      expect(screen.getByText(/Correction successfully applied to storefront/i)).toBeInTheDocument();
      expect(screen.getByText(/VERIFIED_NO_ISSUE/i)).toBeInTheDocument();
    });
  });
});
