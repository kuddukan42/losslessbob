// about-variants.jsx — three About-dialog directions (dark). Echo the splash frame.

(() => {
  const { AboutHeader, BlockTitle, AboutBlurb, TechStack, Acks, Changelog, Links, Footer,
          AboutMeta: Meta, LBB_w: w } = window;
  const Icon = window.LBB_Icon;
  const M = window.LBB_LAUNCH.meta;

  // Dark stage + centered dialog card (ties back to the splash field).
  function Stage({ children }) {
    return (
      <div style={{ position: "relative", width: "100%", height: "100%", background: "#131110",
        backgroundImage: "radial-gradient(120% 90% at 50% 0%, color-mix(in oklab, var(--lbb-accent-mid) 10%, transparent), transparent 50%)",
        display: "flex", alignItems: "stretch", justifyContent: "center", padding: 18,
        fontFamily: "Inter, system-ui, sans-serif" }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0,
          background: "var(--lbb-surface)", border: "1px solid var(--lbb-border2)", borderRadius: 12,
          boxShadow: "0 24px 70px rgba(0,0,0,0.55)", overflow: "hidden" }}>
          {children}
        </div>
      </div>
    );
  }

  const Body = ({ children, style }) => (
    <div style={{ flex: 1, minHeight: 0, overflowY: "auto", ...style }}>{children}</div>
  );

  const Section = ({ title, right, children, first }) => (
    <div style={{ marginTop: first ? 0 : 26 }}>
      <BlockTitle right={right}>{title}</BlockTitle>
      {children}
    </div>
  );

  // ── A · Single column, scrolling ───────────────────────────────────────
  function AboutSingle() {
    return (
      <Stage>
        <AboutHeader onClose={() => {}} />
        <Body style={{ padding: "22px 26px 26px" }}>
          <AboutBlurb />
          <Section title="Links"><Links /></Section>
          <Section title="Acknowledgements"><Acks /></Section>
          <Section title="Tech stack"><TechStack /></Section>
          <Section title="What’s new"><Changelog /></Section>
        </Body>
        <Footer />
      </Stage>
    );
  }

  // ── B · Info rail + scrolling content ──────────────────────────────────
  function AboutRail() {
    return (
      <Stage>
        <AboutHeader onClose={() => {}} />
        <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: "236px 1fr" }}>
          {/* left rail — fixed */}
          <div style={{ borderRight: "1px solid var(--lbb-border)", padding: "20px 20px 22px",
            display: "flex", flexDirection: "column", gap: 20, background: "var(--lbb-surface)" }}>
            <AboutBlurb />
            <div>
              <BlockTitle>Release</BlockTitle>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <Meta k="version" v={`${M.version} · ${M.channel}`} accent />
                <Meta k="build" v={M.build} />
                <Meta k="db" v={M.db} />
                <Meta k="index" v={`${M.checksums}`} />
                <Meta k="python" v="3.11+" />
              </div>
            </div>
            <div>
              <BlockTitle>Links</BlockTitle>
              <Links grid={false} />
            </div>
          </div>
          {/* right — scrolling */}
          <Body style={{ padding: "20px 24px 26px" }}>
            <Section title="Acknowledgements" first><Acks /></Section>
            <Section title="Tech stack"><TechStack /></Section>
            <Section title="What’s new"><Changelog /></Section>
          </Body>
        </div>
        <Footer />
      </Stage>
    );
  }

  // ── C · Tabbed ─────────────────────────────────────────────────────────
  function AboutTabbed() {
    const TABS = [
      { id: "about",  label: "About",   icon: "info" },
      { id: "tech",   label: "Tech",    icon: "setup" },
      { id: "credits",label: "Credits", icon: "user" },
      { id: "log",    label: "Changes", icon: "lbdir" },
    ];
    const [tab, setTab] = React.useState("about");
    return (
      <Stage>
        <AboutHeader onClose={() => {}} compact />
        {/* segmented tab bar */}
        <div style={{ display: "flex", gap: 4, padding: "12px 22px 0", borderBottom: "1px solid var(--lbb-border)" }}>
          {TABS.map((t) => {
            const on = t.id === tab;
            return (
              <button key={t.id} onClick={() => setTab(t.id)} style={{
                display: "inline-flex", alignItems: "center", gap: 7, padding: "9px 14px 11px",
                background: "transparent", border: "none", cursor: "pointer", fontFamily: "inherit",
                fontSize: 12.5, fontWeight: on ? 600 : 500,
                color: on ? "var(--lbb-fg)" : "var(--lbb-fg3)",
                borderBottom: `2px solid ${on ? "var(--lbb-accent-mid)" : "transparent"}`, marginBottom: -1,
              }}>
                <Icon name={t.icon} size={14} style={{ color: on ? "var(--lbb-accent-mid)" : "var(--lbb-fg3)" }} />
                {t.label}
              </button>
            );
          })}
        </div>
        <Body style={{ padding: "22px 24px 26px" }}>
          {tab === "about" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
              <AboutBlurb />
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8,
                padding: "14px 16px", borderRadius: 9, background: "var(--lbb-surface2)",
                border: "1px solid var(--lbb-border)", rowGap: 12 }}>
                <Meta k="version" v={`${M.version} · ${M.channel}`} accent />
                <Meta k="build" v={M.build} />
                <Meta k="database" v={M.db} />
                <Meta k="index" v={M.checksums} />
              </div>
              <div><BlockTitle>Links</BlockTitle><Links /></div>
            </div>
          )}
          {tab === "tech" && <TechStack />}
          {tab === "credits" && <Acks />}
          {tab === "log" && <Changelog />}
        </Body>
        <Footer />
      </Stage>
    );
  }

  Object.assign(window, { AboutSingle, AboutRail, AboutTabbed });
})();
