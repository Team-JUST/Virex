import React from 'react';

const Box = ({ children, isDarkMode }) => {
  const boxStyle = {
    position: 'relative',
    width: '960px',
    margin: '1.3rem 1rem 1rem 0rem',
    padding: '1rem',
    height: '555px',
    background: isDarkMode ? '#1e293b' : 'white',
    borderRadius: '0.6rem',
    boxShadow: isDarkMode
      ? '0 2px 8px rgba(0, 0, 0, 0.5)'
      : '0 2px 8px rgba(0, 0, 0, 0.3)',
    color: isDarkMode ? '#f1f5f9' : 'inherit',
  };


  return (
    <div style={boxStyle}>
      {children}
    </div>
  );
};


export default Box;