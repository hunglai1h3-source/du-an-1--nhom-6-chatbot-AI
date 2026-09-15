/**
 * MediCare AI - Cinematic Auth Experience V3
 * Canvas 2D GPU Health Waveform & Ambient Neural Field
 * Fast & Secure Authentication Handler
 */

"use strict";

(function () {
  const $ = (selector, parent = document) => parent.querySelector(selector);
  const $$ = (selector, parent = document) => [...parent.querySelectorAll(selector)];

  // ==========================================================================
  // 1. THEME MANAGEMENT
  // ==========================================================================
  const THEME_KEY = "medicareThemeV4";

  function initTheme() {
    const saved = localStorage.getItem(THEME_KEY) || "light";
    document.documentElement.dataset.theme = saved;
    updateThemeIcon(saved);
  }

  function toggleTheme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem(THEME_KEY, next);
    updateThemeIcon(next);
  }

  function updateThemeIcon(theme) {
    const icon = $("#themeToggleBtn .theme-icon");
    if (icon) {
      icon.textContent = theme === "dark" ? "☀" : "☾";
    }
  }

  // ==========================================================================
  // 2. CINEMATIC HEALTH WAVEFORM & NEURAL ENGINE (Canvas 2D)
  // ==========================================================================
  class CinematicHealthCanvas {
    constructor(canvasEl) {
      this.canvas = canvasEl;
      if (!this.canvas) return;
      this.ctx = this.canvas.getContext("2d", { alpha: true });
      this.particles = [];
      this.animId = null;
      this.isPaused = false;
      this.width = 0;
      this.height = 0;
      this.ecgOffset = 0;

      // Reduced motion check
      this.reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (this.reducedMotion) return;

      this.init();
    }

    init() {
      this.resize();
      this.createParticles();
      this.bindEvents();
      this.start();
    }

    resize() {
      const rect = this.canvas.parentElement.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      this.width = rect.width;
      this.height = rect.height;
      this.canvas.width = this.width * dpr;
      this.canvas.height = this.height * dpr;
      this.ctx.scale(dpr, dpr);
    }

    createParticles() {
      this.particles = [];
      // Adaptive particle count based on screen width
      const count = this.width > 1200 ? 32 : 20;
      for (let i = 0; i < count; i++) {
        this.particles.push({
          x: Math.random() * this.width,
          y: Math.random() * this.height,
          vx: (Math.random() - 0.5) * 0.45,
          vy: (Math.random() - 0.5) * 0.45,
          radius: Math.random() * 2.2 + 1.2,
          alpha: Math.random() * 0.5 + 0.25,
          glow: Math.random() * 6 + 2,
        });
      }
    }

    bindEvents() {
      window.addEventListener("resize", () => {
        this.resize();
        this.createParticles();
      }, { passive: true });

      // Energy-saving auto-pause when tab is hidden
      document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
          this.pause();
        } else {
          this.resume();
        }
      });
    }

    pause() {
      this.isPaused = true;
      if (this.animId) {
        cancelAnimationFrame(this.animId);
        this.animId = null;
      }
    }

    resume() {
      if (this.isPaused && !this.reducedMotion) {
        this.isPaused = false;
        this.start();
      }
    }

    start() {
      const render = () => {
        if (this.isPaused) return;
        this.draw();
        this.animId = requestAnimationFrame(render);
      };
      this.animId = requestAnimationFrame(render);
    }

    draw() {
      this.ctx.clearRect(0, 0, this.width, this.height);

      // 1. Draw subtle ECG health pulse wave across vertical center
      this.drawEcgWave();

      // 2. Draw neural particles & connections
      this.drawParticles();
    }

    drawEcgWave() {
      this.ecgOffset += 1.4;
      const ctx = this.ctx;
      const centerY = this.height * 0.62;
      ctx.beginPath();
      ctx.strokeStyle = "rgba(13, 148, 136, 0.22)";
      ctx.lineWidth = 1.6;

      const step = 4;
      for (let x = 0; x < this.width; x += step) {
        const waveX = (x + this.ecgOffset) % 420;
        let y = centerY;

        // Simulate periodic P-Q-R-S-T cardiac waveform
        if (waveX > 150 && waveX < 170) {
          y -= Math.sin((waveX - 150) / 20 * Math.PI) * 12; // P wave
        } else if (waveX >= 170 && waveX < 185) {
          y += 6; // Q drop
        } else if (waveX >= 185 && waveX < 205) {
          const t = (waveX - 185) / 20;
          y -= (1 - Math.abs(t - 0.5) * 2) * 52; // R spike
        } else if (waveX >= 205 && waveX < 220) {
          y += 14; // S drop
        } else if (waveX >= 240 && waveX < 275) {
          y -= Math.sin((waveX - 240) / 35 * Math.PI) * 18; // T wave
        }

        if (x === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
    }

    drawParticles() {
      const ctx = this.ctx;
      const pLen = this.particles.length;

      // Update positions & draw points
      for (let i = 0; i < pLen; i++) {
        const p = this.particles[i];
        p.x += p.vx;
        p.y += p.vy;

        if (p.x < 0) p.x = this.width;
        if (p.x > this.width) p.x = 0;
        if (p.y < 0) p.y = this.height;
        if (p.y > this.height) p.y = 0;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(45, 212, 191, ${p.alpha})`;
        ctx.fill();

        // Connect nearby nodes
        for (let j = i + 1; j < pLen; j++) {
          const p2 = this.particles[j];
          const dx = p.x - p2.x;
          const dy = p.y - p2.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < 130) {
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(p2.x, p2.y);
            const lineAlpha = (1 - dist / 130) * 0.22;
            ctx.strokeStyle = `rgba(13, 148, 136, ${lineAlpha})`;
            ctx.lineWidth = 0.9;
            ctx.stroke();
          }
        }
      }
    }
  }

  // ==========================================================================
  // 3. TAB SWITCHING & URL SYNC
  // ==========================================================================
  function setupTabs() {
    const tabLogin = $("#tabLoginBtn");
    const tabRegister = $("#tabRegisterBtn");
    const panelLogin = $("#panelLogin");
    const panelRegister = $("#panelRegister");
    const globalAlert = $("#authGlobalAlert");

    function switchTab(target) {
      if (globalAlert) globalAlert.classList.add("hidden");

      if (target === "register") {
        tabRegister.classList.add("active");
        tabRegister.setAttribute("aria-selected", "true");
        tabLogin.classList.remove("active");
        tabLogin.setAttribute("aria-selected", "false");

        panelRegister.classList.remove("hidden");
        panelLogin.classList.add("hidden");
        history.replaceState(null, "", "/register");
      } else {
        tabLogin.classList.add("active");
        tabLogin.setAttribute("aria-selected", "true");
        tabRegister.classList.remove("active");
        tabRegister.setAttribute("aria-selected", "false");

        panelLogin.classList.remove("hidden");
        panelRegister.classList.add("hidden");
        history.replaceState(null, "", "/login");
      }
    }

    tabLogin?.addEventListener("click", () => switchTab("login"));
    tabRegister?.addEventListener("click", () => switchTab("register"));
    $("#switchToRegisterBtn")?.addEventListener("click", () => switchTab("register"));
    $("#switchToLoginBtn")?.addEventListener("click", () => switchTab("login"));

    // Check initial query parameter or path
    if (window.location.pathname.includes("register") || new URLSearchParams(window.location.search).get("tab") === "register") {
      switchTab("register");
    }
  }

  // ==========================================================================
  // 4. PASSWORD VISIBILITY TOGGLE
  // ==========================================================================
  function setupPasswordToggles() {
    $$(".pwd-toggle-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const targetId = btn.dataset.target;
        const input = $(`#${targetId}`);
        if (!input) return;

        const isPassword = input.type === "password";
        input.type = isPassword ? "text" : "password";
        const eyeIcon = btn.querySelector(".eye-icon");
        if (eyeIcon) {
          eyeIcon.textContent = isPassword ? "🙈" : "👁";
        }
      });
    });
  }

  // ==========================================================================
  // 5. TOAST & NOTIFICATION HELPERS
  // ==========================================================================
  let toastTimer = null;
  function showToast(message, type = "info") {
    const toast = $("#authToast");
    if (!toast) return;
    toast.textContent = message;
    toast.className = `auth-toast show ${type}`;
    toast.classList.remove("hidden");

    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.add("hidden");
    }, 3800);
  }

  function showGlobalAlert(message, type = "error") {
    const alert = $("#authGlobalAlert");
    if (!alert) return;
    alert.textContent = message;
    alert.className = `auth-global-alert ${type}`;
    alert.classList.remove("hidden");
  }

  function setFieldError(fieldId, errorMsg) {
    const errEl = $(`#${fieldId}Error`);
    const input = $(`#${fieldId}`);
    if (errEl) {
      if (errorMsg) {
        errEl.textContent = errorMsg;
        errEl.classList.remove("hidden");
        input?.setAttribute("aria-invalid", "true");
      } else {
        errEl.textContent = "";
        errEl.classList.add("hidden");
        input?.removeAttribute("aria-invalid");
      }
    }
  }

  function clearAllErrors() {
    const alert = $("#authGlobalAlert");
    if (alert) alert.classList.add("hidden");
    $$(".field-error").forEach((el) => el.classList.add("hidden"));
    $$("input").forEach((input) => input.removeAttribute("aria-invalid"));
  }

  // ==========================================================================
  // 6. FORM SUBMISSION (LOGIN & REGISTER)
  // ==========================================================================
  function setupAuthForms() {
    const loginForm = $("#loginForm");
    const registerForm = $("#registerForm");

    // Login Handler
    loginForm?.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearAllErrors();

      const accountInput = $("#loginAccount");
      const passwordInput = $("#loginPassword");
      const submitBtn = $("#loginSubmitBtn");
      const btnText = submitBtn.querySelector(".btn-text");
      const spinner = submitBtn.querySelector(".btn-spinner");

      const account = accountInput.value.trim();
      const password = passwordInput.value;

      let hasError = false;
      if (!account) {
        setFieldError("loginAccount", "Vui lòng nhập email hoặc số điện thoại.");
        hasError = true;
      }
      if (!password) {
        setFieldError("loginPassword", "Vui lòng nhập mật khẩu.");
        hasError = true;
      }
      if (hasError) return;

      submitBtn.disabled = true;
      btnText.textContent = "Đang xác thực...";
      spinner.classList.remove("hidden");

      try {
        const response = await fetch("/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ account, password }),
        });

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
          throw new Error(data.error || "Đăng nhập không thành công.");
        }

        showGlobalAlert("Đăng nhập thành công! Đang chuyển hướng...", "success");
        showToast("Chào mừng bạn trở lại MediCare AI!", "success");

        const redirectUrl = new URLSearchParams(window.location.search).get("redirect") || "/";
        setTimeout(() => {
          window.location.href = redirectUrl;
        }, 550);
      } catch (err) {
        showGlobalAlert(err.message || "Không thể kết nối đến máy chủ.");
        submitBtn.disabled = false;
        btnText.textContent = "Đăng nhập";
        spinner.classList.add("hidden");
      }
    });

    // Register Handler
    registerForm?.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearAllErrors();

      const fullName = $("#regFullName").value.trim();
      const email = $("#regEmail").value.trim().toLowerCase();
      const phone = $("#regPhone").value.trim();
      const password = $("#regPassword").value;
      const confirmPassword = $("#regConfirmPassword").value;

      const submitBtn = $("#registerSubmitBtn");
      const btnText = submitBtn.querySelector(".btn-text");
      const spinner = submitBtn.querySelector(".btn-spinner");

      let hasError = false;
      if (fullName.length < 2) {
        setFieldError("regFullName", "Họ và tên cần có ít nhất 2 ký tự.");
        hasError = true;
      }
      if (!email || !email.includes("@") || !email.includes(".")) {
        setFieldError("regEmail", "Địa chỉ email không đúng định dạng.");
        hasError = true;
      }
      if (phone) {
        const cleanPhone = phone.replace(/[\s-]/g, "");
        if (!/^\d{9,11}$/.test(cleanPhone)) {
          setFieldError("regPhone", "Số điện thoại cần có từ 9 đến 11 chữ số.");
          hasError = true;
        }
      }
      if (password.length < 8) {
        setFieldError("regPassword", "Mật khẩu phải chứa ít nhất 8 ký tự.");
        hasError = true;
      }
      if (password !== confirmPassword) {
        setFieldError("regConfirmPassword", "Mật khẩu xác nhận không khớp.");
        hasError = true;
      }

      if (hasError) return;

      submitBtn.disabled = true;
      btnText.textContent = "Đang tạo tài khoản...";
      spinner.classList.remove("hidden");

      try {
        const response = await fetch("/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({
            full_name: fullName,
            email,
            phone,
            password,
            confirm_password: confirmPassword,
          }),
        });

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
          throw new Error(data.error || "Đăng ký không thành công.");
        }

        showGlobalAlert("Tạo tài khoản thành công! Tự động đăng nhập...", "success");
        showToast("Đăng ký thành công!", "success");

        // Automatically log user in
        const loginRes = await fetch("/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ account: email, password }),
        });

        if (loginRes.ok) {
          setTimeout(() => {
            window.location.href = "/";
          }, 600);
        } else {
          // Switch to login tab if auto-login fails
          $("#tabLoginBtn")?.click();
          submitBtn.disabled = false;
          btnText.textContent = "Đăng ký tài khoản";
          spinner.classList.add("hidden");
        }
      } catch (err) {
        showGlobalAlert(err.message || "Không thể hoàn tất đăng ký.");
        submitBtn.disabled = false;
        btnText.textContent = "Đăng ký tài khoản";
        spinner.classList.add("hidden");
      }
    });

    // Forgot Password link helper
    $("#forgotPwdLink")?.addEventListener("click", () => {
      showToast("Vui lòng liên hệ quản trị viên hoặc sử dụng số điện thoại đăng ký để đặt lại mật khẩu.");
    });
  }

  // ==========================================================================
  // INITIALIZATION
  // ==========================================================================
  document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    $("#themeToggleBtn")?.addEventListener("click", toggleTheme);

    const canvas = $("#healthCanvas");
    if (canvas) {
      new CinematicHealthCanvas(canvas);
    }

    setupTabs();
    setupPasswordToggles();
    setupAuthForms();
  });
})();
