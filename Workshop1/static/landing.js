/**
 * MediCare AI — Public Landing Canvas & Interactivity (VIP Pro V3)
 * Ambient 60 FPS Biometric Flow, Tab Visibility Savings & Theme Toggle
 */

(function() {
  "use strict";

  // 1. Theme Toggle
  const themeToggleBtn = document.getElementById("themeToggleBtn");
  if (themeToggleBtn) {
    const savedTheme = localStorage.getItem("medicareTheme") || "dark";
    document.documentElement.setAttribute("data-theme", savedTheme);

    themeToggleBtn.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme") || "dark";
      const next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("medicareTheme", next);
    });
  }

  // 2. Biometric Canvas Engine
  const canvas = document.getElementById("landingCanvas");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  let width = 0;
  let height = 0;
  let animationFrameId = null;
  let isPaused = false;

  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }
  window.addEventListener("resize", resize);
  resize();

  // Nodes for neural connection network
  const NODE_COUNT = width < 768 ? 24 : 48;
  const nodes = [];

  for (let i = 0; i < NODE_COUNT; i++) {
    nodes.push({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.45,
      vy: (Math.random() - 0.5) * 0.45,
      radius: Math.random() * 2 + 1.2,
      phase: Math.random() * Math.PI * 2
    });
  }

  let step = 0;

  function render(time) {
    if (isPaused) return;

    ctx.clearRect(0, 0, width, height);

    const isDark = document.documentElement.getAttribute("data-theme") !== "light";
    const lineColor = isDark ? "rgba(6, 182, 212, 0.08)" : "rgba(13, 148, 136, 0.07)";
    const nodeColor = isDark ? "rgba(20, 184, 166, 0.55)" : "rgba(13, 148, 136, 0.45)";
    const pulseColor = isDark ? "rgba(6, 182, 212, 0.22)" : "rgba(13, 148, 136, 0.18)";

    step += 0.015;

    // Draw Biometric Wave (Midground)
    ctx.beginPath();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = pulseColor;

    const centerY = height * 0.48;
    for (let x = 0; x < width; x += 10) {
      // Periodic ECG peak
      const waveX = (x + step * 40) % (width * 0.7);
      let ecg = 0;
      if (waveX > 300 && waveX < 360) {
        const p = (waveX - 300) / 60;
        if (p < 0.2) ecg = -15 * Math.sin(p * Math.PI * 5);
        else if (p < 0.5) ecg = 55 * Math.sin((p - 0.2) * Math.PI * 3.33);
        else if (p < 0.7) ecg = -25 * Math.sin((p - 0.5) * Math.PI * 5);
        else ecg = 18 * Math.sin((p - 0.7) * Math.PI * 3.33);
      }
      const y = centerY + Math.sin(x * 0.004 + step) * 20 + ecg;
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Draw Floating Intelligent Neural Nodes & Connections (Foreground)
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      n.x += n.vx;
      n.y += n.vy;

      if (n.x < 0) n.x = width;
      if (n.x > width) n.x = 0;
      if (n.y < 0) n.y = height;
      if (n.y > height) n.y = 0;

      // Draw connections
      for (let j = i + 1; j < nodes.length; j++) {
        const m = nodes[j];
        const dx = n.x - m.x;
        const dy = n.y - m.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 140) {
          ctx.beginPath();
          ctx.strokeStyle = lineColor;
          ctx.lineWidth = 1 - dist / 140;
          ctx.moveTo(n.x, n.y);
          ctx.lineTo(m.x, m.y);
          ctx.stroke();
        }
      }

      // Draw Node
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
      ctx.fillStyle = nodeColor;
      ctx.fill();
    }

    if (!prefersReducedMotion) {
      animationFrameId = requestAnimationFrame(render);
    }
  }

  // 3. Tab Visibility Power-Saving
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      isPaused = true;
      if (animationFrameId) cancelAnimationFrame(animationFrameId);
    } else {
      isPaused = false;
      if (!prefersReducedMotion) {
        animationFrameId = requestAnimationFrame(render);
      }
    }
  });

  // Start Animation
  if (!prefersReducedMotion) {
    animationFrameId = requestAnimationFrame(render);
  } else {
    render();
  }

  // 4. Cinematic Intro Handling
  const intro = document.getElementById("cinematicIntro");
  if (intro) {
    const seen = sessionStorage.getItem("medicareIntroSeen");
    if (seen || prefersReducedMotion) {
      intro.style.display = "none";
    } else {
      setTimeout(() => {
        intro.classList.add("dismissed");
        sessionStorage.setItem("medicareIntroSeen", "1");
        setTimeout(() => { intro.style.display = "none"; }, 600);
      }, 1200);
    }
  }
})();
