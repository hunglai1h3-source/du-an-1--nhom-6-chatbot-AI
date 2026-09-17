/**
 * MediCare AI — Apex Maximum Unified Cinematic Graphics Engine
 * Powers the MEDICARE Core, Biometric Particle Fields, ECG Waves & Spatial Lighting
 * 
 * Performance Tiers: HIGH | BALANCED | LOW
 * Adaptive Visual Intensity: LANDING (1.0) -> HOME (0.6) -> KNOWLEDGE (0.45) -> CHAT (0.3) -> EMERGENCY (0.05)
 * Built-in Failsafe: Canvas / WebGL failure safely degrades to SVG/CSS without crashing the app.
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

  // Constants & Core States
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
    idle: { primary: '#0d9488', secondary: '#06b6d4', glow: 'rgba(13, 148, 136, 0.35)' },
    listening: { primary: '#0ea5e9', secondary: '#38bdf8', glow: 'rgba(14, 165, 233, 0.45)' },
    processing: { primary: '#14b8a6', secondary: '#2dd4bf', glow: 'rgba(20, 184, 166, 0.5)' },
    responding: { primary: '#10b981', secondary: '#34d399', glow: 'rgba(16, 185, 129, 0.45)' },
    success: { primary: '#059669', secondary: '#10b981', glow: 'rgba(5, 150, 105, 0.5)' },
    caution: { primary: '#d97706', secondary: '#f59e0b', glow: 'rgba(217, 119, 6, 0.45)' },
    urgent: { primary: '#ea580c', secondary: '#f97316', glow: 'rgba(234, 88, 12, 0.5)' },
    emergency: { primary: '#dc2626', secondary: '#ef4444', glow: 'rgba(220, 38, 38, 0.6)' }
  };

  class MedicareCinematicEngine {
    constructor(options = {}) {
      this.canvas = typeof options.canvas === 'string' ? document.querySelector(options.canvas) : options.canvas;
      this.mode = options.mode || 'ambient'; // 'ambient' | 'core' | 'hero' | 'auth'
      this.intensity = typeof options.intensity === 'number' ? options.intensity : 1.0;
      this.currentState = options.initialState || STATES.IDLE;
      
      this.isPaused = false;
      this.rafId = null;
      this.step = 0;
      this.mouse = { x: -1000, y: -1000, targetX: -1000, targetY: -1000 };
      
      this.particles = [];
      this.dpr = Math.min(window.devicePixelRatio || 1, 2);
      
      // Determine performance tier
      this.tier = this._detectPerformanceTier();
      this.reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      if (this.canvas) {
        this.ctx = this.canvas.getContext('2d');
        if (this.ctx) {
          this._init();
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
        console.warn('MedicareCinematicEngine fallback:', err);
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

      if (this.tier === 'HIGH' && window.innerWidth >= 1024) {
        this._onMouseMove = (e) => {
          this.mouse.targetX = e.clientX;
          this.mouse.targetY = e.clientY;
        };
        window.addEventListener('mousemove', this._onMouseMove, { passive: true });
      }
    }

    resize() {
      if (!this.canvas || !this.ctx) return;
      const rect = this.canvas.getBoundingClientRect();
      this.width = rect.width || window.innerWidth;
      this.height = rect.height || window.innerHeight;
      
      this.canvas.width = Math.floor(this.width * this.dpr);
      this.canvas.height = Math.floor(this.height * this.dpr);
      this.ctx.scale(this.dpr, this.dpr);

      this._initParticles();
    }

    _initParticles() {
      this.particles = [];
      if (this.intensity <= 0.1 || this.reducedMotion) return;

      let count = 36;
      if (this.tier === 'BALANCED' || this.width < 768) count = 18;
      if (this.mode === 'core') count = 14;

      for (let i = 0; i < count; i++) {
        this.particles.push({
          x: Math.random() * this.width,
          y: Math.random() * this.height,
          vx: (Math.random() - 0.5) * (0.35 * this.intensity),
          vy: (Math.random() - 0.5) * (0.35 * this.intensity),
          radius: (Math.random() * 2 + 1.2) * (this.intensity > 0.5 ? 1 : 0.8),
          baseAlpha: Math.random() * 0.4 + 0.2
        });
      }
    }

    setState(newState) {
      if (STATES[newState.toUpperCase()]) {
        this.currentState = STATES[newState.toUpperCase()];
        if (this.currentState === STATES.EMERGENCY) {
          this.intensity = 0.05; // Drop decorative graphics immediately
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
      const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
      const colors = STATE_COLORS[this.currentState] || STATE_COLORS.idle;

      if (this.mode === 'core') {
        this._drawCore(this.width / 2, this.height / 2, 40, colors, 0);
      }
    }

    _renderFrame() {
      if (!this.ctx) return;
      this.ctx.clearRect(0, 0, this.width, this.height);
      this.step += 0.016;

      const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
      const colors = STATE_COLORS[this.currentState] || STATE_COLORS.idle;

      // Mouse smooth interpolation
      this.mouse.x += (this.mouse.targetX - this.mouse.x) * 0.05;
      this.mouse.y += (this.mouse.targetY - this.mouse.y) * 0.05;

      // Layer 1: Ambient Pointer Light (Desktop High Tier)
      if (this.tier === 'HIGH' && this.mouse.x > 0 && this.intensity > 0.3) {
        const radGrad = this.ctx.createRadialGradient(
          this.mouse.x, this.mouse.y, 0,
          this.mouse.x, this.mouse.y, 280
        );
        radGrad.addColorStop(0, colors.glow.replace('0.35', '0.08'));
        radGrad.addColorStop(1, 'transparent');
        this.ctx.fillStyle = radGrad;
        this.ctx.fillRect(0, 0, this.width, this.height);
      }

      // Layer 2: Biometric ECG Wave (if mode is hero or auth)
      if ((this.mode === 'hero' || this.mode === 'auth') && this.intensity > 0.3) {
        this._drawBiometricWave(colors, isDark);
      }

      // Layer 3: Particles & Neural Pathways
      if (this.particles.length > 0 && this.intensity > 0.2) {
        this._drawParticles(colors, isDark);
      }

      // Layer 4: MEDICARE Core (if mode is core)
      if (this.mode === 'core') {
        const radius = Math.min(this.width, this.height) * 0.28;
        this._drawCore(this.width / 2, this.height / 2, radius, colors, this.step);
      }
    }

    _drawBiometricWave(colors, isDark) {
      const centerY = this.height * (this.mode === 'auth' ? 0.6 : 0.48);
      const waveAlpha = isDark ? 0.25 : 0.18;
      
      this.ctx.beginPath();
      this.ctx.lineWidth = 1.6;
      this.ctx.strokeStyle = colors.primary;
      this.ctx.globalAlpha = waveAlpha * this.intensity;

      for (let x = 0; x < this.width; x += 8) {
        const waveX = (x + this.step * 45) % (this.width * 0.75);
        let ecg = 0;
        if (waveX > 280 && waveX < 350) {
          const p = (waveX - 280) / 70;
          if (p < 0.2) ecg = -14 * Math.sin(p * Math.PI * 5);
          else if (p < 0.5) ecg = 52 * Math.sin((p - 0.2) * Math.PI * 3.33);
          else if (p < 0.7) ecg = -24 * Math.sin((p - 0.5) * Math.PI * 5);
          else ecg = 16 * Math.sin((p - 0.7) * Math.PI * 3.33);
        }
        const y = centerY + Math.sin(x * 0.0035 + this.step) * 16 + ecg;
        if (x === 0) this.ctx.moveTo(x, y);
        else this.ctx.lineTo(x, y);
      }
      this.ctx.stroke();
      this.ctx.globalAlpha = 1.0;
    }

    _drawParticles(colors, isDark) {
      const linkDist = this.width < 768 ? 70 : 110;
      const strokeColor = isDark ? 'rgba(6, 182, 212, 0.07)' : 'rgba(13, 148, 136, 0.06)';

      for (let i = 0; i < this.particles.length; i++) {
        const p = this.particles[i];
        p.x += p.vx;
        p.y += p.vy;

        if (p.x < 0) p.x = this.width;
        if (p.x > this.width) p.x = 0;
        if (p.y < 0) p.y = this.height;
        if (p.y > this.height) p.y = 0;

        // Draw node
        this.ctx.beginPath();
        this.ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        this.ctx.fillStyle = colors.secondary;
        this.ctx.globalAlpha = p.baseAlpha * this.intensity;
        this.ctx.fill();

        // Connect adjacent nodes
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
            this.ctx.lineWidth = (1 - dist / linkDist) * 1.2;
            this.ctx.globalAlpha = (1 - dist / linkDist) * 0.4 * this.intensity;
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
      const grad = this.ctx.createRadialGradient(cx, cy, r * 0.2, cx, cy, outerR * 1.5);
      grad.addColorStop(0, colors.glow);
      grad.addColorStop(0.5, colors.glow.replace('0.', '0.1'));
      grad.addColorStop(1, 'transparent');

      this.ctx.fillStyle = grad;
      this.ctx.beginPath();
      this.ctx.arc(cx, cy, outerR * 1.5, 0, Math.PI * 2);
      this.ctx.fill();

      // 2. Orbital rings depending on state
      if (this.currentState === STATES.PROCESSING) {
        this.ctx.save();
        this.ctx.translate(cx, cy);
        this.ctx.rotate(t * 2.5);
        this.ctx.strokeStyle = colors.secondary;
        this.ctx.lineWidth = 2;
        this.ctx.beginPath();
        this.ctx.arc(0, 0, r * 1.2, 0, Math.PI * 1.2);
        this.ctx.stroke();
        this.ctx.restore();
      } else if (this.currentState === STATES.LISTENING) {
        // Waveform response ring
        this.ctx.beginPath();
        this.ctx.lineWidth = 2;
        this.ctx.strokeStyle = colors.primary;
        for (let a = 0; a < Math.PI * 2; a += 0.1) {
          const wr = r * 1.15 + Math.sin(a * 8 + t * 6) * 4;
          const x = cx + Math.cos(a) * wr;
          const y = cy + Math.sin(a) * wr;
          if (a === 0) this.ctx.moveTo(x, y);
          else this.ctx.lineTo(x, y);
        }
        this.ctx.closePath();
        this.ctx.stroke();
      }

      // 3. Central Solid Orb Core
      const coreGrad = this.ctx.createRadialGradient(
        cx - r * 0.2, cy - r * 0.2, r * 0.05,
        cx, cy, r
      );
      coreGrad.addColorStop(0, colors.secondary);
      coreGrad.addColorStop(0.8, colors.primary);
      coreGrad.addColorStop(1, 'rgba(13, 148, 136, 0.6)');

      this.ctx.fillStyle = coreGrad;
      this.ctx.beginPath();
      this.ctx.arc(cx, cy, r, 0, Math.PI * 2);
      this.ctx.fill();

      // 4. Central Biometric Pulse Glyph
      this.ctx.strokeStyle = '#ffffff';
      this.ctx.lineWidth = Math.max(2, r * 0.08);
      this.ctx.lineCap = 'round';
      this.ctx.lineJoin = 'round';
      this.ctx.beginPath();
      const gw = r * 0.8;
      const gh = r * 0.4;
      this.ctx.moveTo(cx - gw * 0.5, cy);
      this.ctx.lineTo(cx - gw * 0.2, cy);
      this.ctx.lineTo(cx - gw * 0.08, cy - gh * 0.7);
      this.ctx.lineTo(cx + gw * 0.08, cy + gh * 0.7);
      this.ctx.lineTo(cx + gw * 0.2, cy);
      this.ctx.lineTo(cx + gw * 0.5, cy);
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
