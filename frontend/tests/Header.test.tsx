import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { Header } from '../src/components/Header';

describe('Header component', () => {
  it('renders branding and PayPal Sandbox label', () => {
    render(
      <BrowserRouter>
        <Header />
      </BrowserRouter>
    );

    expect(screen.getByText('PRIP')).toBeInTheDocument();
    expect(screen.getByText('PAYPAL SANDBOX')).toBeInTheDocument();
  });

  it('renders navigation links', () => {
    render(
      <BrowserRouter>
        <Header />
      </BrowserRouter>
    );

    expect(screen.getByRole('link', { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /catalog/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /inspection/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /checkout demo/i })).toBeInTheDocument();
  });
});
