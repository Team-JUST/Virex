import React from 'react';

const Badge = ({ label, onClick }) => {
  const sharedStyle = {
    backgroundColor: '#e88e8eff',
    width: '64px',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    color: '#6c1e1dff',
    fontSize: '0.75rem',
    fontWeight: 600,
    padding: '4px 8px',
    borderRadius: '6px',
    cursor: onClick ? 'pointer' : 'default',
    border: 'none',
  };


  return (
    <div style={sharedStyle}>
      {label}
    </div>
  );
};

export default Badge;
