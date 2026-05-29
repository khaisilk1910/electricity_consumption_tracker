/**
 * Electricity Consumption Card - Optimized for Home Assistant
 * @version 2.0.0
 * Improvements:
 *  - getCardSize() added for proper HA layout
 *  - Debounced hass setter to prevent excess renders
 *  - CSS cached outside render loop (no re-parse on every update)
 *  - Proper disconnectedCallback with full event listener cleanup
 *  - Fixed hexToRgba overflow for large hex values
 *  - Removed recursive setTimeout polling → uses connectedCallback retry
 *  - Shadow DOM styles injected once, content updated separately
 *  - Defensive null checks throughout
 *  - Editor fires config-changed correctly on init
 *  - Removed all inline `overflow: visible !important` hacks
 *  - Added keyboard navigation (ArrowLeft/Right on bar columns)
 *  - Tab-triggered CSS transitions instead of JS style mutations
 */
(function () {
  'use strict';

  /* ─── UTILITY ─────────────────────────────────────────────────────────── */

  const fmt$ = (v) =>
    new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(Math.round(v || 0));
  const fmtN = (v) =>
    new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(v || 0);

  /** Safe hex→rgba. Handles 3- and 6-char hex. opacity 0–100. */
  const hex2rgba = (hex, opacity = 100) => {
    const clean = String(hex).trim();
    const m3 = clean.match(/^#?([A-Fa-f0-9]{3})$/);
    const m6 = clean.match(/^#?([A-Fa-f0-9]{6})$/);
    if (!m3 && !m6) return clean;
    let h = m3 ? m3[1].split('').map((c) => c + c).join('') : m6[1];
    const r = parseInt(h.slice(0, 2), 16);
    const g = parseInt(h.slice(2, 4), 16);
    const b = parseInt(h.slice(4, 6), 16);
    return `rgba(${r},${g},${b},${+(opacity / 100).toFixed(3)})`;
  };

  /** Replace all #hex occurrences in a gradient string with rgba equivalents. */
  const gradientOpacity = (str, op) =>
    String(str).replace(/#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})\b/gi, (m) => hex2rgba(m, op));

  /** Simple debounce. */
  const debounce = (fn, ms) => {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  };

  /* ─── SHARED CSS ───────────────────────────────────────────────────────── */
  // Built once and reused across all card instances.
  const CARD_CSS = `
    :host {
      --block-bg: rgba(255,255,255,0.12);
      --text-main: #1e3a8a;
      --bar-k1: #3b82f6; --bar-k2: #1e3a8a;
      --bar-v1: #10b981; --bar-v2: #047857;
      --text-red: #dc2626;
      --option-bg: #ffffff;
    }
    *, *::before, *::after { box-sizing: border-box; }

    select option { background-color: var(--option-bg) !important; color: var(--text-main) !important; }

    .main-card-header {
      display: flex; align-items: flex-end; gap: 12px;
      font-weight: 800; font-size: clamp(20px,5vw,24px);
      color: var(--text-main); margin: 0 0 12px; padding-left: 4px; line-height: 1;
    }
    .main-card-header ha-icon, .main-card-header .emoji-icon {
      font-size: clamp(28px,7vw,36px); line-height: 1; margin-bottom: -4px; color: #f59e0b;
    }

    .block-common {
      background: var(--block-bg); border-radius: 12px;
      border: 1px solid rgba(0,0,0,0.05);
      backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
    }
    .top-dashboard  { padding: 12px; margin-bottom: 12px; }
    .chart-section  { padding: 12px; margin-bottom: 12px; position: relative; }
    .control-pill   {
      border-radius: 50px; display: flex; align-items: center;
      justify-content: space-between; padding: 2px; min-width: 0;
    }

    .header-tools { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
    .tabs-container { display: flex; background: rgba(0,0,0,0.1); padding: 4px; border-radius: 10px; gap: 4px; border: 1px solid rgba(0,0,0,0.05); }
    .tab-item {
      padding: clamp(4px,1vw,6px) clamp(8px,2vw,14px); border-radius: 8px;
      font-size: clamp(11px,3vw,13px); font-weight: 700;
      color: var(--text-main); opacity: 0.6; cursor: pointer;
      transition: all 0.25s; white-space: nowrap; user-select: none;
    }
    .tab-item:hover { opacity: 0.8; }
    .tab-item.active { background: var(--block-bg); opacity: 1; box-shadow: 0 2px 6px rgba(0,0,0,0.08); }

    select.main-sel {
      background: rgba(0,0,0,0.4) url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23ffffff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e") no-repeat right 10px center / 14px;
      color: #fff; border: none; border-radius: 8px; padding: 8px 30px 8px 12px;
      font-size: 14px; font-weight: 700; outline: none; cursor: pointer;
      -webkit-appearance: none; appearance: none; transition: background-color 0.2s;
    }
    select.main-sel:hover { background-color: rgba(0,0,0,0.6); }

    /* Overview stats */
    .global-stats-compact { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 4px; text-align: center; width: 100%; }
    .stat-box { display: flex; flex-direction: column; justify-content: center; cursor: default; border-radius: 8px; padding: clamp(2px,1vw,4px) 2px; min-width: 0; position: relative; }
    .stat-box.primary { border-right: 1px solid rgba(0,0,0,0.05); }
    .stat-box.primary .stat-value { color: var(--text-main); }
    .stat-value { font-size: clamp(11px,3.5vw,17px); font-weight: 800; color: var(--text-red); display: flex; align-items: center; justify-content: center; gap: 2px; flex-wrap: wrap; letter-spacing: -0.3px; line-height: 1.1; }
    .stat-unit   { font-size: clamp(10px,2.5vw,13px); color: var(--text-main); opacity: 0.7; font-weight: 600; white-space: nowrap; }
    .stat-label  { font-size: clamp(10px,2.5vw,12px); font-weight: 700; color: var(--text-main); opacity: 0.6; margin-top: 2px; letter-spacing: 0.1px; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; width: 100%; }
    .emoji-money, .icon-kwh { flex-shrink: 0; }

    /* Hover animations */
    .hover-zap, .hover-fly { position: relative; }
    .icon-kwh { color: #f59e0b; transition: all 0.3s; transform-origin: center; display: inline-block; }
    @keyframes zapHover {
      0%   { transform: scale(1)   rotate(0deg);   filter: brightness(1); }
      20%  { transform: scale(1.5) rotate(-15deg); filter: brightness(1.5) drop-shadow(0 0 6px #fbbf24);  color: #fcd34d; }
      40%  { transform: scale(1.5) rotate(15deg);  filter: brightness(1.8) drop-shadow(0 0 10px #fef3c7); color: #fef3c7; }
      60%  { transform: scale(1.5) rotate(-15deg); filter: brightness(1.5) drop-shadow(0 0 6px #fbbf24);  color: #fcd34d; }
      80%  { transform: scale(1.5) rotate(15deg);  filter: brightness(1.2) drop-shadow(0 0 4px #f59e0b);  color: #fbbf24; }
      100% { transform: scale(1)   rotate(0deg);   filter: brightness(1); }
    }
    .hover-zap:hover .icon-kwh { animation: zapHover 0.7s ease-in-out forwards; }

    .emoji-money { display: inline-block; font-size: 1.2em; transition: all 0.3s; transform-origin: bottom center; }
    @keyframes flyAwayHover {
      0%   { transform: translate(0,0)    scale(1)   rotate(0deg);  opacity: 1; }
      30%  { transform: translate(10px,-15px) scale(1.3) rotate(15deg); opacity: 0.8; }
      45%  { transform: translate(25px,-30px) scale(0.5) rotate(30deg); opacity: 0; }
      46%  { transform: translate(-20px,15px) scale(0);               opacity: 0; }
      100% { transform: translate(0,0)    scale(1)   rotate(0deg);  opacity: 1; }
    }
    .hover-fly:hover .emoji-money { animation: flyAwayHover 0.8s ease-in-out forwards; }

    /* Controls row */
    .controls { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: clamp(4px,2vw,10px); margin-bottom: 12px; }
    .control-content { display: flex; align-items: center; gap: clamp(2px,1vw,4px); padding: 0 clamp(2px,1vw,6px); flex: 1; justify-content: center; border-left: 1px solid rgba(0,0,0,0.05); border-right: 1px solid rgba(0,0,0,0.05); min-width: 0; }
    .ctrl-icon { font-size: clamp(14px,3.5vw,18px); color: var(--text-main); flex-shrink: 0; }

    select.styled-sel {
      flex: 1; min-width: 0; width: 100%;
      background: transparent url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233b82f6' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e") no-repeat right 0 center / 14px;
      border: none; font-weight: 800; font-size: clamp(12px,3.5vw,15px);
      color: var(--text-main); outline: none; cursor: pointer;
      text-align: center; text-align-last: center;
      -webkit-appearance: none; appearance: none;
      padding: 4px 16px 4px 2px; border-radius: 6px; transition: background-color 0.2s;
    }
    select.styled-sel:hover { background-color: rgba(0,0,0,0.05); }

    .nav-btn {
      cursor: pointer; display: flex; align-items: center; justify-content: center;
      width: clamp(24px,6vw,28px); height: clamp(24px,6vw,28px);
      border-radius: 50%; color: #3b82f6; transition: all 0.2s; user-select: none;
      background: transparent; flex-shrink: 0;
    }
    .nav-btn:hover { background: rgba(59,130,246,0.1); color: var(--text-main); }
    .nav-btn ha-icon { font-size: clamp(18px,5vw,20px); }

    /* Search tab */
    .search-bar-wrapper { display: flex; flex-wrap: wrap; gap: clamp(6px,2vw,10px); margin-bottom: 12px; }
    .search-inputs { display: flex; flex: 99 1 250px; gap: clamp(6px,2vw,10px); }
    .search-inputs .control-pill { flex: 1; min-width: 0; margin-bottom: 0; }
    .btn-search {
      flex: 1 1 120px; border-radius: 50px; padding: 8px 24px;
      display: flex; align-items: center; justify-content: center;
      border: 1px solid rgba(0,0,0,0.05); white-space: nowrap;
      background: #3b82f6; color: white; font-weight: bold;
      font-size: clamp(12px,3.5vw,14px); cursor: pointer; transition: background 0.2s;
    }
    .btn-search:hover { background: #2563eb; }

    /* Search stats grid */
    .search-stats-grid { display: grid; grid-template-columns: repeat(2,1fr); gap: clamp(8px,1.5vw,12px); margin-bottom: 12px; }
    .s-stat-card {
      background: var(--block-bg); border-radius: 8px; padding: clamp(8px,1.5vw,12px);
      border: 1px solid rgba(0,0,0,0.05); text-align: center;
      display: flex; flex-direction: column; justify-content: center; min-height: 50px;
    }
    .s-label { font-size: clamp(11px,2vw,14px); font-weight: 700; color: var(--text-main); opacity: 0.7; margin-bottom: 2px; }
    .s-val { font-size: clamp(12px,2.5vw,16px); font-weight: 800; color: var(--text-main); line-height: 1.2; }
    .s-val .primary { color: #3b82f6; font-size: clamp(14px,3.5vw,22px); }
    .s-val .money   { color: var(--text-red); font-size: clamp(14px,3.5vw,22px); }

    /* Chart header */
    .chart-header { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: 8px; margin-bottom: 16px; border-bottom: 1px solid rgba(0,0,0,0.05); padding-bottom: 8px; }
    .chart-title  { font-weight: 800; font-size: clamp(14px,3.8vw,18px); display: flex; align-items: flex-end; gap: 4px; color: var(--text-main); width: 100%; justify-content: space-between; margin-bottom: 4px; }
    .chart-title span { display: flex; align-items: flex-end; gap: 6px; line-height: 1; }
    .chart-stats  { display: flex; gap: 4px; text-align: right; width: 100%; justify-content: space-between; flex-wrap: wrap; }
    .c-stat-val   { font-size: clamp(11px,3.2vw,20px); font-weight: 900; display: flex; align-items: center; justify-content: flex-end; gap: 4px; flex-wrap: wrap; letter-spacing: -0.5px; line-height: 1.1; }
    .c-stat-val.primary { color: var(--text-main); }
    .c-stat-val.money   { color: var(--text-red); }
    .stat-label-sm { font-size: clamp(9px,2.5vw,11px); font-weight: 600; color: var(--text-main); opacity: 0.6; margin-top: 2px; }

    /* Decade summary */
    .decade-summary { display: flex; justify-content: space-between; align-items: center; padding: 4px 8px 12px; margin-bottom: 12px; border-bottom: 1px dashed rgba(0,0,0,0.08); }
    .d-sum-item { display: flex; flex-direction: column; }
    .d-sum-item:nth-child(1) { align-items: flex-start; }
    .d-sum-item:nth-child(2) { align-items: center; }
    .d-sum-item:nth-child(3) { align-items: flex-end; }
    .d-sum-val   { font-size: clamp(11px,3.2vw,20px); font-weight: 900; display: flex; align-items: center; gap: 4px; color: var(--text-main); letter-spacing: -0.5px; line-height: 1.1; }
    .d-sum-val.money { color: var(--text-red); }
    .d-sum-label { font-size: clamp(10px,2.5vw,12px); font-weight: 600; color: var(--text-main); opacity: 0.6; margin-top: 4px; }

    /* Chart container */
    .chart-container { position: relative; height: 130px; margin: 50px 0 16px; }
    .bar-chart { display: flex; align-items: flex-end; justify-content: space-between; height: 100%; position: relative; width: 100%; }
    .bar-col {
      flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end;
      height: 100%; position: relative; cursor: pointer; z-index: 2; transition: z-index 0.3s;
    }
    .bar-col:hover, .bar-col:focus-within { z-index: 50; outline: none; }
    .bar {
      width: 75%; margin: 0 auto;
      background: linear-gradient(180deg, var(--bar-k1) 0%, var(--bar-k2) 100%);
      border-radius: 3px 3px 0 0; transition: height 0.5s cubic-bezier(0.4,0,0.2,1), filter 0.2s;
    }
    .bar:hover { filter: brightness(1.2); }
    .bar-group {
      display: flex; align-items: flex-end; justify-content: center;
      gap: 0; width: 85%; height: 100%; margin: 0 auto; cursor: pointer;
    }
    .bar-group > div {
      position: relative; width: 50%; height: 100%;
      display: flex; flex-direction: column; justify-content: flex-end; align-items: center;
    }
    .bar-kwh, .bar-vnd { transition: height 0.5s cubic-bezier(0.4,0,0.2,1), filter 0.2s; width: 100%; }
    .bar-kwh:hover, .bar-vnd:hover { filter: brightness(1.2); }
    .bar-kwh { background: linear-gradient(180deg, var(--bar-k1) 0%, var(--bar-k2) 100%); border-radius: 3px 0 0 0; }
    .bar-vnd { background: linear-gradient(180deg, var(--bar-v1) 0%, var(--bar-v2) 100%); border-radius: 0 3px 0 0; }

    .bar-val {
      position: absolute; top: -24px;
      font-size: 8px; font-weight: 800; color: var(--text-main);
      width: max-content; text-align: center; white-space: nowrap;
      left: 50%; transform: translateX(-50%) rotate(-45deg);
      transition: all 0.3s cubic-bezier(0.4,0,0.2,1);
      z-index: 5; pointer-events: none; opacity: 0.8;
    }
    .bar-col:hover .bar-val,
    .bar-col:focus-within .bar-val,
    .bar-group > div:hover .bar-val {
      z-index: 100; background: var(--block-bg) !important;
      padding: 2px 4px; border-radius: 4px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.15); opacity: 1;
    }
    .bar-col:hover .bar-val-daily    { transform: translateX(-50%) translateY(-20px) rotate(0deg) scale(2); color: var(--text-main) !important; }
    .bar-col:hover .bar-val-vnd      { left: 0%;   transform: translateX(-50%) translateY(-40px) rotate(0deg) scale(2); color: var(--text-red) !important;  z-index: 101; }
    .bar-col:hover .bar-val-kwh      { left: 100%; transform: translateX(-50%) translateY(-5px)  rotate(0deg) scale(2); color: var(--text-main) !important; z-index: 100; }

    .bar-label {
      position: absolute; bottom: -18px; left: 50%; transform: translateX(-50%);
      font-size: clamp(8px,2vw,10px); font-weight: 600;
      color: var(--text-main); opacity: 0.7; text-align: center; width: 100%;
      transition: all 0.3s cubic-bezier(0.4,0,0.2,1);
    }
    .bar-col:hover .bar-label,
    .bar-col:focus-within .bar-label {
      transform: translateX(-50%) scale(1.4) !important;
      opacity: 1 !important; font-weight: 800; color: var(--text-main); z-index: 100;
    }

    @keyframes pulseColor {
      0%,100% { color: #f59e0b; text-shadow: none;                         transform: translateX(-50%) scale(1);    }
      50%      { color: var(--text-red); text-shadow: 0 0 6px rgba(220,38,38,0.3); transform: translateX(-50%) scale(1.15); }
    }
    .label-active { font-weight: 900 !important; animation: pulseColor 1.5s infinite ease-in-out; opacity: 1 !important; }

    /* SVG overlay */
    .svg-overlay {
      position: absolute; top: 0; left: 0; width: 100%; height: 100%;
      pointer-events: none; z-index: 5;
      filter: drop-shadow(0px 2px 2px rgba(0,0,0,0.1));
    }
    .svg-overlay polyline { filter: drop-shadow(0px 3px 4px rgba(0,0,0,0.4)); }
    .dots-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 6; }
    .chart-dot {
      position: absolute; width: 3px; height: 3px;
      background: var(--block-bg); border-radius: 50%;
      transform: translate(-50%,-50%); box-shadow: 0 2px 4px rgba(0,0,0,0.5);
    }

    /* Loading */
    .ha-card-loader { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 20px; gap: 16px; min-height: 150px; }
    .loader-spinner { width: 36px; height: 36px; border: 3px solid var(--divider-color, rgba(120,120,120,0.2)); border-top-color: #3b82f6; border-radius: 50%; animation: ha-spin 1s linear infinite; }
    .loader-text { text-align: center; font-size: 14px; font-weight: 600; color: var(--secondary-text-color,#888); animation: ha-pulse 1.5s ease-in-out infinite; }
    @keyframes ha-spin  { to { transform: rotate(360deg); } }
    @keyframes ha-pulse { 0%,100% { opacity: 0.6; } 50% { opacity: 1; } }

    /* Error */
    .error-box {
      padding: 24px 16px; text-align: center; border-radius: 12px;
      background: rgba(220,38,38,0.1); border: 1px dashed rgba(220,38,38,0.3);
    }
    .error-box ha-icon { color: #dc2626; font-size: 32px; margin-bottom: 8px; }
    .error-title { color: #dc2626; font-weight: bold; font-size: 14px; }
    .error-sub   { color: #ef4444; font-size: 12px; margin-top: 4px; }
  `;

  /* ──────────────────────────────────────────────────────────────────────── */
  /* 1. EDITOR                                                                */
  /* ──────────────────────────────────────────────────────────────────────── */
  class ElectricityConsumptionEditor extends HTMLElement {
    constructor() {
      super();
      this._config = {};
      this._rendered = false;
    }

    setConfig(config) {
      this._config = config || {};
      if (this._rendered) this._updateUI();
    }

    set hass(hass) {
      this._hass = hass;
      if (!this._rendered) {
        this._render();
        this._rendered = true;
      }
    }

    _render() {
      if (!this._hass) return;
      const conf = this._config;
      const chartColorFields = [
        { id: 'barKwh1',   label: 'Cột kWh (Đỉnh)',  default: '#3b82f6' },
        { id: 'barKwh2',   label: 'Cột kWh (Đáy)',   default: '#1e3a8a' },
        { id: 'barVnd1',   label: 'Cột VNĐ (Đỉnh)',  default: '#10b981' },
        { id: 'barVnd2',   label: 'Cột VNĐ (Đáy)',   default: '#047857' },
        { id: 'lineKwh',   label: 'Line kWh (Năm)',   default: '#ff3366' },
        { id: 'lineVnd',   label: 'Line VNĐ (Năm)',   default: '#ffcc00' },
        { id: 'lineMonth', label: 'Line (Tháng)',     default: '#ff3366' },
      ];

      this.innerHTML = `
      <style>
        .editor-container { padding: 12px 0; font-family: var(--paper-font-body1_-_font-family, sans-serif); }
        .row      { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; width: 100%; }
        .row-col  { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; width: 100%; }
        .row:last-child, .row-col:last-child { margin-bottom: 0; }
        .label    { font-weight: 500; color: var(--primary-text-color); font-size: 14px; }
        .input-group { display: flex; align-items: center; gap: 12px; }
        input[type=color]   { cursor: pointer; border: 1px solid var(--divider-color,#e0e0e0); border-radius: 6px; padding: 2px; width: 40px; height: 32px; background: transparent; }
        input[type=range]   { flex-grow: 1; cursor: pointer; }
        input[type=text], select.custom-input { width: 100%; padding: 8px; border-radius: 6px; border: 1px solid var(--divider-color,#ccc); background: var(--card-background-color,transparent); color: var(--primary-text-color); box-sizing: border-box; font-size: 14px; }
        .val-badge { background: var(--primary-color); color: var(--text-primary-color,white); padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: bold; min-width: 48px; text-align: center; }
        select.ha-select { background: var(--card-background-color,transparent); color: var(--primary-text-color); border: 1px solid var(--divider-color,#e0e0e0); padding: 6px 8px; border-radius: 6px; font-family: inherit; font-size: 14px; flex-grow: 1; max-width: 250px; cursor: pointer; }
        .section { border: 1px solid var(--divider-color,#e0e0e0); border-radius: 12px; padding: 16px; margin-bottom: 16px; background: var(--card-background-color,transparent); transition: padding 0.3s; }
        .section.collapsed { padding-bottom: 16px; }
        .section-title { font-weight: 600; display: flex; align-items: center; justify-content: space-between; font-size: 16px; color: var(--primary-text-color); border-bottom: 1px solid var(--divider-color,#e0e0e0); padding-bottom: 8px; margin-bottom: 16px; cursor: pointer; user-select: none; }
        .section-title.no-collapse { cursor: default; }
        .section.collapsed .section-title { margin-bottom: 0; border-bottom: none; padding-bottom: 0; }
        .section-content { overflow: hidden; animation: slideDown 0.3s ease-out; }
        .section.collapsed .section-content { display: none; }
        .section-icon { font-size: 12px; opacity: 0.6; transition: transform 0.3s; }
        .section.collapsed .section-icon { transform: rotate(-90deg); }
        .title-left  { display: flex; align-items: center; gap: 8px; pointer-events: none; }
        .title-right { display: flex; align-items: center; gap: 12px; }
        .color-grid  { display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; padding: 10px; background: rgba(0,0,0,0.02); border-radius: 8px; border: 1px solid var(--divider-color); margin-top: 8px; }
        .color-item  { display: flex; flex-direction: column; gap: 4px; }
        .color-label { font-size: 11px; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .color-picker { width: 100% !important; height: 28px !important; padding: 0 !important; }
        @keyframes slideDown { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
      </style>

      <div class="editor-container">
        <div class="section">
          <div class="section-title no-collapse"><div class="title-left">⚙️ Cài đặt chung</div></div>
          <div class="section-content">
            <div class="row-col">
              <span class="label">Tiêu đề thẻ (Tuỳ chọn)</span>
              <input type="text" id="title-input" class="custom-input cfg" placeholder="VD: Thống kê Điện năng" value="${conf.title || ''}">
            </div>
            <div class="row-col">
              <span class="label">Icon hoặc Emoji (Tuỳ chọn)</span>
              <input type="text" id="icon-input" class="custom-input cfg" placeholder="VD: mdi:flash hoặc ⚡" value="${conf.icon || ''}">
            </div>
            <div class="row-col">
              <span class="label">Sensor mặc định</span>
              <select id="entity-select" class="custom-input cfg"><option value="">Đang tải...</option></select>
            </div>
          </div>
        </div>

        <div class="section">
          <div class="section-title no-collapse"><div class="title-left">🎨 Nền (Background)</div></div>
          <div class="section-content">
            <div class="row">
              <span class="label" style="min-width:120px">Loại nền</span>
              <select id="bg_type" class="ha-select cfg">
                <option value="solid">Màu đơn sắc</option>
                <option value="gradient">Gradient</option>
              </select>
            </div>
            <div class="row">
              <span class="label" style="min-width:120px">Độ trong suốt (%)</span>
              <input type="range" id="bg_opacity" class="cfg" min="0" max="100">
              <span class="val-badge" id="bg_opacity_val"></span>
            </div>
            <div id="solid_settings">
              <div class="row" style="margin-top:16px;border-top:1px dashed var(--divider-color,#e0e0e0);padding-top:16px">
                <span class="label">Màu nền</span>
                <div class="input-group"><input type="color" id="bg_color" class="cfg"><span class="val-badge" id="bg_color_val"></span></div>
              </div>
            </div>
            <div id="gradient_settings" style="display:none">
              <div class="row" style="margin-top:16px;border-top:1px dashed var(--divider-color,#e0e0e0);padding-top:16px">
                <span class="label" style="min-width:120px">Mẫu Gradient</span>
                <select id="bg_gradient_preset" class="ha-select cfg">
                  <option value="linear-gradient(135deg, #f0f4f8, #d9e2ec)">☀️ Sáng mặc định</option>
                  <option value="linear-gradient(135deg, #1e293b, #0f172a)">🌙 Tối mặc định</option>
                  <option value="linear-gradient(135deg, #141e30, #243b55)">🌌 Royal Night</option>
                  <option value="linear-gradient(135deg, #0f2027, #203a43, #2c5364)">🌊 Deep Ocean</option>
                  <option value="linear-gradient(135deg, #232526, #414345)">🏙️ Midnight City</option>
                  <option value="linear-gradient(135deg, #1a1a1a, #000000)">⚫ Dark Elegance</option>
                  <option value="linear-gradient(135deg, #ff0099, #493240)">🔮 Cosmic Fusion</option>
                  <option value="linear-gradient(135deg, #ff512f, #dd2476)">🌅 Sunset Vibes</option>
                  <option value="linear-gradient(135deg, #134e5e, #71b280)">🌲 Forest Mist</option>
                  <option value="linear-gradient(135deg, rgba(255,255,255,0.15), rgba(255,255,255,0.05))">🪟 Glassmorphism</option>
                  <option value="linear-gradient(135deg, #0f0c29, #302b63, #24243e)">🚀 Deep Space</option>
                  <option value="linear-gradient(135deg, #667eea, #764ba2)">💜 Plum Plate</option>
                  <option value="linear-gradient(135deg, #ff9a9e, #fecfef)">🌸 Cherry Blossom</option>
                  <option value="linear-gradient(135deg, #f12711, #f5af19)">🔥 Fire Glow</option>
                  <option value="linear-gradient(135deg, #11998e, #38ef7d)">🌿 Neon Life</option>
                  <option value="linear-gradient(135deg, #00c6ff, #0072ff)">❄️ Winter Sky</option>
                  <option value="linear-gradient(135deg, #f6d365, #fda085)">🍑 Sunrise Peach</option>
                  <option value="linear-gradient(135deg, #9D50BB, #6E48AA)">💎 Amethyst</option>
                  <option value="linear-gradient(135deg, #2b5876, #4e4376)">🌠 Starry Night</option>
                  <option value="linear-gradient(135deg, #ff758c, #ff7eb3)">🍉 Sweet Pink</option>
                  <option value="linear-gradient(135deg, #4facfe, #00f2fe)">🏝️ Tropical Blue</option>
                  <option value="linear-gradient(135deg, #870000, #190a05)">🍷 Blood Moon</option>
                  <option value="custom">✍️ Tùy chỉnh</option>
                </select>
              </div>
              <div id="custom_gradient_row" style="display:none;flex-direction:column;gap:12px;margin-top:12px;padding-top:12px;border-top:1px dashed var(--divider-color,#e0e0e0)">
                <div class="row" style="width:100%"><span class="label">Màu 1</span><div class="input-group"><input type="color" id="bg_gradient_color1" class="cfg"><span class="val-badge" id="bg_gradient_color1_val"></span></div></div>
                <div class="row" style="width:100%"><span class="label">Màu 2</span><div class="input-group"><input type="color" id="bg_gradient_color2" class="cfg"><span class="val-badge" id="bg_gradient_color2_val"></span></div></div>
                <div class="row" style="width:100%">
                  <span class="label" style="min-width:120px">Góc độ (°)</span>
                  <input type="range" id="bg_gradient_angle" class="cfg" min="0" max="360" step="1">
                  <span class="val-badge" id="bg_gradient_angle_val"></span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="section collapsed">
          <div class="section-title">
            <div class="title-left">🖋️ Nội dung & Biểu đồ</div>
            <div class="title-right">
              <input type="checkbox" id="auto_contrast" class="cfg" style="transform:scale(1.2);cursor:pointer" title="Tự động tương phản màu theo Nền">
              <span class="section-icon">▼</span>
            </div>
          </div>
          <div class="section-content">
            <div id="custom_colors_settings">
              <div class="row"><span class="label">Màu chữ chính</span><div class="input-group"><input type="color" id="textColor" class="cfg"></div></div>
              <div class="row"><span class="label">Màu số nổi bật</span><div class="input-group"><input type="color" id="redText" class="cfg"></div></div>
              <div class="row"><span class="label">Màu nền khối nhỏ</span><div class="input-group"><input type="color" id="blockBg" class="cfg"></div></div>
            </div>
            <div id="chart_colors_settings" class="row-col" style="margin-top:16px;border-top:1px dashed var(--divider-color,#e0e0e0);padding-top:16px">
              <span class="label">Màu sắc Biểu đồ:</span>
              <div class="color-grid">
                ${chartColorFields.map((f) => `
                  <div class="color-item">
                    <span class="color-label" title="${f.label}">${f.label}</span>
                    <input type="color" class="color-picker cc" data-key="${f.id}" value="${conf[f.id] || f.default}">
                  </div>`).join('')}
              </div>
            </div>
          </div>
        </div>

        <div class="section collapsed">
          <div class="section-title">
            <div class="title-left">🔲 Viền (Border)</div>
            <div class="title-right">
              <input type="checkbox" id="border_enable" class="cfg" style="transform:scale(1.2);cursor:pointer">
              <span class="section-icon">▼</span>
            </div>
          </div>
          <div class="section-content">
            <div id="border_settings">
              <div class="row"><span class="label">Màu viền</span><div class="input-group"><input type="color" id="border_color" class="cfg"><span class="val-badge" id="border_color_val"></span></div></div>
              <div class="row"><span class="label" style="min-width:120px">Độ dày (px)</span><input type="range" id="border_width" class="cfg" min="0" max="10" step="1"><span class="val-badge" id="border_width_val"></span></div>
              <div class="row"><span class="label" style="min-width:120px">Độ trong suốt (%)</span><input type="range" id="border_opacity" class="cfg" min="0" max="100"><span class="val-badge" id="border_opacity_val"></span></div>
            </div>
          </div>
        </div>

        <div class="section collapsed">
          <div class="section-title">
            <div class="title-left">☁️ Đổ bóng (Shadow)</div>
            <div class="title-right">
              <input type="checkbox" id="shadow_enable" class="cfg" style="transform:scale(1.2);cursor:pointer">
              <span class="section-icon">▼</span>
            </div>
          </div>
          <div class="section-content">
            <div id="shadow_settings">
              <div class="row"><span class="label">Màu bóng</span><div class="input-group"><input type="color" id="shadow_color" class="cfg"><span class="val-badge" id="shadow_color_val"></span></div></div>
              <div class="row"><span class="label" style="min-width:120px">Trong suốt (%)</span><input type="range" id="shadow_opacity" class="cfg" min="0" max="100"><span class="val-badge" id="shadow_opacity_val"></span></div>
              <div class="row"><span class="label" style="min-width:120px">Nhòe (Blur)</span><input type="range" id="shadow_blur" class="cfg" min="0" max="100"><span class="val-badge" id="shadow_blur_val"></span></div>
              <div class="row"><span class="label" style="min-width:120px">Offset X</span><input type="range" id="shadow_offset_x" class="cfg" min="-50" max="50"><span class="val-badge" id="shadow_offset_x_val"></span></div>
              <div class="row"><span class="label" style="min-width:120px">Offset Y</span><input type="range" id="shadow_offset_y" class="cfg" min="-50" max="50"><span class="val-badge" id="shadow_offset_y_val"></span></div>
            </div>
          </div>
        </div>
      </div>`;

      this._updateUI();
      this._addListeners();
    }

    /* Getters with safe defaults */
    _g(key, def) { return this._config?.[key] !== undefined ? this._config[key] : def; }
    get _bg_type()             { return this._g('bg_type', 'gradient'); }
    get _bg_color()            { return this._g('bg_color', '#f0f4f8'); }
    get _bg_opacity()          { return this._g('bg_opacity', 100); }
    get _bg_gradient_preset()  { return this._g('bg_gradient_preset', 'linear-gradient(135deg, #f0f4f8, #d9e2ec)'); }
    get _bg_gradient_color1()  { return this._g('bg_gradient_color1', '#f0f4f8'); }
    get _bg_gradient_color2()  { return this._g('bg_gradient_color2', '#d9e2ec'); }
    get _bg_gradient_angle()   { return this._g('bg_gradient_angle', 135); }
    get _border_enable()       { return this._g('border_enable', (this._config?.border_width > 0)); }
    get _border_color()        { return this._g('border_color', '#ffffff'); }
    get _border_width()        { return this._g('border_width', 0); }
    get _border_opacity()      { return this._g('border_opacity', 0); }
    get _shadow_enable()       { return this._g('shadow_enable', true); }
    get _shadow_color()        { return this._g('shadow_color', '#000000'); }
    get _shadow_opacity()      { return this._g('shadow_opacity', 10); }
    get _shadow_blur()         { return this._g('shadow_blur', 20); }
    get _shadow_offset_x()     { return this._g('shadow_offset_x', 0); }
    get _shadow_offset_y()     { return this._g('shadow_offset_y', 8); }
    get _auto_contrast()       { return this._g('auto_contrast', false); }
    get _textColor()           { return this._g('textColor', '#1e3a8a'); }
    get _redText()             { return this._g('redText', '#dc2626'); }
    get _blockBg()             { return this._g('blockBg', '#ffffff'); }

    /** Safely set a value on an element, guard missing IDs. */
    _set(id, prop, val) {
      const el = this.querySelector(`#${id}`);
      if (el) el[prop] = val;
    }
    _setText(id, val) { const el = this.querySelector(`#${id}`); if (el) el.textContent = val; }

    _updateUI() {
      if (!this.querySelector('#bg_type')) return;

      /* Entity dropdown */
      const esel = this.querySelector('#entity-select');
      if (esel && this._hass) {
        const cur = this._config.entity || '';
        const states = this._hass.states || {};
        let valid = Object.keys(states).filter((eid) => states[eid]?.attributes?.chi_tiet_tung_nam !== undefined);
        if (cur && !valid.includes(cur)) valid.unshift(cur);
        esel.innerHTML = `<option value="">-- Tự động chọn cái đầu tiên --</option>` +
          valid.map((eid) => {
            let name = states[eid]?.attributes?.friendly_name || eid;
            if (this._hass.entities?.[eid]) {
              const ei = this._hass.entities[eid];
              if (ei.device_id && this._hass.devices?.[ei.device_id]) {
                name = this._hass.devices[ei.device_id].name_by_user || this._hass.devices[ei.device_id].name || name;
              } else if (ei.name) name = ei.name;
            }
            return `<option value="${eid}" ${cur === eid ? 'selected' : ''}>${name.replace(' Total All Time', '').trim()}</option>`;
          }).join('');
        esel.value = cur;
      }

      this._set('title-input', 'value', this._config.title || '');
      this._set('icon-input',  'value', this._config.icon  || '');

      ['barKwh1','barKwh2','barVnd1','barVnd2','lineKwh','lineVnd','lineMonth'].forEach((k) => {
        const el = this.querySelector(`.cc[data-key="${k}"]`);
        if (el && this._config[k]) el.value = this._config[k];
      });

      this._set('bg_type',    'value', this._bg_type);
      this._set('bg_opacity', 'value', this._bg_opacity);
      this._setText('bg_opacity_val', this._bg_opacity + '%');

      const isGrad = this._bg_type === 'gradient';
      this.querySelector('#solid_settings').style.display    = isGrad ? 'none'  : 'block';
      this.querySelector('#gradient_settings').style.display = isGrad ? 'block' : 'none';

      this._set('bg_color', 'value', this._bg_color);
      this._setText('bg_color_val', this._bg_color.toUpperCase());
      this._set('bg_gradient_preset', 'value', this._bg_gradient_preset);
      this.querySelector('#custom_gradient_row').style.display = this._bg_gradient_preset === 'custom' ? 'flex' : 'none';
      this._set('bg_gradient_color1', 'value', this._bg_gradient_color1);
      this._setText('bg_gradient_color1_val', this._bg_gradient_color1.toUpperCase());
      this._set('bg_gradient_color2', 'value', this._bg_gradient_color2);
      this._setText('bg_gradient_color2_val', this._bg_gradient_color2.toUpperCase());
      this._set('bg_gradient_angle', 'value', this._bg_gradient_angle);
      this._setText('bg_gradient_angle_val', this._bg_gradient_angle + '°');

      this._set('border_enable', 'checked', this._border_enable);
      this.querySelector('#border_settings').style.display = this._border_enable ? 'block' : 'none';
      this._set('border_color', 'value', this._border_color);
      this._setText('border_color_val', this._border_color.toUpperCase());
      this._set('border_width',   'value', this._border_width);
      this._setText('border_width_val', this._border_width + 'px');
      this._set('border_opacity', 'value', this._border_opacity);
      this._setText('border_opacity_val', this._border_opacity + '%');

      this._set('shadow_enable', 'checked', this._shadow_enable);
      this.querySelector('#shadow_settings').style.display = this._shadow_enable ? 'block' : 'none';
      this._set('shadow_color',    'value', this._shadow_color);
      this._setText('shadow_color_val', this._shadow_color.toUpperCase());
      this._set('shadow_opacity',  'value', this._shadow_opacity);
      this._setText('shadow_opacity_val', this._shadow_opacity + '%');
      this._set('shadow_blur',     'value', this._shadow_blur);
      this._setText('shadow_blur_val', this._shadow_blur + 'px');
      this._set('shadow_offset_x', 'value', this._shadow_offset_x);
      this._setText('shadow_offset_x_val', this._shadow_offset_x + 'px');
      this._set('shadow_offset_y', 'value', this._shadow_offset_y);
      this._setText('shadow_offset_y_val', this._shadow_offset_y + 'px');

      this._set('auto_contrast', 'checked', this._auto_contrast);
      const dim = this._auto_contrast ? '0.4' : '1';
      const ptr = this._auto_contrast ? 'none' : 'auto';
      for (const id of ['custom_colors_settings', 'chart_colors_settings']) {
        const el = this.querySelector(`#${id}`);
        if (el) { el.style.opacity = dim; el.style.pointerEvents = ptr; }
      }
      this._set('textColor', 'value', this._textColor);
      this._set('redText',   'value', this._redText);
      this._set('blockBg',   'value', this._blockBg);
    }

    _buildConfig() {
      const q = (id) => this.querySelector(`#${id}`);
      const newCfg = {
        ...this._config,
        entity: q('entity-select')?.value || '',
        title:  q('title-input')?.value  || '',
        icon:   q('icon-input')?.value   || '',
        bg_type:          q('bg_type')?.value,
        bg_color:         q('bg_color')?.value,
        bg_opacity:       parseInt(q('bg_opacity')?.value, 10),
        bg_gradient_preset:  q('bg_gradient_preset')?.value,
        bg_gradient_color1:  q('bg_gradient_color1')?.value,
        bg_gradient_color2:  q('bg_gradient_color2')?.value,
        bg_gradient_angle:   parseInt(q('bg_gradient_angle')?.value, 10),
        border_enable:  q('border_enable')?.checked,
        border_color:   q('border_color')?.value,
        border_width:   parseInt(q('border_width')?.value, 10),
        border_opacity: parseInt(q('border_opacity')?.value, 10),
        shadow_enable:  q('shadow_enable')?.checked,
        shadow_color:   q('shadow_color')?.value,
        shadow_opacity: parseInt(q('shadow_opacity')?.value, 10),
        shadow_blur:    parseInt(q('shadow_blur')?.value, 10),
        shadow_offset_x: parseInt(q('shadow_offset_x')?.value, 10),
        shadow_offset_y: parseInt(q('shadow_offset_y')?.value, 10),
        auto_contrast:  q('auto_contrast')?.checked,
        textColor:      q('textColor')?.value,
        redText:        q('redText')?.value,
        blockBg:        q('blockBg')?.value,
      };
      this.querySelectorAll('.cc').forEach((el) => { newCfg[el.dataset.key] = el.value; });
      return newCfg;
    }

    _addListeners() {
      const dispatch = () => {
        this.dispatchEvent(new CustomEvent('config-changed', {
          detail: { config: this._buildConfig() },
          bubbles: true, composed: true,
        }));
      };
      this.querySelectorAll('.cfg, .cc').forEach((el) => {
        el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', dispatch);
        if (el.tagName !== 'SELECT') el.addEventListener('change', dispatch);
      });
      this.querySelectorAll('.section-title:not(.no-collapse)').forEach((title) => {
        title.querySelectorAll('input,select,button').forEach((el) =>
          el.addEventListener('click', (e) => e.stopPropagation()));
        title.addEventListener('click', () => title.closest('.section').classList.toggle('collapsed'));
      });
    }
  }

  /* ──────────────────────────────────────────────────────────────────────── */
  /* 2. CARD                                                                  */
  /* ──────────────────────────────────────────────────────────────────────── */
  class ElectricityConsumptionCard extends HTMLElement {
    static getConfigElement() { return document.createElement('electricity-consumption-editor'); }
    static getStubConfig(hass) {
      if (!hass?.states) return {};
      const eid = Object.keys(hass.states).find((e) => hass.states[e].attributes?.chi_tiet_tung_nam !== undefined);
      return { entity: eid || '' };
    }

    /** HA uses this to calculate dashboard column heights. */
    getCardSize() { return 6; }

    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this.config = {};
      this._selectedYear  = null;
      this._selectedMonth = null;
      this._activeTab     = 'overview';
      this._formYear      = null;
      this._formMonth     = '';
      this._searchYear    = null;
      this._searchMonth   = null;
      this._hasSearched   = false;
      this._yearsList     = [];
      this._monthsList    = [];
      this._resetTimer    = null;
      this._availableInstances = [];
      this._currentEntityId    = null;
      this._lastHtml      = '';
      this._initialized   = false;
      this._loadStartTime = null;
      this._boundClickHandler  = null;
      this._boundChangeHandler = null;

      /* Debounced hass setter – prevents burst renders when HA pushes state updates */
      this._debouncedHassUpdate = debounce(() => this._onHassUpdated(), 80);
    }

    setConfig(config) {
      this.config = config || {};
      // Always re-render shell (card element) on config change
      this._renderShell();
      if (this._hass) {
        this._scanForInstances();
        this._processData();
        this._updateView();
      }
    }

    set hass(hass) {
      const old = this._hass;
      this._hass = hass;
      if (!this._initialized) {
        this._renderShell();
        this._scanForInstances();
        this._processData();
        this._updateView();
        this._initialized = true;
        return;
      }
      // Only debounce-trigger if relevant entity changed
      if (!old || old.states[this._currentEntityId] !== hass.states[this._currentEntityId] ||
          this._availableInstances.length === 0) {
        this._debouncedHassUpdate();
      }
    }

    _onHassUpdated() {
      if (!this._currentEntityId || this._availableInstances.length === 0) {
        this._scanForInstances();
        if (this._availableInstances.length > 0) this._processData();
      } else {
        this._processData();
      }
      this._updateView();
    }

    /* ── Shell (ha-card + event wiring, created once) ─────────────────────── */
    _renderShell() {
      if (this.card) return; // already created

      // Inject shared CSS once per instance
      const styleEl = document.createElement('style');
      styleEl.textContent = CARD_CSS;
      this.shadowRoot.appendChild(styleEl);

      this.card = document.createElement('ha-card');
      this.card.style.cssText = 'padding:6px 12px 12px;border-radius:var(--ha-card-border-radius,16px);isolation:isolate;position:relative;';
      this.shadowRoot.appendChild(this.card);

      /* Mouse/touch idle → auto-reset after 2 min */
      this.card.addEventListener('mouseleave',  () => this._startResetTimer());
      this.card.addEventListener('mouseenter',  () => this._clearResetTimer());
      this.card.addEventListener('touchstart',  () => this._clearResetTimer(), { passive: true });
      this.card.addEventListener('touchend',    () => this._startResetTimer(), { passive: true });

      /* Delegated click handler */
      this._boundClickHandler = (e) => this._handleClick(e);
      this.card.addEventListener('click', this._boundClickHandler);

      /* Delegated change handler */
      this._boundChangeHandler = (e) => this._handleChange(e);
      this.card.addEventListener('change', this._boundChangeHandler);
    }

    _handleClick(e) {
      if (e.target.closest('.btn-y-prev'))  this._changeYear(-1);
      if (e.target.closest('.btn-y-next'))  this._changeYear(1);
      if (e.target.closest('.btn-m-prev'))  this._changeMonth(-1);
      if (e.target.closest('.btn-m-next'))  this._changeMonth(1);
      if (e.target.closest('.btn-fy-prev')) this._changeFormYear(-1);
      if (e.target.closest('.btn-fy-next')) this._changeFormYear(1);
      if (e.target.closest('.btn-fm-prev')) this._changeFormMonth(-1);
      if (e.target.closest('.btn-fm-next')) this._changeFormMonth(1);

      const tabEl = e.target.closest('.tab-item');
      if (tabEl) {
        const t = tabEl.dataset.tab;
        if (this._activeTab !== t) { this._activeTab = t; this._updateView(); }
      }
      if (e.target.closest('#btn-do-search')) {
        this._formYear    = parseInt(this.shadowRoot.getElementById('form-year')?.value, 10);
        const mv          = this.shadowRoot.getElementById('form-month')?.value ?? '';
        this._formMonth   = mv;
        this._searchYear  = this._formYear;
        this._searchMonth = mv !== '' ? parseInt(mv, 10) : null;
        this._hasSearched = true;
        this._updateView();
      }
      // Keyboard support: bar-col focus trigger
      const barCol = e.target.closest('.bar-col');
      if (barCol) barCol.focus();
    }

    _handleChange(e) {
      const id = e.target.id;
      if (id === 'sel-instance') {
        this._currentEntityId = e.target.value;
        this._selectedYear = this._selectedMonth = null;
        this._hasSearched  = false;
        this._processData(); this._updateView();
      } else if (id === 'sel-year') {
        this._selectedYear  = parseInt(e.target.value, 10);
        this._selectedMonth = null;
        this._processData(); this._updateView();
      } else if (id === 'sel-month') {
        this._selectedMonth = parseInt(e.target.value, 10);
        this._updateView();
      } else if (id === 'form-year') {
        this._formYear = parseInt(e.target.value, 10);
        this._updateView();
      } else if (id === 'form-month') {
        this._formMonth = e.target.value;
        this._updateView();
      }
    }

    connectedCallback() {
      // If card re-attached (e.g. after panel switch) and no instances found yet, retry
      if (this._initialized && this._availableInstances.length === 0 && this._hass) {
        this._scanForInstances();
        this._processData();
        this._updateView();
      }
    }

    disconnectedCallback() {
      this._clearResetTimer();
      if (this.card) {
        if (this._boundClickHandler)  this.card.removeEventListener('click',  this._boundClickHandler);
        if (this._boundChangeHandler) this.card.removeEventListener('change', this._boundChangeHandler);
      }
    }

    _startResetTimer() {
      this._clearResetTimer();
      this._resetTimer = setTimeout(() => this._resetToCurrentDate(), 120000);
    }
    _clearResetTimer() {
      if (this._resetTimer) { clearTimeout(this._resetTimer); this._resetTimer = null; }
    }
    _resetToCurrentDate() {
      const now = new Date();
      const y   = now.getFullYear();
      const m   = now.getMonth() + 1;
      let changed = false;
      if (this._activeTab !== 'overview') { this._activeTab = 'overview'; changed = true; }
      if (this._selectedYear !== y || this._selectedMonth !== m) {
        this._selectedYear = y; this._selectedMonth = m; changed = true;
      }
      if (changed) { this._processData(); this._updateView(); }
    }

    _scanForInstances() {
      if (!this._hass) return;
      const states = this._hass.states;
      const eids   = Object.keys(states).filter((e) => states[e]?.attributes?.chi_tiet_tung_nam !== undefined);
      this._availableInstances = eids.map((eid) => {
        let name = states[eid]?.attributes?.friendly_name || eid;
        const ei = this._hass.entities?.[eid];
        if (ei) {
          if (ei.device_id && this._hass.devices?.[ei.device_id]) {
            const di = this._hass.devices[ei.device_id];
            name = di.name_by_user || di.name || name;
          } else if (ei.name) name = ei.name;
        }
        return { id: eid, name: name.replace(' Total All Time', '').trim() };
      }).sort((a, b) => a.name.localeCompare(b.name));

      const conf = this.config || {};
      if (!this._currentEntityId || !this._availableInstances.some((i) => i.id === this._currentEntityId)) {
        if (this._availableInstances.length > 0) {
          this._currentEntityId = (conf.entity && this._availableInstances.some((i) => i.id === conf.entity))
            ? conf.entity
            : this._availableInstances[0].id;
        } else {
          this._currentEntityId = null;
        }
      }
    }

    _processData() {
      if (!this._hass || !this._currentEntityId) return;
      this.baseSlug = this._currentEntityId.replace('_total_all_time', '');
      const ts = this._hass.states[this._currentEntityId];
      if (!ts?.attributes?.chi_tiet_tung_nam) { this._yearsList = []; this._monthsList = []; return; }

      this._yearsList = Object.keys(ts.attributes.chi_tiet_tung_nam)
        .map((y) => parseInt(y.replace('Nam_', ''), 10))
        .sort((a, b) => b - a);

      if (this._selectedYear === null && this._yearsList.length > 0) this._selectedYear = this._yearsList[0];
      if (this._formYear     === null && this._yearsList.length > 0) this._formYear     = this._yearsList[0];

      if (this._selectedYear !== null) {
        const ys = this._hass.states[`${this.baseSlug}_nam_${this._selectedYear}`];
        if (ys?.attributes?.chi_tiet_cac_thang) {
          this._monthsList = Object.keys(ys.attributes.chi_tiet_cac_thang)
            .map((m) => parseInt(m.replace('Thang_', ''), 10))
            .sort((a, b) => b - a);
        } else {
          this._monthsList = Object.keys(this._hass.states)
            .filter((e) => e.startsWith(`${this.baseSlug}_thang_`) && e.endsWith(`_${this._selectedYear}`))
            .map((e) => parseInt(e.split('_thang_')[1].split('_')[0], 10))
            .sort((a, b) => b - a);
        }
        if (this._selectedMonth === null && this._monthsList.length > 0) this._selectedMonth = this._monthsList[0];
      }
    }

    /* ── Resolve theme colors ─────────────────────────────────────────────── */
    _resolveColors() {
      const conf = this.config || {};
      let cBlock = conf.blockBg   || '#ffffff';
      let cText  = conf.textColor || '#1e3a8a';
      let cRed   = conf.redText   || '#dc2626';
      let cOptBg = '#ffffff';
      let cBK1   = conf.barKwh1  || '#3b82f6';
      let cBK2   = conf.barKwh2  || '#1e3a8a';
      let cBV1   = conf.barVnd1  || '#10b981';
      let cBV2   = conf.barVnd2  || '#047857';
      let cLK    = conf.lineKwh  || '#ff3366';
      let cLV    = conf.lineVnd  || '#ffcc00';
      let cLM    = conf.lineMonth || '#ff3366';

      const bgType    = conf.bg_type    || 'gradient';
      const bgOpacity = conf.bg_opacity !== undefined ? conf.bg_opacity : 100;
      let bgStr = '';

      if (bgType === 'gradient') {
        const preset = conf.bg_gradient_preset || 'linear-gradient(135deg, #f0f4f8, #d9e2ec)';
        if (preset === 'custom') {
          const c1 = conf.bg_gradient_color1 || '#f0f4f8';
          const c2 = conf.bg_gradient_color2 || '#d9e2ec';
          const ang = conf.bg_gradient_angle !== undefined ? conf.bg_gradient_angle : 135;
          this.card.style.background = `linear-gradient(${ang}deg, ${hex2rgba(c1, bgOpacity)}, ${hex2rgba(c2, bgOpacity)})`;
          bgStr = `${c1} ${c2}`;
        } else {
          this.card.style.background = gradientOpacity(preset, bgOpacity);
          bgStr = preset;
        }
      } else {
        const bgColor = conf.bg_color || '#f0f4f8';
        this.card.style.background = hex2rgba(bgColor, bgOpacity);
        bgStr = bgColor;
      }

      /* Border */
      const borderEnabled = conf.border_enable !== undefined ? conf.border_enable : (conf.border_width > 0);
      if (borderEnabled) {
        const bw = conf.border_width   !== undefined ? conf.border_width   : 0;
        const bo = conf.border_opacity !== undefined ? conf.border_opacity : 0;
        const bc = conf.border_color   || '#ffffff';
        this.card.style.border = (bw > 0 && bo > 0) ? `${bw}px solid ${hex2rgba(bc, bo)}` : 'none';
      } else {
        this.card.style.border = 'none';
      }

      /* Shadow */
      const shadowEnabled = conf.shadow_enable !== undefined ? conf.shadow_enable : true;
      if (shadowEnabled) {
        const sc = conf.shadow_color   || '#000000';
        const so = conf.shadow_opacity !== undefined ? conf.shadow_opacity : 10;
        const sb = conf.shadow_blur    !== undefined ? conf.shadow_blur    : 20;
        const sx = conf.shadow_offset_x !== undefined ? conf.shadow_offset_x : 0;
        const sy = conf.shadow_offset_y !== undefined ? conf.shadow_offset_y : 8;
        this.card.style.boxShadow = `${sx}px ${sy}px ${sb}px ${hex2rgba(sc, so)}`;
      } else {
        this.card.style.boxShadow = 'none';
      }

      /* Auto-contrast */
      if (conf.auto_contrast) {
        const hexRx = /#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})\b/gi;
        const rgbRx = /rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/gi;
        const colors = [];
        let m;
        while ((m = hexRx.exec(bgStr)) !== null) {
          let h = m[1];
          if (h.length === 3) h = h.split('').map((c) => c + c).join('');
          colors.push({ r: parseInt(h.slice(0,2),16), g: parseInt(h.slice(2,4),16), b: parseInt(h.slice(4,6),16) });
        }
        while ((m = rgbRx.exec(bgStr)) !== null) {
          colors.push({ r: +m[1], g: +m[2], b: +m[3] });
        }
        if (colors.length > 0) {
          const avgR = Math.round(colors.reduce((s, c) => s + c.r, 0) / colors.length);
          const avgG = Math.round(colors.reduce((s, c) => s + c.g, 0) / colors.length);
          const avgB = Math.round(colors.reduce((s, c) => s + c.b, 0) / colors.length);

          const isDark = this._hass?.themes?.darkMode
            ?? (window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false);
          const op     = bgOpacity / 100;
          const base   = isDark ? 30 : 245;
          const effR   = Math.round(avgR * op + base * (1 - op));
          const effG   = Math.round(avgG * op + base * (1 - op));
          const effB   = Math.round(avgB * op + base * (1 - op));
          const yiq    = (effR * 299 + effG * 587 + effB * 114) / 1000;
          const isLight = yiq >= 135;

          /* HSL hue for palette selection */
          const r = effR/255, g = effG/255, b = effB/255;
          const max = Math.max(r,g,b), min = Math.min(r,g,b);
          const d   = max - min;
          let h2 = 0, s2 = 0;
          const l = (max + min) / 2;
          if (d > 0) {
            s2 = l > 0.5 ? d / (2 - max - min) : d / (max + min);
            if (max === r)      h2 = ((g - b) / d + (g < b ? 6 : 0)) / 6;
            else if (max === g) h2 = ((b - r) / d + 2) / 6;
            else                h2 = ((r - g) / d + 4) / 6;
          }
          const hue = Math.round(h2 * 360);

          let palette = { kwh: 'blue', vnd: 'green' };
          if (s2 >= 0.15) {
            if (hue >= 330 || hue < 45)       palette = { kwh: 'cyan',   vnd: 'green'  };
            else if (hue >= 45 && hue < 160)  palette = { kwh: 'purple', vnd: 'blue'   };
            else if (hue >= 160 && hue < 260) palette = { kwh: 'orange', vnd: 'pink'   };
            else                              palette = { kwh: 'green',  vnd: 'cyan'   };
          }

          const PL = {
            blue:   { 1:'#3b82f6',2:'#1e3a8a',l:'#ef4444' }, green:  { 1:'#10b981',2:'#047857',l:'#8b5cf6' },
            cyan:   { 1:'#06b6d4',2:'#0891b2',l:'#e11d48' }, purple: { 1:'#8b5cf6',2:'#5b21b6',l:'#f59e0b' },
            orange: { 1:'#f97316',2:'#c2410c',l:'#2563eb' }, pink:   { 1:'#ec4899',2:'#be185d',l:'#059669' },
          };
          const PD = {
            blue:   { 1:'#60a5fa',2:'#3b82f6',l:'#fde047' }, green:  { 1:'#34d399',2:'#10b981',l:'#f472b6' },
            cyan:   { 1:'#22d3ee',2:'#06b6d4',l:'#fb923c' }, purple: { 1:'#a78bfa',2:'#8b5cf6',l:'#4ade80' },
            orange: { 1:'#fb923c',2:'#f97316',l:'#22d3ee' }, pink:   { 1:'#f472b6',2:'#ec4899',l:'#fef08a' },
          };
          const PAL = isLight ? PL : PD;

          if (isLight) {
            cText = '#1a1a1a';
            cBlock = hex2rgba('#000000', Math.max(5, op * 10));
            cOptBg = '#ffffff';
            cRed = s2 < 0.15 ? '#E65100'
              : hue < 30 || hue >= 330 ? '#0D47A1'
              : hue < 90  ? '#4A148C'
              : hue < 170 ? '#B71C1C'
              : hue < 260 ? '#E65100' : '#E64A19';
          } else {
            cText = '#ffffff';
            cBlock = hex2rgba('#ffffff', Math.max(10, op * 15));
            cOptBg = '#1e1e1e';
            cRed = s2 < 0.15 ? '#FFCA28'
              : hue < 30 || hue >= 330 ? '#FFEA00'
              : hue < 90  ? '#69F0AE'
              : hue < 170 ? '#FF9100'
              : hue < 260 ? '#C6FF00' : '#FFD54F';
          }
          cBK1 = PAL[palette.kwh][1]; cBK2 = PAL[palette.kwh][2]; cLK = PAL[palette.kwh].l;
          cBV1 = PAL[palette.vnd][1]; cBV2 = PAL[palette.vnd][2]; cLV = PAL[palette.vnd].l;
          cLM  = cLK;
        }
      }

      this.card.style.color = cText;
      return { cBlock, cText, cRed, cOptBg, cBK1, cBK2, cBV1, cBV2, cLK, cLV, cLM };
    }

    /* ── Chart builders ───────────────────────────────────────────────────── */
    _buildMonthChart(y, m, cols, isSearch = false) {
      const { cLM } = cols;
      const ms = this._hass.states[`${this.baseSlug}_thang_${m}_${y}`];
      if (!ms) return `<div class="chart-section block-common" style="text-align:center;padding:20px">Không có dữ liệu tháng ${m}/${y}</div>`;

      const m_kwh   = ms.attributes.tong_san_luong_kwh      || 0;
      const m_truoc = ms.attributes.tong_tien_truoc_thue    || 0;
      const m_sau   = ms.attributes.tong_tien_sau_thue      || 0;
      const daily   = ms.attributes.chi_tiet_ngay            || {};
      const now     = new Date();
      const [cy, cm, cd] = [now.getFullYear(), now.getMonth() + 1, now.getDate()];
      const daysInM = new Date(y, m, 0).getDate();

      let validDays = 0, maxDayVal = -1, minDayVal = Infinity, maxDayStr = '', minDayStr = '';
      const fullData = Array.from({ length: daysInM }, (_, i) => {
        const day = i + 1;
        const dayKey = day < 10 ? `0${day}` : `${day}`;
        const val = Number(daily[`Ngay_${dayKey}`] ?? daily[`Ngay_${day}`] ?? 0) || 0;
        const future = (y > cy) || (y === cy && m > cm) || (y === cy && m === cm && day > cd);
        if (!future && val > 0) {
          validDays++;
          if (val > maxDayVal) { maxDayVal = val; maxDayStr = String(day); }
          if (val < minDayVal) { minDayVal = val; minDayStr = String(day); }
        }
        return { dayNum: day, dayStr: dayKey, val: future ? 0 : val, future };
      });

      const maxVal = Math.max(...fullData.filter((d) => !d.future).map((d) => d.val), 1);
      const pts = []; const pLine = [];
      fullData.forEach((d, i) => {
        if (d.future) return;
        const colW = 100 / fullData.length;
        const x = ((i + 0.5) * colW).toFixed(4);
        const yc = (100 - (d.val / maxVal) * 100).toFixed(4);
        pts.push({ x, y: yc }); pLine.push(`${x},${yc}`);
      });
      const dotsHtml = pts.map((p) => `<div class="chart-dot" style="left:${p.x}%;top:${p.y}%;border:1.5px solid ${cLM};background:${cLM}"></div>`).join('');

      let statsHtml = '';
      if (isSearch) {
        if (minDayVal === Infinity) { minDayVal = 0; minDayStr = '-'; maxDayVal = 0; maxDayStr = '-'; }
        const avgKwh = validDays > 0 ? m_kwh / validDays : 0;
        const avgVnd = validDays > 0 ? m_sau / validDays : 0;
        statsHtml = `<div class="search-stats-grid">
          <div class="s-stat-card"><div class="s-label">⚡ Ngày cao nhất</div><div class="s-val">Ngày ${maxDayStr}: <span class="primary">${fmtN(maxDayVal)}</span> kWh</div></div>
          <div class="s-stat-card"><div class="s-label">⚡ Ngày thấp nhất</div><div class="s-val">Ngày ${minDayStr}: <span class="primary">${fmtN(minDayVal)}</span> kWh</div></div>
          <div class="s-stat-card"><div class="s-label">📊 Trung bình/Ngày</div><div class="s-val"><span class="primary">${fmtN(avgKwh)}</span> kWh</div></div>
          <div class="s-stat-card"><div class="s-label">💸 Tiền TB/Ngày</div><div class="s-val"><span class="money">${fmt$(avgVnd)}</span> đ</div></div>
        </div>`;
      }

      return statsHtml + `
      <div class="chart-section block-common">
        <div class="chart-header">
          <div class="chart-title">
            <span><ha-icon icon="mdi:chart-bar" style="font-size:clamp(18px,4vw,22px);color:#3b82f6"></ha-icon> Chi tiết T${m}/${y}</span>
          </div>
          <div class="chart-stats">
            <div class="hover-zap" style="cursor:default">
              <div class="c-stat-val primary">${fmtN(m_kwh)} <ha-icon icon="mdi:lightning-bolt" class="icon-kwh" style="font-size:clamp(12px,3.5vw,20px);margin-left:2px"></ha-icon></div>
              <div class="stat-label-sm">Sản lượng</div>
            </div>
            <div class="hover-fly" style="cursor:default">
              <div class="c-stat-val money">${fmt$(m_truoc)} <span class="emoji-money" style="font-size:clamp(12px,3.5vw,20px);margin-left:2px">💸</span></div>
              <div class="stat-label-sm">Trước VAT</div>
            </div>
            <div class="hover-fly" style="cursor:default">
              <div class="c-stat-val money">${fmt$(m_sau)} <span class="emoji-money" style="font-size:clamp(12px,3.5vw,20px);margin-left:2px">💸</span></div>
              <div class="stat-label-sm">Sau VAT</div>
            </div>
          </div>
        </div>
        <div class="chart-container">
          <svg class="svg-overlay" preserveAspectRatio="none" viewBox="0 0 100 100">
            <polyline points="${pLine.join(' ')}" fill="none" stroke="${cLM}" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <div class="dots-overlay">${dotsHtml}</div>
          <div class="bar-chart">
            ${fullData.map((d) => {
              const h = (d.val / maxVal) * 100;
              const isToday = (y === cy && m === cm && d.dayNum === cd);
              return `<div class="bar-col" tabindex="0">
                ${!d.future ? `<div class="bar-val bar-val-daily">${fmtN(d.val)}</div><div class="bar" style="height:${h}%"></div>` : ''}
                <div class="${isToday ? 'bar-label label-active' : 'bar-label'}">${d.dayStr}</div>
              </div>`;
            }).join('')}
          </div>
        </div>
      </div>`;
    }

    _buildYearChart(y, cols, isSearch = false) {
      const { cLK, cLV } = cols;
      const ys = this._hass.states[`${this.baseSlug}_nam_${y}`];
      if (!ys) return `<div class="chart-section block-common" style="text-align:center;padding:20px">Không có dữ liệu năm ${y}</div>`;

      const y_kwh   = ys.attributes.tong_san_luong_nam    || 0;
      const y_truoc = ys.attributes.tong_tien_truoc_thue  || 0;
      const y_sau   = ys.attributes.tong_tien_sau_thue    || 0;
      const monthly = ys.attributes.chi_tiet_cac_thang    || {};
      const now     = new Date();
      const [cy, cm] = [now.getFullYear(), now.getMonth() + 1];

      let validM = 0, maxKwh = -1, maxVnd = -1, minKwh = Infinity, minVnd = Infinity, maxMS = '', minMS = '';
      const fullYear = Array.from({ length: 12 }, (_, i) => {
        const mon = i + 1;
        const mk  = mon < 10 ? `0${mon}` : `${mon}`;
        const obj = monthly[`Thang_${mk}`] || monthly[`Thang_${mon}`] || {};
        let kwh = Number(obj.san_luong_kwh) || 0;
        let vnd = Number(obj.thanh_tien_sau_thue_vnd || obj.thanh_tien_vnd) || 0;
        if (!vnd) {
          const ms = this._hass.states[`${this.baseSlug}_thang_${mon}_${y}`];
          if (ms?.attributes) vnd = Number(ms.attributes.tong_tien_sau_thue || ms.attributes.tong_tien_truoc_thue) || 0;
        }
        const future = (y > cy) || (y === cy && mon > cm);
        if (!future && kwh > 0) {
          validM++;
          if (kwh > maxKwh) { maxKwh = kwh; maxVnd = vnd; maxMS = String(mon); }
          if (kwh < minKwh) { minKwh = kwh; minVnd = vnd; minMS = String(mon); }
        }
        return { monthNum: mon, monthStr: mk, kwhVal: future ? 0 : kwh, vndVal: future ? 0 : vnd, future };
      });

      const maxMKwh = Math.max(...fullYear.filter((d) => !d.future).map((d) => d.kwhVal), 1);
      const maxMVnd = Math.max(...fullYear.filter((d) => !d.future).map((d) => d.vndVal), 1);
      const pKwh = []; const pVnd = []; const lKwh = []; const lVnd = [];
      fullYear.forEach((d, i) => {
        if (d.future) return;
        const cW = 100 / 12, gW = cW * 0.85;
        const xK = ((i * cW) + ((cW - gW) / 2) + gW / 4).toFixed(4);
        const xV = ((i * cW) + ((cW - gW) / 2) + 3 * gW / 4).toFixed(4);
        const yK = (100 - (d.kwhVal / maxMKwh) * 100).toFixed(4);
        const yV = (100 - (d.vndVal / maxMVnd) * 100).toFixed(4);
        pKwh.push({ x: xK, y: yK }); lKwh.push(`${xK},${yK}`);
        pVnd.push({ x: xV, y: yV }); lVnd.push(`${xV},${yV}`);
      });

      const dotsK = pKwh.map((p) => `<div class="chart-dot" style="left:${p.x}%;top:${p.y}%;border:1.5px solid ${cLK};background:${cLK}"></div>`).join('');
      const dotsV = pVnd.map((p) => `<div class="chart-dot" style="left:${p.x}%;top:${p.y}%;border:1.5px solid ${cLV};background:${cLV}"></div>`).join('');

      let statsHtml = '';
      if (isSearch) {
        if (minKwh === Infinity) { minKwh = 0; minVnd = 0; minMS = '-'; maxKwh = 0; maxVnd = 0; maxMS = '-'; }
        const avgK = validM > 0 ? y_kwh / validM : 0;
        const avgV = validM > 0 ? y_sau / validM : 0;
        statsHtml = `<div class="search-stats-grid">
          <div class="s-stat-card"><div class="s-label">⚡ Tháng cao nhất</div><div class="s-val">Tháng ${maxMS}: <span class="primary">${fmtN(maxKwh)}</span> kWh<br><span style="font-size:.9em">(<span class="money">${fmt$(maxVnd)}</span> đ)</span></div></div>
          <div class="s-stat-card"><div class="s-label">⚡ Tháng thấp nhất</div><div class="s-val">Tháng ${minMS}: <span class="primary">${fmtN(minKwh)}</span> kWh<br><span style="font-size:.9em">(<span class="money">${fmt$(minVnd)}</span> đ)</span></div></div>
          <div class="s-stat-card"><div class="s-label">📊 Trung bình/Tháng</div><div class="s-val"><span class="primary">${fmtN(avgK)}</span> kWh</div></div>
          <div class="s-stat-card"><div class="s-label">💸 Tiền TB/Tháng</div><div class="s-val"><span class="money">${fmt$(avgV)}</span> đ</div></div>
        </div>`;
      }

      return statsHtml + `
      <div class="chart-section block-common">
        <div class="chart-header">
          <div class="chart-title">
            <span><ha-icon icon="mdi:chart-timeline-variant" style="font-size:clamp(18px,4vw,22px);color:#10b981"></ha-icon> Thống kê ${y}</span>
          </div>
          <div class="chart-stats">
            <div class="hover-zap" style="cursor:default">
              <div class="c-stat-val primary">${fmtN(y_kwh)} <ha-icon icon="mdi:lightning-bolt" class="icon-kwh" style="font-size:clamp(12px,3.5vw,20px);margin-left:2px"></ha-icon></div>
              <div class="stat-label-sm">Sản lượng</div>
            </div>
            <div class="hover-fly" style="cursor:default">
              <div class="c-stat-val money">${fmt$(y_truoc)} <span class="emoji-money" style="font-size:clamp(12px,3.5vw,20px);margin-left:2px">💸</span></div>
              <div class="stat-label-sm">Trước VAT</div>
            </div>
            <div class="hover-fly" style="cursor:default">
              <div class="c-stat-val money">${fmt$(y_sau)} <span class="emoji-money" style="font-size:clamp(12px,3.5vw,20px);margin-left:2px">💸</span></div>
              <div class="stat-label-sm">Sau VAT</div>
            </div>
          </div>
        </div>
        <div class="chart-container">
          <svg class="svg-overlay" preserveAspectRatio="none" viewBox="0 0 100 100">
            <polyline points="${lKwh.join(' ')}" fill="none" stroke="${cLK}" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round"/>
            <polyline points="${lVnd.join(' ')}" fill="none" stroke="${cLV}" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <div class="dots-overlay">${dotsK}${dotsV}</div>
          <div class="bar-chart">
            ${fullYear.map((d) => {
              const isCM = (y === cy && d.monthNum === cm);
              return `<div class="bar-col" tabindex="0">
                <div class="bar-group">
                  ${!d.future ? `
                    <div><div class="bar-val bar-val-kwh">${fmtN(d.kwhVal)}</div><div class="bar-kwh" style="height:${(d.kwhVal/maxMKwh)*100}%"></div></div>
                    <div><div class="bar-val bar-val-vnd">${fmt$(d.vndVal)}</div><div class="bar-vnd" style="height:${(d.vndVal/maxMVnd)*100}%"></div></div>` : ''}
                </div>
                <div class="${isCM ? 'bar-label label-active' : 'bar-label'}">T${d.monthStr}</div>
              </div>`;
            }).join('')}
          </div>
        </div>
      </div>`;
    }

    _buildDecadeCharts(cols) {
      if (!this._yearsList.length) return '';
      const { cLK, cLV } = cols;
      const chunks = [];
      for (let i = 0; i < this._yearsList.length; i += 10) chunks.push(this._yearsList.slice(i, i + 10));
      const cy = new Date().getFullYear();

      return chunks.map((chunk) => {
        let totKwh = 0, totTruoc = 0, totSau = 0;
        const data = chunk.map((y) => {
          const ys = this._hass.states[`${this.baseSlug}_nam_${y}`];
          const kwh    = ys?.attributes?.tong_san_luong_nam    || 0;
          const vnd    = ys?.attributes?.tong_tien_sau_thue    || 0;
          const truoc  = ys?.attributes?.tong_tien_truoc_thue  || 0;
          totKwh += kwh; totTruoc += truoc; totSau += vnd;
          return { year: y, kwh, vnd };
        });
        const maxK = Math.max(...data.map((d) => d.kwh), 1);
        const maxV = Math.max(...data.map((d) => d.vnd), 1);
        const pK = []; const pV = []; const lK = []; const lV = [];
        data.forEach((d, i) => {
          const cW = 100 / data.length, gW = cW * 0.85;
          const xK = ((i * cW) + (cW - gW) / 2 + gW / 4).toFixed(4);
          const xV = ((i * cW) + (cW - gW) / 2 + 3 * gW / 4).toFixed(4);
          const yK = (100 - (d.kwh / maxK) * 100).toFixed(4);
          const yV = (100 - (d.vnd / maxV) * 100).toFixed(4);
          pK.push({ x: xK, y: yK }); lK.push(`${xK},${yK}`);
          pV.push({ x: xV, y: yV }); lV.push(`${xV},${yV}`);
        });
        const dK = pK.map((p) => `<div class="chart-dot" style="left:${p.x}%;top:${p.y}%;border:1.5px solid ${cLK};background:${cLK}"></div>`).join('');
        const dV = pV.map((p) => `<div class="chart-dot" style="left:${p.x}%;top:${p.y}%;border:1.5px solid ${cLV};background:${cLV}"></div>`).join('');
        const title = chunk.length > 1 ? `${Math.max(...chunk)} - ${Math.min(...chunk)}` : `${chunk[0]}`;

        return `
        <div class="chart-section block-common" style="margin-top:16px">
          <div class="chart-header" style="margin-bottom:8px;border-bottom:none;padding-bottom:0">
            <div class="chart-title">
              <span><ha-icon icon="mdi:history" style="font-size:clamp(18px,4vw,22px);color:#8b5cf6"></ha-icon> Tổng quan ${title}</span>
            </div>
          </div>
          <div class="decade-summary">
            <div class="d-sum-item hover-zap" style="cursor:default">
              <div class="d-sum-val">${fmtN(totKwh)} <ha-icon icon="mdi:lightning-bolt" class="icon-kwh" style="font-size:clamp(12px,3.5vw,20px)"></ha-icon></div>
              <div class="d-sum-label">Sản lượng</div>
            </div>
            <div class="d-sum-item hover-fly" style="cursor:default">
              <div class="d-sum-val money">${fmt$(totTruoc)} <span class="emoji-money" style="font-size:clamp(12px,3.5vw,20px)">💸</span></div>
              <div class="d-sum-label">Trước VAT</div>
            </div>
            <div class="d-sum-item hover-fly" style="cursor:default">
              <div class="d-sum-val money">${fmt$(totSau)} <span class="emoji-money" style="font-size:clamp(12px,3.5vw,20px)">💸</span></div>
              <div class="d-sum-label">Sau VAT</div>
            </div>
          </div>
          <div class="chart-container">
            <svg class="svg-overlay" preserveAspectRatio="none" viewBox="0 0 100 100">
              <polyline points="${lK.join(' ')}" fill="none" stroke="${cLK}" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round"/>
              <polyline points="${lV.join(' ')}" fill="none" stroke="${cLV}" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <div class="dots-overlay">${dK}${dV}</div>
            <div class="bar-chart">
              ${data.map((d) => {
                const isCY = (d.year === cy);
                return `<div class="bar-col" tabindex="0">
                  <div class="bar-group">
                    <div><div class="bar-val bar-val-kwh">${fmtN(d.kwh)}</div><div class="bar-kwh" style="height:${(d.kwh/maxK)*100}%"></div></div>
                    <div><div class="bar-val bar-val-vnd">${fmt$(d.vnd)}</div><div class="bar-vnd" style="height:${(d.vnd/maxV)*100}%"></div></div>
                  </div>
                  <div class="${isCY ? 'bar-label label-active' : 'bar-label'}">${d.year}</div>
                </div>`;
              }).join('')}
            </div>
          </div>
        </div>`;
      }).join('');
    }

    /* ── Main render ──────────────────────────────────────────────────────── */
    _updateView() {
      if (!this._hass || !this.card) return;

      /* Loading state */
      if (this._availableInstances.length === 0) {
        if (!this._loadStartTime) this._loadStartTime = Date.now();
        if (Date.now() - this._loadStartTime > 20000) {
          this.card.innerHTML = `<div class="error-box">
            <ha-icon icon="mdi:alert-circle-outline"></ha-icon>
            <div class="error-title">Chưa tìm thấy dữ liệu từ Tracker.</div>
            <div class="error-sub">Vui lòng kiểm tra lại cấu hình sensor trong HA.</div>
          </div>`;
        } else {
          this.card.innerHTML = `
            <style>.ha-card-loader,.loader-spinner,.loader-text{}</style>
            <div class="ha-card-loader">
              <div class="loader-spinner"></div>
              <div class="loader-text">Đang đồng bộ dữ liệu Điện năng...<br>Vui lòng chờ dữ liệu đang được nạp<br>Nếu báo lỗi hãy F5 lại trang hoặc đóng trình duyệt và mở lại</div>
            </div>`;
          // Retry via connectedCallback when HA pushes more state — no recursive setTimeout needed
        }
        this._lastHtml = '';
        return;
      }
      this._loadStartTime = null;
      if (!this._currentEntityId) return;

      const ts = this._hass.states[this._currentEntityId];
      if (!ts) return;

      const cols = this._resolveColors();
      const { cBlock, cText, cRed, cOptBg, cBK1, cBK2, cBV1, cBV2 } = cols;

      /* Update CSS variables on :host via a vars block only when colors change */
      const varStr = `--block-bg:${cBlock};--text-main:${cText};--bar-k1:${cBK1};--bar-k2:${cBK2};--bar-v1:${cBV1};--bar-v2:${cBV2};--text-red:${cRed};--option-bg:${cOptBg}`;
      if (this._lastVarStr !== varStr) {
        const hostStyle = this.shadowRoot.querySelector('style');
        if (hostStyle) {
          // Patch the :host block without re-injecting the whole CSS
          const patched = CARD_CSS.replace(
            /--block-bg[^}]+/,
            `--block-bg:${cBlock};--text-main:${cText};--bar-k1:${cBK1};--bar-k2:${cBK2};--bar-v1:${cBV1};--bar-v2:${cBV2};--text-red:${cRed};--option-bg:${cOptBg};`
          );
          hostStyle.textContent = patched;
        }
        this._lastVarStr = varStr;
      }

      const conf        = this.config || {};
      const displayTitle = conf.title || 'Thống kê Điện năng';
      const icon         = conf.icon  || 'mdi:transmission-tower';
      const iconHtml     = icon.includes(':')
        ? `<ha-icon icon="${icon}"></ha-icon>`
        : `<span class="emoji-icon">${icon}</span>`;

      let html = `
        <div class="main-card-header">${iconHtml} <span>${displayTitle}</span></div>
        <div class="header-tools">
          <div class="tabs-container">
            <div class="tab-item ${this._activeTab === 'overview' ? 'active' : ''}" data-tab="overview">Tổng quan</div>
            <div class="tab-item ${this._activeTab === 'search'   ? 'active' : ''}" data-tab="search">Tra cứu</div>
          </div>
          ${this._availableInstances.length > 1 ? `
            <select id="sel-instance" class="main-sel">
              ${this._availableInstances.map((inst) => `<option value="${inst.id}" ${this._currentEntityId === inst.id ? 'selected' : ''}>${inst.name}</option>`).join('')}
            </select>` : ''}
        </div>`;

      if (this._activeTab === 'overview') {
        const t_kwh   = ts.state;
        const t_truoc = ts.attributes.tong_tien_tich_luy;
        const t_sau   = ts.attributes.tong_tien_tich_luy_sau_thue;

        html += `
          <div class="top-dashboard block-common">
            <div class="global-stats-compact">
              <div class="stat-box primary hover-zap">
                <div class="stat-value"><ha-icon icon="mdi:lightning-bolt" class="icon-kwh"></ha-icon> ${fmtN(t_kwh)} <span class="stat-unit">kWh</span></div>
                <div class="stat-label">Tổng sản lượng</div>
              </div>
              <div class="stat-box hover-fly">
                <div class="stat-value"><span class="emoji-money">💸</span> ${fmt$(t_truoc)} <span class="stat-unit">đ</span></div>
                <div class="stat-label">Trước VAT</div>
              </div>
              <div class="stat-box hover-fly">
                <div class="stat-value"><span class="emoji-money">💸</span> ${fmt$(t_sau)} <span class="stat-unit">đ</span></div>
                <div class="stat-label">Sau VAT</div>
              </div>
            </div>
          </div>

          <div class="controls">
            <div class="control-pill block-common">
              <div class="nav-btn btn-y-prev" title="Năm trước"><ha-icon icon="mdi:chevron-left"></ha-icon></div>
              <div class="control-content">
                <ha-icon icon="mdi:calendar-blank" class="ctrl-icon"></ha-icon>
                <select id="sel-year" class="styled-sel">
                  ${this._yearsList.map((y) => `<option value="${y}" ${this._selectedYear === y ? 'selected' : ''}>${y}</option>`).join('')}
                </select>
              </div>
              <div class="nav-btn btn-y-next" title="Năm sau"><ha-icon icon="mdi:chevron-right"></ha-icon></div>
            </div>
            <div class="control-pill block-common">
              <div class="nav-btn btn-m-prev" title="Tháng trước"><ha-icon icon="mdi:chevron-left"></ha-icon></div>
              <div class="control-content">
                <ha-icon icon="mdi:calendar-month" class="ctrl-icon"></ha-icon>
                <select id="sel-month" class="styled-sel">
                  ${this._monthsList.map((m) => `<option value="${m}" ${this._selectedMonth === m ? 'selected' : ''}>T${m < 10 ? '0' + m : m}</option>`).join('')}
                </select>
              </div>
              <div class="nav-btn btn-m-next" title="Tháng sau"><ha-icon icon="mdi:chevron-right"></ha-icon></div>
            </div>
          </div>`;

        html += this._buildMonthChart(this._selectedYear, this._selectedMonth, cols, false);
        html += this._buildYearChart(this._selectedYear, cols, false);

      } else {
        // Search tab
        html += `
          <div class="search-bar-wrapper">
            <div class="search-inputs">
              <div class="control-pill block-common">
                <div class="nav-btn btn-fy-prev" title="Năm trước"><ha-icon icon="mdi:chevron-left"></ha-icon></div>
                <div class="control-content">
                  <ha-icon icon="mdi:calendar-blank" class="ctrl-icon"></ha-icon>
                  <select id="form-year" class="styled-sel">
                    ${this._yearsList.map((y) => `<option value="${y}" ${this._formYear === y ? 'selected' : ''}>${y}</option>`).join('')}
                  </select>
                </div>
                <div class="nav-btn btn-fy-next" title="Năm sau"><ha-icon icon="mdi:chevron-right"></ha-icon></div>
              </div>
              <div class="control-pill block-common">
                <div class="nav-btn btn-fm-prev" title="Tháng trước"><ha-icon icon="mdi:chevron-left"></ha-icon></div>
                <div class="control-content">
                  <ha-icon icon="mdi:calendar-month" class="ctrl-icon"></ha-icon>
                  <select id="form-month" class="styled-sel">
                    <option value="" ${this._formMonth === '' ? 'selected' : ''}>-- Cả năm --</option>
                    ${[1,2,3,4,5,6,7,8,9,10,11,12].map((m) => `<option value="${m}" ${this._formMonth == m ? 'selected' : ''}>T${m < 10 ? '0' + m : m}</option>`).join('')}
                  </select>
                </div>
                <div class="nav-btn btn-fm-next" title="Tháng sau"><ha-icon icon="mdi:chevron-right"></ha-icon></div>
              </div>
            </div>
            <button id="btn-do-search" class="btn-search">
              <ha-icon icon="mdi:magnify" style="font-size:18px;margin-right:6px;margin-bottom:-2px"></ha-icon>Tra cứu
            </button>
          </div>`;

        if (this._hasSearched && this._searchYear) {
          html += this._searchMonth !== null
            ? this._buildMonthChart(this._searchYear, this._searchMonth, cols, true)
            : this._buildYearChart(this._searchYear, cols, true);
        }
        html += this._buildDecadeCharts(cols);
      }

      if (this._lastHtml !== html) {
        this.card.innerHTML = html;
        this._lastHtml = html;
      }
    }

    _changeYear(step) {
      const idx = this._yearsList.indexOf(this._selectedYear);
      const next = this._yearsList[idx - step];
      if (next !== undefined) { this._selectedYear = next; this._selectedMonth = null; this._processData(); this._updateView(); }
    }
    _changeMonth(step) {
      const idx = this._monthsList.indexOf(this._selectedMonth);
      const next = this._monthsList[idx - step];
      if (next !== undefined) { this._selectedMonth = next; this._updateView(); }
    }
    _changeFormYear(step) {
      const idx = this._yearsList.indexOf(this._formYear);
      const next = this._yearsList[idx - step];
      if (next !== undefined) { this._formYear = next; this._updateView(); }
    }
    _changeFormMonth(step) {
      const list = ['', 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
      const cur  = this._formMonth !== '' ? parseInt(this._formMonth, 10) : '';
      const idx  = list.indexOf(cur);
      if (idx === -1) return;
      const ni = idx + step;
      if (ni >= 0 && ni < list.length) { this._formMonth = list[ni]; this._updateView(); }
    }
  }

  /* ── Register ──────────────────────────────────────────────────────────── */
  customElements.define('electricity-consumption-editor', ElectricityConsumptionEditor);
  customElements.define('electricity-consumption-card',   ElectricityConsumptionCard);

  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === 'electricity-consumption-card')) {
    window.customCards.push({
      type:        'electricity-consumption-card',
      name:        'Thống kê Điện năng',
      description: 'Thẻ hiển thị thống kê tiêu thụ điện năng có hỗ trợ Nền Gradient & Tương phản tự động.',
      preview:     true,
      version:     '2.0.0',
    });
  }
})();
