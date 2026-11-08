import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Catalog } from '../src/pages/Catalog';
import { ApiClient } from '../src/services/api';

describe('Catalog Page Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading indicator initially', () => {
    vi.spyOn(ApiClient, 'getProducts').mockImplementation(() => new Promise(() => {}));
    render(<Catalog />);
    expect(screen.getByText(/loading catalog and storefront data/i)).toBeInTheDocument();
  });

  it('renders products with merchant price, storefront price, and discrepancy clearly distinguished', async () => {
    vi.spyOn(ApiClient, 'getProducts').mockResolvedValue([
      {
        id: 1,
        sku: 'SX-001',
        title: 'StrideX Runner',
        description: 'High-performance running shoe.',
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
        updated_at: '2026-11-07T12:00:00Z',
      },
    ]);

    render(<Catalog />);

    await waitFor(() => {
      expect(screen.getByText('StrideX Runner')).toBeInTheDocument();
    });

    expect(screen.getByText('SKU: SX-001')).toBeInTheDocument();
    expect(screen.getByText('PRICE MISMATCH DETECTED')).toBeInTheDocument();
    expect(screen.getByText('Merchant Source of Truth')).toBeInTheDocument();
    expect(screen.getByText('Storefront Customer Facing')).toBeInTheDocument();
    expect(screen.getByText('Discrepancy')).toBeInTheDocument();
    expect(screen.getByText(/100.00/)).toBeInTheDocument();
    expect(screen.getByText(/120.00/)).toBeInTheDocument();
    expect(screen.getByText(/\+20.00/)).toBeInTheDocument();
  });

  it('renders non-comparable state for currency mismatch and does not display numerical discrepancy', async () => {
    vi.spyOn(ApiClient, 'getProducts').mockResolvedValue([
      {
        id: 2,
        sku: 'SX-002',
        title: 'Euro Runner',
        description: 'Cross-border runner with currency mismatch.',
        merchant_price: '100.00',
        merchant_currency: 'USD',
        storefront_price: '120.00',
        storefront_currency: 'EUR',
        price_discrepancy: null,
        has_discrepancy: true,
        is_comparable: false,
        comparability_reason: "CURRENCY_MISMATCH: Catalog currency 'USD' != Storefront currency 'EUR'",
        availability: 'IN_STOCK',
        source_version: 1,
        storefront_version: 1,
        updated_at: '2026-11-07T12:00:00Z',
      },
    ]);

    render(<Catalog />);

    await waitFor(() => {
      expect(screen.getByText('Euro Runner')).toBeInTheDocument();
    });

    expect(screen.getAllByText(/Non-Comparable \(Currency Mismatch\)/i)).toHaveLength(2);
    expect(screen.getByText(/CURRENCY_MISMATCH: Catalog currency 'USD' != Storefront currency 'EUR'/)).toBeInTheDocument();
    expect(screen.queryByText('+20.00')).not.toBeInTheDocument();
  });

  it('renders error state when API fails', async () => {
    vi.spyOn(ApiClient, 'getProducts').mockRejectedValue(new Error('Network error connecting to API'));

    render(<Catalog />);

    await waitFor(() => {
      expect(screen.getByText(/Network error connecting to API/i)).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });
});
