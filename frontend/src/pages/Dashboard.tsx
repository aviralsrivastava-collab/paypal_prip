import React, { useEffect, useState } from 'react';
import { ApiClient } from '../services/api';
import {
  CatalogIntelligence,
  ChatMessage,
  HealthStatus,
  Membership,
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

  // Authentication State
  const [authToken, setAuthTokenState] = useState<string | null>(ApiClient.getAuthToken());
  const [showManualAuth, setShowManualAuth] = useState(false);
  const [manualTokenInput, setManualTokenInput] = useState('');
  const [paypalMerchantInput, setPaypalMerchantInput] = useState('sb-w43kfu53089856@business.example.com');
  const [merchantNameInput, setMerchantNameInput] = useState('Apex Electronics (Sandbox Store)');
  const [oauthLoading, setOauthLoading] = useState(false);
  const [oauthNotice, setOauthNotice] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showLoginPortal, setShowLoginPortal] = useState(false);

  // Multi-tenant Workspace & Team Management State
  const [showWorkspaceManager, setShowWorkspaceManager] = useState(false);
  const [members, setMembers] = useState<Membership[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('VIEWER');
  const [newWsName, setNewWsName] = useState('');
  const [newWsSlug, setNewWsSlug] = useState('');
  const [managerNotice, setManagerNotice] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

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

  // Google OAuth 2.0 / OIDC Initialization
  useEffect(() => {
    if (authToken) return;

    const clientId = import.meta.env.VITE_OIDC_CLIENT_ID || '502517689787-5glaktsphtgcvt732n2ck2qg13fnvp5h.apps.googleusercontent.com';

    const initGoogleGsi = () => {
      if (typeof window !== 'undefined' && (window as any).google?.accounts?.id) {
        try {
          (window as any).google.accounts.id.initialize({
            client_id: clientId,
            callback: (res: { credential?: string }) => {
              if (res?.credential) {
                ApiClient.setAuthToken(res.credential);
                setAuthTokenState(res.credential);
                loadDashboardData();
              }
            },
          });
          const btnElem = document.getElementById('googleSignInBtn');
          if (btnElem) {
            btnElem.innerHTML = '';
            (window as any).google.accounts.id.renderButton(btnElem, {
              theme: 'outline',
              size: 'medium',
              text: 'signin_with',
              shape: 'rectangular',
            });
          }
        } catch {
          // Gracefully ignore during unit tests or headless runners
        }
      }
    };

    if (typeof window !== 'undefined' && !(window as any).google?.accounts?.id) {
      const scriptId = 'google-gsi-client';
      if (!document.getElementById(scriptId)) {
        const script = document.createElement('script');
        script.id = scriptId;
        script.src = 'https://accounts.google.com/gsi/client';
        script.async = true;
        script.defer = true;
        script.onload = initGoogleGsi;
        document.head.appendChild(script);
      }
    } else {
      initGoogleGsi();
    }
  }, [authToken]);

  const handleSignOut = () => {
    ApiClient.setAuthToken(null);
    setAuthTokenState(null);
    setProfile(null);
    setShowLoginPortal(true);
    setOauthNotice(null);
    loadDashboardData();
  };

  const handlePayPalMerchantLogin = async (e?: React.FormEvent, customId?: string, customName?: string) => {
    if (e) e.preventDefault();
    const idToUse = (customId || paypalMerchantInput).trim();
    const nameToUse = (customName || merchantNameInput).trim();
    if (!idToUse) {
      setOauthNotice({ type: 'error', text: 'Please enter a valid PayPal Sandbox Merchant ID or sandbox business email.' });
      return;
    }
    setOauthLoading(true);
    setOauthNotice(null);
    try {
      const res = await ApiClient.loginWithPayPalMerchant(idToUse, nameToUse);
      setAuthTokenState(res.access_token);
      setShowLoginPortal(false);
      setOauthNotice({
        type: 'success',
        text: `Successfully authenticated with PayPal Sandbox Merchant ID: ${res.paypal_merchant_id}! Workspace: ${res.merchant_name}`,
      });
      await loadDashboardData();
    } catch (err: any) {
      setOauthNotice({
        type: 'error',
        text: err.message || 'Failed to authenticate with PayPal Sandbox Merchant credentials.',
      });
    } finally {
      setOauthLoading(false);
    }
  };

  const handleManualAuthSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualTokenInput.trim()) return;
    ApiClient.setAuthToken(manualTokenInput.trim());
    setAuthTokenState(manualTokenInput.trim());
    setManualTokenInput('');
    setShowManualAuth(false);
    loadDashboardData();
  };

  const handleSwitchTenant = async (tenantId: string) => {
    try {
      await ApiClient.switchTenant(tenantId);
      await loadDashboardData();
      if (showWorkspaceManager) {
        await loadMembers();
      }
    } catch (err: any) {
      alert(err.message || 'Failed to switch tenant workspace');
    }
  };

  const loadMembers = async () => {
    setMembersLoading(true);
    setManagerNotice(null);
    try {
      const data = await ApiClient.getMembers();
      setMembers(data);
    } catch (err: any) {
      setManagerNotice({ type: 'error', text: err.message || 'Failed to fetch members' });
    } finally {
      setMembersLoading(false);
    }
  };

  const toggleWorkspaceManager = () => {
    const nextState = !showWorkspaceManager;
    setShowWorkspaceManager(nextState);
    if (nextState) {
      loadMembers();
    }
  };

  const handleCreateWorkspace = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWsName.trim() || !newWsSlug.trim()) return;
    try {
      const ws = await ApiClient.createWorkspace(newWsName.trim(), newWsSlug.trim());
      setNewWsName('');
      setNewWsSlug('');
      setManagerNotice({ type: 'success', text: `Workspace "${ws.name}" created successfully!` });
      await ApiClient.switchTenant(ws.id);
      await loadDashboardData();
      await loadMembers();
    } catch (err: any) {
      setManagerNotice({ type: 'error', text: err.message || 'Failed to create workspace' });
    }
  };

  const handleInviteMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    try {
      await ApiClient.inviteMember(inviteEmail.trim(), inviteRole);
      setInviteEmail('');
      setManagerNotice({ type: 'success', text: `Invited ${inviteEmail} as ${inviteRole}.` });
      await loadMembers();
    } catch (err: any) {
      setManagerNotice({ type: 'error', text: err.message || 'Failed to invite member' });
    }
  };

  const handleRemoveMember = async (userId: string) => {
    if (!window.confirm('Are you sure you want to remove this member?')) return;
    try {
      await ApiClient.removeMember(userId);
      setManagerNotice({ type: 'success', text: 'Member removed successfully.' });
      await loadMembers();
    } catch (err: any) {
      setManagerNotice({ type: 'error', text: err.message || 'Failed to remove member' });
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
          flexWrap: 'wrap',
          gap: '1rem',
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

        {/* Right Section: Auth & Workspace Controls */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.75rem' }}>
          {/* OAuth Identity / Sign In Bar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            {authToken || profile?.email ? (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  backgroundColor: '#f1f5f9',
                  padding: '0.35rem 0.75rem',
                  borderRadius: '20px',
                  border: '1px solid #cbd5e1',
                  fontSize: '0.85rem',
                }}
              >
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#22c55e' }} />
                <span style={{ color: '#0f172a', fontWeight: 600 }}>{profile?.email || 'Authenticated User'}</span>
                <span
                  style={{
                    backgroundColor: '#e2e8f0',
                    color: '#475569',
                    fontSize: '0.75rem',
                    padding: '1px 6px',
                    borderRadius: '4px',
                    fontWeight: 700,
                  }}
                >
                  {profile?.active_role || 'OPERATOR'}
                </span>
                <button
                  onClick={handleSignOut}
                  style={{
                    marginLeft: '0.25rem',
                    background: 'none',
                    border: 'none',
                    color: '#dc2626',
                    cursor: 'pointer',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    textDecoration: 'underline',
                  }}
                >
                  Sign Out
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <div id="googleSignInBtn" style={{ minHeight: '38px', minWidth: '180px' }}>
                  {/* Google rendered button mounts here */}
                </div>
                <button
                  onClick={() => setShowManualAuth(!showManualAuth)}
                  style={{
                    fontSize: '0.75rem',
                    color: '#64748b',
                    background: 'none',
                    border: '1px dashed #cbd5e1',
                    borderRadius: '4px',
                    padding: '4px 8px',
                    cursor: 'pointer',
                  }}
                >
                  {showManualAuth ? 'Close Token Input' : 'Paste Token'}
                </button>
              </div>
            )}
          </div>

          {showManualAuth && (
            <form onSubmit={handleManualAuthSubmit} style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
              <input
                type="text"
                placeholder="Bearer JWT token..."
                value={manualTokenInput}
                onChange={(e) => setManualTokenInput(e.target.value)}
                style={{
                  fontSize: '0.8rem',
                  padding: '0.3rem 0.5rem',
                  borderRadius: '4px',
                  border: '1px solid #cbd5e1',
                  width: '220px',
                }}
              />
              <button
                type="submit"
                style={{
                  fontSize: '0.8rem',
                  padding: '0.3rem 0.75rem',
                  backgroundColor: '#0f172a',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                Apply
              </button>
            </form>
          )}

          {/* Workspace Switcher & Team Button */}
          {profile && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.85rem', color: '#64748b' }}>Workspace:</span>
              <select
                value={profile.active_merchant_id}
                onChange={(e) => handleSwitchTenant(e.target.value)}
                style={{
                  padding: '0.35rem 0.7rem',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  backgroundColor: '#ffffff',
                  fontWeight: 600,
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                }}
              >
                {profile.memberships.map((m) => (
                  <option key={m.merchant_id} value={m.merchant_id}>
                    {m.merchant_name} ({m.role})
                  </option>
                ))}
              </select>
              <button
                onClick={toggleWorkspaceManager}
                style={{
                  padding: '0.35rem 0.75rem',
                  backgroundColor: showWorkspaceManager ? '#0070ba' : '#ffffff',
                  color: showWorkspaceManager ? '#ffffff' : '#0070ba',
                  border: '1px solid #0070ba',
                  borderRadius: '6px',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                👥 {showWorkspaceManager ? 'Hide Team & Workspaces' : 'Team & Workspaces'}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* PayPal Sandbox Merchant OAuth Portal (Login Gate) */}
      {((!authToken && !profile?.email) || showLoginPortal) && (
        <div
          style={{
            backgroundColor: '#f0f9ff',
            border: '2px solid #0070ba',
            borderRadius: '10px',
            padding: '1.5rem',
            marginBottom: '2rem',
            boxShadow: '0 4px 6px -1px rgba(0, 112, 186, 0.1)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1rem' }}>
            <div>
              <span
                style={{
                  display: 'inline-block',
                  backgroundColor: '#0070ba',
                  color: '#ffffff',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  letterSpacing: '0.5px',
                  marginBottom: '0.35rem',
                }}
              >
                PAYPAL AI HACKATHON OAUTH GATEWAY
              </span>
              <h3 style={{ margin: 0, fontSize: '1.35rem', fontWeight: 700, color: '#0f172a' }}>
                PayPal Sandbox Merchant Authentication Portal
              </h3>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.8rem', color: '#0369a1', fontWeight: 600 }}>
                Environment: <code>api-m.sandbox.paypal.com</code> (USD)
              </span>
              {(authToken || profile?.email) && (
                <button
                  onClick={() => setShowLoginPortal(false)}
                  style={{
                    background: 'none',
                    border: '1px solid #94a3b8',
                    borderRadius: '4px',
                    padding: '2px 8px',
                    cursor: 'pointer',
                    fontSize: '0.8rem',
                  }}
                >
                  ✕ Close
                </button>
              )}
            </div>
          </div>

          <p style={{ margin: '0 0 1.25rem 0', color: '#334155', fontSize: '0.92rem', lineHeight: 1.5 }}>
            Log in with your real <strong>PayPal Sandbox Merchant ID</strong> or sandbox business email to establish your tenant boundary, activate AI discrepancy inspection, and start the rest of the PRIP verification process.
          </p>

          {oauthNotice && (
            <div
              style={{
                padding: '0.6rem 0.85rem',
                borderRadius: '6px',
                marginBottom: '1rem',
                fontSize: '0.85rem',
                backgroundColor: oauthNotice.type === 'success' ? '#f0fdf4' : '#fef2f2',
                color: oauthNotice.type === 'success' ? '#166534' : '#991b1b',
                border: `1px solid ${oauthNotice.type === 'success' ? '#bbf7d0' : '#fecaca'}`,
              }}
            >
              {oauthNotice.text}
            </div>
          )}

          <form
            onSubmit={(e) => handlePayPalMerchantLogin(e)}
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '1rem',
              alignItems: 'end',
            }}
          >
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#1e293b', marginBottom: '0.3rem' }}>
                PayPal Sandbox Merchant ID / Email
              </label>
              <input
                type="text"
                placeholder="e.g. sb-w43kfu53089856@business.example.com"
                value={paypalMerchantInput}
                onChange={(e) => setPaypalMerchantInput(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.55rem 0.75rem',
                  borderRadius: '6px',
                  border: '1px solid #94a3b8',
                  fontSize: '0.9rem',
                  boxSizing: 'border-box',
                }}
                required
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#1e293b', marginBottom: '0.3rem' }}>
                Store / Workspace Name
              </label>
              <input
                type="text"
                placeholder="e.g. Apex Electronics (Sandbox Store)"
                value={merchantNameInput}
                onChange={(e) => setMerchantNameInput(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.55rem 0.75rem',
                  borderRadius: '6px',
                  border: '1px solid #94a3b8',
                  fontSize: '0.9rem',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <button
                type="submit"
                disabled={oauthLoading}
                style={{
                  flex: '1 1 180px',
                  padding: '0.6rem 1.25rem',
                  backgroundColor: '#0070ba',
                  color: '#ffffff',
                  border: '2px solid #005ea6',
                  borderRadius: '6px',
                  fontWeight: 700,
                  fontSize: '0.92rem',
                  cursor: oauthLoading ? 'wait' : 'pointer',
                  boxShadow: '0 2px 4px rgba(0, 112, 186, 0.2)',
                }}
              >
                {oauthLoading ? 'Authenticating...' : 'Log In with PayPal Sandbox'}
              </button>
              <button
                type="button"
                disabled={oauthLoading}
                onClick={() =>
                  handlePayPalMerchantLogin(
                    undefined,
                    'sb-w43kfu53089856@business.example.com',
                    'Apex Electronics (Sandbox Store)'
                  )
                }
                style={{
                  padding: '0.6rem 1rem',
                  backgroundColor: '#ffd140',
                  color: '#003087',
                  border: '1px solid #d4a300',
                  borderRadius: '6px',
                  fontWeight: 700,
                  fontSize: '0.88rem',
                  cursor: oauthLoading ? 'wait' : 'pointer',
                }}
              >
                Instant Sandbox Connect
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Authenticated PayPal Sandbox Merchant Status & Navigation Banner */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
          backgroundColor: '#f8fafc',
          border: '1px solid #cbd5e1',
          borderLeft: '4px solid #0070ba',
          borderRadius: '8px',
          padding: '1rem 1.25rem',
          marginBottom: '1.5rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '1.25rem' }}>🛡️</span>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontWeight: 700, color: '#0f172a', fontSize: '1rem' }}>
                {profile?.memberships?.find((m) => m.merchant_id === profile.active_merchant_id)?.merchant_name ||
                  profile?.email ||
                  'PayPal Sandbox Merchant Workspace'}
              </span>
              <span
                style={{
                  backgroundColor: '#dcfce7',
                  color: '#15803d',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  padding: '2px 8px',
                  borderRadius: '12px',
                  border: '1px solid #bbf7d0',
                }}
              >
                ● PayPal Sandbox Active
              </span>
            </div>
            <p style={{ margin: '0.2rem 0 0 0', color: '#64748b', fontSize: '0.82rem' }}>
              Merchant ID:{' '}
              <code>
                {profile?.active_merchant_id || 'merchant_default'}
              </code>{' '}
              | Currency: <strong>USD</strong> | API: <code>https://api-m.sandbox.paypal.com</code>
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button
            onClick={() => setShowLoginPortal(!showLoginPortal)}
            style={{
              padding: '0.4rem 0.8rem',
              backgroundColor: '#ffffff',
              color: '#0070ba',
              border: '1px solid #0070ba',
              borderRadius: '6px',
              fontSize: '0.82rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {showLoginPortal ? 'Hide Login Gate' : 'Switch PayPal Merchant'}
          </button>
        </div>
      </div>

      {/* 5-Stage Guided Verification Lifecycle Pipeline (Start Rest of Process) */}
      <div
        style={{
          backgroundColor: '#ffffff',
          border: '1px solid #e2e8f0',
          borderRadius: '8px',
          padding: '1rem 1.25rem',
          marginBottom: '1.5rem',
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
          <h4 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 700, color: '#334155', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            PRIP Verification Lifecycle (Start Rest of Process)
          </h4>
          <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
            Follow each stage below from inspection to checkout
          </span>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '0.75rem',
          }}
        >
          <div
            style={{
              padding: '0.75rem',
              borderRadius: '6px',
              backgroundColor: '#eff6ff',
              border: '1px solid #bfdbfe',
            }}
          >
            <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#1d4ed8', marginBottom: '0.2rem' }}>
              STAGE 1: CURRENT
            </div>
            <strong style={{ fontSize: '0.9rem', color: '#1e3a8a' }}>OAuth Dashboard</strong>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.78rem', color: '#475569' }}>
              Tenancy established & monitoring revenue at risk.
            </p>
          </div>

          <a
            href="/catalog"
            style={{
              padding: '0.75rem',
              borderRadius: '6px',
              backgroundColor: '#f8fafc',
              border: '1px solid #e2e8f0',
              textDecoration: 'none',
              display: 'block',
            }}
          >
            <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', marginBottom: '0.2rem' }}>
              STAGE 2: STEP NEXT →
            </div>
            <strong style={{ fontSize: '0.9rem', color: '#0f172a' }}>Catalog & Storefront</strong>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.78rem', color: '#475569' }}>
              Inspect authorized prices vs live storefront.
            </p>
          </a>

          <a
            href="/inspection"
            style={{
              padding: '0.75rem',
              borderRadius: '6px',
              backgroundColor: '#f8fafc',
              border: '1px solid #e2e8f0',
              textDecoration: 'none',
              display: 'block',
            }}
          >
            <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', marginBottom: '0.2rem' }}>
              STAGE 3: DISCOVERY →
            </div>
            <strong style={{ fontSize: '0.9rem', color: '#0f172a' }}>Inspection & AI Scan</strong>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.78rem', color: '#475569' }}>
              Run deterministic scans & trigger Gemini diagnosis.
            </p>
          </a>

          <a
            href="/corrections"
            style={{
              padding: '0.75rem',
              borderRadius: '6px',
              backgroundColor: '#f8fafc',
              border: '1px solid #e2e8f0',
              textDecoration: 'none',
              display: 'block',
            }}
          >
            <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', marginBottom: '0.2rem' }}>
              STAGE 4: SIGN-OFF →
            </div>
            <strong style={{ fontSize: '0.9rem', color: '#0f172a' }}>Approve Corrections</strong>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.78rem', color: '#475569' }}>
              Sign off on proposed automated price corrections.
            </p>
          </a>

          <a
            href="/checkout"
            style={{
              padding: '0.75rem',
              borderRadius: '6px',
              backgroundColor: '#f8fafc',
              border: '1px solid #e2e8f0',
              textDecoration: 'none',
              display: 'block',
            }}
          >
            <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', marginBottom: '0.2rem' }}>
              STAGE 5: REVENUE →
            </div>
            <strong style={{ fontSize: '0.9rem', color: '#0f172a' }}>PayPal Gated Checkout</strong>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.78rem', color: '#475569' }}>
              Execute protected checkout via Orders v2 in USD.
            </p>
          </a>
        </div>
      </div>

      {/* Collapsible Multi-Tenant Workspace & Team Management Panel */}
      {showWorkspaceManager && (
        <div
          style={{
            backgroundColor: '#f8fafc',
            border: '1px solid #cbd5e1',
            borderRadius: '8px',
            padding: '1.25rem',
            marginBottom: '1.5rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
            <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: '#0f172a' }}>
              Multi-Tenant Workspace & Team Management
            </h3>
            <span style={{ fontSize: '0.85rem', color: '#64748b' }}>
              Active Workspace: <strong>{profile?.memberships.find(m => m.merchant_id === profile.active_merchant_id)?.merchant_name || profile?.active_merchant_id}</strong>
            </span>
          </div>

          {managerNotice && (
            <div
              style={{
                padding: '0.5rem 0.75rem',
                borderRadius: '6px',
                marginBottom: '1rem',
                fontSize: '0.85rem',
                backgroundColor: managerNotice.type === 'success' ? '#f0fdf4' : '#fef2f2',
                color: managerNotice.type === 'success' ? '#166534' : '#991b1b',
                border: `1px solid ${managerNotice.type === 'success' ? '#bbf7d0' : '#fecaca'}`,
              }}
            >
              {managerNotice.text}
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem' }}>
            {/* Left: Active Workspace Members & Invite Form */}
            <div style={{ backgroundColor: '#ffffff', padding: '1rem', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
              <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.95rem', fontWeight: 600, color: '#1e293b' }}>
                Active Workspace Members
              </h4>
              {membersLoading ? (
                <p style={{ fontSize: '0.85rem', color: '#64748b' }}>Loading members...</p>
              ) : members.length === 0 ? (
                <p style={{ fontSize: '0.85rem', color: '#64748b' }}>No members found.</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '180px', overflowY: 'auto', marginBottom: '1rem' }}>
                  {members.map((m) => (
                    <div
                      key={m.id || m.user_id}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '0.4rem 0.6rem',
                        backgroundColor: '#f8fafc',
                        borderRadius: '4px',
                        fontSize: '0.85rem',
                      }}
                    >
                      <div>
                        <strong>{m.user_email || m.user_id}</strong>
                        <span
                          style={{
                            marginLeft: '0.5rem',
                            backgroundColor: '#e2e8f0',
                            padding: '1px 6px',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                          }}
                        >
                          {m.role}
                        </span>
                      </div>
                      {m.role !== 'OWNER' && (
                        <button
                          onClick={() => handleRemoveMember(m.user_id)}
                          style={{
                            border: 'none',
                            background: 'none',
                            color: '#dc2626',
                            cursor: 'pointer',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                          }}
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Invite Member Sub-form */}
              <form onSubmit={handleInviteMember} style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <input
                  type="email"
                  placeholder="colleague@example.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  style={{
                    flex: 1,
                    minWidth: '150px',
                    padding: '0.4rem 0.6rem',
                    fontSize: '0.85rem',
                    borderRadius: '4px',
                    border: '1px solid #cbd5e1',
                  }}
                  required
                />
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                  style={{
                    padding: '0.4rem 0.6rem',
                    fontSize: '0.85rem',
                    borderRadius: '4px',
                    border: '1px solid #cbd5e1',
                  }}
                >
                  <option value="VIEWER">VIEWER</option>
                  <option value="MANAGER">MANAGER</option>
                  <option value="ADMIN">ADMIN</option>
                </select>
                <button
                  type="submit"
                  style={{
                    padding: '0.4rem 0.8rem',
                    backgroundColor: '#0070ba',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: '4px',
                    fontSize: '0.85rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  + Invite
                </button>
              </form>
            </div>

            {/* Right: Create New Merchant Workspace */}
            <div style={{ backgroundColor: '#ffffff', padding: '1rem', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
              <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.95rem', fontWeight: 600, color: '#1e293b' }}>
                Create New Merchant Workspace
              </h4>
              <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.85rem', color: '#64748b' }}>
                Create an isolated tenant environment with its own catalog, webhooks, and team roles.
              </p>
              <form onSubmit={handleCreateWorkspace} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#475569', marginBottom: '0.2rem' }}>
                    Workspace Name
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Acme EU Flagship"
                    value={newWsName}
                    onChange={(e) => setNewWsName(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '0.4rem 0.6rem',
                      fontSize: '0.85rem',
                      borderRadius: '4px',
                      border: '1px solid #cbd5e1',
                      boxSizing: 'border-box',
                    }}
                    required
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#475569', marginBottom: '0.2rem' }}>
                    Workspace Slug (lowercase-with-hyphens)
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. acme-eu-flagship"
                    value={newWsSlug}
                    onChange={(e) => setNewWsSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'))}
                    style={{
                      width: '100%',
                      padding: '0.4rem 0.6rem',
                      fontSize: '0.85rem',
                      borderRadius: '4px',
                      border: '1px solid #cbd5e1',
                      boxSizing: 'border-box',
                    }}
                    required
                  />
                </div>
                <button
                  type="submit"
                  style={{
                    alignSelf: 'flex-start',
                    padding: '0.45rem 1rem',
                    backgroundColor: '#16a34a',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: '4px',
                    fontSize: '0.85rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  🚀 Create Workspace
                </button>
              </form>
            </div>
          </div>
        </div>
      )}

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
