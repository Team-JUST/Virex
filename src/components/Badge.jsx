import React from 'react';

const Badge = ({ label, onClick, variant = "blue", size = "default" }) => {
  // size에 따라 height/lineHeight 변경
  const isBig = size === 'big';
  const baseStyle = {
    width: '70px',
    minWidth: '64px',
    height: isBig ? '45px' : '28px',
    minHeight: isBig ? '45px' : '20px',
    lineHeight: isBig ? '45px' : '20px',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    fontSize: '0.75rem',
    fontWeight: 600,
    padding: isBig ? '8px 16px' : '4px 8px',
    borderRadius: '6px',
    border: 'none',
    boxSizing: 'border-box',
    cursor: onClick ? 'pointer' : 'default',
    transition: 'height 0.2s, line-height 0.2s, font-size 0.2s',
  };

  const colorStyles = {
    blue:   { backgroundColor: '#e0edff', color: '#0051b3' },
    red:    { backgroundColor: '#ffe0e0', color: '#b30000' },
    yellow: { backgroundColor: '#FEF3C7', color: '#92400E' },
  };

  const style = { ...baseStyle, ...(colorStyles[variant] || colorStyles.blue) };

  // 항상 button으로 렌더링
  return (
    <button style={style} onClick={onClick} type="button" tabIndex={0} disabled={!onClick}>
      {label}
    </button>
  );
};

export default Badge;