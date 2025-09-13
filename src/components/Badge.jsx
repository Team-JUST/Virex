import React from 'react';

const Badge = ({ label, onClick, variant = "blue" }) => {
  const baseStyle = {
    width: '64px',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    fontSize: '0.75rem',
    fontWeight: 600,
    padding: '4px 8px',
    borderRadius: '6px',
    border: 'none',
    cursor: onClick ? 'pointer' : 'default',
  };

  const colorStyles = {
    blue:   { backgroundColor: '#e0edff', color: '#0051b3' },
    red:    { backgroundColor: '#ffe0e0', color: '#b30000' },
    yellow: { backgroundColor: '#FEF3C7', color: '#92400E' },
  };

  const style = { ...baseStyle, ...(colorStyles[variant] || colorStyles.blue) };

  if (onClick) {
    return <button style={style} onClick={onClick}>{label}</button>;
  }
  return <div style={style}>{label}</div>;
};

export default Badge;