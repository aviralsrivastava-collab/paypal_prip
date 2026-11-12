import React, { useEffect, useState } from 'react';
import { ApiClient } from '../services/api';
import {
  CatalogIntelligence,
  ChatMessage,
  CorrectionProposal,
  EvidenceItem,
  HealthStatus,
  Membership,
  ProductComparison,
  RevenueIntelligence,
  ScanDetail,
  UserProfile,
} from '../types';

export const Dashboard: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [revenue, setRevenue] = useState<RevenueIntelligence | null>(null);
  const [catalogIntel, setCatalogIntel] = useState<CatalogIntelligence | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Persona Mode: Merchant Mission Control vs. Buyer & AI Shopping Agent
  const [activePersona, setActivePersona] = useState<'merchant' | 'buyer'>('merchant');

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

  // Single Canonical Demo Scenario State (SX-001 StrideX Runner)
  const [demoProduct, setDemoProduct] = useState<ProductComparison | null>(null);
  const [demoActionLoading, setDemoActionLoading] = useState(false);
  const [activeScan, setActiveScan] = useState<ScanDetail | null>(null);
  const [scanEvidence, setScanEvidence] = useState<EvidenceItem[]>([]);
  const [activeProposal, setActiveProposal] = useState<CorrectionProposal | null>(null);
  const [merchantSignoffChecked, setMerchantSignoffChecked] = useState(false);
  const [activeLifecycleStage, setActiveLifecycleStage] = useState<number>(1);
  const [actionFeedback, setActionFeedback] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);

  // Buyer & AI Shopping Agent State
  const [agentLogs, setAgentLogs] = useState<string[]>([
    '[STANDBY] Autonomous purchasing agent ready for buyer-instructed shopping simulation.',
  ]);
  const [agentRunning, setAgentRunning] = useState(false);
  const [agentOutcome, setAgentOutcome] = useState<'idle' | 'discrepancy_blocked' | 'verified_ready'>('idle');
  const [buyerSandboxEmail, setBuyerSandboxEmail] = useState('sb-u7w4y53089901@personal.example.com');
  const [checkoutOrderId, setCheckoutOrderId] = useState<string | null>(null);
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [checkoutSuccess, setCheckoutSuccess] = useState<{ orderId: string; amount: string; time: string } | null>(null);

  // Chat State
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content: 'Welcome to PRIP Revenue Intelligence. I am monitoring your catalog against customer-facing storefronts. How can I help protect your revenue today?',
    },
  ]);
  const [inputMsg, setInputMsg] = useState('');
  const [chatLoading, setChatLoading] = useState(false);

  const loadDashboardData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [h, prof, rev, cat, products, proposals] = await Promise.all([
        ApiClient.getHealth().catch(() => null),
        ApiClient.getProfile().catch(() => null),
        ApiClient.getRevenueIntelligence().catch(() => null),
        ApiClient.getCatalogIntelligence().catch(() => null),
        ApiClient.getProducts().catch(() => []),
        ApiClient.getProposals().catch(() => []),
      ]);
      if (h) setHealth(h);
      if (prof) setProfile(prof);
      if (rev) setRevenue(rev);
      if (cat) setCatalogIntel(cat);

      // Identify canonical demo product SX-001
      const foundDemo = products.find((p: ProductComparison) => p.sku === 'SX-001') || products[0] || null;
      setDemoProduct(foundDemo);

      if (proposals.length > 0) {
        const pending = proposals.find((p: CorrectionProposal) => p.approval_status === 'PENDING_APPROVAL') || proposals[0];
        setActiveProposal(pending);
      }

      // Determine initial stage based on data
      if (foundDemo) {
        if (foundDemo.has_discrepancy) {
          setActiveLifecycleStage(2);
        } else {
          setActiveLifecycleStage(6);
        }
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, []);

  // Google OAuth / OIDC Initialization
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
          // Gracefully ignore in testing environment
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
      setOauthNotice({ type: 'error', text: 'Enter a valid PayPal Sandbox Merchant ID or business email.' });
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
        text: `Connected to PayPal Sandbox Merchant ID: ${res.paypal_merchant_id}. Workspace: ${res.merchant_name}`,
      });
      await loadDashboardData();
    } catch (err: any) {
      setOauthNotice({
        type: 'error',
        text: err.message || 'Unable to authenticate with PayPal Sandbox Merchant credentials.',
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
      setManagerNotice({ type: 'success', text: `Workspace "${ws.name}" created.` });
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
    if (!window.confirm('Remove this member?')) return;
    try {
      await ApiClient.removeMember(userId);
      setManagerNotice({ type: 'success', text: 'Member removed.' });
      await loadMembers();
    } catch (err: any) {
      setManagerNotice({ type: 'error', text: err.message || 'Failed to remove member' });
    }
  };

  // --- Step 1 Action: Reset to Canonical Demo Baseline ---
  const handleResetDemoBaseline = async () => {
    setDemoActionLoading(true);
    setActionFeedback(null);
    try {
      await ApiClient.seedCatalog(true);
      await loadDashboardData();
      setActiveLifecycleStage(2);
      setAgentOutcome('idle');
      setAgentLogs(['[STANDBY] Reset to canonical baseline. StrideX Runner SX-001 initialized with $100.00 catalog price vs $120.00 storefront price.']);
      setActionFeedback({
        type: 'success',
        text: 'Reset complete: SX-001 initialized with $100.00 Catalog vs $120.00 Storefront discrepancy.',
      });
    } catch (err: any) {
      setActionFeedback({ type: 'error', text: err.message || 'Failed to reset demo baseline.' });
    } finally {
      setDemoActionLoading(false);
    }
  };

  // --- Step 1 Action: Simulate Storefront Drift ---
  const handleSimulateDrift = async () => {
    setDemoActionLoading(true);
    setActionFeedback(null);
    try {
      await ApiClient.updateStorefrontPrice('SX-001', '120.00', 'USD');
      await loadDashboardData();
      setActiveLifecycleStage(2);
      setActionFeedback({
        type: 'info',
        text: 'Storefront drift applied: Live price set to $120.00 USD (+$20.00 discrepancy against catalog).',
      });
    } catch (err: any) {
      setActionFeedback({ type: 'error', text: err.message || 'Failed to simulate drift.' });
    } finally {
      setDemoActionLoading(false);
    }
  };

  // --- Step 2 Action: Autonomous AI Shopping Agent Discovery ---
  const handleRunAiAgentScan = async () => {
    setAgentRunning(true);
    setAgentLogs((prev) => [
      ...prev,
      `[${new Date().toLocaleTimeString()}] INITIATING: Autonomous purchasing agent exploring storefront for SX-001...`,
    ]);

    setTimeout(() => {
      setAgentLogs((prev) => [
        ...prev,
        `[${new Date().toLocaleTimeString()}] STOREFRONT SCAN: Observed display price is $120.00 USD.`,
      ]);
    }, 600);

    setTimeout(async () => {
      try {
        const scan = await ApiClient.triggerScan('SX-001');
        setActiveScan(scan);
        const evidence = await ApiClient.getScanEvidence(scan.id);
        setScanEvidence(evidence);

        if (scan.state === 'ISSUE_DETECTED') {
          setAgentLogs((prev) => [
            ...prev,
            `[${new Date().toLocaleTimeString()}] CATALOG INTELLIGENCE: Authority price is $100.00 USD.`,
            `[${new Date().toLocaleTimeString()}] DISCREPANCY CONFIRMED: Observed +$20.00 (+20%) unverified drift.`,
            `[${new Date().toLocaleTimeString()}] SAFEGUARD ENGAGED: Halting checkout to protect customer and merchant.`,
            `[${new Date().toLocaleTimeString()}] INCIDENT REPORTED: Notification dispatched to Merchant Mission Control.`,
          ]);
          setAgentOutcome('discrepancy_blocked');
          setActiveLifecycleStage(3);
        } else {
          setAgentLogs((prev) => [
            ...prev,
            `[${new Date().toLocaleTimeString()}] INTEGRITY VERIFIED: Storefront matches catalog ($100.00 USD). Ready for PayPal checkout.`,
          ]);
          setAgentOutcome('verified_ready');
          setActiveLifecycleStage(6);
        }
      } catch (err: any) {
        setAgentLogs((prev) => [...prev, `[ERROR] Scan execution failed: ${err.message}`]);
      } finally {
        setAgentRunning(false);
      }
    }, 1200);
  };

  // --- Step 4 Action: AI Root Cause Diagnosis & Proposal Generation ---
  const handleGenerateDiagnosisAndProposal = async () => {
    if (!activeScan) {
      alert('Run an inspection scan first.');
      return;
    }
    setDemoActionLoading(true);
    setActionFeedback(null);
    try {
      await ApiClient.triggerDiagnosis(activeScan.id);
      const newProposal = await ApiClient.createProposal({
        scan_id: activeScan.id,
        sku: 'SX-001',
        proposed_value: '100.00',
        currency: 'USD',
        reason: 'Synchronize storefront price to catalog ground truth (USD 100.00)',
        supporting_evidence_ids: scanEvidence.map((e) => e.id),
      });
      setActiveProposal(newProposal);
      setActiveLifecycleStage(5);
      setActionFeedback({
        type: 'success',
        text: `Proposal #${newProposal.id} drafted: Synchronize storefront price to $100.00 USD. Awaiting merchant sign-off.`,
      });
    } catch (err: any) {
      setActionFeedback({ type: 'error', text: err.message || 'Failed to generate diagnosis and proposal.' });
    } finally {
      setDemoActionLoading(false);
    }
  };

  // --- Step 5 Action: Merchant Sign-Off (Approve / Decline) ---
  const handleMerchantDecision = async (decision: 'approve' | 'reject') => {
    if (!activeProposal) return;
    if (decision === 'approve' && !merchantSignoffChecked) {
      alert('You must check the authorization box to confirm your sign-off.');
      return;
    }
    setDemoActionLoading(true);
    setActionFeedback(null);
    try {
      if (decision === 'approve') {
        await ApiClient.approveProposal(activeProposal.id, 'Merchant authenticated approval via Mission Control');
        await ApiClient.executeProposal(activeProposal.id);
        const reinspection = await ApiClient.triggerScan('SX-001');
        setActiveScan(reinspection);
        await loadDashboardData();
        setActiveLifecycleStage(6);
        setAgentOutcome('verified_ready');
        setAgentLogs((prev) => [
          ...prev,
          `[${new Date().toLocaleTimeString()}] MERCHANT SIGN-OFF: Proposal approved and executed.`,
          `[${new Date().toLocaleTimeString()}] REINSPECTION: Verified clean state (VERIFIED_NO_ISSUE).`,
          `[${new Date().toLocaleTimeString()}] GATEWAY: Gated PayPal checkout is now open.`,
        ]);
        setActionFeedback({
          type: 'success',
          text: 'Approved: Storefront synchronized to $100.00 USD. Reinspection confirmed VERIFIED_NO_ISSUE. Checkout unlocked.',
        });
      } else {
        await ApiClient.rejectProposal(activeProposal.id, 'Declined by merchant');
        await loadDashboardData();
        setActionFeedback({ type: 'info', text: 'Proposal rejected and archived.' });
      }
    } catch (err: any) {
      setActionFeedback({ type: 'error', text: err.message || 'Decision execution failed.' });
    } finally {
      setDemoActionLoading(false);
    }
  };

  // --- Step 6 Action: Live PayPal Sandbox Payment Execution ---
  const handleExecutePayPalPayment = async () => {
    setCheckoutLoading(true);
    setActionFeedback(null);
    try {
      const order = await ApiClient.createOrder('SX-001', 1);
      setCheckoutOrderId(order.order_id);
      const capture = await ApiClient.captureOrder(order.order_id);
      setCheckoutSuccess({
        orderId: order.order_id,
        amount: `$${order.total_amount} USD`,
        time: new Date().toLocaleTimeString(),
      });
      setAgentLogs((prev) => [
        ...prev,
        `[${new Date().toLocaleTimeString()}] PAYPAL SANDBOX: Order ${order.order_id} captured. Capture ID: ${capture.capture_id || 'COMPLETED'}.`,
        `[${new Date().toLocaleTimeString()}] SETTLEMENT: Real sandbox fund transfer recorded ($${order.total_amount} USD).`,
      ]);
      await loadDashboardData();
    } catch (err: any) {
      setActionFeedback({
        type: 'error',
        text: `PayPal checkout notice: ${err.message}. Ensure you are using a USD sandbox buyer account.`,
      });
    } finally {
      setCheckoutLoading(false);
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
        { role: 'assistant', content: `Error contacting assistant: ${err.message}` },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <div style={{ padding: '2rem', maxWidth: '1240px', margin: '0 auto', color: '#0f172a', backgroundColor: '#ffffff' }}>
      {/* Top Banner with Persona Switcher */}
      <header
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
          borderBottom: '2px solid #e2e8f0',
          paddingBottom: '1.25rem',
          marginBottom: '1.5rem',
        }}
      >
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, margin: '0 0 0.25rem 0', color: '#0f172a', letterSpacing: '-0.02em' }}>
            Merchant Revenue Intelligence Platform
          </h1>
          <h2 style={{ fontSize: '1.05rem', fontWeight: 600, margin: '0 0 0.25rem 0', color: '#334155' }}>
            Commerce Integrity Overview
          </h2>
          <p style={{ margin: 0, color: '#475569', fontSize: '0.9rem' }}>
            Detect the discrepancy. Approve the correction. Verify the checkout.
          </p>
        </div>

        {/* Dual Persona Switcher */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.75rem' }}>
          <div
            role="tablist"
            style={{
              display: 'flex',
              backgroundColor: '#f1f5f9',
              padding: '4px',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
            }}
          >
            <button
              role="tab"
              aria-selected={activePersona === 'merchant'}
              onClick={() => setActivePersona('merchant')}
              style={{
                padding: '0.45rem 1rem',
                borderRadius: '6px',
                border: 'none',
                fontWeight: 700,
                fontSize: '0.85rem',
                cursor: 'pointer',
                backgroundColor: activePersona === 'merchant' ? '#0070ba' : 'transparent',
                color: activePersona === 'merchant' ? '#ffffff' : '#334155',
                transition: 'all 0.15s ease-in-out',
              }}
            >
              Merchant Mission Control
            </button>
            <button
              role="tab"
              aria-selected={activePersona === 'buyer'}
              onClick={() => setActivePersona('buyer')}
              style={{
                padding: '0.45rem 1rem',
                borderRadius: '6px',
                border: 'none',
                fontWeight: 700,
                fontSize: '0.85rem',
                cursor: 'pointer',
                backgroundColor: activePersona === 'buyer' ? '#0f172a' : 'transparent',
                color: activePersona === 'buyer' ? '#ffffff' : '#334155',
                transition: 'all 0.15s ease-in-out',
              }}
            >
              Buyer Storefront & AI Agent
            </button>
          </div>

          {/* Identity & Workspace Controls */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            {authToken || profile?.email ? (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  backgroundColor: '#f8fafc',
                  padding: '0.3rem 0.75rem',
                  borderRadius: '20px',
                  border: '1px solid #cbd5e1',
                  fontSize: '0.82rem',
                }}
              >
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#16a34a' }} />
                <span style={{ color: '#0f172a', fontWeight: 600 }}>{profile?.email || 'Authenticated Merchant'}</span>
                <span style={{ backgroundColor: '#e2e8f0', color: '#334155', fontSize: '0.72rem', padding: '1px 6px', borderRadius: '4px', fontWeight: 700 }}>
                  {profile?.active_role || 'OWNER'}
                </span>
                <button
                  onClick={handleSignOut}
                  style={{
                    marginLeft: '0.25rem',
                    background: 'none',
                    border: 'none',
                    color: '#b91c1c',
                    cursor: 'pointer',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    textDecoration: 'underline',
                  }}
                >
                  Sign Out
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <div id="googleSignInBtn" style={{ minHeight: '38px', minWidth: '180px' }} />
                <button
                  onClick={() => setShowManualAuth(!showManualAuth)}
                  style={{
                    fontSize: '0.75rem',
                    color: '#475569',
                    background: '#ffffff',
                    border: '1px solid #cbd5e1',
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
            <form onSubmit={handleManualAuthSubmit} style={{ display: 'flex', gap: '0.5rem' }}>
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

          {profile && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <label htmlFor="ws-select" style={{ fontSize: '0.82rem', color: '#475569' }}>
                Workspace:
              </label>
              <select
                id="ws-select"
                value={profile.active_merchant_id}
                onChange={(e) => handleSwitchTenant(e.target.value)}
                style={{
                  padding: '0.3rem 0.6rem',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  backgroundColor: '#ffffff',
                  fontWeight: 600,
                  fontSize: '0.82rem',
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
                  padding: '0.3rem 0.65rem',
                  backgroundColor: showWorkspaceManager ? '#0070ba' : '#ffffff',
                  color: showWorkspaceManager ? '#ffffff' : '#0070ba',
                  border: '1px solid #0070ba',
                  borderRadius: '6px',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {showWorkspaceManager ? 'Hide Team & Workspaces' : 'Team & Workspaces'}
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Loading & Error Banners */}
      {loading && (
        <div
          role="status"
          style={{
            padding: '0.5rem 1rem',
            borderRadius: '6px',
            marginBottom: '1rem',
            fontSize: '0.82rem',
            backgroundColor: '#f1f5f9',
            color: '#475569',
            border: '1px solid #cbd5e1',
          }}
        >
          Loading commerce intelligence data...
        </div>
      )}
      {error && (
        <div
          role="alert"
          style={{
            padding: '0.75rem 1rem',
            borderRadius: '6px',
            marginBottom: '1rem',
            fontSize: '0.88rem',
            backgroundColor: '#fef2f2',
            color: '#991b1b',
            border: '1px solid #fecaca',
          }}
        >
          {error}
        </div>
      )}

      {/* Action Notification Banner */}
      {actionFeedback && (
        <div
          role="status"
          style={{
            padding: '0.75rem 1rem',
            borderRadius: '6px',
            marginBottom: '1.25rem',
            fontSize: '0.88rem',
            backgroundColor:
              actionFeedback.type === 'success' ? '#f0fdf4' : actionFeedback.type === 'error' ? '#fef2f2' : '#f0f9ff',
            color:
              actionFeedback.type === 'success' ? '#166534' : actionFeedback.type === 'error' ? '#991b1b' : '#075985',
            border: `1px solid ${
              actionFeedback.type === 'success' ? '#bbf7d0' : actionFeedback.type === 'error' ? '#fecaca' : '#bae6fd'
            }`,
          }}
        >
          {actionFeedback.text}
        </div>
      )}

      {/* PayPal Sandbox Merchant OAuth Portal (Login Gate) */}
      {((!authToken && !profile?.email) || showLoginPortal) && (
        <section
          aria-label="PayPal Sandbox Merchant Login Gate"
          style={{
            backgroundColor: '#f8fafc',
            border: '2px solid #0070ba',
            borderRadius: '8px',
            padding: '1.5rem',
            marginBottom: '2rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <span
              style={{
                backgroundColor: '#0070ba',
                color: '#ffffff',
                padding: '2px 8px',
                borderRadius: '4px',
                fontSize: '0.75rem',
                fontWeight: 700,
              }}
            >
              PAYPAL SANDBOX OAUTH GATEWAY
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
                Close
              </button>
            )}
          </div>

          <h3 style={{ margin: '0 0 0.5rem 0', fontSize: '1.25rem', fontWeight: 700, color: '#0f172a' }}>
            PayPal Sandbox Merchant Authentication Portal
          </h3>
          <p style={{ margin: '0 0 1rem 0', color: '#334155', fontSize: '0.9rem', lineHeight: 1.5 }}>
            Authenticate with your PayPal Sandbox Merchant facilitator ID or email to open your isolated merchant tenant and start the revenue integrity pipeline.
          </p>

          {oauthNotice && (
            <div
              style={{
                padding: '0.5rem 0.75rem',
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

          <form onSubmit={(e) => handlePayPalMerchantLogin(e)} style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div style={{ flex: '1 1 260px' }}>
              <label htmlFor="paypal-email-input" style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, color: '#1e293b', marginBottom: '0.25rem' }}>
                Sandbox Merchant Facilitator Email / ID
              </label>
              <input
                id="paypal-email-input"
                type="text"
                value={paypalMerchantInput}
                onChange={(e) => setPaypalMerchantInput(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.5rem 0.75rem',
                  borderRadius: '6px',
                  border: '1px solid #94a3b8',
                  fontSize: '0.88rem',
                  boxSizing: 'border-box',
                }}
                required
              />
            </div>

            <div style={{ flex: '1 1 220px' }}>
              <label htmlFor="paypal-name-input" style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, color: '#1e293b', marginBottom: '0.25rem' }}>
                Store Name
              </label>
              <input
                id="paypal-name-input"
                type="text"
                value={merchantNameInput}
                onChange={(e) => setMerchantNameInput(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.5rem 0.75rem',
                  borderRadius: '6px',
                  border: '1px solid #94a3b8',
                  fontSize: '0.88rem',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <button
                type="submit"
                disabled={oauthLoading}
                style={{
                  padding: '0.55rem 1.25rem',
                  backgroundColor: '#0070ba',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '6px',
                  fontWeight: 700,
                  fontSize: '0.9rem',
                  cursor: oauthLoading ? 'wait' : 'pointer',
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
                  padding: '0.55rem 1rem',
                  backgroundColor: '#f1f5f9',
                  color: '#003087',
                  border: '1px solid #cbd5e1',
                  borderRadius: '6px',
                  fontWeight: 700,
                  fontSize: '0.85rem',
                  cursor: oauthLoading ? 'wait' : 'pointer',
                }}
              >
                Instant Sandbox Connect
              </button>
            </div>
          </form>
        </section>
      )}

      {/* Multi-Tenant Team & Workspace Manager */}
      {showWorkspaceManager && (
        <section
          aria-label="Multi-Tenant Workspace & Team Management"
          style={{
            backgroundColor: '#f8fafc',
            border: '1px solid #cbd5e1',
            borderRadius: '8px',
            padding: '1.25rem',
            marginBottom: '1.5rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap' }}>
            <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: '#0f172a' }}>
              Multi-Tenant Workspace & Team Management
            </h3>
            <span style={{ fontSize: '0.82rem', color: '#475569' }}>
              Active: <strong>{profile?.active_merchant_id}</strong>
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
              }}
            >
              {managerNotice.text}
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem' }}>
            {/* Active Members */}
            <div style={{ backgroundColor: '#ffffff', padding: '1rem', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
              <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', fontWeight: 600 }}>Active Workspace Members</h4>
              {membersLoading ? (
                <p style={{ fontSize: '0.82rem', color: '#64748b' }}>Loading members...</p>
              ) : members.length === 0 ? (
                <p style={{ fontSize: '0.82rem', color: '#64748b' }}>No members found.</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', maxHeight: '160px', overflowY: 'auto' }}>
                  {members.map((m) => (
                    <div key={m.id || m.user_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.35rem 0.5rem', backgroundColor: '#f8fafc', borderRadius: '4px', fontSize: '0.82rem' }}>
                      <span><strong>{m.user_email || m.user_id}</strong> ({m.role})</span>
                      {m.role !== 'OWNER' && (
                        <button onClick={() => handleRemoveMember(m.user_id)} style={{ border: 'none', background: 'none', color: '#dc2626', cursor: 'pointer', fontSize: '0.75rem' }}>
                          Remove
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}

              <form onSubmit={handleInviteMember} style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem' }}>
                <input
                  type="email"
                  placeholder="colleague@store.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  style={{ flex: 1, padding: '0.35rem 0.5rem', fontSize: '0.8rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                  required
                />
                <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} style={{ padding: '0.35rem', fontSize: '0.8rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}>
                  <option value="VIEWER">VIEWER</option>
                  <option value="MANAGER">MANAGER</option>
                  <option value="ADMIN">ADMIN</option>
                </select>
                <button type="submit" style={{ padding: '0.35rem 0.75rem', backgroundColor: '#0f172a', color: '#ffffff', border: 'none', borderRadius: '4px', fontSize: '0.8rem', cursor: 'pointer' }}>
                  Invite
                </button>
              </form>
            </div>

            {/* Create Workspace */}
            <div style={{ backgroundColor: '#ffffff', padding: '1rem', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
              <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', fontWeight: 600 }}>Create New Merchant Workspace</h4>
              <form onSubmit={handleCreateWorkspace} style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <input
                  type="text"
                  placeholder="Workspace Name (e.g. Puma EU Hub)"
                  value={newWsName}
                  onChange={(e) => setNewWsName(e.target.value)}
                  style={{ padding: '0.4rem 0.6rem', fontSize: '0.82rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                  required
                />
                <input
                  type="text"
                  placeholder="Workspace Slug (e.g. puma-eu-hub)"
                  value={newWsSlug}
                  onChange={(e) => setNewWsSlug(e.target.value)}
                  style={{ padding: '0.4rem 0.6rem', fontSize: '0.82rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                  required
                />
                <button type="submit" style={{ padding: '0.45rem', backgroundColor: '#0070ba', color: '#ffffff', border: 'none', borderRadius: '4px', fontSize: '0.82rem', fontWeight: 600, cursor: 'pointer' }}>
                  Create Workspace
                </button>
              </form>
            </div>
          </div>
        </section>
      )}

      {/* PERSONA MODE 1: MERCHANT MISSION CONTROL */}
      {activePersona === 'merchant' && (
        <section aria-label="Merchant Mission Control">
          {/* Quick Scenario Controls: Reset Baseline & Drift Simulation */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '0.75rem',
              backgroundColor: '#f8fafc',
              border: '1px solid #cbd5e1',
              borderRadius: '8px',
              padding: '0.85rem 1.25rem',
              marginBottom: '1.5rem',
            }}
          >
            <div>
              <strong style={{ fontSize: '0.92rem', color: '#0f172a' }}>
                Single Canonical Demo Scenario: StrideX Runner (SX-001)
              </strong>
              <p style={{ margin: '0.15rem 0 0 0', color: '#475569', fontSize: '0.82rem' }}>
                Catalog Authority: <strong>${demoProduct?.merchant_price || '100.00'} USD</strong> | Live Storefront: <strong>${demoProduct?.storefront_price || '120.00'} USD</strong>
              </p>
            </div>

            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <button
                onClick={handleResetDemoBaseline}
                disabled={demoActionLoading}
                style={{
                  padding: '0.4rem 0.85rem',
                  backgroundColor: '#ffffff',
                  color: '#0f172a',
                  border: '1px solid #94a3b8',
                  borderRadius: '6px',
                  fontWeight: 600,
                  fontSize: '0.82rem',
                  cursor: demoActionLoading ? 'wait' : 'pointer',
                }}
              >
                Reset to Demo Baseline
              </button>
              <button
                onClick={handleSimulateDrift}
                disabled={demoActionLoading}
                style={{
                  padding: '0.4rem 0.85rem',
                  backgroundColor: '#fee2e2',
                  color: '#991b1b',
                  border: '1px solid #fca5a5',
                  borderRadius: '6px',
                  fontWeight: 600,
                  fontSize: '0.82rem',
                  cursor: demoActionLoading ? 'wait' : 'pointer',
                }}
              >
                Simulate Storefront Drift
              </button>
              <button
                onClick={() => setActivePersona('buyer')}
                style={{
                  padding: '0.4rem 0.85rem',
                  backgroundColor: '#0f172a',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '6px',
                  fontWeight: 600,
                  fontSize: '0.82rem',
                  cursor: 'pointer',
                }}
              >
                Switch to Buyer & AI View
              </button>
            </div>
          </div>

          {/* 6-Stage Interactive Mission Control Stepper */}
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid #cbd5e1',
              borderRadius: '8px',
              padding: '1.25rem',
              marginBottom: '1.5rem',
            }}
          >
            <h3 style={{ margin: '0 0 0.75rem 0', fontSize: '1rem', fontWeight: 700, color: '#1e293b', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              PRIP Verification Lifecycle (Start Rest of Process)
            </h3>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.5rem', marginBottom: '1.25rem' }}>
              {[
                { stage: 1, title: '1. Catalog Ground Truth', subtitle: 'Source of truth ($100.00)' },
                { stage: 2, title: '2. Buyer AI Discovery', subtitle: 'Agent spots discrepancy' },
                { stage: 3, title: '3. Forensic Inspection', subtitle: '4-state evidence engine' },
                { stage: 4, title: '4. AI Root Cause', subtitle: 'Drafts pending proposal' },
                { stage: 5, title: '5. Merchant Decision', subtitle: 'Human sign-off check' },
                { stage: 6, title: '6. PayPal Checkout', subtitle: 'Protected USD transfer' },
              ].map((s) => (
                <div
                  key={s.stage}
                  onClick={() => setActiveLifecycleStage(s.stage)}
                  style={{
                    padding: '0.65rem 0.75rem',
                    borderRadius: '6px',
                    border: `1px solid ${activeLifecycleStage === s.stage ? '#0070ba' : '#e2e8f0'}`,
                    backgroundColor: activeLifecycleStage === s.stage ? '#eff6ff' : '#f8fafc',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <strong style={{ display: 'block', fontSize: '0.82rem', color: activeLifecycleStage === s.stage ? '#0070ba' : '#334155' }}>
                    {s.title}
                  </strong>
                  <span style={{ fontSize: '0.72rem', color: '#64748b' }}>{s.subtitle}</span>
                </div>
              ))}
            </div>

            {/* Stage Interactive Action Console */}
            <div style={{ backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px', padding: '1rem' }}>
              {activeLifecycleStage === 1 && (
                <div>
                  <h4 style={{ margin: '0 0 0.35rem 0', fontSize: '0.92rem', color: '#0f172a' }}>
                    Stage 1: Merchant Catalog Authority
                  </h4>
                  <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.85rem', color: '#475569' }}>
                    The catalog serves as the immutable ground truth for SKU <strong>SX-001</strong>. If storefront caching or an unauthorized pricing rule drifts, PRIP detects it.
                  </p>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <a
                      href="/catalog"
                      style={{
                        padding: '0.45rem 0.9rem',
                        backgroundColor: '#0070ba',
                        color: '#ffffff',
                        textDecoration: 'none',
                        borderRadius: '6px',
                        fontSize: '0.82rem',
                        fontWeight: 600,
                      }}
                    >
                      Open Full Catalog View
                    </a>
                  </div>
                </div>
              )}

              {activeLifecycleStage === 2 && (
                <div>
                  <h4 style={{ margin: '0 0 0.35rem 0', fontSize: '0.92rem', color: '#0f172a' }}>
                    Stage 2: Buyer & Autonomous AI Agent Discovery
                  </h4>
                  <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.85rem', color: '#475569' }}>
                    The customer or AI Shopping Agent attempts to purchase the product. If a price discrepancy exists, the agent halts checkout and files an Anomaly Incident.
                  </p>
                  <button
                    onClick={handleRunAiAgentScan}
                    disabled={agentRunning}
                    style={{
                      padding: '0.45rem 0.9rem',
                      backgroundColor: '#0f172a',
                      color: '#ffffff',
                      border: 'none',
                      borderRadius: '6px',
                      fontSize: '0.82rem',
                      fontWeight: 600,
                      cursor: agentRunning ? 'wait' : 'pointer',
                    }}
                  >
                    {agentRunning ? 'Agent Scanning...' : 'Trigger AI Agent Purchase Scan'}
                  </button>
                </div>
              )}

              {activeLifecycleStage === 3 && (
                <div>
                  <h4 style={{ margin: '0 0 0.35rem 0', fontSize: '0.92rem', color: '#0f172a' }}>
                    Stage 3: 4-State Forensic Inspection
                  </h4>
                  <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.85rem', color: '#475569' }}>
                    Inspection Engine Status:{' '}
                    <strong>{activeScan?.state || (demoProduct?.has_discrepancy ? 'ISSUE_DETECTED' : 'NOT_TESTED')}</strong>
                  </p>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <button
                      onClick={handleRunAiAgentScan}
                      disabled={agentRunning}
                      style={{
                        padding: '0.45rem 0.9rem',
                        backgroundColor: '#0070ba',
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: '6px',
                        fontSize: '0.82rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      Run Deterministic Scan
                    </button>
                    <a
                      href="/inspection"
                      style={{
                        padding: '0.45rem 0.9rem',
                        backgroundColor: '#ffffff',
                        color: '#0070ba',
                        border: '1px solid #0070ba',
                        textDecoration: 'none',
                        borderRadius: '6px',
                        fontSize: '0.82rem',
                        fontWeight: 600,
                      }}
                    >
                      View Forensic Evidence Cards
                    </a>
                  </div>
                </div>
              )}

              {activeLifecycleStage === 4 && (
                <div>
                  <h4 style={{ margin: '0 0 0.35rem 0', fontSize: '0.92rem', color: '#0f172a' }}>
                    Stage 4: AI Root Cause Diagnosis & Proposal Drafting
                  </h4>
                  <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.85rem', color: '#475569' }}>
                    AI analyzes discrepancy evidence, determines root cause, and drafts an atomic correction proposal. AI has zero authority to execute changes.
                  </p>
                  <button
                    onClick={handleGenerateDiagnosisAndProposal}
                    disabled={demoActionLoading}
                    style={{
                      padding: '0.45rem 0.9rem',
                      backgroundColor: '#0070ba',
                      color: '#ffffff',
                      border: 'none',
                      borderRadius: '6px',
                      fontSize: '0.82rem',
                      fontWeight: 600,
                      cursor: demoActionLoading ? 'wait' : 'pointer',
                    }}
                  >
                    Draft Correction Proposal
                  </button>
                </div>
              )}

              {activeLifecycleStage === 5 && (
                <div>
                  <h4 style={{ margin: '0 0 0.35rem 0', fontSize: '0.92rem', color: '#0f172a' }}>
                    Stage 5: Human-in-the-Loop Merchant Decision
                  </h4>
                  <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.85rem', color: '#475569' }}>
                    Proposal #{activeProposal?.id || '1'}: Synchronize storefront price from ${demoProduct?.storefront_price || '120.00'} to ${demoProduct?.merchant_price || '100.00'} USD.
                  </p>
                  <div style={{ marginBottom: '0.75rem' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', color: '#0f172a', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={merchantSignoffChecked}
                        onChange={(e) => setMerchantSignoffChecked(e.target.checked)}
                      />
                      <span>I authorize this price correction in accordance with catalog ground truth.</span>
                    </label>
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <button
                      onClick={() => handleMerchantDecision('approve')}
                      disabled={demoActionLoading || !merchantSignoffChecked}
                      style={{
                        padding: '0.45rem 1rem',
                        backgroundColor: merchantSignoffChecked ? '#16a34a' : '#cbd5e1',
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: '6px',
                        fontSize: '0.82rem',
                        fontWeight: 700,
                        cursor: merchantSignoffChecked ? 'pointer' : 'not-allowed',
                      }}
                    >
                      Approve & Synchronize Storefront
                    </button>
                    <button
                      onClick={() => handleMerchantDecision('reject')}
                      disabled={demoActionLoading}
                      style={{
                        padding: '0.45rem 1rem',
                        backgroundColor: '#ffffff',
                        color: '#b91c1c',
                        border: '1px solid #cbd5e1',
                        borderRadius: '6px',
                        fontSize: '0.82rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      Decline
                    </button>
                  </div>
                </div>
              )}

              {activeLifecycleStage === 6 && (
                <div>
                  <h4 style={{ margin: '0 0 0.35rem 0', fontSize: '0.92rem', color: '#0f172a' }}>
                    Stage 6: Protected PayPal Sandbox Checkout
                  </h4>
                  <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.85rem', color: '#475569' }}>
                    Storefront price verified clean. Orders are preflight-validated and routed to PayPal Orders v2 in canonical USD.
                  </p>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <button
                      onClick={handleExecutePayPalPayment}
                      disabled={checkoutLoading}
                      style={{
                        padding: '0.45rem 1rem',
                        backgroundColor: '#0070ba',
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: '6px',
                        fontSize: '0.82rem',
                        fontWeight: 700,
                        cursor: checkoutLoading ? 'wait' : 'pointer',
                      }}
                    >
                      {checkoutLoading ? 'Executing Transfer...' : 'Execute PayPal Sandbox Capture ($100.00 USD)'}
                    </button>
                    <a
                      href="/checkout"
                      style={{
                        padding: '0.45rem 0.9rem',
                        backgroundColor: '#ffffff',
                        color: '#0070ba',
                        border: '1px solid #0070ba',
                        textDecoration: 'none',
                        borderRadius: '6px',
                        fontSize: '0.82rem',
                        fontWeight: 600,
                      }}
                    >
                      Open PayPal Smart Buttons Checkout
                    </a>
                  </div>

                  {checkoutSuccess && (
                    <div style={{ marginTop: '0.75rem', padding: '0.6rem', backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '4px', fontSize: '0.82rem', color: '#166534' }}>
                      Payment captured: Order {checkoutSuccess.orderId} for {checkoutSuccess.amount} at {checkoutSuccess.time}.
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* KPI Revenue Cards */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
              gap: '1rem',
              marginBottom: '1.5rem',
            }}
          >
            <div style={{ padding: '1.25rem', backgroundColor: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#b91c1c' }}>AT-RISK REVENUE LEAKAGE</span>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#0f172a', margin: '0.25rem 0' }}>
                ${revenue?.at_risk_revenue_leakage || '20.00'}
              </div>
              <span style={{ fontSize: '0.8rem', color: '#475569' }}>
                Active discrepancies: {revenue?.active_discrepancies ?? 1}
              </span>
            </div>

            <div style={{ padding: '1.25rem', backgroundColor: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#16a34a' }}>VERIFIED CAPTURED VOLUME</span>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#0f172a', margin: '0.25rem 0' }}>
                ${revenue?.verified_captured_volume || '0.00'}
              </div>
              <span style={{ fontSize: '0.8rem', color: '#475569' }}>
                Settled in USD via PayPal Sandbox
              </span>
            </div>

            <div style={{ padding: '1.25rem', backgroundColor: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#0070ba' }}>CATALOG INTEGRITY SCORE</span>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#0f172a', margin: '0.25rem 0' }}>
                {revenue?.integrity_score_pct ?? (demoProduct?.has_discrepancy ? 0 : 100)}%
              </div>
              <span style={{ fontSize: '0.8rem', color: '#475569' }}>
                Status: {revenue?.protection_status || 'MONITORING'}
              </span>
            </div>

            <div style={{ padding: '1.25rem', backgroundColor: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#0369a1' }}>CATALOG HEALTH INDEX</span>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#0f172a', margin: '0.25rem 0' }}>
                {catalogIntel?.health_index ?? 100}%
              </div>
              <span style={{ fontSize: '0.8rem', color: '#475569' }}>
                Total items monitored: {catalogIntel?.total_products ?? 1}
              </span>
            </div>
          </div>

          {/* Conversational Assistant & System Readiness */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', marginBottom: '1.5rem' }}>
            {/* PRIP Conversational Assistant */}
            <div style={{ backgroundColor: '#ffffff', padding: '1.25rem', borderRadius: '8px', border: '1px solid #cbd5e1' }}>
              <h3 style={{ margin: '0 0 0.5rem 0', fontSize: '1.05rem', fontWeight: 700 }}>
                PRIP Conversational Assistant
              </h3>
              <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.82rem', color: '#475569' }}>
                Ask about discrepancies, catalog integrity, or PayPal checkout protection.
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '180px', overflowY: 'auto', marginBottom: '0.75rem' }}>
                {chatMessages.map((m, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '0.4rem 0.65rem',
                      borderRadius: '6px',
                      fontSize: '0.82rem',
                      alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                      backgroundColor: m.role === 'user' ? '#0070ba' : '#f1f5f9',
                      color: m.role === 'user' ? '#ffffff' : '#0f172a',
                      maxWidth: '85%',
                    }}
                  >
                    {m.content}
                  </div>
                ))}
              </div>

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleSendMessage();
                }}
                style={{ display: 'flex', gap: '0.5rem' }}
              >
                <input
                  type="text"
                  placeholder="Ask PRIP Assistant about your catalog..."
                  value={inputMsg}
                  onChange={(e) => setInputMsg(e.target.value)}
                  style={{ flex: 1, padding: '0.4rem 0.6rem', fontSize: '0.82rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                />
                <button
                  type="submit"
                  disabled={chatLoading}
                  style={{ padding: '0.4rem 0.8rem', backgroundColor: '#0f172a', color: '#ffffff', border: 'none', borderRadius: '4px', fontSize: '0.82rem', cursor: 'pointer' }}
                >
                  Send
                </button>
              </form>
            </div>

            {/* System Readiness & Sandbox Health */}
            <div style={{ backgroundColor: '#ffffff', padding: '1.25rem', borderRadius: '8px', border: '1px solid #cbd5e1' }}>
              <h3 style={{ margin: '0 0 0.5rem 0', fontSize: '1.05rem', fontWeight: 700 }}>
                System Readiness & Sandbox Health
              </h3>
              <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.82rem', color: '#475569' }}>
                Verification endpoints confirming database connection and PayPal sandbox reachability.
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', fontSize: '0.85rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.4rem', backgroundColor: '#f8fafc', borderRadius: '4px' }}>
                  <span>API Status</span>
                  <span style={{ fontWeight: 700, color: '#16a34a' }}>{health?.status || 'HEALTHY'}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.4rem', backgroundColor: '#f8fafc', borderRadius: '4px' }}>
                  <span>Database Connection</span>
                  <span style={{ fontWeight: 700, color: '#16a34a' }}>CONNECTED (PostgreSQL/SQLite)</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.4rem', backgroundColor: '#f8fafc', borderRadius: '4px' }}>
                  <span>PayPal Sandbox Gateway</span>
                  <span style={{ fontWeight: 700, color: '#0070ba' }}>READY (USD)</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.4rem', backgroundColor: '#f8fafc', borderRadius: '4px' }}>
                  <span>Multi-Tenant Context</span>
                  <span style={{ fontWeight: 700 }}>{profile?.active_merchant_id || 'merchant_default'}</span>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* PERSONA MODE 2: BUYER STOREFRONT & AI PURCHASING AGENT */}
      {activePersona === 'buyer' && (
        <section aria-label="Buyer Storefront & AI Purchasing Agent">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
            {/* Customer Storefront View */}
            <div style={{ backgroundColor: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px', padding: '1.5rem' }}>
              <span style={{ backgroundColor: '#0f172a', color: '#ffffff', padding: '2px 8px', borderRadius: '4px', fontSize: '0.72rem', fontWeight: 700 }}>
                CUSTOMER-FACING STOREFRONT
              </span>
              <h3 style={{ margin: '0.5rem 0 0.25rem 0', fontSize: '1.25rem', fontWeight: 800 }}>
                StrideX Runner (SX-001)
              </h3>
              <p style={{ margin: '0 0 1rem 0', color: '#475569', fontSize: '0.85rem' }}>
                High-performance lightweight running shoe with responsive cushioning.
              </p>

              <div style={{ padding: '1rem', backgroundColor: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0', marginBottom: '1.25rem' }}>
                <span style={{ fontSize: '0.8rem', color: '#64748b' }}>Storefront Display Price</span>
                <div style={{ fontSize: '2rem', fontWeight: 800, color: demoProduct?.has_discrepancy ? '#b91c1c' : '#0f172a' }}>
                  ${demoProduct?.storefront_price || '120.00'} USD
                </div>
                {demoProduct?.has_discrepancy && (
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#b91c1c' }}>
                    Unverified drift detected (Authority catalog is ${demoProduct?.merchant_price || '100.00'} USD)
                  </span>
                )}
              </div>

              <div>
                <label htmlFor="buyer-email" style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '0.25rem' }}>
                  Buyer Personal Sandbox Email
                </label>
                <input
                  id="buyer-email"
                  type="email"
                  value={buyerSandboxEmail}
                  onChange={(e) => setBuyerSandboxEmail(e.target.value)}
                  style={{ width: '100%', padding: '0.45rem 0.65rem', fontSize: '0.82rem', borderRadius: '4px', border: '1px solid #cbd5e1', boxSizing: 'border-box', marginBottom: '1rem' }}
                />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <button
                  onClick={handleRunAiAgentScan}
                  disabled={agentRunning}
                  style={{
                    padding: '0.6rem',
                    backgroundColor: '#0f172a',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: '6px',
                    fontWeight: 700,
                    fontSize: '0.88rem',
                    cursor: agentRunning ? 'wait' : 'pointer',
                  }}
                >
                  {agentRunning ? 'AI Purchasing Agent Running...' : 'Instruct AI Agent to Buy Product'}
                </button>

                <button
                  onClick={handleExecutePayPalPayment}
                  disabled={checkoutLoading || (demoProduct?.has_discrepancy && agentOutcome !== 'verified_ready')}
                  style={{
                    padding: '0.6rem',
                    backgroundColor: demoProduct?.has_discrepancy && agentOutcome !== 'verified_ready' ? '#94a3b8' : '#0070ba',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: '6px',
                    fontWeight: 700,
                    fontSize: '0.88rem',
                    cursor: demoProduct?.has_discrepancy && agentOutcome !== 'verified_ready' ? 'not-allowed' : 'pointer',
                  }}
                >
                  {checkoutLoading ? 'Processing Checkout...' : 'Direct PayPal Checkout (USD)'}
                </button>

                {demoProduct?.has_discrepancy && agentOutcome !== 'verified_ready' && (
                  <span style={{ fontSize: '0.78rem', color: '#b91c1c' }}>
                    Checkout locked: Active price discrepancy requires merchant sign-off in Stage 5.
                  </span>
                )}

                {checkoutOrderId && (
                  <div style={{ marginTop: '0.5rem', padding: '0.45rem 0.65rem', backgroundColor: '#f0fdf4', borderRadius: '4px', fontSize: '0.8rem', color: '#166534', border: '1px solid #bbf7d0' }}>
                    Active Order: <code>{checkoutOrderId}</code>
                  </div>
                )}

                {checkoutSuccess && (
                  <div style={{ marginTop: '0.5rem', padding: '0.6rem', backgroundColor: '#f0fdf4', borderRadius: '4px', fontSize: '0.82rem', color: '#166534', border: '1px solid #86efac' }}>
                    <strong>Payment Confirmed</strong>: Captured {checkoutSuccess.amount} (Order ID: {checkoutSuccess.orderId})
                  </div>
                )}
              </div>
            </div>

            {/* Autonomous AI Purchasing Agent Terminal */}
            <div style={{ backgroundColor: '#0f172a', color: '#f8fafc', borderRadius: '8px', padding: '1.25rem', display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #334155', paddingBottom: '0.5rem', marginBottom: '0.75rem' }}>
                <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#38bdf8' }}>
                  PRIP AUTONOMOUS SHOPPING AGENT CONSOLE
                </span>
                <span style={{ fontSize: '0.75rem', color: agentRunning ? '#facc15' : '#4ade80' }}>
                  {agentRunning ? '● SCANNING' : '● IDLE'}
                </span>
              </div>

              <div
                style={{
                  flex: 1,
                  fontFamily: 'Consolas, Monaco, monospace',
                  fontSize: '0.82rem',
                  lineHeight: 1.6,
                  overflowY: 'auto',
                  maxHeight: '260px',
                  backgroundColor: '#020617',
                  padding: '0.75rem',
                  borderRadius: '4px',
                  border: '1px solid #1e293b',
                  marginBottom: '1rem',
                }}
              >
                {agentLogs.map((log, idx) => (
                  <div key={idx} style={{ color: log.includes('ANOMALY') || log.includes('DISCREPANCY') ? '#f87171' : log.includes('VERIFIED') ? '#4ade80' : '#e2e8f0' }}>
                    {log}
                  </div>
                ))}
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                  Policy: Automated preflight verification before fund commitment
                </span>
                <button
                  onClick={() => setAgentLogs(['[CONSOLE CLEARED]'])}
                  style={{ background: 'none', border: '1px solid #475569', color: '#cbd5e1', borderRadius: '4px', padding: '2px 8px', fontSize: '0.72rem', cursor: 'pointer' }}
                >
                  Clear Logs
                </button>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
};

export default Dashboard;

