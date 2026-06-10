// lbb-tokens.js
// Design tokens for LosslessBob hi-fi.
// Two modes (light/dark) × eight accents × three density presets.
// applyTheme writes CSS custom properties to the document root.

window.LBB_TOKENS = (() => {
  // Status colors: fixed across modes; only the bg-wash flavor adjusts.
  // Live on left-edge bar + pill, never paint full rows except as a wash.
  const STATUS = {
    light: {
      ok:    { fg: "#1f7a3e", bg: "#e7f2e2", bar: "#39a360" },
      warn:  { fg: "#9a6800", bg: "#f8eed3", bar: "#cc9f3d" },
      bad:   { fg: "#b03f30", bg: "#fbe6df", bar: "#d8604f" },
      info:  { fg: "#1f5b8f", bg: "#e2ecf6", bar: "#4c89c4" },
      mute:  { fg: "#8a8473", bg: "#ecebe4", bar: "#a8a293" },
    },
    dark: {
      ok:    { fg: "#5db679", bg: "#1f2d22", bar: "#39a360" },
      warn:  { fg: "#d4a35a", bg: "#2e2719", bar: "#b58a3a" },
      bad:   { fg: "#e08070", bg: "#321f1d", bar: "#c25a48" },
      info:  { fg: "#7eb4e8", bg: "#1b2733", bar: "#5891cf" },
      mute:  { fg: "#857d6b", bg: "#252320", bar: "#6e6759" },
    },
  };

  const MODES = {
    light: {
      bg:        "#faf8f3",   // app body — warm cream
      surface:   "#ffffff",   // cards, sidebar panels
      surface2:  "#f1efe7",   // table header, subtle wells
      surface3:  "#e7e4d8",   // hover surface
      border:    "#e2dfd2",   // hairlines
      border2:   "#c8c3b1",   // stronger borders
      fg:        "#1c1a17",   // primary text
      fg2:       "#5b554a",   // secondary text
      fg3:       "#8e8676",   // tertiary / placeholder
      shadow:    "0 1px 0 rgba(0,0,0,0.02), 0 2px 6px rgba(40,30,15,0.06)",
      shadowLg:  "0 4px 16px rgba(40,30,15,0.08), 0 1px 0 rgba(255,255,255,0.6) inset",
      focusRing: "0 0 0 3px rgba(0,0,0,0.08)",
    },
    dark: {
      bg:        "#161510",
      surface:   "#1d1c16",
      surface2:  "#27251d",
      surface3:  "#34312a",
      border:    "#36332b",
      border2:   "#4b463c",
      fg:        "#f1ecdf",
      fg2:       "#b6ad9a",
      fg3:       "#756f60",
      shadow:    "0 1px 0 rgba(255,255,255,0.04) inset, 0 2px 8px rgba(0,0,0,0.4)",
      shadowLg:  "0 1px 0 rgba(255,255,255,0.05) inset, 0 8px 24px rgba(0,0,0,0.5)",
      focusRing: "0 0 0 3px rgba(255,255,255,0.12)",
    },
  };

  // Each accent ships paired tones for light/dark mode so contrast holds.
  // `mid` = primary fill, `hi` = hover, `lo` = pressed, `soft` = subtle bg.
  const ACCENTS = {
    indigo:  { light: { mid:"#2b5fd0", hi:"#3a6cdb", lo:"#1f4baa", soft:"#e3ebf8", onMid:"#ffffff" },
               dark:  { mid:"#5b8df2", hi:"#7aa3f7", lo:"#3d72de", soft:"#1c2640", onMid:"#0a0f1c" } },
    plum:    { light: { mid:"#7a3fb1", hi:"#8a4dc1", lo:"#612f8d", soft:"#efe5f6", onMid:"#ffffff" },
               dark:  { mid:"#b07cd9", hi:"#c193e2", lo:"#8a5cba", soft:"#2a1e36", onMid:"#150c1c" } },
    rust:    { light: { mid:"#a8462e", hi:"#bb5439", lo:"#883820", soft:"#f6e2da", onMid:"#ffffff" },
               dark:  { mid:"#d9784c", hi:"#e58c63", lo:"#b25e3a", soft:"#3a201a", onMid:"#1a0f0a" } },
    forest:  { light: { mid:"#2a7a4a", hi:"#338857", lo:"#1f5e38", soft:"#dfeee5", onMid:"#ffffff" },
               dark:  { mid:"#5db679", hi:"#7ac491", lo:"#3f9a60", soft:"#1a2e22", onMid:"#0a1810" } },
    teal:    { light: { mid:"#2b6f7c", hi:"#357f8c", lo:"#1f5660", soft:"#dceaed", onMid:"#ffffff" },
               dark:  { mid:"#5ab0bc", hi:"#7bc1cb", lo:"#3e8e99", soft:"#1a2c30", onMid:"#0a1518" } },
    amber:   { light: { mid:"#9a6800", hi:"#ad7400", lo:"#7d5200", soft:"#f7ead0", onMid:"#ffffff" },
               dark:  { mid:"#d6a455", hi:"#e3b66c", lo:"#b78a3e", soft:"#322713", onMid:"#1a1408" } },
    gray:    { light: { mid:"#4a463e", hi:"#5b554a", lo:"#332f29", soft:"#e6e3d8", onMid:"#ffffff" },
               dark:  { mid:"#a59c89", hi:"#b9b09c", lo:"#878070", soft:"#2a2820", onMid:"#0f0e0a" } },
    crimson: { light: { mid:"#a31a35", hi:"#b62442", lo:"#82132a", soft:"#f6dde2", onMid:"#ffffff" },
               dark:  { mid:"#e26679", hi:"#ea8094", lo:"#bf4d5e", soft:"#33191e", onMid:"#1a0a0d" } },
  };

  const DENSITY = {
    compact:     { row: 24, pad: 6,  gap: 4,  font: 11.5, sideRow: 24 },
    default:     { row: 32, pad: 8,  gap: 6,  font: 12.5, sideRow: 28 },
    comfortable: { row: 40, pad: 12, gap: 10, font: 13.5, sideRow: 34 },
  };

  function applyTheme({ mode, accent, density }) {
    const root = document.documentElement;
    const m = MODES[mode] || MODES.light;
    const a = (ACCENTS[accent] || ACCENTS.indigo)[mode] || ACCENTS.indigo.light;
    const s = STATUS[mode] || STATUS.light;
    const d = DENSITY[density] || DENSITY.default;

    Object.entries(m).forEach(([k, v]) => root.style.setProperty(`--lbb-${k}`, v));
    Object.entries(a).forEach(([k, v]) => root.style.setProperty(`--lbb-accent-${k}`, v));
    Object.entries(s).forEach(([k, v]) => {
      root.style.setProperty(`--lbb-${k}-fg`, v.fg);
      root.style.setProperty(`--lbb-${k}-bg`, v.bg);
      root.style.setProperty(`--lbb-${k}-bar`, v.bar);
    });
    Object.entries(d).forEach(([k, v]) => root.style.setProperty(`--lbb-d-${k}`, typeof v === "number" ? `${v}px` : v));

    root.setAttribute("data-mode", mode);
    root.setAttribute("data-accent", accent);
    root.setAttribute("data-density", density);
    root.style.colorScheme = mode;
  }

  return { MODES, ACCENTS, STATUS, DENSITY, applyTheme };
})();
