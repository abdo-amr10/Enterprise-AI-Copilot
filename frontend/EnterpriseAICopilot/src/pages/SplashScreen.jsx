
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import Logo from "../assets/Logo.png";
import "../styles/splash.css";

function SplashScreen() {
    const navigate = useNavigate();

  useEffect(() => {
    const timer = setTimeout(() => {
      navigate("/login");
    }, 7500);

  return () => clearTimeout(timer);
  }, [navigate]);

  return (
    <div className="stage">
        <div className="lockup">
        <div className="logo-stage">
          <svg
            className="network-svg"
            viewBox="0 0 300 300"
            xmlns="http://www.w3.org/2000/svg"
          >
            <defs>
              <linearGradient
                id="lineGrad"
                x1="0%"
                y1="0%"
                x2="100%"
                y2="100%"
              >
                <stop offset="0%" stopColor="#3fa0ff" />
                <stop offset="100%" stopColor="#1f6fff" />
              </linearGradient>

              <radialGradient
                id="nodeGrad"
                cx="35%"
                cy="30%"
                r="75%"
              >
                <stop offset="0%" stopColor="#bfe4ff" />
                <stop offset="45%" stopColor="#3fa0ff" />
                <stop offset="100%" stopColor="#1355c9" />
              </radialGradient>

              <linearGradient
                id="hexGrad"
                x1="10%"
                y1="0%"
                x2="90%"
                y2="100%"
              >
                <stop offset="0%" stopColor="#0a1230" />
                <stop offset="55%" stopColor="#0e2258" />
                <stop offset="100%" stopColor="#1450c4" />
              </linearGradient>
            </defs>

            <polygon
              id="hexFill"
              points="150,55 67.7,102.5 67.7,197.5 150,245 232.3,197.5 232.3,102.5"
            />

            <polygon
              id="hexOutline"
              points="150,55 67.7,102.5 67.7,197.5 150,245 232.3,197.5 232.3,102.5"
            />

            <path
              id="line1"
              className="n-line"
              d="M150,150 L150,55"
            />

            <path
              id="line2"
              className="n-line"
              d="M150,150 L67.7,102.5"
            />

            <path
              id="line3"
              className="n-line"
              d="M150,150 L150,245"
            />

            <circle
              id="node1"
              className="n-node"
              cx="150"
              cy="55"
              r="7"
            />

            <circle
              id="node2"
              className="n-node"
              cx="67.7"
              cy="102.5"
              r="7"
            />

            <circle
              id="node3"
              className="n-node"
              cx="150"
              cy="245"
              r="7"
            />

            <circle
              className="n-dot"
              cx="150"
              cy="150"
              r="10"
            />
          </svg>

          <img
            className="logo-img"
            src={Logo}
            alt="Enterprise AI Copilot logo"
          />

          <div className="pulse-ring"></div>
        </div>

        <div className="reveal-block">
          <div className="divider"></div>

          <div className="wordmark">
            <div className="l1">Enterprise</div>

            <div className="l2">
              <span className="ai">AI</span> Copilot
            </div>
          </div>
        </div>
      </div>

      <div className="tagline">
        ASK YOUR DATA. GET SECURE ANSWERS.
      </div>

     
    </div>
  );
}

export default SplashScreen;