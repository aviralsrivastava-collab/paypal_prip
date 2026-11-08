import React, { useEffect, useState } from 'react';
import { ApiClient } from '../services/api';
import { Diagnosis, EvidenceItem, InspectionState, ScanDetail, ScanSummary } from '../types';

export const Inspection: React.FC = () => {
  const [sku, setSku] = useState<string>('SX-001');
  const [simulatedScenario, setSimulatedScenario] = useState<string>('');
  const [currentScan, setCurrentScan] = useState<ScanDetail | null>(null);
  const [scanHistory, setScanHistory] = useState<ScanSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Phase 4: AI Diagnosis state
  const [currentDiagnosis, setCurrentDiagnosis] = useState<Diagnosis | null>(null);
  const [diagnosisLoading, setDiagnosisLoading] = useState<boolean>(false);
  const [diagnosisError, setDiagnosisError] = useState<string | null>(null);
  const [aiSimulatedFailure, setAiSimulatedFailure] = useState<string>('');

  const loadDiagnosisForScan = async (scanId: number) => {
    try {
      const list = await ApiClient.getScanDiagnoses(scanId);
      if (list && list.length > 0) {
        setCurrentDiagnosis(list[0]);
      } else {
        setCurrentDiagnosis(null);
      }
    } catch {
      setCurrentDiagnosis(null);
    }
  };

  const loadProductHistory = async (productSku: string) => {
    try {
      const history = await ApiClient.getProductScans(productSku);
      setScanHistory(history);
      if (history.length > 0 && !currentScan) {
        const latestDetail = await ApiClient.getScan(history[0].id);
        setCurrentScan(latestDetail);
      }
    } catch {
      // It is normal if no history exists yet
      setScanHistory([]);
    }
  };

  useEffect(() => {
    loadProductHistory(sku);
  }, [sku]);

  useEffect(() => {
    if (currentScan) {
      loadDiagnosisForScan(currentScan.id);
    } else {
      setCurrentDiagnosis(null);
    }
  }, [currentScan?.id]);

  const handleRunInspection = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await ApiClient.triggerScan(sku, simulatedScenario || undefined);
      setCurrentScan(result);
      await loadProductHistory(sku);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Inspection execution failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleRunDiagnosis = async () => {
    if (!currentScan) return;
    setDiagnosisLoading(true);
    setDiagnosisError(null);
    try {
      const diag = await ApiClient.triggerDiagnosis(
        currentScan.id,
        aiSimulatedFailure || undefined
      );
      setCurrentDiagnosis(diag);
    } catch (err: unknown) {
      setDiagnosisError(err instanceof Error ? err.message : 'AI diagnosis request failed.');
    } finally {
      setDiagnosisLoading(false);
    }
  };

  const getStatusBadgeStyle = (status: string) => {
    switch (status) {
      case 'MATCH':
        return { backgroundColor: '#dcfce7', color: '#166534', border: '1px solid #bbf7d0' };
      case 'MISMATCH':
        return { backgroundColor: '#fee2e2', color: '#991b1b', border: '1px solid #fecaca' };
      case 'BLOCKED':
      default:
        return { backgroundColor: '#fef3c7', color: '#92400e', border: '1px solid #fde68a' };
    }
  };

  const currentState: InspectionState = currentScan ? currentScan.state : 'NOT_TESTED';

  const getStateBannerConfig = (state: InspectionState) => {
    switch (state) {
      case 'ISSUE_DETECTED':
        return {
          title: 'ISSUE DETECTED',
          bg: '#fef2f2',
          border: '#f87171',
          text: '#991b1b',
          desc: 'Observations are comparable, but a price mismatch or policy violation was detected.',
        };
      case 'VERIFIED_NO_ISSUE':
        return {
          title: 'VERIFIED NO ISSUE',
          bg: '#f0fdf4',
          border: '#4ade80',
          text: '#166534',
          desc: 'Inspection completed successfully: All observations are comparable and no discrepancies exist.',
        };
      case 'BLOCKED_UNKNOWN':
        return {
          title: 'BLOCKED / UNKNOWN',
          bg: '#fffbeb',
          border: '#fbbf24',
          text: '#92400e',
          desc: 'Inconclusive scan. Missing evidence is not evidence of correctness. Non-comparable observations or extraction failures cannot verify correctness.',
        };
      case 'NOT_TESTED':
      default:
        return {
          title: 'NOT TESTED',
          bg: '#f8fafc',
          border: '#cbd5e1',
          text: '#475569',
          desc: 'This product has not yet been inspected. Trigger a scan below to begin.',
        };
    }
  };

  const banner = getStateBannerConfig(currentState);

  return (
    <div style={{ padding: '2rem', maxWidth: '1000px', margin: '0 auto', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      {/* Header */}
      <div style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ margin: '0 0 0.5rem', color: '#0f172a' }}>Storefront Inspection & Evidence Engine</h2>
        <p style={{ margin: 0, color: '#64748b', fontSize: '0.95rem' }}>
          Deterministic inspection comparing authoritative merchant catalog ground truth against controlled storefront observations.
        </p>
      </div>

      {/* Mandatory 4-State Outcome Banner */}
      <div
        data-testid="state-banner"
        style={{
          backgroundColor: banner.bg,
          border: `2px solid ${banner.border}`,
          borderRadius: '8px',
          padding: '1.25rem',
          marginBottom: '1.5rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
          <span style={{ fontSize: '1.1rem', fontWeight: 700, color: banner.text, letterSpacing: '0.05em' }}>
            {banner.title}
          </span>
          {currentScan && (
            <span style={{ fontSize: '0.85rem', color: '#64748b' }}>
              Scan ID: #{currentScan.id} | Timestamp: {new Date(currentScan.created_at).toLocaleTimeString()}
            </span>
          )}
        </div>
        <p style={{ margin: '0 0 0.75rem', color: banner.text, fontSize: '0.95rem' }}>
          {banner.desc}
        </p>

        {currentScan && (
          <div style={{ display: 'flex', gap: '2rem', marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: `1px solid ${banner.border}` }}>
            <div>
              <span style={{ fontSize: '0.8rem', color: '#64748b', display: 'block' }}>CATALOG GROUND TRUTH</span>
              <span style={{ fontWeight: 600, color: '#0f172a' }}>
                {currentScan.catalog_price ? `${currentScan.catalog_price} ${currentScan.currency}` : 'N/A'}
              </span>
            </div>
            <div>
              <span style={{ fontSize: '0.8rem', color: '#64748b', display: 'block' }}>STOREFRONT OBSERVED</span>
              <span style={{ fontWeight: 600, color: '#0f172a' }}>
                {currentScan.observed_price ? `${currentScan.observed_price} ${currentScan.currency}` : 'N/A'}
              </span>
            </div>
            <div>
              <span style={{ fontSize: '0.8rem', color: '#64748b', display: 'block' }}>PRICE DISCREPANCY</span>
              <span style={{ fontWeight: 700, color: currentScan.discrepancy_amount ? '#dc2626' : '#166534' }}>
                {currentScan.discrepancy_amount ? `${currentScan.discrepancy_amount} ${currentScan.currency}` : 'None'}
              </span>
            </div>
            <div>
              <span style={{ fontSize: '0.8rem', color: '#64748b', display: 'block' }}>COMPARABLE</span>
              <span style={{ fontWeight: 600, color: currentScan.is_comparable ? '#166534' : '#b45309' }}>
                {currentScan.is_comparable ? 'YES' : 'NO'}
              </span>
            </div>
          </div>
        )}

        {currentScan?.failure_reason && (
          <div style={{ marginTop: '0.75rem', padding: '0.5rem', backgroundColor: '#fff', borderRadius: '4px', border: '1px solid #fde68a' }}>
            <strong style={{ color: '#92400e', fontSize: '0.85rem' }}>Comparability Blocker: </strong>
            <span style={{ color: '#78350f', fontSize: '0.85rem' }}>{currentScan.failure_reason}</span>
          </div>
        )}
      </div>

      {/* Control Panel / Runner */}
      <div style={{ backgroundColor: '#fff', padding: '1.25rem', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: '1.5rem' }}>
        <h3 style={{ margin: '0 0 1rem', fontSize: '1rem', color: '#1e293b' }}>Inspection Controls</h3>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div>
            <label htmlFor="sku-input" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#475569', marginBottom: '0.35rem' }}>
              Product SKU
            </label>
            <input
              id="sku-input"
              type="text"
              value={sku}
              onChange={(e) => setSku(e.target.value)}
              placeholder="e.g. SX-001"
              style={{
                padding: '0.5rem 0.75rem',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '0.9rem',
                minWidth: '160px',
              }}
            />
          </div>

          <div>
            <label htmlFor="fault-select" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#475569', marginBottom: '0.35rem' }}>
              Fault Injection Simulation (Testing)
            </label>
            <select
              id="fault-select"
              value={simulatedScenario}
              onChange={(e) => setSimulatedScenario(e.target.value)}
              style={{
                padding: '0.5rem 0.75rem',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '0.9rem',
                minWidth: '220px',
              }}
            >
              <option value="">Normal Extraction (Controlled Storefront)</option>
              <option value="timeout">Simulate Timeout (BLOCKED_UNKNOWN)</option>
              <option value="missing">Simulate Missing Product 404 (BLOCKED_UNKNOWN)</option>
              <option value="blocked">Simulate Access Blocked 403 (BLOCKED_UNKNOWN)</option>
              <option value="unsupported">Simulate Unsupported Content (BLOCKED_UNKNOWN)</option>
            </select>
          </div>

          <button
            onClick={handleRunInspection}
            disabled={loading}
            style={{
              padding: '0.55rem 1.4rem',
              backgroundColor: '#0070ba',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              fontWeight: 600,
              fontSize: '0.9rem',
              cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? 'Inspecting...' : 'Run Inspection'}
          </button>
        </div>

        {error && (
          <div style={{ marginTop: '1rem', padding: '0.75rem', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', color: '#991b1b', fontSize: '0.9rem' }}>
            {error}
          </div>
        )}
      </div>

      {/* Structured Evidence Items */}
      {currentScan && currentScan.evidence_items && currentScan.evidence_items.length > 0 && (
        <div style={{ backgroundColor: '#fff', padding: '1.25rem', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '1rem', color: '#1e293b' }}>Structured Evidence Items</h3>
              <p style={{ margin: '0.25rem 0 0', color: '#64748b', fontSize: '0.85rem' }}>
                Immutable, cryptographically verified observation facts bound to this scan.
              </p>
            </div>
            <span style={{ fontSize: '0.85rem', color: '#64748b' }}>
              {currentScan.evidence_items.length} records captured
            </span>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #e2e8f0', backgroundColor: '#f8fafc' }}>
                  <th style={{ padding: '0.6rem 0.75rem', color: '#475569' }}>Type</th>
                  <th style={{ padding: '0.6rem 0.75rem', color: '#475569' }}>Field</th>
                  <th style={{ padding: '0.6rem 0.75rem', color: '#475569' }}>Catalog (Expected)</th>
                  <th style={{ padding: '0.6rem 0.75rem', color: '#475569' }}>Storefront (Observed)</th>
                  <th style={{ padding: '0.6rem 0.75rem', color: '#475569' }}>Status</th>
                  <th style={{ padding: '0.6rem 0.75rem', color: '#475569' }}>Content Hash (SHA-256)</th>
                </tr>
              </thead>
              <tbody>
                {currentScan.evidence_items.map((item: EvidenceItem) => {
                  const badge = getStatusBadgeStyle(item.status);
                  return (
                    <tr key={item.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '0.6rem 0.75rem', fontWeight: 600, color: '#334155' }}>
                        {item.evidence_type}
                      </td>
                      <td style={{ padding: '0.6rem 0.75rem', color: '#64748b', fontFamily: 'monospace' }}>
                        {item.field_name}
                      </td>
                      <td style={{ padding: '0.6rem 0.75rem', color: '#0f172a' }}>
                        {item.expected_value ?? '—'}
                      </td>
                      <td style={{ padding: '0.6rem 0.75rem', color: '#0f172a', fontWeight: item.status === 'MISMATCH' ? 700 : 400 }}>
                        {item.observed_value ?? '—'}
                      </td>
                      <td style={{ padding: '0.6rem 0.75rem' }}>
                        <span
                          style={{
                            display: 'inline-block',
                            padding: '0.2rem 0.5rem',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            ...badge,
                          }}
                        >
                          {item.status}
                        </span>
                      </td>
                      <td style={{ padding: '0.6rem 0.75rem', fontFamily: 'monospace', fontSize: '0.75rem', color: '#64748b' }}>
                        <span title={item.content_hash || ''}>
                          {item.content_hash ? `${item.content_hash.substring(0, 12)}...${item.content_hash.substring(item.content_hash.length - 6)}` : '—'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Advisory AI Diagnosis Section */}
      {currentScan && (
        <div
          data-testid="ai-diagnosis-panel"
          style={{
            backgroundColor: '#fff',
            padding: '1.25rem',
            borderRadius: '8px',
            border: '1px solid #cbd5e1',
            marginBottom: '1.5rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1rem' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <h3 style={{ margin: 0, fontSize: '1.05rem', color: '#1e293b' }}>
                  Advisory AI Diagnosis & Root Cause Intelligence
                </h3>
                <span
                  data-testid="advisory-badge"
                  style={{
                    backgroundColor: '#e0e7ff',
                    color: '#3730a3',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    padding: '0.2rem 0.55rem',
                    borderRadius: '9999px',
                    border: '1px solid #c7d2fe',
                  }}
                >
                  Advisory Only
                </span>
              </div>
              <p style={{ margin: '0.25rem 0 0', color: '#64748b', fontSize: '0.85rem' }}>
                AI explains observed evidence and suggests actions. AI has NO authority to mutate data, alter inspection states, or execute payments.
              </p>
            </div>

            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <select
                id="ai-fault-select"
                aria-label="AI Simulation Mode"
                value={aiSimulatedFailure}
                onChange={(e) => setAiSimulatedFailure(e.target.value)}
                style={{
                  padding: '0.4rem 0.6rem',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  fontSize: '0.85rem',
                }}
              >
                <option value="">Normal Advisory Output</option>
                <option value="timeout">Simulate AI Timeout</option>
                <option value="rate_limit">Simulate AI Rate Limit</option>
                <option value="outage">Simulate AI Outage</option>
                <option value="invalid_output">Simulate Invalid Output</option>
              </select>

              <button
                onClick={handleRunDiagnosis}
                disabled={diagnosisLoading}
                style={{
                  padding: '0.45rem 1rem',
                  backgroundColor: '#4338ca',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  fontWeight: 600,
                  fontSize: '0.85rem',
                  cursor: diagnosisLoading ? 'not-allowed' : 'pointer',
                  opacity: diagnosisLoading ? 0.7 : 1,
                }}
              >
                {diagnosisLoading ? 'Analyzing...' : currentDiagnosis ? 'Re-analyze with AI' : 'Request AI Diagnosis'}
              </button>
            </div>
          </div>

          {diagnosisError && (
            <div style={{ padding: '0.75rem', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', color: '#991b1b', fontSize: '0.85rem', marginBottom: '1rem' }}>
              <strong>AI Diagnostic Error: </strong>{diagnosisError}
            </div>
          )}

          {currentDiagnosis ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              {/* Status and Provenance */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', paddingBottom: '0.75rem', borderBottom: '1px solid #f1f5f9' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#475569' }}>Diagnosis Status:</span>
                  <span
                    data-testid="diagnosis-status-badge"
                    style={{
                      padding: '0.2rem 0.6rem',
                      borderRadius: '4px',
                      fontSize: '0.8rem',
                      fontWeight: 700,
                      backgroundColor: currentDiagnosis.status === 'COMPLETED' ? '#e0e7ff' : currentDiagnosis.status === 'INSUFFICIENT_EVIDENCE' ? '#fef3c7' : '#fee2e2',
                      color: currentDiagnosis.status === 'COMPLETED' ? '#3730a3' : currentDiagnosis.status === 'INSUFFICIENT_EVIDENCE' ? '#92400e' : '#991b1b',
                      border: currentDiagnosis.status === 'COMPLETED' ? '1px solid #c7d2fe' : currentDiagnosis.status === 'INSUFFICIENT_EVIDENCE' ? '1px solid #fde68a' : '1px solid #fecaca',
                    }}
                  >
                    {currentDiagnosis.status}
                  </span>
                </div>
                <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
                  Provider: <strong>{currentDiagnosis.provider}</strong> | Model: <strong>{currentDiagnosis.model}</strong> | Prompt: <strong>{currentDiagnosis.prompt_version}</strong>
                </span>
              </div>

              {/* Summary */}
              <div style={{ backgroundColor: '#f8fafc', padding: '0.85rem', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                <strong style={{ display: 'block', fontSize: '0.85rem', color: '#1e293b', marginBottom: '0.35rem' }}>Summary:</strong>
                <p style={{ margin: 0, fontSize: '0.9rem', color: '#334155', lineHeight: 1.5 }}>
                  {currentDiagnosis.summary}
                </p>
              </div>

              {/* Likely Causes */}
              {currentDiagnosis.likely_causes && currentDiagnosis.likely_causes.length > 0 && (
                <div>
                  <strong style={{ display: 'block', fontSize: '0.85rem', color: '#1e293b', marginBottom: '0.35rem' }}>Likely Causes:</strong>
                  <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.85rem', color: '#475569', lineHeight: 1.5 }}>
                    {currentDiagnosis.likely_causes.map((cause, idx) => (
                      <li key={idx}>{cause}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Supporting Evidence IDs */}
              <div>
                <strong style={{ display: 'block', fontSize: '0.85rem', color: '#1e293b', marginBottom: '0.35rem' }}>Supporting Grounded Evidence:</strong>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  {currentDiagnosis.supporting_evidence_ids && currentDiagnosis.supporting_evidence_ids.length > 0 ? (
                    currentDiagnosis.supporting_evidence_ids.map((id) => (
                      <span
                        key={id}
                        data-testid={`evidence-tag-${id}`}
                        style={{
                          padding: '0.15rem 0.5rem',
                          backgroundColor: '#f1f5f9',
                          border: '1px solid #cbd5e1',
                          borderRadius: '4px',
                          fontFamily: 'monospace',
                          fontSize: '0.8rem',
                          color: '#334155',
                        }}
                      >
                        Evidence #{id}
                      </span>
                    ))
                  ) : (
                    <span style={{ fontSize: '0.85rem', color: '#94a3b8' }}>None cited (inconclusive evidence)</span>
                  )}
                </div>
              </div>

              {/* Missing Information */}
              {currentDiagnosis.missing_information && currentDiagnosis.missing_information.length > 0 && (
                <div style={{ backgroundColor: '#fffbeb', padding: '0.75rem', borderRadius: '6px', border: '1px solid #fde68a' }}>
                  <strong style={{ display: 'block', fontSize: '0.85rem', color: '#92400e', marginBottom: '0.25rem' }}>Missing Information:</strong>
                  <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.85rem', color: '#78350f' }}>
                    {currentDiagnosis.missing_information.map((item, idx) => (
                      <li key={idx}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Advisory Recommendations */}
              {currentDiagnosis.recommended_actions && currentDiagnosis.recommended_actions.length > 0 && (
                <div>
                  <strong style={{ display: 'block', fontSize: '0.85rem', color: '#1e293b', marginBottom: '0.35rem' }}>Advisory Recommendations for Merchant:</strong>
                  <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.85rem', color: '#475569', lineHeight: 1.5 }}>
                    {currentDiagnosis.recommended_actions.map((act, idx) => (
                      <li key={idx} style={{ marginBottom: '0.25rem' }}>
                        <span style={{ fontWeight: 600, color: '#4338ca' }}>[Advisory] </span>
                        {act}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Confidence Explanation */}
              {currentDiagnosis.confidence_explanation && (
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontStyle: 'italic', paddingTop: '0.5rem', borderTop: '1px solid #f1f5f9' }}>
                  Provenance & Confidence: {currentDiagnosis.confidence_explanation}
                </div>
              )}
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '1.5rem', backgroundColor: '#f8fafc', borderRadius: '6px', border: '1px dashed #cbd5e1' }}>
              <p style={{ margin: '0 0 0.75rem', color: '#64748b', fontSize: '0.9rem' }}>
                No advisory diagnosis requested yet for Scan #{currentScan.id}.
              </p>
              <button
                onClick={handleRunDiagnosis}
                disabled={diagnosisLoading}
                style={{
                  padding: '0.5rem 1.25rem',
                  backgroundColor: '#4338ca',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  fontWeight: 600,
                  fontSize: '0.85rem',
                  cursor: diagnosisLoading ? 'not-allowed' : 'pointer',
                }}
              >
                {diagnosisLoading ? 'Analyzing...' : 'Request Advisory Diagnosis'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Scan History */}
      {scanHistory.length > 0 && (
        <div style={{ backgroundColor: '#fff', padding: '1.25rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
          <h3 style={{ margin: '0 0 0.75rem', fontSize: '1rem', color: '#1e293b' }}>
            Historical Inspection Timeline ({scanHistory.length})
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {scanHistory.map((scan) => {
              const bannerCfg = getStateBannerConfig(scan.state);
              return (
                <div
                  key={scan.id}
                  onClick={async () => {
                    const detail = await ApiClient.getScan(scan.id);
                    setCurrentScan(detail);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.6rem 0.8rem',
                    border: '1px solid #e2e8f0',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    backgroundColor: currentScan?.id === scan.id ? '#f1f5f9' : '#fff',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <span
                      style={{
                        padding: '0.15rem 0.45rem',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        backgroundColor: bannerCfg.bg,
                        color: bannerCfg.text,
                        border: `1px solid ${bannerCfg.border}`,
                      }}
                    >
                      {scan.state}
                    </span>
                    <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#334155' }}>
                      Scan #{scan.id} (v{scan.source_version})
                    </span>
                    {scan.discrepancy_amount && (
                      <span style={{ fontSize: '0.8rem', color: '#dc2626', fontWeight: 600 }}>
                        {scan.discrepancy_amount} {scan.currency}
                      </span>
                    )}
                  </div>
                  <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                    {new Date(scan.created_at).toLocaleString()}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
