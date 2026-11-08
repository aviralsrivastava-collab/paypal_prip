import React, { useEffect, useState } from 'react';
import { ApiClient } from '../services/api';
import { HealthStatus } from '../types';

export const Dashboard: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    ApiClient.getHealth()
      .then((data) => {
        setHealth(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <div style={{ padding: '2rem' }}>
      <h2>Commerce Integrity Overview</h2>
      <p style={{ color: '#555' }}>
        Detect the discrepancy. Approve the correction. Verify the checkout.
      </p>

      <div style={{
        marginTop: '1.5rem',
        padding: '1rem',
        border: '1px solid #ddd',
        borderRadius: '6px',
        maxWidth: '500px'
      }}>
        <h3>System Readiness (Phase 1)</h3>
        {loading && <p>Checking backend health...</p>}
        {error && <p style={{ color: '#d93025' }}>Backend Status: Offline ({error})</p>}
        {health && (
          <div>
            <p><strong>Status:</strong> {health.status}</p>
            <p><strong>Database Connected:</strong> {health.database_connected ? 'Yes' : 'No'}</p>
            <p><strong>Environment:</strong> {health.environment}</p>
            <p><strong>Version:</strong> {health.version}</p>
          </div>
        )}
      </div>
    </div>
  );
};
