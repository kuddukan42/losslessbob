// Design token engine for LosslessBob.
// Ports _source/lbb-tokens.js; call applyTheme() once before React mounts.

export type Mode = 'light' | 'dark' | 'system';
// Mode after resolving 'system' to a concrete preference — used to index
// MODES/PALETTES/ACCENT_PALETTES/STATUS, which only ever ship light+dark.
type ConcreteMode = 'light' | 'dark';
export type Accent = 'indigo' | 'plum' | 'rust' | 'forest' | 'teal' | 'amber' | 'gray' | 'crimson';
export type Density = 'compact' | 'default' | 'comfortable';
export type Font = 'inter' | 'ibm-plex' | 'source';
export type FontSize = 12 | 13 | 14;
export type Palette = 'slate' | 'blue' | 'purple' | 'green' | 'graphite';
export type CardStyle = 'framed' | 'flat';

export interface ThemeOptions {
  mode: Mode;
  accent: Accent;
  density: Density;
  /** Frame theme — tints surfaces/borders/text over the mode. Unset = mode default. */
  palette?: Palette;
  /** framed = elevated cards on a gutter; flat = flush hairline separation (default). */
  cardStyle?: CardStyle;
  font?: Font;
  fontSize?: FontSize;
  customTokens?: Record<string, string>;
}

export const ACCENTS: Accent[] = ['indigo', 'plum', 'rust', 'forest', 'teal', 'amber', 'gray', 'crimson'];
export const DENSITIES: Density[] = ['compact', 'default', 'comfortable'];
export const FONTS: Font[] = ['inter', 'ibm-plex', 'source'];
export const FONT_SIZES: FontSize[] = [12, 13, 14];
export const PALETTE_OPTIONS: Palette[] = ['slate', 'blue', 'purple', 'green', 'graphite'];
export const CARD_STYLES: CardStyle[] = ['framed', 'flat'];

const FONT_STACKS: Record<Font, string> = {
  'inter':    '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
  'ibm-plex': '"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif',
  'source':   '"Source Sans 3", "Source Sans Pro", "Trebuchet MS", sans-serif',
};

export const DEFAULT_THEME: ThemeOptions = {
  mode: 'light', accent: 'indigo', density: 'default', cardStyle: 'flat',
  font: 'inter', fontSize: 13, customTokens: {},
};
const STORAGE_KEY = 'lbb-theme';

interface StatusTone { fg: string; bg: string; bar: string; }
interface AccentTone { mid: string; hi: string; lo: string; soft: string; onMid: string; }
interface ModePalette {
  bg: string; surface: string; surface2: string; surface3: string;
  border: string; border2: string;
  fg: string; fg2: string; fg3: string;
  shadow: string; shadowLg: string; focusRing: string;
}
interface FramePaletteTone {
  bg: string; surface: string; surface2: string; surface3: string;
  border: string; border2: string;
  fg: string; fg2: string; fg3: string;
}
interface DensityScale { row: number; pad: number; gap: number; font: number; sideRow: number; }

const STATUS: Record<ConcreteMode, Record<string, StatusTone>> = {
  light: {
    ok:   { fg: '#1f7a3e', bg: '#e7f2e2', bar: '#39a360' },
    warn: { fg: '#9a6800', bg: '#f8eed3', bar: '#cc9f3d' },
    bad:  { fg: '#b03f30', bg: '#fbe6df', bar: '#d8604f' },
    info: { fg: '#1f5b8f', bg: '#e2ecf6', bar: '#4c89c4' },
    mute: { fg: '#8a8473', bg: '#ecebe4', bar: '#a8a293' },
  },
  dark: {
    ok:   { fg: '#5db679', bg: '#1f2d22', bar: '#39a360' },
    warn: { fg: '#d4a35a', bg: '#2e2719', bar: '#b58a3a' },
    bad:  { fg: '#e08070', bg: '#321f1d', bar: '#c25a48' },
    info: { fg: '#7eb4e8', bg: '#1b2733', bar: '#5891cf' },
    mute: { fg: '#888888', bg: '#272727', bar: '#6a6a6a' },
  },
};

