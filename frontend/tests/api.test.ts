import { describe, it, expect, afterEach, vi } from 'vitest';
import { ApiClient } from '../src/services/api';

describe('ApiClient URL normalization', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('normalizes VITE_API_URL without /api suffix', () => {
    vi.stubEnv('VITE_API_URL', 'https://prip-backend.onrender.com');
    const getBaseUrl = (ApiClient as any).getBaseUrl;
    expect(getBaseUrl()).toBe('https://prip-backend.onrender.com/api');
  });

  it('preserves VITE_API_URL that already includes /api suffix', () => {
    vi.stubEnv('VITE_API_URL', 'https://prip-backend.onrender.com/api');
    const getBaseUrl = (ApiClient as any).getBaseUrl;
    expect(getBaseUrl()).toBe('https://prip-backend.onrender.com/api');
  });

  it('strips trailing slashes cleanly', () => {
    const getBaseUrl = (ApiClient as any).getBaseUrl;

    vi.stubEnv('VITE_API_URL', 'https://prip-backend.onrender.com/api///');
    expect(getBaseUrl()).toBe('https://prip-backend.onrender.com/api');

    vi.stubEnv('VITE_API_URL', 'https://prip-backend.onrender.com/');
    expect(getBaseUrl()).toBe('https://prip-backend.onrender.com/api');
  });

  it('falls back to /api when VITE_API_URL is unset or empty', () => {
    const getBaseUrl = (ApiClient as any).getBaseUrl;

    vi.stubEnv('VITE_API_URL', '');
    expect(getBaseUrl()).toBe('/api');

    vi.stubEnv('VITE_API_URL', '   ');
    expect(getBaseUrl()).toBe('/api');
  });
});
