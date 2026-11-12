import React, { useEffect, useState } from 'react';
import { ApiClient } from '../services/api';
import {
  CatalogIntelligence,
  ChatMessage,
  HealthStatus,
  RevenueIntelligence,
  UserProfile,
} from '../types';

export const Dashboard: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [revenue, setRevenue] = useState<RevenueIntelligence | null>(null);
  const [catalogIntel, setCatalogIntel] = useState<CatalogIntelligence | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Chat State
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content: 'Welcome to PRIP Revenue Intelligence! I am monitoring your catalog against customer-facing storefronts. How can I help protect your revenue today?',
    },
  ]);
  const [inputMsg, setInputMsg] = useState('');
  const [chatLoading, setChatLoading] = useState(false);

  const loadDashboardData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [h, prof, rev, cat] = await Promise.all([
        ApiClient.getHealth().catch(() => null),
        ApiClient.getProfile().catch(() => null),
        ApiClient.getRevenueIntelligence().catch(() => null),
        ApiClient.getCatalogIntelligence().catch(() => null),
      ]);
      if (h) setHealth(h);
      if (prof) setProfile(prof);
      if (rev) setRevenue(rev);
      if (cat) setCatalogIntel(cat);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, []);

  const handleSwitchTenant = async (tenantId: string) => {
    try {
      await ApiClient.switchTenant(tenantId);
      await loadDashboardData();
    } catch (err: any) {
      alert(err.message || 'Failed to switch tenant workspace');
    }
  };

  const handleSendMessage = async (customText?: string) => {
    const textToSend = customText || inputMsg;
    if (!textToSend.trim() || chatLoading) return;

    const newMsgs: ChatMessage[] = [...chatMessages, { role: 'user', content: textToSend }];
    setChatMessages(newMsgs);
    if (!customText) setInputMsg('');
    setChatLoading(true);

    try {
      const res = await ApiClient.sendChatMessage(newMsgs);
      setChatMessages([...newMsgs, { role: 'assistant', content: res.reply }]);
    } catch (err: any) {
      setChatMessages([
        ...newMsgs,
        { role: 'assistant', content: `Error: Unable to contact AI assistant (${err.message}).` },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto', color: '#1e293b' }}>
      {/* Top Banner / Merchant Workspace */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          borderBottom: '1px solid #e2e8f0',
          paddingBottom: '1.25rem',
          marginBottom: '1.5rem',
        }}
      >
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: '0 0 0.25rem 0', color: '#0f172a' }}>
            Merchant Revenue Intelligence Platform
          </h1>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: '0 0 0.25rem 0', color: '#334155' }}>
            Commerce Integrity Overview
          </h2>
          <p style={{ margin: 0, color: '#64748b', fontSize: '0.95rem' }}>
            Detect the discrepancy. Approve the correction. Verify the checkout.
          </p>
        </div>

        {/* Workspace Switcher */}
        {profile && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '0.85rem', color: '#64748b' }}>Active Workspace:</span>
            <select
              value={profile.active_merchant_id}
              onChange={(e) => handleSwitchTenant(e.target.value)}
              style={{
                padding: '0.4rem 0.8rem',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                backgroundColor: '#ffffff',
                fontWeight: 600,
                fontSize: '0.9rem',
                cursor: 'pointer',
              }}
            >
              {profile.memberships.map((m) => (
                <option key={m.merchant_id} value={m.merchant_id}>
                  {m.merchant_name} ({m.role})
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {loading && <p style={{ color: '#64748b' }}>Loading merchant analytics and AI insights...</p>}
      {error && <p style={{ color: '#ef4444' }}>Error: {error}</p>}

      {/* KPI Revenue Analytics Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '1rem',
          marginBottom: '2rem',
        }}
      >
        <div
          style={{
            backgroundColor: '#ffffff',
            padding: '1.25rem',
            borderRadius: '8px',
            border: '1px solid #e2e8f0',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          }}
        >
          <div style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 600 }}>AT-RISK REVENUE LEAKAGE</div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#dc2626', marginTop: '0.25rem' }}>
            ${revenue?.at_risk_revenue_leakage || '0.00'} <span style={{ fontSize: '1rem' }}>{revenue?.currency || 'USD'}</span>
          </div>
          <div style={{ fontSize: '0.8rem', color: '#dc2626', marginTop: '0.25rem' }}>
            {revenue?.active_discrepancies || 0} active discrepancies flagged
          </div>
        </div>

        <div
          style={{
            backgroundColor: '#ffffff',
            padding: '1.25rem',
            borderRadius: '8px',
            border: '1px solid #e2e8f0',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          }}
        >
          <div style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 600 }}>VERIFIED CAPTURED VOLUME</div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#16a34a', marginTop: '0.25rem' }}>
            ${revenue?.verified_captured_volume || '0.00'} <span style={{ fontSize: '1rem' }}>{revenue?.currency || 'USD'}</span>
          </div>
          <div style={{ fontSize: '0.8rem', color: '#16a34a', marginTop: '0.25rem' }}>
            {revenue?.completed_captured_orders || 0} orders verified by PayPal preflight
          </div>
        </div>

        <div
          style={{
            backgroundColor: '#ffffff',
            padding: '1.25rem',
            borderRadius: '8px',
            border: '1px solid #e2e8f0',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          }}
        >
          <div style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 600 }}>CATALOG INTEGRITY SCORE</div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#0284c7', marginTop: '0.25rem' }}>
            {revenue?.integrity_score_pct || 100}%
          </div>
          <div style={{ fontSize: '0.8rem', color: '#0284c7', marginTop: '0.25rem' }}>
            {revenue?.total_products_monitored || 0} products monitored
          </div>
        </div>

        <div
          style={{
            backgroundColor: '#ffffff',
            padding: '1.25rem',
            borderRadius: '8px',
            border: '1px solid #e2e8f0',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          }}
        >
          <div style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 600 }}>CATALOG QUALITY INDEX</div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#7c3aed', marginTop: '0.25rem' }}>
            {catalogIntel?.health_index || 100}/100
          </div>
          <div style={{ fontSize: '0.8rem', color: '#7c3aed', marginTop: '0.25rem' }}>
            {catalogIntel?.items_complete || 0} complete / {catalogIntel?.items_needing_improvement || 0} need review
          </div>
        </div>
      </div>

      {/* Main Content Grid: AI Assistant & Integrity Status */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '1.5rem', alignItems: 'start' }}>
        {/* Left Column: Conversational AI Assistant */}
        <div
          style={{
            backgroundColor: '#ffffff',
            borderRadius: '8px',
            border: '1px solid #e2e8f0',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
            display: 'flex',
            flexDirection: 'column',
            height: '520px',
          }}
        >
          <div
            style={{
              padding: '1rem 1.25rem',
              borderBottom: '1px solid #e2e8f0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              backgroundColor: '#f8fafc',
              borderTopLeftRadius: '8px',
              borderTopRightRadius: '8px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#22c55e' }} />
              <strong style={{ fontSize: '1rem', color: '#0f172a' }}>PRIP Conversational Assistant (Gemini AI)</strong>
            </div>
            <span style={{ fontSize: '0.75rem', color: '#64748b', backgroundColor: '#e2e8f0', padding: '2px 8px', borderRadius: '4px' }}>
              Bounded Context
            </span>
          </div>

          {/* Chat Messages Log */}
          <div
            style={{
              flex: 1,
              padding: '1rem',
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
            }}
          >
            {chatMessages.map((m, idx) => (
              <div
                key={idx}
                style={{
                  alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                  maxWidth: '80%',
                  padding: '0.75rem 1rem',
                  borderRadius: '8px',
                  backgroundColor: m.role === 'user' ? '#0070ba' : '#f1f5f9',
                  color: m.role === 'user' ? '#ffffff' : '#0f172a',
                  fontSize: '0.9rem',
                  lineHeight: 1.4,
                  whiteSpace: 'pre-wrap',
                }}
              >
                {m.content}
              </div>
            ))}
            {chatLoading && (
              <div
                style={{
                  alignSelf: 'flex-start',
                  padding: '0.5rem 1rem',
                  borderRadius: '8px',
                  backgroundColor: '#f1f5f9',
                  color: '#64748b',
                  fontSize: '0.85rem',
                }}
              >
                Thinking...
              </div>
            )}
          </div>

          {/* Quick Prompt Pills */}
          <div style={{ padding: '0.5rem 1rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap', borderTop: '1px solid #f1f5f9' }}>
            <button
              onClick={() => handleSendMessage('What is the current discrepancy status for my store?')}
              style={{
                fontSize: '0.75rem',
                padding: '4px 10px',
                borderRadius: '12px',
                border: '1px solid #cbd5e1',
                backgroundColor: '#ffffff',
                cursor: 'pointer',
              }}
            >
              📊 Check Discrepancies
            </button>
            <button
              onClick={() => handleSendMessage('How much revenue is protected through PayPal checkout?')}
              style={{
                fontSize: '0.75rem',
                padding: '4px 10px',
                borderRadius: '12px',
                border: '1px solid #cbd5e1',
                backgroundColor: '#ffffff',
                cursor: 'pointer',
              }}
            >
              💰 Revenue Protection
            </button>
            <button
              onClick={() => handleSendMessage('Explain the latest correction proposal for StrideX Runner.')}
              style={{
                fontSize: '0.75rem',
                padding: '4px 10px',
                borderRadius: '12px',
                border: '1px solid #cbd5e1',
                backgroundColor: '#ffffff',
                cursor: 'pointer',
              }}
            >
              🔍 Explain Proposal
            </button>
          </div>

          {/* Chat Input Bar */}
          <div
            style={{
              padding: '0.75rem 1rem',
              borderTop: '1px solid #e2e8f0',
              display: 'flex',
              gap: '0.5rem',
            }}
          >
            <input
              type="text"
              value={inputMsg}
              onChange={(e) => setInputMsg(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
              placeholder="Ask PRIP Assistant about your catalog, revenue, or PayPal Sandbox..."
              style={{
                flex: 1,
                padding: '0.6rem 0.8rem',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '0.9rem',
                outline: 'none',
              }}
            />
            <button
              onClick={() => handleSendMessage()}
              disabled={chatLoading || !inputMsg.trim()}
              style={{
                padding: '0.6rem 1.25rem',
                backgroundColor: '#0070ba',
                color: '#ffffff',
                border: 'none',
                borderRadius: '6px',
                fontWeight: 600,
                fontSize: '0.9rem',
                cursor: chatLoading || !inputMsg.trim() ? 'not-allowed' : 'pointer',
                opacity: chatLoading || !inputMsg.trim() ? 0.6 : 1,
              }}
            >
              Send
            </button>
          </div>
        </div>

        {/* Right Column: Platform Status & Action Cards */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div
            style={{
              backgroundColor: '#ffffff',
              padding: '1.25rem',
              borderRadius: '8px',
              border: '1px solid #e2e8f0',
              boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
            }}
          >
            <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: '0 0 0.75rem 0', color: '#0f172a' }}>
              System Readiness & Sandbox Health
            </h3>
            <div style={{ fontSize: '0.85rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>Backend Status:</span>
                <span style={{ fontWeight: 600, color: health?.status === 'healthy' ? '#16a34a' : '#ea580c' }}>
                  {health?.status || 'Online'}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>Database:</span>
                <span style={{ fontWeight: 600 }}>{health?.database_connected ? 'Connected' : 'Active'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>Environment:</span>
                <span style={{ fontWeight: 600 }}>{health?.environment || 'Development'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>PayPal Gateway:</span>
                <span style={{ fontWeight: 600, color: '#0070ba' }}>Sandbox Orders v2</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>AI Diagnostic Engine:</span>
                <span style={{ fontWeight: 600, color: '#7c3aed' }}>Google Gemini Active</span>
              </div>
            </div>
          </div>

          <div
            style={{
              backgroundColor: '#ffffff',
              padding: '1.25rem',
              borderRadius: '8px',
              border: '1px solid #e2e8f0',
              boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
            }}
          >
            <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: '0 0 0.75rem 0', color: '#0f172a' }}>
              Quick Navigation
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <a
                href="/catalog"
                style={{
                  display: 'block',
                  padding: '0.5rem 0.75rem',
                  backgroundColor: '#f8fafc',
                  borderRadius: '6px',
                  color: '#0f172a',
                  textDecoration: 'none',
                  fontSize: '0.85rem',
                  fontWeight: 500,
                }}
              >
                📦 Manage Catalog Products →
              </a>
              <a
                href="/inspection"
                style={{
                  display: 'block',
                  padding: '0.5rem 0.75rem',
                  backgroundColor: '#f8fafc',
                  borderRadius: '6px',
                  color: '#0f172a',
                  textDecoration: 'none',
                  fontSize: '0.85rem',
                  fontWeight: 500,
                }}
              >
                🔬 Run Storefront Inspection →
              </a>
              <a
                href="/corrections"
                style={{
                  display: 'block',
                  padding: '0.5rem 0.75rem',
                  backgroundColor: '#f8fafc',
                  borderRadius: '6px',
                  color: '#0f172a',
                  textDecoration: 'none',
                  fontSize: '0.85rem',
                  fontWeight: 500,
                }}
              >
                ⚖️ Review Correction Proposals →
              </a>
              <a
                href="/checkout"
                style={{
                  display: 'block',
                  padding: '0.5rem 0.75rem',
                  backgroundColor: '#f8fafc',
                  borderRadius: '6px',
                  color: '#0f172a',
                  textDecoration: 'none',
                  fontSize: '0.85rem',
                  fontWeight: 500,
                }}
              >
                🛒 Test PayPal Checkout Preflight →
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