const MODES: Record<ConcreteMode, ModePalette> = {
  light: {
    bg:        '#faf8f3',
    surface:   '#ffffff',
    surface2:  '#f1efe7',
    surface3:  '#e7e4d8',
    border:    '#e2dfd2',
    border2:   '#c8c3b1',
    fg:        '#1c1a17',
    fg2:       '#5b554a',
    fg3:       '#8e8676',
    shadow:    '0 1px 0 rgba(0,0,0,0.02), 0 2px 6px rgba(40,30,15,0.06)',
    shadowLg:  '0 4px 16px rgba(40,30,15,0.08), 0 1px 0 rgba(255,255,255,0.6) inset',
    focusRing: '0 0 0 3px rgba(0,0,0,0.08)',
  },
  dark: {
    bg:        '#1a1a1a',
    surface:   '#222222',
    surface2:  '#2b2b2b',
    surface3:  '#353535',
    border:    '#383838',
    border2:   '#4d4d4d',
    fg:        '#f0f0f0',
    fg2:       '#aaaaaa',
    fg3:       '#6e6e6e',
    shadow:    '0 1px 0 rgba(255,255,255,0.04) inset, 0 2px 8px rgba(0,0,0,0.4)',
    shadowLg:  '0 1px 0 rgba(255,255,255,0.05) inset, 0 8px 24px rgba(0,0,0,0.5)',
    focusRing: '0 0 0 3px rgba(255,255,255,0.12)',
  },
};

const ACCENT_PALETTES: Record<Accent, Record<ConcreteMode, AccentTone>> = {
  indigo:  { light: { mid: '#2b5fd0', hi: '#3a6cdb', lo: '#1f4baa', soft: '#e3ebf8', onMid: '#ffffff' },
             dark:  { mid: '#5b8df2', hi: '#7aa3f7', lo: '#3d72de', soft: '#1c2640', onMid: '#0a0f1c' } },
  plum:    { light: { mid: '#7a3fb1', hi: '#8a4dc1', lo: '#612f8d', soft: '#efe5f6', onMid: '#ffffff' },
             dark:  { mid: '#b07cd9', hi: '#c193e2', lo: '#8a5cba', soft: '#2a1e36', onMid: '#150c1c' } },
  rust:    { light: { mid: '#a8462e', hi: '#bb5439', lo: '#883820', soft: '#f6e2da', onMid: '#ffffff' },
             dark:  { mid: '#d9784c', hi: '#e58c63', lo: '#b25e3a', soft: '#3a201a', onMid: '#1a0f0a' } },
  forest:  { light: { mid: '#2a7a4a', hi: '#338857', lo: '#1f5e38', soft: '#dfeee5', onMid: '#ffffff' },
             dark:  { mid: '#5db679', hi: '#7ac491', lo: '#3f9a60', soft: '#1a2e22', onMid: '#0a1810' } },
  teal:    { light: { mid: '#2b6f7c', hi: '#357f8c', lo: '#1f5660', soft: '#dceaed', onMid: '#ffffff' },
             dark:  { mid: '#5ab0bc', hi: '#7bc1cb', lo: '#3e8e99', soft: '#1a2c30', onMid: '#0a1518' } },
  amber:   { light: { mid: '#9a6800', hi: '#ad7400', lo: '#7d5200', soft: '#f7ead0', onMid: '#ffffff' },
             dark:  { mid: '#d6a455', hi: '#e3b66c', lo: '#b78a3e', soft: '#322713', onMid: '#1a1408' } },
  gray:    { light: { mid: '#4a463e', hi: '#5b554a', lo: '#332f29', soft: '#e6e3d8', onMid: '#ffffff' },
             dark:  { mid: '#a59c89', hi: '#b9b09c', lo: '#878070', soft: '#2a2820', onMid: '#0f0e0a' } },
  crimson: { light: { mid: '#a31a35', hi: '#b62442', lo: '#82132a', soft: '#f6dde2', onMid: '#ffffff' },
             dark:  { mid: '#e26679', hi: '#ea8094', lo: '#bf4d5e', soft: '#33191e', onMid: '#1a0a0d' } },
};

