// lbb-ui.jsx
// Primitive UI components. Pure, themed via CSS variables set by lbb-tokens.js.

const Icon = window.LBB_Icon;

// ────────────────────────────────────────────────────────────────────
// Pill — outlined status indicator. tone: ok / warn / bad / info / mute
// ────────────────────────────────────────────────────────────────────
function Pill({ tone = "mute", children, soft = false, dot = false, style }) {
  const bg   = soft ? `var(--lbb-${tone}-bg)` : "transparent";
  const fg   = `var(--lbb-${tone}-fg)`;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "1px 7px", borderRadius: 999,
      fontSize: 10.5, fontWeight: 600, letterSpacing: "0.02em",
      color: fg, background: bg,
      border: `1px solid ${soft ? "transparent" : fg}`,
      whiteSpace: "nowrap", lineHeight: 1.45,
      ...style,
    }}>
      {dot && <span style={{ width: 6, height: 6, borderRadius: "50%", background: fg }} />}
      {children}
    </span>
  );
}

// ────────────────────────────────────────────────────────────────────
// Chip — filter / tag. variant: filter (default) / segmented
// ────────────────────────────────────────────────────────────────────
function Chip({ active = false, onClick, children, count, icon, style, size = "md" }) {
  const padding = size === "sm" ? "2px 8px" : "3px 10px";
  const font    = size === "sm" ? 11 : 11.5;
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        padding, fontSize: font, fontFamily: "inherit",
        borderRadius: 999, cursor: "pointer",
        border: `1px solid ${active ? "var(--lbb-accent-mid)" : "var(--lbb-border2)"}`,
        background: active ? "var(--lbb-accent-soft)" : "var(--lbb-surface)",
        color: active ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
        fontWeight: active ? 600 : 500, lineHeight: 1.5,
        ...style,
      }}
    >
      {icon && <Icon name={icon} size={12} />}
      {children}
      {count !== undefined && (
        <span style={{ fontSize: 10, opacity: 0.6, fontWeight: 500 }}>{count.toLocaleString()}</span>
      )}
    </button>
  );
}

// ────────────────────────────────────────────────────────────────────
// Button — primary / secondary / ghost / danger
// ────────────────────────────────────────────────────────────────────
function Button({
  variant = "secondary", size = "md", icon, iconRight, onClick,
  children, disabled, block, style, ...rest
}) {
  const heights = { sm: 24, md: 30, lg: 36 };
  const padX    = { sm: 8,  md: 12, lg: 14 };
  const fonts   = { sm: 11.5, md: 12.5, lg: 13.5 };

  const colors = {
    primary:   { bg: "var(--lbb-accent-mid)", fg: "var(--lbb-accent-onMid)",
                 border: "var(--lbb-accent-mid)", hover: "var(--lbb-accent-hi)" },
    secondary: { bg: "var(--lbb-surface)", fg: "var(--lbb-fg)",
                 border: "var(--lbb-border2)", hover: "var(--lbb-surface2)" },
    ghost:     { bg: "transparent", fg: "var(--lbb-fg2)",
                 border: "transparent", hover: "var(--lbb-surface2)" },
    danger:    { bg: "var(--lbb-surface)", fg: "var(--lbb-bad-fg)",
                 border: "var(--lbb-bad-fg)", hover: "var(--lbb-bad-bg)" },
  };
  const c = colors[variant] || colors.secondary;

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6,
        height: heights[size], padding: `0 ${padX[size]}px`,
        fontSize: fonts[size], fontWeight: 600, fontFamily: "inherit",
        borderRadius: 6, cursor: disabled ? "not-allowed" : "pointer",
        background: c.bg, color: c.fg,
        border: `1px solid ${c.border}`,
        opacity: disabled ? 0.5 : 1,
        boxShadow: variant === "primary" ? "0 1px 0 rgba(0,0,0,0.05)" : "none",
        whiteSpace: "nowrap", width: block ? "100%" : "auto",
        transition: "background 120ms ease, border-color 120ms ease",
        ...style,
      }}
      onMouseEnter={e => !disabled && (e.currentTarget.style.background = c.hover)}
      onMouseLeave={e => !disabled && (e.currentTarget.style.background = c.bg)}
      {...rest}
    >
      {icon && <Icon name={icon} size={size === "sm" ? 12 : 14} />}
      {children}
      {iconRight && <Icon name={iconRight} size={size === "sm" ? 12 : 14} />}
    </button>
  );
}

