import React from 'react';
import '../styles/Button.css';

const Button = ({ children, variant = 'dark', onClick, disabled = false }) => {
  return (
    <button
      className={`button ${variant}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
};

export default Button;
