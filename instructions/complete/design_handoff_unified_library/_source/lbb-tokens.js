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
      mute:  { fg: "#7d838d", bg: "#23262b", bar: "#646b75" },
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
      bg:        "#141619",   // app body — cool slate
      surface:   "#1b1e23",   // cards, sidebar panels
      surface2:  "#24282f",   // table header, subtle wells
      surface3:  "#2f343c",   // hover surface
      border:    "#33373f",   // hairlines
      border2:   "#474d57",   // stronger borders
      fg:        "#eef0f4",   // primary text
      fg2:       "#aab1bd",   // secondary text
      fg3:       "#6c7480",   // tertiary / placeholder
      shadow:    "0 1px 0 rgba(255,255,255,0.04) inset, 0 2px 8px rgba(0,0,0,0.45)",
      shadowLg:  "0 1px 0 rgba(255,255,255,0.05) inset, 0 8px 24px rgba(0,0,0,0.55)",
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
               dark:  { mid:"#9aa1ad", hi:"#b0b6c0", lo:"#7f8691", soft:"#262a31", onMid:"#0e1013" } },
    crimson: { light: { mid:"#a31a35", hi:"#b62442", lo:"#82132a", soft:"#f6dde2", onMid:"#ffffff" },
               dark:  { mid:"#e26679", hi:"#ea8094", lo:"#bf4d5e", soft:"#33191e", onMid:"#1a0a0d" } },
  };

  // ── Frame palettes ──────────────────────────────────────────────
  // Tint the *surfaces themselves* (gutter + cards), not just the accent.
  // Each palette overrides the mode's bg/surface/border tokens; framed
  // cards (which read --lbb-surface) pick up the tint automatically.
  // `slate` in dark = the lifted soft palette; in light it is null
  // (keeps the shipped warm-cream default).
  const PALETTES = {
    dark: {
      slate:    { bg:"#1b1f26", surface:"#252a33", surface2:"#2f3540", surface3:"#3a414d", border:"#3b4250", border2:"#515a6a", fg:"#eef1f6", fg2:"#b2bac8", fg3:"#7c8595" },
      blue:     { bg:"#131c2e", surface:"#1e2a45", surface2:"#273457", surface3:"#324069", border:"#37466c", border2:"#4c5c88", fg:"#eef3fc", fg2:"#aebcd6", fg3:"#7384a2" },
      purple:   { bg:"#1d1832", surface:"#2a2249", surface2:"#342b5a", surface3:"#40356c", border:"#463b70", border2:"#5b4e89", fg:"#f2ecfc", fg2:"#beb2d9", fg3:"#867aa2" },
      green:    { bg:"#13201a", surface:"#1d2d26", surface2:"#263a31", surface3:"#30473c", border:"#354a40", border2:"#486455", fg:"#ecf4ef", fg2:"#aec4b7", fg3:"#74897e" },
      graphite: { bg:"#17181b", surface:"#202227", surface2:"#2a2d33", surface3:"#34383f", border:"#383c44", border2:"#4d535d", fg:"#eef0f4", fg2:"#aab1bd", fg3:"#6c7480" },
    },
    // Light palettes mirror the dark hues 1:1, tuned to NOT read washed-out:
    //  · the gutter (bg) carries a real tint — cards visibly float above it
    //  · cards (surface) are the lightest element, faintly tinted (never stark #fff)
    //  · surface2/3 step down for wells + hover; borders are visible hairlines
    //  · fg/fg2/fg3 carry a hint of the palette hue so text isn't pure neutral
    light: {
      slate:    { bg:"#e3e7ef", surface:"#f8f9fc", surface2:"#e7ebf3", surface3:"#dae0ec", border:"#cdd5e2", border2:"#aab5c8", fg:"#191d26", fg2:"#48515f", fg3:"#76808f" },
      blue:     { bg:"#dde7f6", surface:"#f6f9fe", surface2:"#e3edfa", surface3:"#d2e1f4", border:"#c2d4ec", border2:"#9bb9e0", fg:"#13203a", fg2:"#3f547a", fg3:"#6f83a6" },
      purple:   { bg:"#eae3f6", surface:"#faf8fe", surface2:"#ebe2f7", surface3:"#ddd0f1", border:"#d4c6ec", border2:"#b9a2df", fg:"#1f1336", fg2:"#534277", fg3:"#8579a6" },
      green:    { bg:"#deeae1", surface:"#f5faf7", surface2:"#e2efe8", surface3:"#d1e6da", border:"#c5ddcf", border2:"#9fc7b1", fg:"#12281d", fg2:"#3d5d4c", fg3:"#739283" },
      graphite: { bg:"#e6e6eb", surface:"#fbfbfd", surface2:"#ececf1", surface3:"#e0e0e6", border:"#d6d6dd", border2:"#b7b7c1", fg:"#18191d", fg2:"#4f515a", fg3:"#81838c" },
    },
  };

  const DENSITY = {
    compact:     { row: 24, pad: 6,  gap: 4,  font: 11.5, sideRow: 24 },
    default:     { row: 32, pad: 8,  gap: 6,  font: 12.5, sideRow: 28 },
    comfortable: { row: 40, pad: 12, gap: 10, font: 13.5, sideRow: 34 },
  };

  function applyTheme({ mode, accent, density, palette }) {
    const root = document.documentElement;
    const base = MODES[mode] || MODES.light;
    // Layer the chosen frame palette over the mode's surface tokens.
    const pal = palette && PALETTES[mode] ? PALETTES[mode][palette] : null;
    const m = pal ? { ...base, ...pal } : base;
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
    if (palette) root.setAttribute("data-palette", palette);
    root.style.colorScheme = mode;
  }

  return { MODES, ACCENTS, STATUS, DENSITY, PALETTES, applyTheme };
})();
