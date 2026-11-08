import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from '../src/App';

// Mock global fetch for health check
global.fetch = vi.fn().mockResolvedValue({
  ok: true,
  json: async () => ({
    status: 'healthy',
    environment: 'development',
    version: '0.1.0',
    database_connected: true,
    timestamp: '2026-11-06T23:00:00Z',
  }),
});

describe('App component', () => {
  it('renders application shell and dashboard overview', async () => {
    render(<App />);

    expect(screen.getByText('PRIP')).toBeInTheDocument();
    expect(screen.getByText(/Commerce Integrity Overview/i)).toBeInTheDocument();
    expect(screen.getByText(/System Readiness/i)).toBeInTheDocument();
  });
});