// Frame theme — tints the surfaces themselves (gutter + cards + borders +
// text), layered on top of the chosen mode. Distinct from accent, which only
// colors interactive highlights. Light palettes mirror the dark hues 1:1.
export const PALETTES: Record<ConcreteMode, Record<Palette, FramePaletteTone>> = {
  dark: {
    slate:    { bg: '#1b1f26', surface: '#252a33', surface2: '#2f3540', surface3: '#3a414d', border: '#3b4250', border2: '#515a6a', fg: '#eef1f6', fg2: '#b2bac8', fg3: '#7c8595' },
    blue:     { bg: '#131c2e', surface: '#1e2a45', surface2: '#273457', surface3: '#324069', border: '#37466c', border2: '#4c5c88', fg: '#eef3fc', fg2: '#aebcd6', fg3: '#7384a2' },
    purple:   { bg: '#1d1832', surface: '#2a2249', surface2: '#342b5a', surface3: '#40356c', border: '#463b70', border2: '#5b4e89', fg: '#f2ecfc', fg2: '#beb2d9', fg3: '#867aa2' },
    green:    { bg: '#13201a', surface: '#1d2d26', surface2: '#263a31', surface3: '#30473c', border: '#354a40', border2: '#486455', fg: '#ecf4ef', fg2: '#aec4b7', fg3: '#74897e' },
    graphite: { bg: '#17181b', surface: '#202227', surface2: '#2a2d33', surface3: '#34383f', border: '#383c44', border2: '#4d535d', fg: '#eef0f4', fg2: '#aab1bd', fg3: '#6c7480' },
  },
  light: {
    slate:    { bg: '#e3e7ef', surface: '#f8f9fc', surface2: '#e7ebf3', surface3: '#dae0ec', border: '#cdd5e2', border2: '#aab5c8', fg: '#191d26', fg2: '#48515f', fg3: '#76808f' },
    blue:     { bg: '#dde7f6', surface: '#f6f9fe', surface2: '#e3edfa', surface3: '#d2e1f4', border: '#c2d4ec', border2: '#9bb9e0', fg: '#13203a', fg2: '#3f547a', fg3: '#6f83a6' },
    purple:   { bg: '#eae3f6', surface: '#faf8fe', surface2: '#ebe2f7', surface3: '#ddd0f1', border: '#d4c6ec', border2: '#b9a2df', fg: '#1f1336', fg2: '#534277', fg3: '#8579a6' },
    green:    { bg: '#deeae1', surface: '#f5faf7', surface2: '#e2efe8', surface3: '#d1e6da', border: '#c5ddcf', border2: '#9fc7b1', fg: '#12281d', fg2: '#3d5d4c', fg3: '#739283' },
    graphite: { bg: '#e6e6eb', surface: '#fbfbfd', surface2: '#ececf1', surface3: '#e0e0e6', border: '#d6d6dd', border2: '#b7b7c1', fg: '#18191d', fg2: '#4f515a', fg3: '#81838c' },
  },
};

const DENSITY: Record<Density, DensityScale> = {
  compact:     { row: 24, pad: 6,  gap: 4,  font: 11.5, sideRow: 24 },
  default:     { row: 32, pad: 8,  gap: 6,  font: 12.5, sideRow: 28 },
  comfortable: { row: 40, pad: 12, gap: 10, font: 13.5, sideRow: 34 },
};

// Unified Library type scale (spec §2). Nine roles mapping a literal pixel size
// (at the default fontSize:13 base) to a name; emitted as --t-<role> by
// applyTheme, scaled by the active fontSize. See §2 "Role → element binding".
const TYPE_ROLES: Record<string, number> = {
  'display':  22,    // panel headline (show date)
  'title':    15,    // venue, family-card primary
  'strong':   13,    // card titles, family name, emphasis
  'body':     12.5,  // default reading size — rows & descriptions
  'meta':     11.5,  // secondary meta · captions · city line
  'label':    10.5,  // zone label / eyebrow (uppercase)
  'micro':    10,    // pill text · counts · badges
  'mono':     11.5,  // LB#, dates (mono)
  'mono-sm':  10.5,  // timestamps · tree glyphs (mono)
};

// Weight ramp (spec §2). Four weights replacing the off-ramp 650/800.
const WEIGHT_RAMP: Record<string, number> = {
  'reg':  400,  // body, un-emphasized rows
  'med':  500,  // controls, inactive tabs, meta emphasis
  'semi': 600,  // titles, active controls, emphasized data (was 600·650)
  'bold': 700,  // display, eyebrows, stat values, badges (was 700·800)
};

