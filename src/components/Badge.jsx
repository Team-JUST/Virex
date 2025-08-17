import React from 'react';

const Badge = ({ label, onClick }) => {
  const sharedStyle = {
    backgroundColor: '#e0edff',
    width: '64px',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    color: '#0051b3',
    fontSize: '0.75rem',
    fontWeight: 600,
    padding: '4px 8px',
    borderRadius: '6px',
    cursor: onClick ? 'pointer' : 'default',
    border: 'none',
  };

  if (onClick) {
    return (
      <button style={sharedStyle} onClick={onClick}>
        {label}
      </button>
    );
  }

  return (
    <div style={sharedStyle}>
      {label}
    </div>
  );
};

export default Badge;
