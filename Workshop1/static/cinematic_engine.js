/**
 * MediCare AI — Apex Unified Cinematic Graphics Engine
 * Powers the MEDICARE Core, Harmonic Biometric Fields, Neural Signal Paths & Spatial Lighting
 * 
 * Performance Tiers: HIGH | BALANCED | LOW
 * Adaptive Visual Modes: 'ambient' | 'hero' | 'auth' | 'intro' | 'core'
 * Built-in Failsafe: WebGL / Canvas failure gracefully falls back to SVG/CSS without crashing the UI.
 * Zero Fake Medical Telemetry: Renders pure decorative brand biometric wave & neural connectivity.
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.MedicareCinematicEngine = factory();
  }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // System Core States & Semantic Visual Colors
  const STATES = {
    IDLE: 'idle',
    LISTENING: 'listening',
    PROCESSING: 'processing',
    RESPONDING: 'responding',
    SUCCESS: 'success',
    CAUTION: 'caution',
    URGENT: 'urgent',
    EMERGENCY: 'emergency'
  };

  const STATE_COLORS = {
    idle: { primary: '#0d9488', secondary: '#06b6d4', glow: 'rgba(13, 148, 136, 0.35)', coreGlow: 'rgba(6, 182, 212, 0.25)' },
    listening: { primary: '#0ea5e9', secondary: '#38bdf8', glow: 'rgba(14, 165, 233, 0.45)', coreGlow: 'rgba(56, 189, 248, 0.3)' },
    processing: { primary: '#14b8a6', secondary: '#2dd4bf', glow: 'rgba(20, 184, 166, 0.5)', coreGlow: 'rgba(45, 212, 191, 0.35)' },
    responding: { primary: '#10b981', secondary: '#34d399', glow: 'rgba(16, 185, 129, 0.45)', coreGlow: 'rgba(52, 211, 153, 0.3)' },
    success: { primary: '#059669', secondary: '#10b981', glow: 'rgba(5, 150, 105, 0.5)', coreGlow: 'rgba(16, 185, 129, 0.35)' },
    caution: { primary: '#d97706', secondary: '#f59e0b', glow: 'rgba(217, 119, 6, 0.45)', coreGlow: 'rgba(245, 158, 11, 0.3)' },
    urgent: { primary: '#ea580c', secondary: '#f97316', glow: 'rgba(234, 88, 12, 0.5)', coreGlow: 'rgba(249, 115, 22, 0.35)' },
    emergency: { primary: '#dc2626', secondary: '#ef4444', glow: 'rgba(220, 38, 38, 0.6)', coreGlow: 'rgba(239, 68, 68, 0.4)' }
  };

  class MedicareCinematicEngine {
    constructor(options = {}) {
      this.canvas = typeof options.canvas === 'string' ? document.querySelector(options.canvas) : options.canvas;
      this.mode = options.mode || 'hero'; // 'ambient' | 'hero' | 'auth' | 'intro' | 'core'
      this.intensity = typeof options.intensity === 'number' ? options.intensity : 1.0;
      this.currentState = options.initialState || STATES.IDLE;
      
      this.isPaused = false;
      this.rafId = null;
      this.step = 0;
      this.mouse = { x: -1000, y: -1000, targetX: -1000, targetY: -1000 };
      
      this.particles = [];
      this.dpr = Math.min(window.devicePixelRatio || 1, 2);
      
      // Determine device performance tier
      this.tier = this._detectPerformanceTier();
      this.reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      if (this.canvas) {
        try {
          this.ctx = this.canvas.getContext('2d', { alpha: true, desynchronized: true }) || this.canvas.getContext('2d');
          if (this.ctx) {
            this._init();
          } else {
            this._handleFallback();
          }
        } catch (err) {
          console.warn('MedicareCinematicEngine context error, falling back:', err);
          this._handleFallback();
        }
      }
    }

    _detectPerformanceTier() {
      const memory = navigator.deviceMemory || 4;
      const cores = navigator.hardwareConcurrency || 4;
      const isMobile = window.innerWidth < 768;

      if (isMobile || memory < 4 || cores < 4) {
        return 'BALANCED';
      }
      return 'HIGH';
    }

    _handleFallback() {
      if (this.canvas && this.canvas.parentElement) {
        this.canvas.parentElement.classList.add('cinematic-fallback');
      }
    }

    _init() {
      try {
        this._bindEvents();
        this.resize();
        this._initParticles();
        if (!this.reducedMotion && this.intensity > 0.05) {
          this.start();
        } else {
          this.renderStatic();
        }
      } catch (err) {
        console.warn('MedicareCinematicEngine initialization fallback:', err);
        this._handleFallback();
      }
    }

    _bindEvents() {
      this._onResize = () => this.resize();
      window.addEventListener('resize', this._onResize, { passive: true });

      this._onVisibilityChange = () => {
        if (document.hidden) {
          this.pause();
        } else if (!this.reducedMotion && this.intensity > 0.05) {
          this.resume();
        }
      };
      document.addEventListener('visibilitychange', this._onVisibilityChange);

      if (this.tier === 'HIGH' && window.innerWidth >= 1024 && !this.reducedMotion) {
        this._onMouseMove = (e) => {
          this.mouse.targetX = e.clientX;
          this.mouse.targetY = e.clientY;
        };
        window.addEventListener('mousemove', this._onMouseMove, { passive: true });
      }
    }

    resize() {
      if (!this.canvas || !this.ctx) return;
      const rect = this.canvas.parentElement ? this.canvas.parentElement.getBoundingClientRect() : this.canvas.getBoundingClientRect();
      this.width = rect.width || window.innerWidth;
      this.height = rect.height || window.innerHeight;
      
      this.canvas.width = Math.floor(this.width * this.dpr);
      this.canvas.height = Math.floor(this.height * this.dpr);
      this.ctx.setTransform(1, 0, 0, 1, 0, 0);
      this.ctx.scale(this.dpr, this.dpr);

      this._initParticles();
    }

    _initParticles() {
      this.particles = [];
      if (this.intensity <= 0.1 || this.reducedMotion) return;

      let count = 38;
      if (this.tier === 'BALANCED' || this.width < 768) count = 18;
      if (this.mode === 'auth') count = this.width < 768 ? 14 : 26;
      if (this.mode === 'core') count = 12;

      for (let i = 0; i < count; i++) {
        this.particles.push({
          x: Math.random() * this.width,
          y: Math.random() * this.height,
          vx: (Math.random() - 0.5) * (0.32 * this.intensity),
          vy: (Math.random() - 0.5) * (0.32 * this.intensity),
          radius: (Math.random() * 2 + 1.2) * (this.intensity > 0.5 ? 1 : 0.8),
          baseAlpha: Math.random() * 0.45 + 0.2
        });
      }
    }

    setState(newState) {
      if (STATES[newState.toUpperCase()]) {
        this.currentState = STATES[newState.toUpperCase()];
        if (this.currentState === STATES.EMERGENCY) {
          this.intensity = 0.05;
        }
      }
    }

    setIntensity(level) {
      this.intensity = Math.max(0, Math.min(1, level));
      if (this.intensity <= 0.05) {
        this.renderStatic();
      }
    }

    start() {
      if (this.rafId) return;
      this.isPaused = false;
      const loop = () => {
        if (!this.isPaused) {
          this._renderFrame();
          this.rafId = requestAnimationFrame(loop);
        }
      };
      this.rafId = requestAnimationFrame(loop);
    }

    pause() {
      this.isPaused = true;
      if (this.rafId) {
        cancelAnimationFrame(this.rafId);
        this.rafId = null;
      }
    }

    resume() {
      if (this.isPaused && !this.reducedMotion && this.intensity > 0.05) {
        this.start();
      }
    }

    renderStatic() {
      if (!this.ctx) return;
      this.pause();
      this.ctx.clearRect(0, 0, this.width, this.height);
      const colors = STATE_COLORS[this.currentState] || STATE_COLORS.idle;
      const isDark = document.documentElement.getAttribute('data-theme') !== 'light';

      if (this.mode === 'core') {
        this._drawCore(this.width / 2, this.height / 2, 44, colors, 0);
      } else {
        // Draw one static clean ambient wave
        this._drawHarmonicBiometricWave(colors, isDark, true);
      }
    }

    _renderFrame() {
      if (!this.ctx) return;
      this.ctx.clearRect(0, 0, this.width, this.height);
      this.step += 0.015;

      const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
      const colors = STATE_COLORS[this.currentState] || STATE_COLORS.idle;

      // Smooth pointer interpolation
      if (this.tier === 'HIGH' && this.mouse.targetX > -500) {
        this.mouse.x += (this.mouse.targetX - this.mouse.x) * 0.04;
        this.mouse.y += (this.mouse.targetY - this.mouse.y) * 0.04;

        // Layer 1: Subtle Ambient Volumetric Pointer Aura (< 5px parallax response)
        if (this.mouse.x > 0 && this.intensity > 0.3) {
          const radGrad = this.ctx.createRadialGradient(
            this.mouse.x, this.mouse.y, 0,
            this.mouse.x, this.mouse.y, 240
          );
          radGrad.addColorStop(0, colors.glow.replace(/[\d\.]+\)$/, '0.07)'));
          radGrad.addColorStop(1, 'transparent');
          this.ctx.fillStyle = radGrad;
          this.ctx.fillRect(0, 0, this.width, this.height);
        }
      }

      // Layer 2: Harmonic Biometric Intelligence Wave (Organic Brand Flow, NO Fake ECG)
      if ((this.mode === 'hero' || this.mode === 'auth' || this.mode === 'ambient') && this.intensity > 0.2) {
        this._drawHarmonicBiometricWave(colors, isDark, false);
      }

      // Layer 3: Neural Particles & Living Signal Pathways
      if (this.particles.length > 0 && this.intensity > 0.2) {
        this._drawParticles(colors, isDark);
      }

      // Layer 4: MEDICARE Core (if mode is core)
      if (this.mode === 'core') {
        const radius = Math.min(this.width, this.height) * 0.28;
        this._drawCore(this.width / 2, this.height / 2, radius, colors, this.step);
      }
    }

    _drawHarmonicBiometricWave(colors, isDark, isStatic = false) {
      const centerY = this.height * (this.mode === 'auth' ? 0.6 : 0.48);
      const waveAlpha = isDark ? 0.22 : 0.16;
      const t = isStatic ? 1.0 : this.step;

      // Primary Flow Wave (Teal/Emerald intelligence flow)
      this.ctx.beginPath();
      this.ctx.lineWidth = 1.6;
      this.ctx.strokeStyle = colors.primary;
      this.ctx.globalAlpha = waveAlpha * this.intensity;

      for (let x = 0; x < this.width; x += 10) {
        // Multi-frequency organic wave modulation
        const wave1 = Math.sin(x * 0.0032 + t * 0.8) * 18;
        const wave2 = Math.sin(x * 0.008 - t * 0.5) * 8;
        const y = centerY + wave1 + wave2;

        if (x === 0) this.ctx.moveTo(x, y);
        else this.ctx.lineTo(x, y);
      }
      this.ctx.stroke();

      // Secondary Harmonic Counter-Wave (Cyan subtle undertone)
      if (this.tier === 'HIGH' && !isStatic) {
        this.ctx.beginPath();
        this.ctx.lineWidth = 1.2;
        this.ctx.strokeStyle = colors.secondary;
        this.ctx.globalAlpha = waveAlpha * 0.65 * this.intensity;

        for (let x = 0; x < this.width; x += 12) {
          const waveHarmonic = Math.sin(x * 0.0045 + t * 1.1 + 1.2) * 14;
          const y = centerY + waveHarmonic;
          if (x === 0) this.ctx.moveTo(x, y);
          else this.ctx.lineTo(x, y);
        }
        this.ctx.stroke();
      }

      this.ctx.globalAlpha = 1.0;
    }

    _drawParticles(colors, isDark) {
      const linkDist = this.width < 768 ? 75 : 120;
      const strokeColor = isDark ? 'rgba(6, 182, 212, 0.08)' : 'rgba(13, 148, 136, 0.07)';

      for (let i = 0; i < this.particles.length; i++) {
        const p = this.particles[i];
        p.x += p.vx;
        p.y += p.vy;

        if (p.x < 0) p.x = this.width;
        if (p.x > this.width) p.x = 0;
        if (p.y < 0) p.y = this.height;
        if (p.y > this.height) p.y = 0;

        // Draw particle node
        this.ctx.beginPath();
        this.ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        this.ctx.fillStyle = colors.secondary;
        this.ctx.globalAlpha = p.baseAlpha * this.intensity;
        this.ctx.fill();

        // Connect adjacent nodes with neural signal lines
        for (let j = i + 1; j < this.particles.length; j++) {
          const p2 = this.particles[j];
          const dx = p.x - p2.x;
          const dy = p.y - p2.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < linkDist) {
            this.ctx.beginPath();
            this.ctx.moveTo(p.x, p.y);
            this.ctx.lineTo(p2.x, p2.y);
            this.ctx.strokeStyle = strokeColor;
            this.ctx.lineWidth = (1 - dist / linkDist) * 1.1;
            this.ctx.globalAlpha = (1 - dist / linkDist) * 0.42 * this.intensity;
            this.ctx.stroke();
          }
        }
      }
      this.ctx.globalAlpha = 1.0;
    }

    _drawCore(cx, cy, r, colors, t) {
      // 1. Core outer breathing aura
      const breath = Math.sin(t * 2) * (r * 0.12);
      const outerR = r + breath;
      const grad = this.ctx.createRadialGradient(cx, cy, r * 0.2, cx, cy, outerR * 1.6);
      grad.addColorStop(0, colors.glow);
      grad.addColorStop(0.5, colors.glow.replace(/[\d\.]+\)$/, '0.12)'));
      grad.addColorStop(1, 'transparent');

      this.ctx.fillStyle = grad;
      this.ctx.beginPath();
      this.ctx.arc(cx, cy, outerR * 1.6, 0, Math.PI * 2);
      this.ctx.fill();

      // 2. Orbital rings
      this.ctx.save();
      this.ctx.translate(cx, cy);
      this.ctx.rotate(t * 0.8);
      this.ctx.strokeStyle = colors.secondary;
      this.ctx.lineWidth = 1.4;
      this.ctx.setLineDash([4, 6]);
      this.ctx.beginPath();
      this.ctx.arc(0, 0, r * 1.25, 0, Math.PI * 2);
      this.ctx.stroke();
      this.ctx.restore();

      // 3. Central Solid Orb Core
      const coreGrad = this.ctx.createRadialGradient(
        cx - r * 0.2, cy - r * 0.2, r * 0.05,
        cx, cy, r
      );
      coreGrad.addColorStop(0, '#ffffff');
      coreGrad.addColorStop(0.3, colors.secondary);
      coreGrad.addColorStop(0.75, colors.primary);
      coreGrad.addColorStop(1, '#094e47');

      this.ctx.fillStyle = coreGrad;
      this.ctx.beginPath();
      this.ctx.arc(cx, cy, r, 0, Math.PI * 2);
      this.ctx.fill();

      // 4. Central Harmonic Biometric Wave inside Core
      this.ctx.strokeStyle = '#ffffff';
      this.ctx.lineWidth = Math.max(1.8, r * 0.07);
      this.ctx.lineCap = 'round';
      this.ctx.lineJoin = 'round';
      this.ctx.beginPath();
      const gw = r * 0.8;
      const gh = r * 0.35;
      for (let x = -gw / 2; x <= gw / 2; x += 4) {
        const normX = x / (gw / 2);
        const y = Math.sin(normX * Math.PI * 2 + t * 3) * (gh * (1 - Math.abs(normX) * 0.4));
        if (x === -gw / 2) this.ctx.moveTo(cx + x, cy + y);
        else this.ctx.lineTo(cx + x, cy + y);
      }
      this.ctx.stroke();
    }

    destroy() {
      this.pause();
      if (this._onResize) window.removeEventListener('resize', this._onResize);
      if (this._onVisibilityChange) document.removeEventListener('visibilitychange', this._onVisibilityChange);
      if (this._onMouseMove) window.removeEventListener('mousemove', this._onMouseMove);
      this.particles = [];
      this.canvas = null;
      this.ctx = null;
    }
  }

  MedicareCinematicEngine.STATES = STATES;
  return MedicareCinematicEngine;
}));