// ────────────────────────────────────────────────────────────────────
// IconButton — square, icon-only
// ────────────────────────────────────────────────────────────────────
function IconButton({ icon, size = 28, onClick, title, active, style }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      style={{
        width: size, height: size, padding: 0,
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        borderRadius: 6, cursor: "pointer", fontFamily: "inherit",
        background: active ? "var(--lbb-surface2)" : "transparent",
        color: active ? "var(--lbb-fg)" : "var(--lbb-fg2)",
        border: "1px solid transparent",
        ...style,
      }}
      onMouseEnter={e => (e.currentTarget.style.background = "var(--lbb-surface2)")}
      onMouseLeave={e => (e.currentTarget.style.background = active ? "var(--lbb-surface2)" : "transparent")}
    >
      <Icon name={icon} size={Math.round(size * 0.55)} />
    </button>
  );
}

// ────────────────────────────────────────────────────────────────────
// Input — text field
// ────────────────────────────────────────────────────────────────────
function Input({ icon, placeholder, value, onChange, size = "md", width, style }) {
  const heights = { sm: 24, md: 30, lg: 36 };
  const fonts   = { sm: 11.5, md: 12.5, lg: 13.5 };
  return (
    <div style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      height: heights[size], padding: "0 10px",
      background: "var(--lbb-surface)", borderRadius: 6,
      border: "1px solid var(--lbb-border2)",
      width: width || "auto",
      ...style,
    }}>
      {icon && <Icon name={icon} size={13} style={{ color: "var(--lbb-fg3)" }} />}
      <input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        style={{
          flex: 1, height: "100%", border: "none", outline: "none",
          background: "transparent", color: "var(--lbb-fg)",
          fontSize: fonts[size], fontFamily: "inherit", minWidth: 0,
        }}
      />
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Kbd — keyboard shortcut hint
// ────────────────────────────────────────────────────────────────────
function Kbd({ children }) {
  return (
    <kbd style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      minWidth: 18, height: 18, padding: "0 4px",
      fontSize: 10.5, fontFamily: "inherit", fontWeight: 500,
      background: "var(--lbb-surface2)", color: "var(--lbb-fg2)",
      border: "1px solid var(--lbb-border)",
      borderRadius: 3, lineHeight: 1,
    }}>{children}</kbd>
  );
}

// ────────────────────────────────────────────────────────────────────
// Card — surface container with optional title
// ────────────────────────────────────────────────────────────────────
function Card({ title, subtitle, action, children, pad = 16, style }) {
  return (
    <div style={{
      background: "var(--lbb-surface)",
      border: "1px solid var(--lbb-border)",
      borderRadius: 8,
      overflow: "hidden",
      boxShadow: "var(--lbb-shadow)",
      ...style,
    }}>
      {(title || action) && (
        <div style={{
          display: "flex", alignItems: "center", gap: 12,
          padding: `${pad - 4}px ${pad}px`,
          borderBottom: "1px solid var(--lbb-border)",
        }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            {title && <div style={{ fontSize: 12.5, fontWeight: 600, letterSpacing: 0.01 }}>{title}</div>}
            {subtitle && <div style={{ fontSize: 11, color: "var(--lbb-fg3)", marginTop: 2 }}>{subtitle}</div>}
          </div>
          {action}
        </div>
      )}
      <div style={{ padding: title ? pad : pad }}>{children}</div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Toolbar — horizontal action strip
// ────────────────────────────────────────────────────────────────────
function Toolbar({ children, style, bordered = true, pad = "10px 14px" }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8, padding: pad,
      borderBottom: bordered ? "1px solid var(--lbb-border)" : "none",
      flexWrap: "wrap",
      ...style,
    }}>{children}</div>
  );
}

// ────────────────────────────────────────────────────────────────────
// TableShell — wraps thead+tbody. Use with TableRow + TableCell.
// rows respect density via row-height CSS var.
// ────────────────────────────────────────────────────────────────────
function TableShell({ children, stickyHeader = true, style }) {
  return (
    <table style={{
      width: "100%",
      borderCollapse: "separate",
      borderSpacing: 0,
      fontSize: "var(--lbb-d-font)",
      lineHeight: 1.4,
      tableLayout: "fixed",
      ...style,
    }} className={stickyHeader ? "lbb-sticky" : ""}>{children}</table>
  );
}

function TH({ children, style, width, align = "left" }) {
  return (
    <th style={{
      textAlign: align,
      padding: "8px var(--lbb-d-pad) 8px var(--lbb-d-pad)",
      fontWeight: 600, fontSize: 10.5, letterSpacing: 0.04,
      textTransform: "uppercase",
      color: "var(--lbb-fg3)",
      background: "var(--lbb-surface2)",
      borderBottom: "1px solid var(--lbb-border2)",
      width,
      whiteSpace: "nowrap",
      ...style,
    }}>{children}</th>
  );
}

