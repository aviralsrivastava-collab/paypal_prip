import React, { useEffect, useState } from 'react';
import { PriceBadge } from '../components/PriceBadge';
import { ApiClient } from '../services/api';
import { ProductComparison } from '../types';

export const Catalog: React.FC = () => {
  const [products, setProducts] = useState<ProductComparison[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [seeding, setSeeding] = useState<boolean>(false);

  const fetchCatalog = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await ApiClient.getProducts();
      setProducts(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred while fetching products.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCatalog();
  }, []);

  const handleSeed = async (reset = false) => {
    setSeeding(true);
    try {
      await ApiClient.seedCatalog(reset);
      await fetchCatalog();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to seed demo catalog.');
    } finally {
      setSeeding(false);
    }
  };

  return (
    <div style={{ padding: '2rem', maxWidth: '1000px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ margin: 0, color: '#1e293b' }}>Merchant-Authorized Catalog</h2>
          <p style={{ margin: '0.5rem 0 0', color: '#64748b', fontSize: '0.95rem' }}>
            Merchant catalog is the MVP source of truth for configured fields. Storefront values reflect customer-facing demo prices.
          </p>
        </div>
        <button
          onClick={() => handleSeed(true)}
          disabled={seeding || loading}
          style={{
            padding: '0.6rem 1.2rem',
            backgroundColor: '#0070ba',
            color: '#fff',
            border: 'none',
            borderRadius: '6px',
            fontWeight: 600,
            cursor: seeding ? 'not-allowed' : 'pointer',
            opacity: seeding ? 0.7 : 1,
          }}
        >
          {seeding ? 'Seeding...' : 'Reset Demo Seed'}
        </button>
      </div>

      {loading && (
        <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>
          <p>Loading catalog and storefront data...</p>
        </div>
      )}

      {error && (
        <div
          style={{
            padding: '1rem',
            marginBottom: '1.5rem',
            backgroundColor: '#fee2e2',
            border: '1px solid #f87171',
            borderRadius: '6px',
            color: '#991b1b',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>{error}</span>
          <button
            onClick={fetchCatalog}
            style={{
              padding: '0.4rem 0.8rem',
              backgroundColor: '#991b1b',
              color: '#fff',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !error && products.length === 0 && (
        <div style={{ padding: '2rem', textAlign: 'center', backgroundColor: '#f8fafc', borderRadius: '8px' }}>
          <p style={{ color: '#64748b', marginBottom: '1rem' }}>No catalog products found.</p>
          <button
            onClick={() => handleSeed(false)}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: '#0070ba',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
            }}
          >
            Seed StrideX Runner (SX-001)
          </button>
        </div>
      )}

      {!loading && !error && products.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {products.map((product) => (
            <div
              key={product.sku}
              style={{
                border: product.has_discrepancy ? '1px solid #f87171' : '1px solid #e2e8f0',
                borderRadius: '8px',
                padding: '1.5rem',
                backgroundColor: '#ffffff',
                boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <h3 style={{ margin: 0, fontSize: '1.25rem', color: '#0f172a' }}>{product.title}</h3>
                    <span
                      style={{
                        padding: '0.2rem 0.5rem',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        backgroundColor: '#f1f5f9',
                        color: '#475569',
                        borderRadius: '4px',
                      }}
                    >
                      SKU: {product.sku}
                    </span>
                  </div>
                  {product.description && (
                    <p style={{ margin: '0.5rem 0 0', color: '#64748b', fontSize: '0.9rem' }}>
                      {product.description}
                    </p>
                  )}
                </div>

                <span
                  style={{
                    padding: '0.35rem 0.75rem',
                    borderRadius: '20px',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    backgroundColor: !product.is_comparable
                      ? '#e0e7ff'
                      : product.has_discrepancy
                      ? '#fee2e2'
                      : '#ecfdf5',
                    color: !product.is_comparable
                      ? '#3730a3'
                      : product.has_discrepancy
                      ? '#991b1b'
                      : '#065f46',
                  }}
                >
                  {!product.is_comparable
                    ? 'NON-COMPARABLE (CURRENCY MISMATCH)'
                    : product.has_discrepancy
                    ? 'PRICE MISMATCH DETECTED'
                    : 'PRICES IN SYNC'}
                </span>
              </div>

              <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid #f1f5f9' }}>
                <p style={{ margin: '0 0 0.75rem', fontSize: '0.8rem', fontWeight: 600, color: '#475569', textTransform: 'uppercase' }}>
                  Price Comparison
                </p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <PriceBadge
                    label="Merchant Source of Truth"
                    amount={product.merchant_price}
                    currency={product.merchant_currency}
                    type="source-of-truth"
                  />
                  {product.storefront_price && (
                    <PriceBadge
                      label="Storefront Customer Facing"
                      amount={product.storefront_price}
                      currency={product.storefront_currency || product.merchant_currency}
                      type="storefront"
                    />
                  )}
                  {product.is_comparable && product.price_discrepancy && product.has_discrepancy && (
                    <PriceBadge
                      label="Discrepancy"
                      amount={product.price_discrepancy}
                      currency={product.merchant_currency}
                      type="discrepancy"
                    />
                  )}
                  {!product.is_comparable && (
                    <PriceBadge
                      label="Discrepancy"
                      type="non-comparable"
                      note="Non-Comparable (Currency Mismatch)"
                    />
                  )}
                </div>
                {!product.is_comparable && product.comparability_reason && (
                  <p style={{ margin: '0.5rem 0 0', fontSize: '0.85rem', color: '#4338ca', fontStyle: 'italic' }}>
                    {product.comparability_reason}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
