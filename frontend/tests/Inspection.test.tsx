import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Inspection } from '../src/pages/Inspection';
import { ApiClient } from '../src/services/api';
import { Diagnosis, ScanDetail } from '../src/types';

describe('Inspection Page Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockIssueScan: ScanDetail = {
    id: 1,
    product_id: 1,
    sku: 'SX-001',
    source_version: 1,
    state: 'ISSUE_DETECTED',
    is_comparable: true,
    catalog_price: '100.00',
    observed_price: '120.00',
    currency: 'USD',
    discrepancy_amount: '+20.00',
    created_at: '2026-11-07T12:00:00Z',
    url: '/products/sx-001',
    failure_reason: null,
    correlation_id: 'test-corr-1',
    comparability_reasons: [],
    evidence_items: [
      {
        id: 1,
        scan_id: 1,
        evidence_type: 'EXTRACTION',
        field_name: 'storefront_status',
        expected_value: 'SUCCESS',
        observed_value: 'SUCCESS',
        source_url: '/products/sx-001',
        observation_timestamp: '2026-11-07T12:00:00Z',
        content_hash: 'b6e8041dbc16b31038a9a2d6865542989b749e42aa06d2e6a0f2e9dbda02f9c9',
        status: 'MATCH',
        details: 'Storefront HTML parsed',
        created_at: '2026-11-07T12:00:00Z',
      },
      {
        id: 2,
        scan_id: 1,
        evidence_type: 'PRICE',
        field_name: 'price',
        expected_value: '100.00',
        observed_value: '120.00',
        source_url: '/products/sx-001',
        observation_timestamp: '2026-11-07T12:00:00Z',
        content_hash: 'b6e8041dbc16b31038a9a2d6865542989b749e42aa06d2e6a0f2e9dbda02f9c9',
        status: 'MISMATCH',
        details: 'Discrepancy: 20.00',
        created_at: '2026-11-07T12:00:00Z',
      },
    ],
  };

  it('renders initial NOT_TESTED state when no previous scans exist', async () => {
    vi.spyOn(ApiClient, 'getProductScans').mockResolvedValue([]);

    render(<Inspection />);

    expect(screen.getByText('Storefront Inspection & Evidence Engine')).toBeInTheDocument();
    expect(screen.getByText('NOT TESTED')).toBeInTheDocument();
    expect(screen.getByText(/This product has not yet been inspected/i)).toBeInTheDocument();
  });

  it('renders ISSUE_DETECTED outcome with discrepancy and evidence items', async () => {
    vi.spyOn(ApiClient, 'getProductScans').mockResolvedValue([mockIssueScan]);
    vi.spyOn(ApiClient, 'getScan').mockResolvedValue(mockIssueScan);

    render(<Inspection />);

    await waitFor(() => {
      expect(screen.getByText('ISSUE DETECTED')).toBeInTheDocument();
    });

    expect(screen.getByText(/price mismatch or policy violation was detected/i)).toBeInTheDocument();
    expect(screen.getByText('100.00 USD')).toBeInTheDocument();
    expect(screen.getByText('120.00 USD')).toBeInTheDocument();
    expect(screen.getAllByText(/\+20\.00/).length).toBeGreaterThan(0);
    expect(screen.getByText('Structured Evidence Items')).toBeInTheDocument();
    expect(screen.getByText('EXTRACTION')).toBeInTheDocument();
    expect(screen.getByText('PRICE')).toBeInTheDocument();
  });

  it('renders VERIFIED_NO_ISSUE when prices match', async () => {
    const verifiedScan: ScanDetail = {
      ...mockIssueScan,
      id: 2,
      state: 'VERIFIED_NO_ISSUE',
      observed_price: '100.00',
      discrepancy_amount: null,
    };
    vi.spyOn(ApiClient, 'getProductScans').mockResolvedValue([verifiedScan]);
    vi.spyOn(ApiClient, 'getScan').mockResolvedValue(verifiedScan);

    render(<Inspection />);

    await waitFor(() => {
      expect(screen.getByText('VERIFIED NO ISSUE')).toBeInTheDocument();
    });
    expect(screen.getByText(/All observations are comparable and no discrepancies exist/i)).toBeInTheDocument();
  });

  it('renders BLOCKED_UNKNOWN outcome and blocker reason when non-comparable', async () => {
    const blockedScan: ScanDetail = {
      ...mockIssueScan,
      id: 3,
      state: 'BLOCKED_UNKNOWN',
      is_comparable: false,
      discrepancy_amount: null,
      failure_reason: 'CURRENCY_MISMATCH: Catalog currency USD differs from storefront currency EUR',
    };
    vi.spyOn(ApiClient, 'getProductScans').mockResolvedValue([blockedScan]);
    vi.spyOn(ApiClient, 'getScan').mockResolvedValue(blockedScan);

    render(<Inspection />);

    await waitFor(() => {
      expect(screen.getByText('BLOCKED / UNKNOWN')).toBeInTheDocument();
    });
    expect(screen.getByText(/Missing evidence is not evidence of correctness/i)).toBeInTheDocument();
    expect(screen.getByText(/CURRENCY_MISMATCH: Catalog currency USD differs from storefront currency EUR/i)).toBeInTheDocument();
  });

  it('triggers an inspection when "Run Inspection" button is clicked', async () => {
    vi.spyOn(ApiClient, 'getProductScans').mockResolvedValue([]);
    const triggerSpy = vi.spyOn(ApiClient, 'triggerScan').mockResolvedValue(mockIssueScan);

    render(<Inspection />);

    const runBtn = screen.getByRole('button', { name: /run inspection/i });
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(triggerSpy).toHaveBeenCalledWith('SX-001', undefined);
    });

    await waitFor(() => {
      expect(screen.getByText('ISSUE DETECTED')).toBeInTheDocument();
    });
  });

  const mockDiagnosis: Diagnosis = {
    id: 10,
    scan_id: 1,
    provider: 'mock',
    model: 'prip-diagnostic-v1',
    prompt_version: 'v1.0',
    status: 'COMPLETED',
    summary: 'A price discrepancy of 20.00 USD was detected on product SX-001.',
    likely_causes: ['Storefront listing price was manually updated or not synchronized with merchant catalog.'],
    supporting_evidence_ids: [1, 2],
    missing_information: [],
    recommended_actions: ['Synchronize storefront price to match merchant catalog baseline (100.00 USD).'],
    confidence_explanation: 'High confidence based on direct extraction of price and catalog facts.',
    is_advisory: true,
    created_at: '2026-11-07T12:05:00Z',
  };

  it('renders advisory AI diagnosis panel with clear separation from inspection state', async () => {
    vi.spyOn(ApiClient, 'getProductScans').mockResolvedValue([mockIssueScan]);
    vi.spyOn(ApiClient, 'getScan').mockResolvedValue(mockIssueScan);
    vi.spyOn(ApiClient, 'getScanDiagnoses').mockResolvedValue([mockDiagnosis]);

    render(<Inspection />);

    await waitFor(() => {
      expect(screen.getByText('ISSUE DETECTED')).toBeInTheDocument();
      expect(screen.getByTestId('ai-diagnosis-panel')).toBeInTheDocument();
    });

    // Verify advisory-only banner and strict separation
    expect(screen.getByTestId('advisory-badge')).toHaveTextContent('Advisory Only');
    expect(screen.getByText(/AI has NO authority to mutate data/i)).toBeInTheDocument();

    // Verify distinct diagnosis status badge vs inspection outcome
    const diagnosisStatusBadge = screen.getByTestId('diagnosis-status-badge');
    expect(diagnosisStatusBadge).toHaveTextContent('COMPLETED');
    expect(screen.getByTestId('state-banner')).toHaveTextContent('ISSUE DETECTED');

    // Verify summary, causes, grounded evidence tags, advisory recommendations
    expect(screen.getByText(/A price discrepancy of 20.00 USD was detected on product SX-001/i)).toBeInTheDocument();
    expect(screen.getByText(/Storefront listing price was manually updated/i)).toBeInTheDocument();
    expect(screen.getByTestId('evidence-tag-1')).toHaveTextContent('Evidence #1');
    expect(screen.getByTestId('evidence-tag-2')).toHaveTextContent('Evidence #2');
    expect(screen.getByText(/Synchronize storefront price to match merchant catalog baseline/i)).toBeInTheDocument();
    expect(screen.getByText(/Provenance & Confidence: High confidence/i)).toBeInTheDocument();
  });

  it('triggers advisory AI diagnosis on user button click', async () => {
    vi.spyOn(ApiClient, 'getProductScans').mockResolvedValue([mockIssueScan]);
    vi.spyOn(ApiClient, 'getScan').mockResolvedValue(mockIssueScan);
    vi.spyOn(ApiClient, 'getScanDiagnoses').mockResolvedValue([]);
    const triggerDiagSpy = vi.spyOn(ApiClient, 'triggerDiagnosis').mockResolvedValue(mockDiagnosis);

    render(<Inspection />);

    await waitFor(() => {
      expect(screen.getByText('No advisory diagnosis requested yet for Scan #1.')).toBeInTheDocument();
    });

    const requestBtn = screen.getByRole('button', { name: /request advisory diagnosis/i });
    fireEvent.click(requestBtn);

    await waitFor(() => {
      expect(triggerDiagSpy).toHaveBeenCalledWith(1, undefined);
    });

    await waitFor(() => {
      expect(screen.getByTestId('diagnosis-status-badge')).toHaveTextContent('COMPLETED');
    });
  });

  it('displays AI diagnostic error without altering inspection state banner', async () => {
    vi.spyOn(ApiClient, 'getProductScans').mockResolvedValue([mockIssueScan]);
    vi.spyOn(ApiClient, 'getScan').mockResolvedValue(mockIssueScan);
    vi.spyOn(ApiClient, 'getScanDiagnoses').mockResolvedValue([]);
    vi.spyOn(ApiClient, 'triggerDiagnosis').mockRejectedValue(new Error('AI provider connection timed out.'));

    render(<Inspection />);

    await waitFor(() => {
      expect(screen.getByText('No advisory diagnosis requested yet for Scan #1.')).toBeInTheDocument();
    });

    const requestBtn = screen.getByRole('button', { name: /request advisory diagnosis/i });
    fireEvent.click(requestBtn);

    await waitFor(() => {
      expect(screen.getByText(/AI provider connection timed out/i)).toBeInTheDocument();
    });

    // Critical Invariant: Scan inspection state banner must remain ISSUE_DETECTED
    expect(screen.getByTestId('state-banner')).toHaveTextContent('ISSUE DETECTED');
  });
});
