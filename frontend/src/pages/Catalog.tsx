import React, { useEffect, useState } from 'react';
import { PriceBadge } from '../components/PriceBadge';
import { ApiClient } from '../services/api';
import { ProductComparison } from '../types';

export const Catalog: React.FC = () => {
  const [products, setProducts] = useState<ProductComparison[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [seeding, setSeeding] = useState<boolean>(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  // Storefront simulation inputs
  const [storefrontInputs, setStorefrontInputs] = useState<Record<string, string>>({});
  const [actionLoadingSku, setActionLoadingSku] = useState<string | null>(null);

  // Add Product form state
  const [showAddForm, setShowAddForm] = useState(false);
  const [newSku, setNewSku] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [newPrice, setNewPrice] = useState('');
  const [newStorefrontPrice, setNewStorefrontPrice] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [addingProduct, setAddingProduct] = useState(false);

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
    setActionMessage(null);
    try {
      await ApiClient.seedCatalog(reset);
      setActionMessage('Catalog seeded successfully.');
      await fetchCatalog();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to seed demo catalog.');
    } finally {
      setSeeding(false);
    }
  };

  const handleUpdateStorefrontPrice = async (sku: string) => {
    const val = storefrontInputs[sku];
    if (!val || isNaN(Number(val))) {
      alert('Please enter a valid numeric price.');
      return;
    }
    setActionLoadingSku(sku);
    setActionMessage(null);
    try {
      await ApiClient.updateStorefrontPrice(sku, val);
      setActionMessage(`Updated storefront price for ${sku} to $${val}. Discrepancy simulated.`);
      await fetchCatalog();
    } catch (err: any) {
      setError(err.message || 'Failed to update storefront price.');
    } finally {
      setActionLoadingSku(null);
    }
  };

  const handleDeleteProduct = async (id: number, sku: string) => {
    if (!confirm(`Are you sure you want to delete product SKU ${sku}?`)) return;
    try {
      await ApiClient.deleteProduct(id);
      setActionMessage(`Deleted product ${sku}.`);
      await fetchCatalog();
    } catch (err: any) {
      setError(err.message || 'Failed to delete product.');
    }
  };

  const handleAddProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSku.trim() || !newTitle.trim() || !newPrice.trim()) {
      alert('SKU, Title, and Catalog Price are required.');
      return;
    }
    setAddingProduct(true);
    setError(null);
    try {
      await ApiClient.createProduct({
        sku: newSku.trim(),
        title: newTitle.trim(),
        price: newPrice.trim(),
        storefront_price: newStorefrontPrice.trim() || newPrice.trim(),
        description: newDescription.trim() || undefined,
        currency: 'USD',
      });
      setActionMessage(`Created product ${newSku.trim()} successfully.`);
      setNewSku('');
      setNewTitle('');
      setNewPrice('');
      setNewStorefrontPrice('');
      setNewDescription('');
      setShowAddForm(false);
      await fetchCatalog();
    } catch (err: any) {
      setError(err.message || 'Failed to create product.');
    } finally {
      setAddingProduct(false);
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
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            style={{
              padding: '0.6rem 1.2rem',
              backgroundColor: '#0f172a',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {showAddForm ? 'Cancel' : '+ Add Product'}
          </button>
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
      </div>

      {actionMessage && (
        <div
          style={{
            padding: '0.75rem 1rem',
            marginBottom: '1rem',
            backgroundColor: '#ecfdf5',
            border: '1px solid #a7f3d0',
            borderRadius: '6px',
            color: '#065f46',
            fontSize: '0.9rem',
          }}
        >
          {actionMessage}
        </div>
      )}

      {showAddForm && (
        <form
          onSubmit={handleAddProduct}
          style={{
            backgroundColor: '#f8fafc',
            border: '1px solid #cbd5e1',
            borderRadius: '8px',
            padding: '1.25rem',
            marginBottom: '1.5rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.75rem',
          }}
        >
          <h4 style={{ margin: 0, color: '#0f172a' }}>Add New Product to Authorized Catalog</h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
            <div>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: '#475569' }}>SKU *</label>
              <input
                type="text"
                value={newSku}
                onChange={(e) => setNewSku(e.target.value)}
                placeholder="e.g. SX-002"
                style={{ width: '100%', padding: '0.4rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                required
              />
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: '#475569' }}>Title *</label>
              <input
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="e.g. Apex Trail Pro"
                style={{ width: '100%', padding: '0.4rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                required
              />
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: '#475569' }}>Catalog Price ($) *</label>
              <input
                type="number"
                step="0.01"
                value={newPrice}
                onChange={(e) => setNewPrice(e.target.value)}
                placeholder="e.g. 150.00"
                style={{ width: '100%', padding: '0.4rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                required
              />
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: '#475569' }}>Initial Storefront Price ($)</label>
              <input
                type="number"
                step="0.01"
                value={newStorefrontPrice}
                onChange={(e) => setNewStorefrontPrice(e.target.value)}
                placeholder="e.g. 175.00 (or leave empty)"
                style={{ width: '100%', padding: '0.4rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
              />
            </div>
          </div>
          <div>
            <label style={{ fontSize: '0.8rem', fontWeight: 600, color: '#475569' }}>Description</label>
            <input
              type="text"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              placeholder="e.g. Lightweight trail running shoes with enhanced grip"
              style={{ width: '100%', padding: '0.4rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.5rem' }}>
            <button
              type="button"
              onClick={() => setShowAddForm(false)}
              style={{ padding: '0.4rem 0.8rem', border: '1px solid #cbd5e1', borderRadius: '4px', background: '#fff', cursor: 'pointer' }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={addingProduct}
              style={{ padding: '0.4rem 1rem', background: '#16a34a', color: '#fff', border: 'none', borderRadius: '4px', fontWeight: 600, cursor: addingProduct ? 'not-allowed' : 'pointer' }}
            >
              {addingProduct ? 'Adding...' : 'Save Product'}
            </button>
          </div>
        </form>
      )}

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

              {/* Storefront Simulation & Actions */}
              <div
                style={{
                  marginTop: '1rem',
                  paddingTop: '0.75rem',
                  borderTop: '1px dashed #e2e8f0',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '0.75rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{ fontSize: '0.85rem', color: '#64748b' }}>Simulate Storefront Price:</span>
                  <div style={{ display: 'flex', alignItems: 'center' }}>
                    <span style={{ padding: '0.35rem 0.5rem', background: '#f1f5f9', border: '1px solid #cbd5e1', borderRight: 'none', borderTopLeftRadius: '4px', borderBottomLeftRadius: '4px', fontSize: '0.85rem' }}>$</span>
                    <input
                      type="number"
                      step="0.01"
                      placeholder={product.storefront_price || product.merchant_price}
                      value={storefrontInputs[product.sku] ?? ''}
                      onChange={(e) =>
                        setStorefrontInputs({ ...storefrontInputs, [product.sku]: e.target.value })
                      }
                      style={{
                        width: '90px',
                        padding: '0.35rem 0.5rem',
                        border: '1px solid #cbd5e1',
                        borderTopRightRadius: '4px',
                        borderBottomRightRadius: '4px',
                        fontSize: '0.85rem',
                      }}
                    />
                  </div>
                  <button
                    onClick={() => handleUpdateStorefrontPrice(product.sku)}
                    disabled={actionLoadingSku === product.sku}
                    style={{
                      padding: '0.35rem 0.75rem',
                      backgroundColor: '#0284c7',
                      color: '#fff',
                      border: 'none',
                      borderRadius: '4px',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      cursor: actionLoadingSku === product.sku ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {actionLoadingSku === product.sku ? 'Applying...' : 'Apply Storefront Price'}
                  </button>
                </div>

                <button
                  onClick={() => handleDeleteProduct(product.id, product.sku)}
                  style={{
                    padding: '0.35rem 0.6rem',
                    backgroundColor: '#fee2e2',
                    color: '#991b1b',
                    border: '1px solid #fca5a5',
                    borderRadius: '4px',
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
