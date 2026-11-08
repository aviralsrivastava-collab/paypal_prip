import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Header } from './components/Header';
import { Dashboard } from './pages/Dashboard';
import { Catalog } from './pages/Catalog';
import { Inspection } from './pages/Inspection';
import { Corrections } from './pages/Corrections';
import { Checkout } from './pages/Checkout';
import { Operations } from './pages/Operations';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', fontFamily: 'system-ui, sans-serif' }}>
        <Header />
        <main style={{ flex: 1 }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/catalog" element={<Catalog />} />
            <Route path="/inspection" element={<Inspection />} />
            <Route path="/corrections" element={<Corrections />} />
            <Route path="/checkout" element={<Checkout />} />
            <Route path="/operations" element={<Operations />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
};

export default App;