function TR({ children, edge, selected, onClick, style }) {
  // edge can be "ok"|"warn"|"bad"|"info"|"mute" — paints 3px left border + subtle row wash
  const wash = edge ? `var(--lbb-${edge}-bg)` : "transparent";
  const bar  = edge ? `var(--lbb-${edge}-bar)` : "transparent";
  return (
    <tr
      onClick={onClick}
      data-selected={selected ? "true" : undefined}
      style={{
        background: selected ? "var(--lbb-accent-soft)" : wash,
        cursor: onClick ? "pointer" : "default",
        ...style,
      }}
      className={edge ? `lbb-tr-edge` : ""}
    >
      <td style={{
        width: 3, padding: 0,
        background: bar,
        borderBottom: "1px solid var(--lbb-border)",
      }}></td>
      {children}
    </tr>
  );
}

function TD({ children, mono = false, dim = false, align = "left", style, colSpan }) {
  return (
    <td colSpan={colSpan} style={{
      textAlign: align,
      padding: "calc(var(--lbb-d-pad) - 2px) var(--lbb-d-pad)",
      borderBottom: "1px solid var(--lbb-border)",
      color: dim ? "var(--lbb-fg3)" : "var(--lbb-fg2)",
      fontFamily: mono ? "var(--lbb-mono)" : "inherit",
      fontSize: mono ? "calc(var(--lbb-d-font) - 0.5px)" : "var(--lbb-d-font)",
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis",
      verticalAlign: "middle",
      ...style,
    }}>{children}</td>
  );
}

// Group-header row (collapsible)
function GroupRow({ label, count, expanded = true, onToggle, colSpan = 99 }) {
  return (
    <tr>
      <td style={{ width: 3, padding: 0, background: "transparent" }}></td>
      <td colSpan={colSpan} onClick={onToggle} style={{
        padding: "5px var(--lbb-d-pad)",
        background: "var(--lbb-surface2)",
        fontSize: 11, fontWeight: 600, letterSpacing: 0.04,
        textTransform: "uppercase",
        color: "var(--lbb-fg2)",
        cursor: onToggle ? "pointer" : "default",
        borderBottom: "1px solid var(--lbb-border)",
        borderTop: "1px solid var(--lbb-border)",
      }}>
        <Icon name={expanded ? "chevDown" : "chevRight"} size={11} style={{ marginRight: 4 }} />
        {label}
        {count !== undefined && (
          <span style={{ marginLeft: 8, fontSize: 10.5, color: "var(--lbb-fg3)", fontWeight: 500 }}>{count.toLocaleString()}</span>
        )}
      </td>
    </tr>
  );
}

// Stat — big number + label
function Stat({ value, label, delta, tone }) {
  return (
    <div>
      <div style={{ fontSize: 22, fontWeight: 700, fontVariantNumeric: "tabular-nums", letterSpacing: -0.01 }}>{value}</div>
      <div style={{ fontSize: 11.5, color: "var(--lbb-fg3)", marginTop: 2, display: "flex", alignItems: "center", gap: 6 }}>
        {label}
        {delta && <Pill tone={tone || "ok"} soft style={{ fontSize: 9.5, padding: "0 5px" }}>{delta}</Pill>}
      </div>
    </div>
  );
}

// Section header (within a screen)
function SectionHead({ title, subtitle, action, style }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginBottom: 12, ...style }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <h3 style={{ margin: 0, fontSize: 13, fontWeight: 700, letterSpacing: 0.04, textTransform: "uppercase", color: "var(--lbb-fg2)" }}>{title}</h3>
        {subtitle && <div style={{ marginTop: 4, fontSize: 12, color: "var(--lbb-fg3)" }}>{subtitle}</div>}
      </div>
      {action}
    </div>
  );
}

// Empty / placeholder banner
function Banner({ tone = "info", icon = "info", title, children, action, style }) {
  return (
    <div style={{
      display: "flex", alignItems: "flex-start", gap: 10,
      padding: "10px 12px", borderRadius: 6,
      background: `var(--lbb-${tone}-bg)`, color: `var(--lbb-${tone}-fg)`,
      border: `1px solid var(--lbb-${tone}-bar)`,
      fontSize: 12,
      ...style,
    }}>
      <Icon name={icon} size={14} style={{ marginTop: 2, flex: "0 0 auto" }} />
      <div style={{ flex: 1 }}>
        {title && <div style={{ fontWeight: 600, marginBottom: 2, color: `var(--lbb-${tone}-fg)` }}>{title}</div>}
        <div style={{ color: "var(--lbb-fg2)" }}>{children}</div>
      </div>
      {action}
    </div>
  );
}

Object.assign(window, { Pill, Chip, Button, IconButton, Input, Kbd, Card, Toolbar, TableShell, TH, TR, TD, GroupRow, Stat, SectionHead, Banner });
