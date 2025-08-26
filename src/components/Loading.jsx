import React from "react";

const Loading = ({
  size = 160,          
  segments = 16,  
  radius = 56,     
  dotRadius = 9,     
  speed = 1.6,      
  color = "#2F6BFF",   
  baseAlpha = 0.25,   
  peakAlpha = 1.0,
  text = "Recovering...",
}) => {

  const perStepDelay = speed / segments;

  return (
    <div
      style={{
        marginTop: 40,
        marginBottom:20,
        width: size,
        height: size + 28,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {Array.from({ length: segments }).map((_, i) => {
          const angle = (i * 360) / segments;
          const rad = (angle * Math.PI) / 180;
          const cx = size / 2 + radius * Math.cos(rad);
          const cy = size / 2 + radius * Math.sin(rad);

          return (
            <circle
              key={i}
              cx={cx}
              cy={cy}
              r={dotRadius}
              fill={color}
              style={{
                opacity: baseAlpha,
                animation: `sweep ${speed}s linear infinite`,
                animationDelay: `${-perStepDelay * i}s`,
              }}
            />
          );
        })}
      </svg>

      <div style={{ marginTop: 8, fontWeight: 600 }}>{text}</div>

      <style>{`
        @keyframes sweep {
          0%   { opacity: ${baseAlpha}; }
          40%  { opacity: ${baseAlpha}; }
          50%  { opacity: ${peakAlpha}; }  /* 하이라이트 */
          60%  { opacity: ${baseAlpha}; }
          100% { opacity: ${baseAlpha}; }
        }
      `}</style>
    </div>
  );
};

export default Loading;
