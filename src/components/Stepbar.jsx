import React, { useEffect, useRef } from 'react';
import '../styles/Stepbar.css';
import '@fortawesome/fontawesome-free/css/all.min.css';

const Stepbar = ({ currentStep }) => {
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
      steps[i].querySelector('.circle').innerHTML = '<i class="fas fa-check"></i>';
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
      stepLine.style.background = `linear-gradient(to right, #1f2937 0%, #1f2937 ${percent}%, #d7d7d7 ${percent}%, #d7d7d7 100%)`;
    }
  }, [currentStep]);

  return (
    <div className="rcvpage">
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
