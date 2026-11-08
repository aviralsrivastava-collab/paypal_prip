import React from 'react';
import { Link } from 'react-router-dom';

export const Header: React.FC = () => {
  return (
    <header style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '1rem 2rem',
      backgroundColor: '#003087',
      color: '#ffffff'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <h1 style={{ margin: 0, fontSize: '1.25rem' }}>PRIP</h1>
        <span style={{
          backgroundColor: '#0070BA',
          color: '#ffffff',
          padding: '2px 8px',
          borderRadius: '4px',
          fontSize: '0.75rem',
          fontWeight: 'bold'
        }}>
          PAYPAL SANDBOX
        </span>
      </div>
      <nav style={{ display: 'flex', gap: '1.5rem' }}>
        <Link to="/" style={{ color: '#ffffff', textDecoration: 'none' }}>Dashboard</Link>
        <Link to="/catalog" style={{ color: '#ffffff', textDecoration: 'none' }}>Catalog</Link>
        <Link to="/inspection" style={{ color: '#ffffff', textDecoration: 'none' }}>Inspection</Link>
        <Link to="/corrections" style={{ color: '#ffffff', textDecoration: 'none' }}>Corrections</Link>
        <Link to="/checkout" style={{ color: '#ffffff', textDecoration: 'none' }}>Checkout Demo</Link>
        <Link to="/operations" style={{ color: '#ffffff', textDecoration: 'none' }}>Operations</Link>
      </nav>
    </header>
  );
};
