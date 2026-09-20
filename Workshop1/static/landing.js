/**
 * MediCare AI — Apex Public Landing Controller
 * Integrates MedicareCinematicEngine, 1.4s Intro Sequence, Session Continuation & Parallax
 */

(function () {
  "use strict";

  const prefersReducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ==========================================================================
  // 1. THEME MANAGEMENT
  // ==========================================================================
  const THEME_KEY = "medicareThemeV4";

  function initTheme() {
    const saved = localStorage.getItem(THEME_KEY) || "dark";
    document.documentElement.setAttribute("data-theme", saved);

    const toggleBtn = document.getElementById("themeToggleBtn");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        const current = document.documentElement.getAttribute("data-theme") || "dark";
        const next = current === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        localStorage.setItem(THEME_KEY, next);
      });
    }
  }

  // ==========================================================================
  // 2. CINEMATIC INTRO LIFECYCLE (~1.4s on first session, skippable)
  // ==========================================================================
  function initIntro() {
    const introEl = document.getElementById("cinematicIntro");
    if (!introEl) return;

    const skipBtn = document.getElementById("introSkipBtn");
    const introSeen = sessionStorage.getItem("medicareIntroSeen");

    function dismissIntro() {
      introEl.classList.add("dismissed");
      sessionStorage.setItem("medicareIntroSeen", "1");
      setTimeout(() => {
        introEl.style.display = "none";
      }, 600);
    }

    if (introSeen || prefersReducedMotion) {
      introEl.style.display = "none";
    } else {
      // Run the 1.4s intro sequence then dismiss
      const timer = setTimeout(() => {
        dismissIntro();
      }, 1400);

      if (skipBtn) {
        skipBtn.addEventListener("click", () => {
          clearTimeout(timer);
          dismissIntro();
        });
      }
    }
  }

  // ==========================================================================
  // 3. UNIFIED CINEMATIC GRAPHICS ENGINE INITIALIZATION & ENERGY SAVINGS
  // ==========================================================================
  let engineInstance = null;
  let landingRafId = null;

  function initGraphicsEngine() {
    const canvas = document.getElementById("landingCanvas");
    if (!canvas || typeof window.MedicareCinematicEngine === "undefined") return;

    try {
      engineInstance = new window.MedicareCinematicEngine({
        canvas: canvas,
        mode: "hero",
        intensity: 1.0,
        initialState: "idle"
      });
    } catch (err) {
      console.warn("Could not instantiate MedicareCinematicEngine:", err);
    }

    // Auto energy-saving when tab is hidden
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        if (engineInstance) engineInstance.pause();
        if (landingRafId) {
          cancelAnimationFrame(landingRafId);
          landingRafId = null;
        }
      } else if (!prefersReducedMotion) {
        if (engineInstance) engineInstance.resume();
      }
    });
  }

  // ==========================================================================
  // 4. ACTIVE SESSION RESUMPTION (RESPECT AUTHENTICATED STATE)
  // ==========================================================================
  async function checkActiveSession() {
    try {
      const response = await fetch("/current-user", {
        method: "GET",
        headers: { "Accept": "application/json" },
        credentials: "same-origin"
      });

      if (!response.ok) return;
      const data = await response.json();

      if (data && data.logged_in) {
        // User has an active authenticated session
        const navAuthGroup = document.getElementById("navAuthGroup");
        if (navAuthGroup) {
          navAuthGroup.innerHTML = `
            <a href="/dashboard" class="nav-btn-primary" style="display:inline-flex;align-items:center;gap:6px;">
              <span>Không gian Sức khỏe</span>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
            </a>
          `;
        }

        const primaryBtn = document.getElementById("primaryActionBtn");
        if (primaryBtn) {
          primaryBtn.href = "/dashboard";
          primaryBtn.innerHTML = `
            <span>Tiếp tục với MediCare AI</span>
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
          `;
        }

        const secondaryBtn = document.getElementById("secondaryActionBtn");
        if (secondaryBtn) {
          secondaryBtn.href = "/tu-van";
          secondaryBtn.querySelector("span").textContent = "Tư vấn AI";
        }

        const bannerRegisterBtn = document.getElementById("bannerRegisterBtn");
        if (bannerRegisterBtn) {
          bannerRegisterBtn.href = "/dashboard";
          bannerRegisterBtn.textContent = "Vào Không gian Sức khỏe →";
        }

        const bannerLoginBtn = document.getElementById("bannerLoginBtn");
        if (bannerLoginBtn) {
          bannerLoginBtn.href = "/tu-van";
          bannerLoginBtn.textContent = "Bắt đầu cuộc trò chuyện";
        }
      }
    } catch (err) {
      // Silently ignore network failures on public landing
    }
  }

  // ==========================================================================
  // 5. SCROLL OBSERVATION & SUBTLE CORE REACTIONS
  // ==========================================================================
  function setupScrollStoryObserver() {
    if (!("IntersectionObserver" in window) || prefersReducedMotion) return;

    const safetySection = document.getElementById("safety");
    if (safetySection && engineInstance) {
      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            engineInstance.setState("caution");
          } else {
            engineInstance.setState("idle");
          }
        });
      }, { threshold: 0.4 });

      observer.observe(safetySection);
    }
  }

  // DOM Content Ready Bootstrapper
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      initTheme();
      initIntro();
      initGraphicsEngine();
      checkActiveSession();
      setupScrollStoryObserver();
    });
  } else {
    initTheme();
    initIntro();
    initGraphicsEngine();
    checkActiveSession();
    setupScrollStoryObserver();
  }
})();
