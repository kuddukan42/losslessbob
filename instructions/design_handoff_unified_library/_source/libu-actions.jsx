// libu-actions.jsx
// The shared ACTION SYSTEM for the unified Library. One action vocabulary,
// rendered in two surfaces that can never drift apart:
//   1. the right-click row context menu (every action, grouped)
//   2. the detail-panel action bar (one primary + Reveal + a ⋯ More menu)
// Plus the two redesigned workflow blocks the old panels lacked:
//   · ShareSeed  — the unified torrent + forum distribution workflow
//   · AssetStrip — attachments / spectrograms / map as state-bearing chips
//
// NOTE FOR DEVS: action onClick handlers here are intentionally inert
// (they only close the menu). The intended behavior + data needs for each
// action id are specified in the handoff's interaction punchlist — this
// file is the single source of truth for WHICH actions exist and WHERE.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, IconButton, Pill } = window;

  // ─── Group ordering + labels (shared by menu + overflow) ──────────
  const GROUP_ORDER = ["open", "listen", "acquire", "share", "assets", "maintain"];
  const GROUP_LABEL = {
    open: null, listen: null, acquire: "Acquire",
    share: "Share & seed", assets: "Assets", maintain: "Maintain",
  };

  // ─── Canonical action registries ──────────────────────────────────
  // Each action: { id, label, icon, group, primary?, danger? }
  function recordingActions(r) {
    const owned = !!r.owned;
    const A = [
      { id: "open",   label: "Open LB page", icon: "globe", group: "open" },
      { id: "copyLb", label: "Copy LB number", icon: "copy", group: "open" },
    ];
    if (owned) {
      A.push(
        { id: "play",     label: "Play",               icon: "play",   group: "listen", primary: true },
        { id: "reveal",   label: "Reveal on disk",     icon: "reveal", group: "listen" },
        { id: "copyPath", label: "Copy disk path",     icon: "copy",   group: "listen" },
        { id: "qbt",      label: "Add to qBittorrent", icon: "upload", group: "share" },
        { id: "torrent",  label: "Create / regenerate torrent", icon: "copy", group: "share" },
        { id: "forum",    label: "Post to forum",      icon: "globe",  group: "share" },
        { id: "attach",   label: "Attachments",        icon: "attachments", group: "assets" },
        { id: "spectro",  label: "Spectrograms",       icon: "spectro", group: "assets" },
        { id: "map",      label: "Show on map",        icon: "map",    group: "assets" },
        { id: "reconfirm",label: "Re-confirm checksums", icon: "verify", group: "maintain" },
        { id: "refp",     label: "Re-fingerprint",     icon: "spectro", group: "maintain" },
        { id: "relocate", label: "Update location…",   icon: "reveal", group: "maintain" },
        { id: "remove",   label: "Remove from collection", icon: "trash", group: "maintain", danger: true },
      );
    } else {
      A.push(
        { id: "wishlist", label: r.wish ? "On wishlist" : "Add to wishlist",
          icon: r.wish ? "starFill" : "star", group: "acquire", primary: !r.wish },
        { id: "sources",  label: "Find sources",         icon: "globe", group: "acquire" },
        { id: "notify",   label: "Notify when available", icon: "bell",  group: "acquire" },
      );
    }
    return A;
  }

  function performanceActions(p, ru) {
    const owned = ru ? ru.ownedCount > 0 : (p.recordings || []).some(r => r.owned);
    const A = [{ id: "open", label: "Open LB page", icon: "globe", group: "open" }];
    if (owned) {
      A.push(
        { id: "play",    label: "Play best recording", icon: "play",   group: "listen", primary: true },
        { id: "reveal",  label: "Reveal best on disk", icon: "reveal", group: "listen" },
        { id: "m3u",     label: "Export show as M3U",  icon: "download", group: "share" },
        { id: "qbt",     label: "Add owned to qBittorrent", icon: "upload", group: "share" },
        { id: "torrent", label: "Create torrent…",     icon: "copy",   group: "share" },
        { id: "forum",   label: "Post to forum",       icon: "globe",  group: "share" },
      );
    }
    A.push({ id: "wishlistGaps", label: "Wishlist missing sources", icon: "star", group: "acquire" });
    return A;
  }

  // ─── Grouped action list (used by ContextMenu + MoreMenu) ─────────
  function groupActions(actions) {
    const by = {};
    actions.forEach(a => { (by[a.group] = by[a.group] || []).push(a); });
    return GROUP_ORDER.filter(g => by[g]).map(g => ({ group: g, label: GROUP_LABEL[g], items: by[g] }));
  }

  function ActionList({ actions, onPick }) {
    const groups = groupActions(actions);
    return (
      <div style={{ display: "flex", flexDirection: "column", minWidth: 208 }}>
        {groups.map((grp, gi) => (
          <React.Fragment key={grp.group}>
            {gi > 0 && <div style={{ height: 1, background: "var(--lbb-border)", margin: "4px 4px" }} />}
            {grp.label && (
              <div style={{
                fontSize: 9.5, fontWeight: 700, letterSpacing: 0.1, textTransform: "uppercase",
                color: "var(--lbb-fg3)", padding: "5px 10px 3px",
              }}>{grp.label}</div>
            )}
            {grp.items.map(a => (
              <button key={a.id} type="button"
                onClick={() => onPick && onPick(a)}
                style={{
                  display: "flex", alignItems: "center", gap: 9, width: "100%",
                  padding: "6px 10px", borderRadius: 6, cursor: "pointer",
                  background: "transparent", border: "1px solid transparent",
                  color: a.danger ? "var(--lbb-bad-fg)" : "var(--lbb-fg)",
                  fontSize: 12, fontWeight: 500, fontFamily: "inherit", textAlign: "left",
                }}
                onMouseEnter={e => e.currentTarget.style.background = a.danger ? "var(--lbb-bad-bg)" : "var(--lbb-surface2)"}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                <Icon name={a.icon} size={14} style={{ color: a.danger ? "var(--lbb-bad-fg)" : "var(--lbb-fg3)", flex: "0 0 auto" }} />
                <span style={{ flex: 1 }}>{a.label}</span>
                {a.primary && <span style={{ fontSize: 9, fontWeight: 700, color: "var(--lbb-fg3)" }}>↵</span>}
              </button>
            ))}
          </React.Fragment>
        ))}
      </div>
    );
  }

  // ─── Right-click context menu — portals to <body> so it escapes the
  //     scaled #frame transform and clamps to the real viewport. ──────
  function ContextMenu({ x, y, title, actions, onClose }) {
    const ref = React.useRef(null);
    const [pos, setPos] = React.useState({ left: x, top: y, visibility: "hidden" });

    React.useEffect(() => {
      const onDown = (e) => { if (!ref.current || !ref.current.contains(e.target)) onClose(); };
      const onEsc  = (e) => { if (e.key === "Escape") onClose(); };
      window.addEventListener("mousedown", onDown, true);
      window.addEventListener("keydown", onEsc);
      window.addEventListener("blur", onClose);
      window.addEventListener("resize", onClose);
      return () => {
        window.removeEventListener("mousedown", onDown, true);
        window.removeEventListener("keydown", onEsc);
        window.removeEventListener("blur", onClose);
        window.removeEventListener("resize", onClose);
      };
    }, [onClose]);

    React.useLayoutEffect(() => {
      const el = ref.current; if (!el) return;
      const r = el.getBoundingClientRect();
      let left = x, top = y;
      if (left + r.width  > window.innerWidth  - 8) left = window.innerWidth  - r.width  - 8;
      if (top  + r.height > window.innerHeight - 8) top  = Math.max(8, window.innerHeight - r.height - 8);
      setPos({ left, top, visibility: "visible" });
    }, [x, y]);

    return ReactDOM.createPortal(
      <div ref={ref} onContextMenu={(e) => e.preventDefault()} style={{
        position: "fixed", left: pos.left, top: pos.top, visibility: pos.visibility, zIndex: 9999,
        padding: 5, borderRadius: 10, maxHeight: "80vh", overflowY: "auto",
        background: "var(--lbb-surface)", border: "1px solid var(--lbb-border2)",
        boxShadow: "var(--lbb-shadowLg)",
        fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
      }}>
        {title && (
          <div style={{
            padding: "4px 10px 7px", marginBottom: 3, borderBottom: "1px solid var(--lbb-border)",
            fontSize: 11, fontWeight: 700, color: "var(--lbb-fg2)", maxWidth: 240,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>{title}</div>
        )}
        <ActionList actions={actions} onPick={() => onClose()} />
      </div>,
      document.body
    );
  }

  // Hook: gives a row an onContextMenu handler + the menu node to render.
  function useRowMenu() {
    const [menu, setMenu] = React.useState(null);
    const openMenu = React.useCallback((e, { title, actions }) => {
      e.preventDefault(); e.stopPropagation();
      setMenu({ x: e.clientX, y: e.clientY, title, actions });
    }, []);
    const close = React.useCallback(() => setMenu(null), []);
    const menuNode = menu
      ? <ContextMenu x={menu.x} y={menu.y} title={menu.title} actions={menu.actions} onClose={close} />
      : null;
    return { openMenu, menuNode };
  }

  // ─── MoreMenu — anchored overflow dropdown for the detail action bar.
  function MoreMenu({ actions }) {
    const [open, setOpen] = React.useState(false);
    const ref = React.useRef(null);
    React.useEffect(() => {
      if (!open) return;
      const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
      const onEsc = (e) => { if (e.key === "Escape") setOpen(false); };
      document.addEventListener("mousedown", onDoc);
      document.addEventListener("keydown", onEsc);
      return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onEsc); };
    }, [open]);
    return (
      <div ref={ref} style={{ position: "relative" }}>
        <Button size="sm" variant="ghost" icon="more" onClick={() => setOpen(o => !o)}>More</Button>
        {open && (
          <div style={{
            position: "absolute", top: "calc(100% + 6px)", right: 0, zIndex: 90,
            padding: 5, borderRadius: 10, minWidth: 220, maxHeight: 360, overflowY: "auto",
            background: "var(--lbb-surface)", border: "1px solid var(--lbb-border2)",
            boxShadow: "var(--lbb-shadowLg)",
          }}>
            <ActionList actions={actions} onPick={() => setOpen(false)} />
          </div>
        )}
      </div>
    );
  }

  // ─── ActionBar — the detail-panel command row. Primary + Reveal + More.
  // Renders the SAME `actions` array the right-click menu uses.
  function ActionBar({ actions }) {
    const primary = actions.find(a => a.primary);
    const reveal  = actions.find(a => a.id === "reveal");
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 14, flexWrap: "wrap" }}>
        {primary && <Button size="sm" variant="primary" icon={primary.icon}>{primary.label}</Button>}
        {reveal  && <Button size="sm" variant="secondary" icon={reveal.icon}>{reveal.label}</Button>}
        <div style={{ flex: 1 }} />
        <MoreMenu actions={actions} />
      </div>
    );
  }

  // ─── AssetStrip — attachments / spectrograms / map as state chips ──
  // `assets` (optional): { attachments?: n, spectrograms?: bool, map?: bool }
  function AssetChip({ icon, label, state, ready }) {
    return (
      <button type="button" style={{
        display: "inline-flex", alignItems: "center", gap: 7,
        padding: "5px 10px", borderRadius: 7, cursor: "pointer", fontFamily: "inherit",
        background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)",
        color: "var(--lbb-fg2)", fontSize: 11.5, fontWeight: 550,
      }}
        onMouseEnter={e => e.currentTarget.style.borderColor = "var(--lbb-border2)"}
        onMouseLeave={e => e.currentTarget.style.borderColor = "var(--lbb-border)"}>
        <Icon name={icon} size={13} style={{ color: ready ? "var(--lbb-accent-mid)" : "var(--lbb-fg3)" }} />
        <span>{label}</span>
        {state !== undefined && state !== null && (
          <span style={{
            fontSize: 10, fontWeight: 700, color: ready ? "var(--lbb-accent-mid)" : "var(--lbb-fg3)",
            fontVariantNumeric: "tabular-nums",
          }}>{state}</span>
        )}
      </button>
    );
  }

  function AssetStrip({ assets }) {
    const a = assets || { attachments: 3, spectrograms: true, map: true };
    return (
      <div style={{ marginTop: 16 }}>
        <SectionLabel>Assets</SectionLabel>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <AssetChip icon="attachments" label="Attachments" state={a.attachments} ready={a.attachments > 0} />
          <AssetChip icon="spectro" label="Spectrograms" state={a.spectrograms ? "ready" : "generate"} ready={!!a.spectrograms} />
          <AssetChip icon="map" label="Map" ready={!!a.map} />
        </div>
      </div>
    );
  }

  // ─── ShareSeed — the unified distribution workflow ────────────────
  // Replaces the old "History" toggle + disconnected Regenerate/Post row.
  // Status summary, primary distribution actions, then a unified activity
  // log (torrents + forum, filterable). Degrades gracefully when never shared.
  function SectionLabel({ children, right }) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.08, textTransform: "uppercase", color: "var(--lbb-fg3)" }}>{children}</span>
        <div style={{ flex: 1 }} />
        {right}
      </div>
    );
  }

  function ShareSeed({ lb, hist }) {
    const [tab, setTab] = React.useState("all");
    const torrents = (hist && hist.torrents) || [];
    const forum    = (hist && hist.forum) || [];
    const seeding  = torrents.filter(t => /qbt/i.test(t.tag)).length;
    const lastForum = forum[0] ? forum[0].d : null;
    const shared = torrents.length > 0 || forum.length > 0;

    // Unified, date-sorted activity log
    const log = [
      ...torrents.map(t => ({ ...t, kind: "torrent" })),
      ...forum.map(f => ({ ...f, kind: "forum" })),
    ].sort((a, b) => (a.d < b.d ? 1 : -1));
    const shown = tab === "all" ? log : log.filter(e => e.kind === tab.replace(/s$/, ""));

    return (
      <div style={{ marginTop: 18 }}>
        <SectionLabel
          right={shared ? (
            <div style={{ display: "flex", gap: 4 }}>
              {["all", "torrents", "forum"].map(t => (
                <button key={t} type="button" onClick={() => setTab(t)} style={{
                  padding: "1px 8px", borderRadius: 999, cursor: "pointer", fontFamily: "inherit",
                  fontSize: 10.5, fontWeight: tab === t ? 700 : 500,
                  background: tab === t ? "var(--lbb-accent-soft)" : "transparent",
                  color: tab === t ? "var(--lbb-accent-mid)" : "var(--lbb-fg3)",
                  border: "1px solid " + (tab === t ? "var(--lbb-accent-mid)" : "var(--lbb-border)"),
                  textTransform: "capitalize",
                }}>{t}</button>
              ))}
            </div>
          ) : null}
        >Share &amp; seed</SectionLabel>

        {/* Status summary */}
        <div style={{
          padding: "10px 12px", borderRadius: 8, marginBottom: 8,
          background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)",
          display: "flex", alignItems: "center", gap: 10,
        }}>
          <Icon name={seeding > 0 ? "upload" : "globe"} size={15}
            style={{ color: seeding > 0 ? "var(--lbb-ok-fg)" : "var(--lbb-fg3)", flex: "0 0 auto" }} />
          <div style={{ flex: 1, fontSize: 11.5, lineHeight: 1.45, color: "var(--lbb-fg2)" }}>
            {shared ? (
              <span>
                {seeding > 0
                  ? <strong style={{ color: "var(--lbb-fg)" }}>Seeding {seeding} torrent{seeding > 1 ? "s" : ""}</strong>
                  : <span>{torrents.length} torrent{torrents.length === 1 ? "" : "s"} on file</span>}
                {forum.length > 0 && <span> · {forum.length} forum post{forum.length === 1 ? "" : "s"}{lastForum ? ` · last ${lastForum}` : ""}</span>}
              </span>
            ) : (
              <span>Not shared yet — create a torrent or post to the forum to start a distribution history.</span>
            )}
          </div>
        </div>

        {/* Primary distribution actions */}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <Button size="sm" variant="primary" icon="upload">Add to qBittorrent</Button>
          <Button size="sm" variant="secondary" icon="copy">{torrents.length ? "Regenerate torrent" : "Create torrent"}</Button>
          <Button size="sm" variant="ghost" icon="globe">Post to forum</Button>
        </div>

        {/* Unified activity log */}
        {shared && (
          <div style={{ marginTop: 10, border: "1px solid var(--lbb-border)", borderRadius: 8, overflow: "hidden" }}>
            {shown.map((e, i) => (
              <div key={i} style={{
                padding: "8px 10px", display: "flex", alignItems: "center", gap: 8, fontSize: 11.5,
                borderBottom: i < shown.length - 1 ? "1px solid var(--lbb-border)" : "none",
              }}>
                <Icon name={e.kind === "torrent" ? "copy" : "globe"} size={12}
                  style={{ color: "var(--lbb-fg3)", flex: "0 0 auto" }} />
                <span style={{ fontFamily: "var(--lbb-mono)", color: "var(--lbb-fg3)", flex: "0 0 auto" }}>{e.d}</span>
                <span style={{ flex: 1, fontFamily: "var(--lbb-mono)", color: "var(--lbb-fg)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.f}</span>
                <Pill tone={/qbt|posted/i.test(e.tag) ? "ok" : "mute"} soft style={{ fontSize: 9, padding: "0 5px", flex: "0 0 auto" }}>{e.tag}</Pill>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  Object.assign(window, {
    LBB_recordingActions: recordingActions,
    LBB_performanceActions: performanceActions,
    LBB_useRowMenu: useRowMenu,
    LBB_ActionBar: ActionBar,
    LBB_ShareSeed: ShareSeed,
    LBB_AssetStrip: AssetStrip,
    LBB_SectionLabel: SectionLabel,
  });
})();
