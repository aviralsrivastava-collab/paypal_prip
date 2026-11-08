import React from 'react';

interface PriceBadgeProps {
  label: string;
  amount?: string;
  currency?: string;
  type?: 'source-of-truth' | 'storefront' | 'discrepancy' | 'non-comparable';
  note?: string;
}

export const PriceBadge: React.FC<PriceBadgeProps> = ({
  label,
  amount,
  currency,
  type = 'source-of-truth',
  note,
}) => {
  const isDiscrepancy = type === 'discrepancy';
  const isStorefront = type === 'storefront';
  const isNonComparable = type === 'non-comparable';

  const backgroundColor = isNonComparable
    ? '#f1f5f9'
    : isDiscrepancy
    ? '#fee2e2'
    : isStorefront
    ? '#fef3c7'
    : '#ecfdf5';

  const textColor = isNonComparable
    ? '#475569'
    : isDiscrepancy
    ? '#991b1b'
    : isStorefront
    ? '#92400e'
    : '#065f46';

  const borderColor = isNonComparable
    ? '#cbd5e1'
    : isDiscrepancy
    ? '#f87171'
    : isStorefront
    ? '#fcd34d'
    : '#a7f3d0';

  return (
    <div
      style={{
        display: 'inline-flex',
        flexDirection: 'column',
        padding: '0.5rem 0.75rem',
        borderRadius: '6px',
        backgroundColor,
        color: textColor,
        border: `1px solid ${borderColor}`,
        marginRight: '0.75rem',
        minWidth: '130px',
      }}
    >
      <span style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </span>
      {amount && currency ? (
        <span style={{ fontSize: '1.1rem', fontWeight: 700, marginTop: '0.2rem' }}>
          ${amount} <span style={{ fontSize: '0.8rem', fontWeight: 500 }}>{currency}</span>
        </span>
      ) : (
        <span style={{ fontSize: '0.9rem', fontWeight: 700, marginTop: '0.2rem' }}>
          {note || 'N/A'}
        </span>
      )}
    </div>
  );
};
