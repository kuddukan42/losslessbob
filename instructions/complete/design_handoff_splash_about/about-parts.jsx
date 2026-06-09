// about-parts.jsx — reusable blocks for the About dialogs (dark).

(() => {
  const { DoubleSquareFrame, Monogram, Wordmark, Tagline, LBB_w: w } = window;
  const Icon = window.LBB_Icon;
  const D = window.LBB_LAUNCH;
  const M = D.meta;

  // Small labelled metadata pill (mono).
  function Meta({ k, v, accent }) {
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontFamily: "var(--lbb-mono)", fontSize: 11 }}>
        <span style={{ color: "var(--lbb-fg3)" }}>{k}</span>
        <span style={{ color: accent ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)", fontWeight: 600 }}>{v}</span>
      </span>
    );
  }

  // ── Header ─────────────────────────────────────────────────────────────
  // Double-square-framed monogram + wordmark + version line. Echoes the splash.
  function AboutHeader({ onClose, compact }) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 18, padding: compact ? "20px 22px" : "24px 26px",
        borderBottom: "1px solid var(--lbb-border)" }}>
        <DoubleSquareFrame inset={6} radius={10} outer={0.55} inner={0.2} style={{ width: 66, height: 66 }}>
          <div style={{ height: 66, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Monogram size={42} radius={9} />
          </div>
        </DoubleSquareFrame>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Wordmark size={28} color="var(--lbb-fg)" />
          <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
            <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 11, fontWeight: 600,
              color: "var(--lbb-accent-mid)", padding: "2px 8px", borderRadius: 5,
              background: "var(--lbb-accent-soft)", border: "1px solid color-mix(in oklab, var(--lbb-accent-mid) 40%, transparent)" }}>
              v{M.version}
            </span>
            <Tagline size={9.5}>{M.tagline}</Tagline>
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} title="Close" style={{
            width: 30, height: 30, borderRadius: 7, cursor: "pointer", flex: "0 0 auto",
            background: "transparent", border: "1px solid var(--lbb-border)", color: "var(--lbb-fg2)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
          }}><Icon name="x" size={14} /></button>
        )}
      </div>
    );
  }

  function BlockTitle({ children, right }) {
    return (
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 11, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase",
          color: "var(--lbb-fg3)" }}>{children}</h3>
        <div style={{ flex: 1, height: 1, background: "var(--lbb-border)" }} />
        {right}
      </div>
    );
  }

  // ── About blurb + architecture ─────────────────────────────────────────
  function AboutBlurb() {
    return (
      <p style={{ margin: 0, fontSize: 13, lineHeight: 1.7, color: "var(--lbb-fg2)" }}>
        A local-first tool for cataloguing, verifying and renaming a lossless live-recording
        collection against the master <strong style={{ color: "var(--lbb-fg)" }}>LB</strong> checksum
        database. {M.checksums} checksums indexed across 4 mounts.
      </p>
    );
  }

  // ── Tech stack ─────────────────────────────────────────────────────────
  function StackRows({ rows }) {
    return (
      <div>
        {rows.map((r, i) => (
          <div key={i} style={{
            display: "grid", gridTemplateColumns: "120px 1fr auto", alignItems: "center", gap: 12,
            padding: "7px 0", borderTop: i ? "1px solid var(--lbb-border)" : "none",
          }}>
            <span style={{ fontSize: 11.5, color: "var(--lbb-fg3)" }}>{r[0]}</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 12.5,
              color: "var(--lbb-fg)", fontWeight: 500 }}>
              {r[3] && <span title="primary target" style={{ width: 6, height: 6, borderRadius: "50%",
                background: "var(--lbb-accent-mid)", boxShadow: "0 0 6px var(--lbb-accent-mid)", flex: "0 0 auto" }} />}
              {r[1]}
            </span>
            <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 11, color: "var(--lbb-fg2)",
              textAlign: "right", whiteSpace: "nowrap" }}>{r[2]}</span>
          </div>
        ))}
      </div>
    );
  }

  function TechStack({ showArch = true }) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        {D.stack.map((g) => (
          <div key={g.group}>
            <div style={{ fontFamily: "var(--lbb-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase",
              color: "var(--lbb-accent-mid)", marginBottom: 4, opacity: 0.85 }}>{g.group}</div>
            <StackRows rows={g.rows} />
          </div>
        ))}
        {showArch && (
          <div style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "11px 13px", borderRadius: 8,
            background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)" }}>
            <Icon name="info" size={14} style={{ color: "var(--lbb-fg3)", marginTop: 1, flex: "0 0 auto" }} />
            <p style={{ margin: 0, fontSize: 11.5, lineHeight: 1.6, color: "var(--lbb-fg2)" }}>{D.arch}</p>
          </div>
        )}
      </div>
    );
  }

  // ── Acknowledgements ───────────────────────────────────────────────────
  function AckCard({ a }) {
    const memory = a.tone === "memory";
    return (
      <div style={{
        display: "flex", gap: 13, padding: "13px 15px", borderRadius: 9,
        background: memory ? "color-mix(in oklab, var(--lbb-accent-mid) 7%, var(--lbb-surface2))" : "var(--lbb-surface2)",
        border: "1px solid var(--lbb-border)",
        borderLeft: `2px solid ${memory ? "var(--lbb-accent-mid)" : "var(--lbb-border2)"}`,
      }}>
        <div style={{
          width: 34, height: 34, borderRadius: 8, flex: "0 0 auto",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          background: memory ? "var(--lbb-accent-soft)" : "var(--lbb-surface)",
          border: "1px solid var(--lbb-border2)", color: memory ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
        }}>
          <Icon name={memory ? "star" : "user"} size={15} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--lbb-fg)" }}>{a.name}</span>
            {memory && (
              <span style={{ marginLeft: "auto", fontFamily: "var(--lbb-mono)", fontSize: 9.5, letterSpacing: 0.6,
                textTransform: "uppercase", color: "var(--lbb-accent-mid)", padding: "1px 7px", borderRadius: 4,
                background: "var(--lbb-accent-soft)", border: "1px solid color-mix(in oklab, var(--lbb-accent-mid) 35%, transparent)" }}>
                In memory
              </span>
            )}
          </div>
          <div style={{ fontFamily: "var(--lbb-mono)", fontSize: 10.5, color: "var(--lbb-fg3)", marginTop: 2 }}>{a.handle}</div>
          <p style={{ margin: "6px 0 0", fontSize: 11.8, lineHeight: 1.55, color: "var(--lbb-fg2)" }}>{a.note}</p>
        </div>
      </div>
    );
  }

  function Acks() {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
        {D.acks.map((a) => <AckCard key={a.name} a={a} />)}
      </div>
    );
  }

  // ── Changelog ──────────────────────────────────────────────────────────
  const TAG_COLOR = {
    new:      "var(--lbb-accent-mid)",
    improved: "var(--lbb-ok-fg)",
    changed:  "var(--lbb-warn-fg)",
    fixed:    "var(--lbb-fg3)",
  };
  function Changelog() {
    const c = D.changelog;
    return (
      <div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 11 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: "var(--lbb-fg)" }}>v{c.version}</span>
          <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 11, color: "var(--lbb-fg3)" }}>{c.date}</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
          {c.entries.map((e, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "74px 1fr", gap: 12, alignItems: "baseline" }}>
              <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 9.5, letterSpacing: 0.5, textTransform: "uppercase",
                fontWeight: 600, color: TAG_COLOR[e[0]], textAlign: "right" }}>{e[0]}</span>
              <span style={{ fontSize: 12.3, lineHeight: 1.5, color: "var(--lbb-fg2)" }}>{e[1]}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── Links ──────────────────────────────────────────────────────────────
  function Links({ grid = true }) {
    return (
      <div style={{ display: "grid", gridTemplateColumns: grid ? "1fr 1fr" : "1fr", gap: 8 }}>
        {D.links.map((l) => (
          <a key={l.label} href={l.href} style={{
            display: "flex", alignItems: "center", gap: 11, padding: "9px 11px", borderRadius: 8,
            background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)", textDecoration: "none",
          }}
            onMouseEnter={(e) => e.currentTarget.style.borderColor = "var(--lbb-border2)"}
            onMouseLeave={(e) => e.currentTarget.style.borderColor = "var(--lbb-border)"}>
            <span style={{ width: 28, height: 28, borderRadius: 7, flex: "0 0 auto",
              background: "var(--lbb-surface)", border: "1px solid var(--lbb-border)",
              display: "inline-flex", alignItems: "center", justifyContent: "center", color: "var(--lbb-accent-mid)" }}>
              <Icon name={l.icon} size={14} />
            </span>
            <span style={{ flex: 1, minWidth: 0 }}>
              <span style={{ display: "block", fontSize: 12.3, fontWeight: 600, color: "var(--lbb-fg)",
                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{l.label}</span>
              <span style={{ display: "block", fontSize: 10.5, color: "var(--lbb-fg3)" }}>{l.sub}</span>
            </span>
            <Icon name="reveal" size={12} style={{ color: "var(--lbb-fg3)", flex: "0 0 auto" }} />
          </a>
        ))}
      </div>
    );
  }

  function Footer() {
    return (
      <div style={{ padding: "12px 26px", borderTop: "1px solid var(--lbb-border)",
        display: "flex", alignItems: "center", gap: 14, fontFamily: "var(--lbb-mono)", fontSize: 10.5,
        color: "var(--lbb-fg3)", background: "var(--lbb-surface)" }}>
        <span>{M.copyright}</span>
        <span style={{ marginLeft: "auto", display: "inline-flex", gap: 12 }}>
          <span>DB {M.db}</span><span>·</span><span>build {M.build}</span>
        </span>
      </div>
    );
  }

  Object.assign(window, {
    AboutHeader, BlockTitle, AboutBlurb, TechStack, StackRows, Acks, Changelog, Links, Footer, AboutMeta: Meta,
  });
})();
