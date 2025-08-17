import React from 'react';

const boxStyle = {
  position: 'relative',
  width: '960px',
  margin: '1.3rem 1rem 1rem 0rem',
  padding: '1rem',
  height: '555px',
  background: 'white',
  borderRadius: '0.6rem',
  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.3)',
};

const Box = ({ children }) => {
  return (
    <div style={boxStyle}>
      {children}
    </div>
  );
};

export default Box;
