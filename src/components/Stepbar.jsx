import React, { useEffect, useRef } from 'react';
import '../styles/Stepbar.css';
import '@fortawesome/fontawesome-free/css/all.min.css';

const Stepbar = ({ currentStep, isDarkMode }) => {
  const wrapperRef = useRef(null);

  useEffect(() => {
    const steps = wrapperRef.current?.querySelectorAll('.step');

    if (!steps || steps.length === 0) return;

    // 모든 step 초기화
    steps.forEach((step, index) => {
      step.classList.remove('active', 'completed');
      step.querySelector('.circle').textContent = '';
    });

    // completed 처리
    for (let i = 0; i < currentStep; i++) {
      steps[i].classList.add('completed');
      steps[i].querySelector('.circle').innerHTML = '<i class="fas fa-check" style="margin-top: 2px;"></i>';
    }

    // active 처리
    if (steps[currentStep]) {
      steps[currentStep].classList.add('active');
      steps[currentStep].querySelector('.circle').textContent = currentStep + 1;
    }

    // step-line 진행선
    const percent = (currentStep / (steps.length - 1)) * 100;
    const stepLine = wrapperRef.current.querySelector('.step-line');
    if (stepLine) {
      const activeColor = isDarkMode ? '#3b82f6' : '#1f2937';
      const inactiveColor = isDarkMode ? '#475569' : '#d7d7d7';
      stepLine.style.background = `linear-gradient(to right, ${activeColor} 0%, ${activeColor} ${percent}%, ${inactiveColor} ${percent}%, ${inactiveColor} 100%)`;
    }
  }, [currentStep, isDarkMode]);

  return (
    <div className={`rcvpage ${isDarkMode ? 'dark-mode' : ''}`}>
      <div className="stepper-wrapper" ref={wrapperRef}>
        <div className="step-line"></div>
        <div className="steps">
          <div className="step">
            <div className="circle"></div>
            <div className="label">File Upload</div>
          </div>
          <div className="step">
            <div className="circle"></div>
            <div className="label">File Recovery</div>
          </div>
          <div className="step">
            <div className="circle"></div>
            <div className="label">Result</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Stepbar;
