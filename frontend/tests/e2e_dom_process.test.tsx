import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { ApiClient } from '../src/services/api';

describe('End-to-End DOM User Process Verification', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    ApiClient.setAuthToken(null);
    ApiClient.setActiveMerchantId('merchant_default');
  });

  it('Stage 1 - DOM Verification: Dashboard Overview, Team & Workspaces, and AI Chat Assistant', async () => {
    vi.spyOn(ApiClient, 'getHealth').mockResolvedValue({
      status: 'healthy',
      environment: 'development',
      version: '0.1.0',
      database_connected: true,
      timestamp: '2026-11-12T00:00:00Z',
    });
    vi.spyOn(ApiClient, 'getProfile').mockResolvedValue({
      id: 'usr_demo_operator',
      email: 'operator@prip.local',
      full_name: 'Demo Operator',
      active_merchant_id: 'merchant_default',
      active_role: 'OWNER',
      memberships: [
        {
          id: 'mem_1',
          merchant_id: 'merchant_default',
          merchant_name: 'StrideX Sports (Default)',
          merchant_slug: 'default',
          user_id: 'usr_demo_operator',
          user_email: 'operator@prip.local',
          role: 'OWNER',
          is_active: true,
          created_at: '2026-11-12T00:00:00Z',
        },
      ],
    });
    vi.spyOn(ApiClient, 'getRevenueIntelligence').mockResolvedValue({
      merchant_id: 'merchant_default',
      currency: 'USD',
      total_products_monitored: 1,
      active_discrepancies: 1,
      integrity_score_pct: 0,
      at_risk_revenue_leakage: '20.00',
      verified_captured_volume: '0.00',
      total_orders_processed: 0,
      completed_captured_orders: 0,
      protection_status: 'DISCREPANCY_FLAGGED',
    });
    vi.spyOn(ApiClient, 'getCatalogIntelligence').mockResolvedValue({
      total_products: 1,
      health_index: 85,
      items_complete: 1,
      items_needing_improvement: 0,
      products_analysis: [],
    });
    vi.spyOn(ApiClient, 'getMembers').mockResolvedValue([
      {
        id: 'mem_1',
        merchant_id: 'merchant_default',
        merchant_name: 'StrideX Sports (Default)',
        merchant_slug: 'default',
        user_id: 'usr_demo_operator',
        user_email: 'operator@prip.local',
        role: 'OWNER',
        is_active: true,
        created_at: '2026-11-12T00:00:00Z',
      },
    ]);
    vi.spyOn(ApiClient, 'sendChatMessage').mockResolvedValue({
      reply: 'Monitoring active. StrideX Runner SX-001 has a $20.00 price mismatch.',
      suggested_actions: ['Run storefront inspection', 'Review correction proposal'],
    });

    render(<App />);

    // 1. Verify Dashboard header and KPI metrics exist in DOM
    await waitFor(() => {
      expect(screen.getByText(/Commerce Integrity Overview/i)).toBeInTheDocument();
      expect(screen.getByText('AT-RISK REVENUE LEAKAGE')).toBeInTheDocument();
      expect(screen.getByText('$20.00')).toBeInTheDocument();
      expect(screen.getByText('VERIFIED CAPTURED VOLUME')).toBeInTheDocument();
      expect(screen.getByText('CATALOG INTEGRITY SCORE')).toBeInTheDocument();
    });

    // 2. Test DOM interaction: Open "Team & Workspaces" panel
    const teamBtn = screen.getByText(/Team & Workspaces/i);
    fireEvent.click(teamBtn);

    await waitFor(() => {
      expect(screen.getByText(/Multi-Tenant Workspace & Team Management/i)).toBeInTheDocument();
      expect(screen.getByText('operator@prip.local')).toBeInTheDocument();
      expect(screen.getByText(/Create New Merchant Workspace/i)).toBeInTheDocument();
    });

    // 3. Test DOM interaction: Conversational Assistant chat input
    const chatInput = screen.getByPlaceholderText(/Ask PRIP Assistant about your catalog/i);
    fireEvent.change(chatInput, { target: { value: 'What is the current discrepancy status for my store?' } });
    const sendBtn = screen.getByText('Send');
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(screen.getByText(/Monitoring active\. StrideX Runner SX-001 has a \$20\.00 price mismatch\./i)).toBeInTheDocument();
    });
  });

  it('Stage 2 - DOM Verification: Catalog Management, Add Product Form, and Storefront Price Simulation', async () => {
    vi.spyOn(ApiClient, 'getProducts').mockResolvedValue([
      {
        id: 1,
        sku: 'SX-001',
        title: 'StrideX Runner',
        description: 'High-performance lightweight running shoe.',
        merchant_price: '100.00',
        merchant_currency: 'USD',
        storefront_price: '120.00',
        storefront_currency: 'USD',
        price_discrepancy: '+20.00',
        has_discrepancy: true,
        is_comparable: true,
        comparability_reason: null,
        availability: 'IN_STOCK',
        source_version: 1,
        storefront_version: 1,
        updated_at: '2026-11-12T00:00:00Z',
      },
    ]);
    const mockUpdateStorefrontPrice = vi.spyOn(ApiClient, 'updateStorefrontPrice').mockResolvedValue({
      id: 1,
      sku: 'SX-001',
      title: 'StrideX Runner',
      merchant_price: '100.00',
      merchant_currency: 'USD',
      storefront_price: '125.00',
      storefront_currency: 'USD',
      price_discrepancy: '+25.00',
      has_discrepancy: true,
      is_comparable: true,
      comparability_reason: null,
      availability: 'IN_STOCK',
      source_version: 1,
      storefront_version: 2,
      updated_at: '2026-11-12T00:00:00Z',
    });

    render(<App />);

    // Navigate to Catalog via Header DOM link
    const catalogNav = screen.getByText('Catalog');
    fireEvent.click(catalogNav);

    await waitFor(() => {
      expect(screen.getByText('StrideX Runner')).toBeInTheDocument();
      expect(screen.getByText('PRICE MISMATCH DETECTED')).toBeInTheDocument();
      expect(screen.getByText(/100.00/)).toBeInTheDocument();
      expect(screen.getByText(/120.00/)).toBeInTheDocument();
    });

    // Test DOM interaction: Open Add Product form
    const addProductBtn = screen.getByText('+ Add Product');
    fireEvent.click(addProductBtn);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('e.g. SX-002')).toBeInTheDocument();
      expect(screen.getByText('Save Product')).toBeInTheDocument();
    });

    // Test DOM interaction: Update storefront simulation price
    const storefrontPriceInput = screen.getByPlaceholderText('120.00');
    fireEvent.change(storefrontPriceInput, { target: { value: '125.00' } });

    const applyPriceBtn = screen.getByText('Apply Storefront Price');
    fireEvent.click(applyPriceBtn);

    expect(mockUpdateStorefrontPrice).toHaveBeenCalledWith('SX-001', '125.00');
  });

  it('Stage 3 - DOM Verification: Storefront Inspection Execution and Evidence Item Presentation', async () => {
    vi.spyOn(ApiClient, 'getProducts').mockResolvedValue([
      {
        id: 1,
        sku: 'SX-001',
        title: 'StrideX Runner',
        merchant_price: '100.00',
        merchant_currency: 'USD',
        storefront_price: '120.00',
        storefront_currency: 'USD',
        price_discrepancy: '+20.00',
        has_discrepancy: true,
        is_comparable: true,
        comparability_reason: null,
        availability: 'IN_STOCK',
        source_version: 1,
        storefront_version: 1,
        updated_at: '2026-11-12T00:00:00Z',
      },
    ]);
    vi.spyOn(ApiClient, 'triggerScan').mockResolvedValue({
      id: 14,
      product_id: 1,
      sku: 'SX-001',
      source_version: 1,
      state: 'ISSUE_DETECTED',
      is_comparable: true,
      catalog_price: '100.00',
      observed_price: '120.00',
      currency: 'USD',
      discrepancy_amount: '+20.00',
      created_at: '2026-11-12T12:00:00Z',
      url: '/products/sx-001',
      failure_reason: null,
      correlation_id: 'test-corr-1',
      comparability_reasons: [],
      evidence_items: [
        {
          id: 1,
          scan_id: 14,
          evidence_type: 'PRICE',
          field_name: 'price',
          expected_value: '100.00',
          observed_value: '120.00',
          source_url: 'http://localhost:3000/products/SX-001',
          observation_timestamp: '2026-11-12T12:00:00Z',
          content_hash: 'hash-abc-123',
          status: 'MISMATCH',
          details: 'Discrepancy: +20.00 USD between catalog and customer storefront.',
          created_at: '2026-11-12T12:00:00Z',
        },
      ],
    });

    render(<App />);

    // Navigate to Inspection
    const inspectionNav = screen.getByText('Inspection');
    fireEvent.click(inspectionNav);

    await waitFor(() => {
      expect(screen.getByText('Storefront Inspection & Evidence Engine')).toBeInTheDocument();
      expect(screen.getByText('Run Inspection')).toBeInTheDocument();
    });

    // Click Run Inspection button
    const runBtn = screen.getByText('Run Inspection');
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(screen.getByText('ISSUE DETECTED')).toBeInTheDocument();
      expect(screen.getByText(/\+20\.00 USD/)).toBeInTheDocument();
      expect(screen.getByText('Structured Evidence Items')).toBeInTheDocument();
      expect(screen.getByText('MISMATCH')).toBeInTheDocument();
    });
  });

  it('Stage 4 - DOM Verification: Correction Proposals, Checkbox Sign-Off, and Approval', async () => {
    vi.spyOn(ApiClient, 'getProposals').mockResolvedValue([
      {
        id: 1,
        scan_id: 14,
        diagnosis_id: 10,
        product_id: 1,
        sku: 'SX-001',
        proposal_type: 'PRICE_SYNCHRONIZATION',
        current_value: '120.00',
        proposed_value: '100.00',
        currency: 'USD',
        reason: 'Align storefront price with catalog ground truth',
        supporting_evidence_ids: [1],
        policy_validation_status: 'VALID',
        approval_status: 'PENDING_APPROVAL',
        execution_status: 'NOT_STARTED',
        created_at: '2026-11-12T12:00:00Z',
        updated_at: '2026-11-12T12:00:00Z',
        expires_at: '2026-11-13T12:00:00Z',
        created_by: 'system_diagnosis',
        expected_catalog_version: 1,
        expected_storefront_version: 1,
        idempotency_key: 'prop-1-key',
      },
    ]);
    const mockApprove = vi.spyOn(ApiClient, 'approveProposal').mockResolvedValue({
      id: 1,
      scan_id: 14,
      product_id: 1,
      sku: 'SX-001',
      proposal_type: 'PRICE_SYNCHRONIZATION',
      current_value: '120.00',
      proposed_value: '100.00',
      currency: 'USD',
      reason: 'Align storefront price with catalog ground truth',
      supporting_evidence_ids: [1],
      policy_validation_status: 'VALID',
      approval_status: 'APPROVED',
      execution_status: 'SUCCEEDED',
      created_at: '2026-11-12T12:00:00Z',
      updated_at: '2026-11-12T12:01:00Z',
      expires_at: '2026-11-13T12:00:00Z',
      created_by: 'system_diagnosis',
      approved_by: 'operator@prip.local',
      executed_at: '2026-11-12T12:01:05Z',
      expected_catalog_version: 1,
      expected_storefront_version: 1,
    });

    render(<App />);

    // Navigate to Corrections
    const correctionsNav = screen.getByText('Corrections');
    fireEvent.click(correctionsNav);

    await waitFor(() => {
      expect(screen.getByText('Merchant Corrections & Remediation Hub')).toBeInTheDocument();
      expect(screen.getByText(/#1 — SX-001/)).toBeInTheDocument();
      expect(screen.getAllByText(/120\.00/).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/100\.00/).length).toBeGreaterThan(0);
      expect(screen.getByText('Review & Authorize')).toBeInTheDocument();
    });

    // Open explicit merchant authorization modal
    const reviewBtn = screen.getByText('Review & Authorize');
    fireEvent.click(reviewBtn);

    await waitFor(() => {
      expect(screen.getByText('Explicit Merchant Authorization')).toBeInTheDocument();
      expect(screen.getByTestId('approve-confirm-checkbox')).toBeInTheDocument();
    });

    // Check confirmation checkbox
    const confirmCheckbox = screen.getByTestId('approve-confirm-checkbox') as HTMLInputElement;
    expect(confirmCheckbox.checked).toBe(false);
    fireEvent.click(confirmCheckbox);
    expect(confirmCheckbox.checked).toBe(true);

    // Click Authorize & Approve button
    const approveBtn = screen.getByTestId('approve-submit-btn');
    expect(approveBtn).not.toBeDisabled();
    fireEvent.click(approveBtn);

    expect(mockApprove).toHaveBeenCalledWith(1, undefined);
  });

  it('Stage 5 - DOM Verification: PayPal Sandbox Preflight and Verified Checkout', async () => {
    vi.spyOn(ApiClient, 'getProducts').mockResolvedValue([
      {
        id: 1,
        sku: 'SX-001',
        title: 'StrideX Runner',
        merchant_price: '100.00',
        merchant_currency: 'USD',
        storefront_price: '100.00',
        storefront_currency: 'USD',
        price_discrepancy: '0.00',
        has_discrepancy: false,
        is_comparable: true,
        comparability_reason: null,
        availability: 'IN_STOCK',
        source_version: 1,
        storefront_version: 1,
        updated_at: '2026-11-12T00:00:00Z',
      },
    ]);
    vi.spyOn(ApiClient, 'checkPreflight').mockResolvedValue({
      passed: true,
      sku: 'SX-001',
      catalog_price: '100.00',
      storefront_price: '100.00',
      currency: 'USD',
      scan_id: 15,
      scan_state: 'VERIFIED_NO_ISSUE',
      blocking_reasons: [],
      message: 'Preflight passed. Price verified clean.',
    });
    const mockCreateOrder = vi.spyOn(ApiClient, 'createOrder').mockResolvedValue({
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
      created_at: '2026-11-12T12:00:00Z',
      updated_at: '2026-11-12T12:00:00Z',
    });

    render(<App />);

    // Navigate to Checkout Demo
    const checkoutNav = screen.getByText('Checkout Demo');
    fireEvent.click(checkoutNav);

    await waitFor(() => {
      expect(screen.getByText('PayPal Sandbox Checkout Demo')).toBeInTheDocument();
      expect(screen.getByText('1. Checkout Preflight Discrepancy Gate')).toBeInTheDocument();
      expect(screen.getByText('2. PayPal Sandbox Order')).toBeInTheDocument();
    });

    // Click "Pay with PayPal Sandbox"
    const payBtn = screen.getByText('Pay with PayPal Sandbox');
    fireEvent.click(payBtn);

    await waitFor(() => {
      expect(mockCreateOrder).toHaveBeenCalled();
    });
    expect(mockCreateOrder.mock.calls[0][0]).toBe('SX-001');
    expect(mockCreateOrder.mock.calls[0][1]).toBe(1);
  });
});
