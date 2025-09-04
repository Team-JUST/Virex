import React, { forwardRef } from 'react';
import '../styles/Alert.css';

const Alert = forwardRef(({ icon, title, description, children, isDarkMode }, ref) => {
  return (
    <div className={`alert-box ${isDarkMode ? 'dark-mode' : ''}`} ref={ref}>
      <div className="alert-title">
        <div className="alert-icon-wrapper">{icon}</div>
        <span>{title}</span>
      </div>
      <div className="alert-desc">{description}</div>
      <div style={{ marginTop: '1rem' }}>
        {children}
      </div>
    </div>
  );
});

export default Alert;
