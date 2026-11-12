import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Dashboard } from '../src/pages/Dashboard';
import { ApiClient } from '../src/services/api';

describe('Dashboard Page Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    ApiClient.setAuthToken(null);
  });

  it('renders KPI revenue cards, AI assistant, and health overview', async () => {
    vi.spyOn(ApiClient, 'getHealth').mockResolvedValue({
      status: 'healthy',
      environment: 'development',
      version: '0.1.0',
      database_connected: true,
      timestamp: '2026-11-12T00:00:00Z',
    });
    vi.spyOn(ApiClient, 'getProfile').mockResolvedValue({
      id: 'usr_demo_operator',
      email: 'demo@prip.internal',
      full_name: 'Demo Operator',
      active_merchant_id: 'merchant_default',
      active_role: 'OWNER',
      memberships: [
        {
          id: 'mem_1',
          merchant_id: 'merchant_default',
          merchant_name: 'Default Merchant',
          merchant_slug: 'default-merchant',
          user_id: 'usr_demo_operator',
          user_email: 'demo@prip.internal',
          role: 'OWNER',
          is_active: true,
          created_at: '2026-11-12T00:00:00Z',
        },
      ],
    });
    vi.spyOn(ApiClient, 'getRevenueIntelligence').mockResolvedValue({
      merchant_id: 'merchant_default',
      currency: 'USD',
      total_products_monitored: 5,
      active_discrepancies: 2,
      integrity_score_pct: 60,
      at_risk_revenue_leakage: '40.00',
      verified_captured_volume: '300.00',
      total_orders_processed: 3,
      completed_captured_orders: 3,
      protection_status: 'ACTIVE',
    });
    vi.spyOn(ApiClient, 'getCatalogIntelligence').mockResolvedValue({
      total_products: 5,
      health_index: 85,
      items_complete: 4,
      items_needing_improvement: 1,
      products_analysis: [],
    });

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText(/Commerce Integrity Overview/i)).toBeInTheDocument();
      expect(screen.getByText('AT-RISK REVENUE LEAKAGE')).toBeInTheDocument();
      expect(screen.getByText('VERIFIED CAPTURED VOLUME')).toBeInTheDocument();
      expect(screen.getByText('CATALOG INTEGRITY SCORE')).toBeInTheDocument();
    });

    expect(screen.getByText(/PRIP Conversational Assistant/i)).toBeInTheDocument();
    expect(screen.getByText(/System Readiness & Sandbox Health/i)).toBeInTheDocument();
  });

  it('toggles Team & Workspaces panel and displays workspace creation controls', async () => {
    vi.spyOn(ApiClient, 'getProfile').mockResolvedValue({
      id: 'usr_demo_operator',
      email: 'demo@prip.internal',
      full_name: 'Demo Operator',
      active_merchant_id: 'merchant_default',
      active_role: 'OWNER',
      memberships: [
        {
          id: 'mem_1',
          merchant_id: 'merchant_default',
          merchant_name: 'Default Merchant',
          merchant_slug: 'default-merchant',
          user_id: 'usr_demo_operator',
          role: 'OWNER',
          is_active: true,
          created_at: '2026-11-12T00:00:00Z',
        },
      ],
    });
    vi.spyOn(ApiClient, 'getMembers').mockResolvedValue([
      {
        id: 'mem_1',
        merchant_id: 'merchant_default',
        merchant_name: 'Default Merchant',
        merchant_slug: 'default-merchant',
        user_id: 'usr_demo_operator',
        user_email: 'owner@merchant.com',
        role: 'OWNER',
        is_active: true,
        created_at: '2026-11-12T00:00:00Z',
      },
      {
        id: 'mem_2',
        merchant_id: 'merchant_default',
        merchant_name: 'Default Merchant',
        merchant_slug: 'default-merchant',
        user_id: 'usr_staff_1',
        user_email: 'staff@merchant.com',
        role: 'VIEWER',
        is_active: true,
        created_at: '2026-11-12T00:00:00Z',
      },
    ]);

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText(/Team & Workspaces/i)).toBeInTheDocument();
    });

    const toggleBtn = screen.getByText(/Team & Workspaces/i);
    fireEvent.click(toggleBtn);

    await waitFor(() => {
      expect(screen.getByText(/Multi-Tenant Workspace & Team Management/i)).toBeInTheDocument();
      expect(screen.getByText('owner@merchant.com')).toBeInTheDocument();
      expect(screen.getByText('staff@merchant.com')).toBeInTheDocument();
      expect(screen.getByText(/Create New Merchant Workspace/i)).toBeInTheDocument();
    });
  });

  it('supports manual token entry and sign out', async () => {
    vi.spyOn(ApiClient, 'getProfile').mockResolvedValue(null as any);

    render(<Dashboard />);

    const pasteBtn = screen.getByText(/Paste Token/i);
    fireEvent.click(pasteBtn);

    const tokenInput = screen.getByPlaceholderText(/Bearer JWT token.../i);
    fireEvent.change(tokenInput, { target: { value: 'eyMockToken123' } });

    const applyBtn = screen.getByText('Apply');
    fireEvent.click(applyBtn);

    expect(ApiClient.getAuthToken()).toBe('eyMockToken123');
  });
});

