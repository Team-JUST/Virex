import React from 'react';
import '../styles/Button.css';

const Button = ({ children, variant = 'dark', onClick }) => {
  return (
    <button className={`button ${variant}`} onClick={onClick}>
      {children}
    </button>
  );
};

export default Button;
