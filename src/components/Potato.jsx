import React from "react";
import '../styles/Potato.css';
import potatoImage from '../images/potato.png'; // 이미지 경로 주의!
import potatoSmall from '../images/potatoSmall.png';

const PotatoJuggling = () => {
  return (
    <div style={{ width: "200px", height: "200px", position: "relative" }}>
      {/* 아래 고정 감자 */}
      <img
        src={potatoImage}
        alt="potato"
        style={{
          position: "absolute",
          bottom: "-12px",
          left: 0,
          right: 0,
          margin: "0 auto",
          display: "block",
          width: "120px",
          zIndex: 0,
        }}
      />

      <svg
        viewBox="0 0 200 200"
        xmlns="http://www.w3.org/2000/svg"
        style={{
          width: "100%",
          height: "100%",
          position: "absolute",
          top: 0,
          left: 0,
          zIndex: 1,
        }}
      >
        {[0, 0.5, 0.9].map((delay, i) => (
        <g
            key={i}
            className="orbit"
            style={{
            transformOrigin: "100px 90px",
            animationDelay: `${delay}s`,
            }}
        >
            <image
            href={potatoSmall}
            x="80"     // ← 더 바깥으로 (왼쪽/중심 맞추기)
            y="25"     // ← 더 위로 이동해서 궤도 넓힘
            width="50"
            height="50"
            />
        </g>
        ))}
      </svg>

      <style>
        {`
          @keyframes rotateOrbit {
            0%   { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }

          .orbit {
            animation: rotateOrbit 2s linear infinite;
          }
        `}
      </style>
    </div>
  );
};

export default PotatoJuggling;