export function applyTheme({ mode, accent, density, font, fontSize, customTokens, palette, cardStyle }: ThemeOptions): void {
  const root = document.documentElement;
  // Resolve 'system' to a concrete light/dark before indexing any table below.
  const resolved: ConcreteMode = mode === 'system' ? getSystemMode() : mode;
  const base = MODES[resolved] ?? MODES.light;
  const pal = palette ? PALETTES[resolved]?.[palette] : undefined;
  const m = pal ? { ...base, ...pal } : base;
  const a = (ACCENT_PALETTES[accent] ?? ACCENT_PALETTES.indigo)[resolved];
  const s = STATUS[resolved] ?? STATUS.light;
  const d = DENSITY[density] ?? DENSITY.default;

  (Object.entries(m) as [string, string][]).forEach(([k, v]) => root.style.setProperty(`--lbb-${k}`, v));
  (Object.entries(a) as [string, string][]).forEach(([k, v]) => root.style.setProperty(`--lbb-accent-${k}`, v));
  Object.entries(s).forEach(([tone, v]) => {
    root.style.setProperty(`--lbb-${tone}-fg`,  v.fg);
    root.style.setProperty(`--lbb-${tone}-bg`,  v.bg);
    root.style.setProperty(`--lbb-${tone}-bar`, v.bar);
  });
  (Object.entries(d) as [string, number][]).forEach(([k, v]) =>
    root.style.setProperty(`--lbb-d-${k}`, `${v}px`)
  );

  root.style.setProperty('--lbb-font', FONT_STACKS[font ?? 'inter'] ?? FONT_STACKS.inter);
  root.style.setProperty('--lbb-font-size', `${fontSize ?? 13}px`);
  const fsScale = (fontSize ?? 13) / 13;
  for (const v of [8.5, 9, 9.5, 10, 10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14, 15, 16, 17, 18, 20, 22, 28, 32]) {
    root.style.setProperty(`--lbb-fs-${String(v).replace('.', '-')}`, `${(v * fsScale).toFixed(2)}px`);
  }

  // Type-scale roles for the Unified Library screen (spec §2). Each maps a
  // single pixel size + intended weight to a named role; sizes scale with the
  // user's base fontSize like --lbb-fs-* so the light/font-size settings still
  // apply. The --lbb-fs-* loop above stays — other screens reference it.
  for (const [role, px] of Object.entries(TYPE_ROLES)) {
    root.style.setProperty(`--t-${role}`, `${(px * fsScale).toFixed(2)}px`);
  }
  for (const [name, weight] of Object.entries(WEIGHT_RAMP)) {
    root.style.setProperty(`--w-${name}`, String(weight));
  }
  root.style.setProperty('--track-eyebrow', '0.09em');

  Object.entries(customTokens ?? {}).forEach(([k, v]) => root.style.setProperty(k, v));

  root.setAttribute('data-mode',    resolved);
  root.setAttribute('data-accent',  accent);
  root.setAttribute('data-density', density);
  if (palette) root.setAttribute('data-palette', palette);
  else root.removeAttribute('data-palette');
  if (cardStyle === 'framed') root.setAttribute('data-sep', 'framed');
  else root.removeAttribute('data-sep');
  root.style.colorScheme = resolved;
}

export function loadTheme(): ThemeOptions {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as Partial<ThemeOptions>;
      return {
        mode:         ((['light', 'dark', 'system'] as Mode[]).includes(parsed.mode as Mode) ? parsed.mode : DEFAULT_THEME.mode) as Mode,
        accent:       (ACCENT_PALETTES[parsed.accent as Accent]   ? parsed.accent  : DEFAULT_THEME.accent) as Accent,
        density:      (DENSITY[parsed.density as Density]         ? parsed.density : DEFAULT_THEME.density) as Density,
        palette:      (PALETTE_OPTIONS.includes(parsed.palette as Palette) ? parsed.palette : undefined) as Palette | undefined,
        cardStyle:    (parsed.cardStyle === 'framed' || parsed.cardStyle === 'flat' ? parsed.cardStyle : DEFAULT_THEME.cardStyle) as CardStyle,
        font:         (FONT_STACKS[parsed.font as Font]            ? parsed.font    : DEFAULT_THEME.font)   as Font,
        fontSize:     ([12, 13, 14].includes(parsed.fontSize as number) ? parsed.fontSize : DEFAULT_THEME.fontSize) as FontSize,
        customTokens: (parsed.customTokens && typeof parsed.customTokens === 'object' ? parsed.customTokens : {}) as Record<string, string>,
      };
    }
  } catch {
    // corrupt storage — fall back to default
  }
  return { ...DEFAULT_THEME, customTokens: {} };
}

export function saveTheme(opts: ThemeOptions): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(opts));
}

export function getSystemMode(): 'light' | 'dark' {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
