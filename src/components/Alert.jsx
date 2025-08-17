import React, { forwardRef } from 'react';
import '../styles/Alert.css';

const Alert = forwardRef(({ icon, title, description, children }, ref) => {
  return (
    <div className="alert-box" ref={ref}>
      <div className="alert-title">
        <img src={icon} alt="아이콘" style={{ width: 30, height: 30 }} />
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
