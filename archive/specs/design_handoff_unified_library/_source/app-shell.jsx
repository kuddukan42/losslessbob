// app-shell.jsx
// LosslessBob — full app shell: sidebar nav + topbar + status footer.

const { Icon: ShellIcon } = window.LBB_Icon ? { Icon: window.LBB_Icon } : {};

(() => {
  const Icon = window.LBB_Icon;

  // Each entry: id, label, icon, count (optional), gated (optional)
  const NAV_GROUPS = [
    {
      label: null,
      items: [
        { id: "home", label: "Home", icon: "home" },
      ],
    },
    {
      label: "Ingest",
      items: [
        { id: "pipeline", label: "Pipeline", icon: "pipeline", featured: true },
        { id: "verify",   label: "Verify",   icon: "verify" },
        { id: "lookup",   label: "Lookup",   icon: "lookup" },
        { id: "tapematch", label: "Tapematch", icon: "tapematch", featured: true },
        { id: "rename",   label: "Rename",   icon: "rename" },
        { id: "lbdir",    label: "LBDIR",    icon: "lbdir" },
      ],
    },
    {
      label: "Library",
      items: [
        { id: "collection", label: "My Collection", icon: "collection", count: 15967 },
        { id: "search",     label: "Search",        icon: "search" },
        { id: "bootlegs",   label: "Bootlegs",      icon: "bootlegs", count: 1380 },
      ],
    },
    {
      label: "Assets",
      items: [
        { id: "attachments",  label: "Attachments",  icon: "attachments" },
        { id: "spectrograms", label: "Spectrograms", icon: "spectro" },
        { id: "map",          label: "Map",          icon: "map" },
      ],
    },
    {
      label: "Curator", gatedGroup: true,
      items: [
        { id: "dbeditor", label: "DB Editor", icon: "dbeditor" },
        { id: "scraper",  label: "Scraper",   icon: "scraper" },
      ],
    },
    {
      label: "Settings",
      items: [
        { id: "setup",  label: "Setup",  icon: "setup" },
        { id: "themes", label: "Themes", icon: "themes" },
      ],
    },
  ];

  // ────────────────────────────────────────────────────────────────────
  // Sidebar
  // ────────────────────────────────────────────────────────────────────
  function Sidebar({ active, onNav, curatorMode, nav }) {
    const groups = nav || NAV_GROUPS;
    return (
      <aside style={{
        width: 224, flex: "0 0 224px",
        background: "var(--lbb-surface)",
        borderRight: "1px solid var(--lbb-border)",
        display: "flex", flexDirection: "column", minHeight: 0,
      }}>
        {/* Brand */}
        <div style={{
          padding: "16px 18px 14px",
          display: "flex", alignItems: "center", gap: 10,
          borderBottom: "1px solid var(--lbb-border)",
        }}>
          <div style={{
            width: 30, height: 30, borderRadius: 8,
            background: "var(--lbb-accent-mid)",
            color: "var(--lbb-accent-onMid)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            fontWeight: 800, fontSize: 14, letterSpacing: -0.02,
            boxShadow: "0 1px 0 rgba(255,255,255,0.18) inset, 0 1px 2px rgba(0,0,0,0.12)",
          }}>LB</div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: -0.01, lineHeight: 1.1 }}>LosslessBob</div>
            <div style={{ fontSize: 10.5, color: "var(--lbb-fg3)", marginTop: 2, letterSpacing: 0.04, whiteSpace: "nowrap" }}>Checksum Lookup · v3.2.0</div>
          </div>
        </div>

        {/* Nav */}
        <div style={{ flex: 1, overflowY: "auto", padding: "10px 8px 16px" }}>
          {groups.map((group, gi) => {
            const isGatedGroup = group.gatedGroup;
            if (isGatedGroup && !curatorMode) return null;
            return (
              <div key={gi} style={{ marginTop: gi === 0 ? 0 : 14 }}>
                {group.label && (
                  <div style={{
                    fontSize: 10, fontWeight: 700, color: "var(--lbb-fg3)",
                    letterSpacing: 0.12, textTransform: "uppercase",
                    padding: "6px 10px 6px",
                    display: "flex", alignItems: "center", gap: 6,
                  }}>
                    <span>{group.label}</span>
                    {isGatedGroup && (
                      <span style={{
                        fontSize: 8.5, fontWeight: 700, letterSpacing: 0.1,
                        padding: "1px 5px", borderRadius: 3,
                        background: "var(--lbb-warn-bg)", color: "var(--lbb-warn-fg)",
                        border: "1px solid var(--lbb-warn-bar)",
                      }}>CURATOR</span>
                    )}
                  </div>
                )}
                {group.items.map(item => {
                  const isActive = item.id === active;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => onNav(item.id)}
                      className="lbb-nav-item"
                      style={{
                        width: "100%", display: "flex", alignItems: "center", gap: 10,
                        padding: "7px 10px", marginBottom: 1,
                        border: "1px solid transparent", borderRadius: 6,
                        background: isActive ? "var(--lbb-accent-soft)" : "transparent",
                        color: isActive ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
                        fontSize: 12.5, fontWeight: isActive ? 600 : 500,
                        textAlign: "left", cursor: "pointer", lineHeight: 1.2,
                        fontFamily: "inherit",
                      }}
                      onMouseEnter={e => !isActive && (e.currentTarget.style.background = "var(--lbb-surface2)")}
                      onMouseLeave={e => !isActive && (e.currentTarget.style.background = "transparent")}
                    >
                      <Icon name={item.icon} size={15} />
                      <span style={{ flex: 1 }}>{item.label}</span>
                      {item.featured && !isActive && (
                        <span style={{
                          fontSize: 8.5, fontWeight: 700, padding: "0 5px", borderRadius: 3,
                          background: "var(--lbb-accent-soft)", color: "var(--lbb-accent-mid)",
                          letterSpacing: 0.06,
                        }}>NEW</span>
                      )}
                      {item.count !== undefined && (
                        <span style={{
                          fontSize: 10.5, color: isActive ? "var(--lbb-accent-mid)" : "var(--lbb-fg3)",
                          fontVariantNumeric: "tabular-nums", fontWeight: 500,
                        }}>{item.count.toLocaleString()}</span>
                      )}
                    </button>
                  );
                })}
              </div>
            );
          })}

          {!curatorMode && (
            <div style={{
              margin: "16px 6px 0", padding: "10px 12px",
              background: "var(--lbb-surface2)", borderRadius: 8,
              border: "1px dashed var(--lbb-border2)",
              fontSize: 11, color: "var(--lbb-fg3)", lineHeight: 1.4,
            }}>
              Maintaining the master DB?
              <div style={{ marginTop: 6 }}>
                <span style={{ color: "var(--lbb-accent-mid)", fontWeight: 600, cursor: "pointer" }}>Enable Curator mode →</span>
              </div>
            </div>
          )}
        </div>

        {/* User chip */}
        <div style={{
          padding: "10px 12px", borderTop: "1px solid var(--lbb-border)",
          display: "flex", alignItems: "center", gap: 10,
        }}>
          <div style={{
            width: 28, height: 28, borderRadius: "50%",
            background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border2)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            fontSize: 11, fontWeight: 700, color: "var(--lbb-fg2)",
          }}>RW</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 600, lineHeight: 1.1 }}>rolling.thunder</div>
            <div style={{ fontSize: 10.5, color: "var(--lbb-fg3)" }}>Local · 4 mounts</div>
          </div>
          <button style={{
            width: 24, height: 24, borderRadius: 5,
            background: "transparent", border: "1px solid transparent",
            color: "var(--lbb-fg3)", cursor: "pointer",
          }}>
            <Icon name="more" size={14} />
          </button>
        </div>
      </aside>
    );
  }

  // ────────────────────────────────────────────────────────────────────
  // Topbar — breadcrumb + global search + accent chip
  // ────────────────────────────────────────────────────────────────────
  function Topbar({ crumbs, actions }) {
    return (
      <header style={{
        height: 52, flex: "0 0 52px",
        padding: "0 20px", display: "flex", alignItems: "center", gap: 16,
        borderBottom: "1px solid var(--lbb-border)",
        background: "var(--lbb-surface)",
      }}>
        {/* Crumbs */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          {crumbs.map((c, i) => (
            <React.Fragment key={i}>
              {i > 0 && <span style={{ color: "var(--lbb-fg3)", fontSize: 12 }}>/</span>}
              <span style={{
                fontSize: 13,
                fontWeight: i === crumbs.length - 1 ? 600 : 500,
                color: i === crumbs.length - 1 ? "var(--lbb-fg)" : "var(--lbb-fg2)",
                letterSpacing: -0.005,
              }}>{c}</span>
            </React.Fragment>
          ))}
        </div>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Optional per-screen actions */}
        {actions}

        {/* Search */}
        <button style={{
          display: "inline-flex", alignItems: "center", gap: 10,
          height: 32, padding: "0 10px 0 12px",
          background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)",
          borderRadius: 8, color: "var(--lbb-fg3)", fontSize: 12.5,
          cursor: "pointer", minWidth: 280,
        }}>
          <Icon name="search" size={14} />
          <span style={{ flex: 1, textAlign: "left" }}>Find LB#, folder, location…</span>
          <span className="kbd-pill">⌘K</span>
        </button>

        {/* Bell */}
        <button style={{
          width: 34, height: 34, borderRadius: 8,
          background: "transparent", border: "1px solid transparent",
          color: "var(--lbb-fg2)", cursor: "pointer", position: "relative",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
        }}>
          <Icon name="bell" size={16} />
          <span style={{
            position: "absolute", top: 7, right: 8,
            width: 7, height: 7, borderRadius: "50%",
            background: "var(--lbb-bad-bar)", border: "1.5px solid var(--lbb-surface)",
          }}/>
        </button>
      </header>
    );
  }

  // ────────────────────────────────────────────────────────────────────
  // Status footer
  // ────────────────────────────────────────────────────────────────────
  function StatusBar({ extra }) {
    const item = (label, value, tone) => (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6, whiteSpace: "nowrap" }}>
        {tone && (
          <span style={{
            width: 6, height: 6, borderRadius: "50%",
            background: `var(--lbb-${tone}-bar)`,
          }}/>
        )}
        <span style={{ color: "var(--lbb-fg3)" }}>{label}</span>
        <span style={{ color: "var(--lbb-fg2)", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{value}</span>
      </span>
    );
    return (
      <footer style={{
        height: 28, flex: "0 0 28px",
        padding: "0 20px", display: "flex", alignItems: "center", gap: 20,
        borderTop: "1px solid var(--lbb-border)",
        background: "var(--lbb-surface)",
        fontSize: 11, fontFamily: "var(--lbb-mono)",
      }}>
        {item("DB:",        "LB-16630",  "ok")}
        <span style={{ color: "var(--lbb-border2)" }}>·</span>
        {item("Checksums:", "704,624")}
        <span style={{ color: "var(--lbb-border2)" }}>·</span>
        {item("Last import:", "2026-05-21")}
        <span style={{ color: "var(--lbb-border2)" }}>·</span>
        {item("Bootlegs:", "1,380")}
        {extra && <>{" "}<span style={{ color: "var(--lbb-border2)" }}>·</span>{extra}</>}
        <div style={{ flex: 1 }} />
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "var(--lbb-fg3)" }}>
          <Icon name="shield" size={11} /> Synced · idle
        </span>
      </footer>
    );
  }

  // ────────────────────────────────────────────────────────────────────
  // Shell
  // ────────────────────────────────────────────────────────────────────
  function AppShell({ active, onNav, curatorMode, crumbs, topActions, statusExtra, nav, children }) {
    return (
      <div style={{
        width: 1920, height: 1080, display: "flex", flexDirection: "column",
        background: "var(--lbb-bg)", color: "var(--lbb-fg)", overflow: "hidden",
      }}>
        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          <Sidebar active={active} onNav={onNav} curatorMode={curatorMode} nav={nav} />
          <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
            <Topbar crumbs={crumbs} actions={topActions} />
            <div style={{ flex: 1, overflow: "auto", minHeight: 0 }}>{children}</div>
          </main>
        </div>
        <StatusBar extra={statusExtra} />
      </div>
    );
  }

  window.LBB_AppShell = AppShell;
})();
