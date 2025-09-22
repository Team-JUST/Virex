import React from "react";
import Lottie from "lottie-react";
import carLoading from "../images/carLoading.json";

const Loading = ({ text = "Recovering..." }) => (
  <div
    style={{
      marginTop: 40,
      marginBottom: 20,
      width: 260,
      height: 180,
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
    }}
  >
  <Lottie animationData={carLoading} style={{ width: 320, height: 180 }} loop />
    <div style={{ fontWeight: 600 }}>{text}</div>
  </div>
);

export default Loading;