/**
 * MediCare AI — Apex Cinematic Auth Controller
 * Integrates MedicareCinematicEngine, Fluid Morphing Tabs & Signature Login-Success Transition
 */

(function () {
  "use strict";

  const $ = (selector, parent = document) => parent.querySelector(selector);
  const $$ = (selector, parent = document) => [...parent.querySelectorAll(selector)];

  // ==========================================================================
  // 1. THEME MANAGEMENT
  // ==========================================================================
  const THEME_KEY = "medicareThemeV4";

  function initTheme() {
    const saved = localStorage.getItem(THEME_KEY) || "dark";
    document.documentElement.setAttribute("data-theme", saved);
    updateThemeIcon(saved);

    const toggleBtn = $("#themeToggleBtn");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        const current = document.documentElement.getAttribute("data-theme") || "dark";
        const next = current === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        localStorage.setItem(THEME_KEY, next);
        updateThemeIcon(next);
      });
    }
  }

  function updateThemeIcon(theme) {
    const icon = $("#themeToggleBtn .theme-icon");
    if (icon) {
      icon.textContent = theme === "dark" ? "☀" : "☾";
    }
  }

  // ==========================================================================
  // 2. UNIFIED CINEMATIC GRAPHICS ENGINE INTEGRATION
  // ==========================================================================
  let authEngine = null;

  function initAuthGraphics() {
    const canvas = $("#healthCanvas");
    if (!canvas || typeof window.MedicareCinematicEngine === "undefined") return;

    try {
      authEngine = new window.MedicareCinematicEngine({
        canvas: canvas,
        mode: "auth",
        intensity: 0.8,
        initialState: "idle"
      });
    } catch (err) {
      console.warn("Auth graphics fallback:", err);
    }
  }

  // ==========================================================================
  // 3. MORPHING TAB SWITCHER & URL SYNC
  // ==========================================================================
  function setupTabs() {
    const tabLogin = $("#tabLoginBtn");
    const tabRegister = $("#tabRegisterBtn");
    const panelLogin = $("#panelLogin");
    const panelRegister = $("#panelRegister");
    const globalAlert = $("#authGlobalAlert");
    const quoteText = $("#authQuoteText");

    function switchTab(target) {
      if (globalAlert) globalAlert.classList.add("hidden");

      if (target === "register") {
        tabRegister?.classList.add("active");
        tabRegister?.setAttribute("aria-selected", "true");
        tabLogin?.classList.remove("active");
        tabLogin?.setAttribute("aria-selected", "false");

        panelRegister?.classList.remove("hidden");
        panelLogin?.classList.add("hidden");
        history.replaceState(null, "", "/register");

        if (quoteText) {
          quoteText.textContent = '"Khởi tạo tài khoản MediCare AI để đồng hành và bảo vệ sức khỏe cho bạn cùng từng thành viên gia đình."';
        }
      } else {
        tabLogin?.classList.add("active");
        tabLogin?.setAttribute("aria-selected", "true");
        tabRegister?.classList.remove("active");
        tabRegister?.setAttribute("aria-selected", "false");

        panelLogin?.classList.remove("hidden");
        panelRegister?.classList.add("hidden");
        history.replaceState(null, "", "/login");

        if (quoteText) {
          quoteText.textContent = '"Chào mừng trở lại. Tiếp tục hành trình sức khỏe thông minh và an toàn của bạn."';
        }
      }
    }

    tabLogin?.addEventListener("click", () => switchTab("login"));
    tabRegister?.addEventListener("click", () => switchTab("register"));
    $("#switchToRegisterBtn")?.addEventListener("click", () => switchTab("register"));
    $("#switchToLoginBtn")?.addEventListener("click", () => switchTab("login"));

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
  // 5. NOTIFICATION & ERROR HELPERS
  // ==========================================================================
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
  // 6. FORM SUBMISSIONS & SIGNATURE LOGIN-SUCCESS TRANSITION
  // ==========================================================================
  function setupAuthForms() {
    const loginForm = $("#loginForm");
    const registerForm = $("#registerForm");

    // --- Login Form Submission ---
    loginForm?.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearAllErrors();

      const accountInput = $("#loginAccount");
      const passwordInput = $("#loginPassword");
      const submitBtn = $("#loginSubmitBtn");
      const btnText = submitBtn?.querySelector(".btn-text");
      const spinner = submitBtn?.querySelector(".btn-spinner");

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

      if (submitBtn) submitBtn.disabled = true;
      if (btnText) btnText.textContent = "Đang xác thực...";
      if (spinner) spinner.classList.remove("hidden");

      try {
        const response = await fetch("/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ account, password })
        });

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
          throw new Error(data.error || "Đăng nhập không thành công.");
        }

        // SIGNATURE LOGIN-SUCCESS CINEMATIC TRANSITION
        const cardPanel = $("#authCardPanel");
        const successStage = $("#loginSuccessStage");

        if (cardPanel) cardPanel.classList.add("transitioning-out");
        if (successStage) successStage.classList.add("active");

        // Set session continuity flag for Health OS
        sessionStorage.setItem("medicare_login_transition", "1");

        const redirectUrl = new URLSearchParams(window.location.search).get("redirect") || "/dashboard";

        setTimeout(() => {
          window.location.href = redirectUrl;
        }, 650);

      } catch (err) {
        showGlobalAlert(err.message || "Không thể kết nối đến máy chủ.");
        if (submitBtn) submitBtn.disabled = false;
        if (btnText) btnText.textContent = "Đăng nhập";
        if (spinner) spinner.classList.add("hidden");
      }
    });

    // --- Register Form Submission ---
    registerForm?.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearAllErrors();

      const fullName = $("#regFullName").value.trim();
      const email = $("#regEmail").value.trim().toLowerCase();
      const phone = $("#regPhone").value.trim();
      const password = $("#regPassword").value;
      const confirmPassword = $("#regConfirmPassword").value;

      const submitBtn = $("#registerSubmitBtn");
      const btnText = submitBtn?.querySelector(".btn-text");
      const spinner = submitBtn?.querySelector(".btn-spinner");

      let hasError = false;
      if (fullName.length < 2) {
        setFieldError("regFullName", "Vui lòng nhập họ và tên đầy đủ.");
        hasError = true;
      }
      if (!email || !email.includes("@") || !email.includes(".")) {
        setFieldError("regEmail", "Địa chỉ email không đúng định dạng.");
        hasError = true;
      }
      if (password.length < 8) {
        setFieldError("regPassword", "Mật khẩu phải có ít nhất 8 ký tự.");
        hasError = true;
      }
      if (password !== confirmPassword) {
        setFieldError("regConfirmPassword", "Mật khẩu xác nhận không khớp.");
        hasError = true;
      }
      if (hasError) return;

      if (submitBtn) submitBtn.disabled = true;
      if (btnText) btnText.textContent = "Đang khởi tạo tài khoản...";
      if (spinner) spinner.classList.remove("hidden");

      try {
        const response = await fetch("/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({
            full_name: fullName,
            email: email,
            phone: phone,
            password: password,
            confirm_password: confirmPassword
          })
        });

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
          throw new Error(data.error || "Không thể tạo tài khoản lúc này.");
        }

        showGlobalAlert("Đăng ký thành công! Đang chuyển sang màn hình đăng nhập...", "success");

        // Automatically prefill account and switch to login
        const loginAccount = $("#loginAccount");
        if (loginAccount) loginAccount.value = email;

        setTimeout(() => {
          $("#tabLoginBtn")?.click();
          if (submitBtn) submitBtn.disabled = false;
          if (btnText) btnText.textContent = "Đăng ký tài khoản";
          if (spinner) spinner.classList.add("hidden");
        }, 900);

      } catch (err) {
        showGlobalAlert(err.message || "Lỗi kết nối máy chủ.");
        if (submitBtn) submitBtn.disabled = false;
        if (btnText) btnText.textContent = "Đăng ký tài khoản";
        if (spinner) spinner.classList.add("hidden");
      }
    });
  }

  // DOM Bootstrapper
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      initTheme();
      initAuthGraphics();
      setupTabs();
      setupPasswordToggles();
      setupAuthForms();
    });
  } else {
    initTheme();
    initAuthGraphics();
    setupTabs();
    setupPasswordToggles();
    setupAuthForms();
  }
})();
