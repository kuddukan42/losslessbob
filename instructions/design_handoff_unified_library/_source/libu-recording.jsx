// libu-recording.jsx
// Unified Library — "By recording" lens. Same data, flat LB#-keyed rows.
// Left filter rail replaced by a top filter bar (Views menu + per-facet
// dropdown popovers); active filters surface as removable chips in the
// summary strip. Shares chrome 1:1 with the "By performance" lens.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Chip, Input, IconButton, TableShell, TH, TR, TD, GroupRow,
          FilterMenu, MenuLabel } = window;
  const { LBB_RatingChip: RatingChip, LBB_ScopeControl: ScopeControl, LBB_ActiveFilter: ActiveFilter,
          LBB_DetailPanel: DetailPanel, LBB_BulkBar: BulkBar } = window;
  const LIB = window.LBB_LIB;

  const decadeOf = (year) => {
    if (!year) return null;
    const d = Math.floor((year % 100) / 10) * 10;
    return `${d === 0 ? "00" : d}s`;
  };

  const EMPTY_FACETS = () => ({
    decade: new Set(), status: new Set(), rating: new Set(), source: new Set(), files: new Set(),
  });

  const VIEW_PRESETS = {
    "all":         { scope: null },
    "next":        { scope: "owned" },
    "a-rated":     { scope: "unowned", rating: ["A", "A−"] },
    "sbd80s":      { scope: null, decade: ["80s"], source: ["Soundboard"] },
    "wishlist":    { scope: "unowned", flag: "wish" },
    "duplicates":  { scope: "owned", flag: "dup" },
    "unconfirmed": { scope: "owned", flag: "unconf" },
    "nofp":        { scope: "owned", flag: "nofp" },
  };

  // ── Views dropdown (saved searches + collection health) ─────────────
  function ViewRow({ icon, label, count, active, onClick }) {
    return (
      <button type="button" onClick={onClick} style={{
        display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", width: "100%",
        background: active ? "var(--lbb-accent-soft)" : "transparent",
        color: active ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
        border: "1px solid transparent", borderRadius: 6, cursor: "pointer",
        fontFamily: "inherit", textAlign: "left",
      }}>
        <Icon name={icon} size={13} />
        <span style={{ flex: 1, fontSize: 12, fontWeight: active ? 600 : 500 }}>{label}</span>
        {count !== undefined && (
          <span style={{ fontSize: 10.5, color: active ? "var(--lbb-accent-mid)" : "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums" }}>
            {count.toLocaleString()}
          </span>
        )}
      </button>
    );
  }

  function ViewsMenu({ view, setView, viewCounts }) {
    const SAVED = [
      { id: "next",    label: "My next listens",   count: 47 },
      { id: "a-rated", label: "A-rated unowned",   count: 38 },
      { id: "sbd80s",  label: "1980s soundboards", count: 540 },
    ];
    const HEALTH = [
      { id: "wishlist",    label: "Wishlist",       icon: "star" },
      { id: "duplicates",  label: "Duplicates",     icon: "copy" },
      { id: "unconfirmed", label: "Unconfirmed",    icon: "alert" },
      { id: "nofp",        label: "No fingerprint", icon: "spectro" },
    ];
    const label = view === "all" ? "All entries"
      : (SAVED.find(v => v.id === view) || HEALTH.find(v => v.id === view) || {}).label || "Views";
    const lit = view !== "all";
    return (
      <FilterMenu label={label} icon="library" count={0} width={246}
        buttonStyle={lit ? { background: "var(--lbb-accent-soft)", color: "var(--lbb-accent-mid)", borderColor: "var(--lbb-accent-mid)", fontWeight: 650 } : undefined}>
        {(close) => (
          <div>
            <MenuLabel>Saved views</MenuLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <ViewRow icon="library" label="All entries" active={view === "all"} onClick={() => { setView("all"); close(); }} />
              {SAVED.map(v => (
                <ViewRow key={v.id} icon={view === v.id ? "starFill" : "star"} label={v.label} count={v.count}
                  active={view === v.id} onClick={() => { setView(v.id); close(); }} />
              ))}
            </div>
            <div style={{ height: 1, background: "var(--lbb-border)", margin: "10px -12px" }}></div>
            <MenuLabel>Collection health</MenuLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              {HEALTH.map(v => (
                <ViewRow key={v.id} icon={v.icon} label={v.label} count={viewCounts[v.id]}
                  active={view === v.id} onClick={() => { setView(v.id); close(); }} />
              ))}
            </div>
          </div>
        )}
      </FilterMenu>
    );
  }

  // ── A facet dropdown: label + count badge, chips inside ─────────────
  function FacetMenu({ label, group, facets, toggleFacet, items, render, width }) {
    const count = facets[group].size;
    return (
      <FilterMenu label={label} count={count} width={width || 244}>
        <MenuLabel
          action={count > 0 ? (
            <button type="button" onClick={() => items.forEach(f => facets[group].has(f.k) && toggleFacet(group, f.k))}
              style={{ background: "transparent", border: "none", color: "var(--lbb-accent-mid)", fontSize: 11, fontWeight: 600, cursor: "pointer", fontFamily: "inherit", padding: 0 }}>
              Clear
            </button>) : null}
        >{label}</MenuLabel>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {items.map(f => (
            <Chip key={f.k} size="sm" count={f.n} active={facets[group].has(f.k)} onClick={() => toggleFacet(group, f.k)}>
              {render ? render(f.k) : f.k}
            </Chip>
          ))}
        </div>
      </FilterMenu>
    );
  }

  function LibURecording({ tweaks, viewSwitch }) {
    const [scope, setScope]       = React.useState("all");
    const [view, setViewState]    = React.useState("all");
    const [facets, setFacets]     = React.useState(EMPTY_FACETS);
    const [query, setQuery]       = React.useState("");
    const [selected, setSelected] = React.useState("LB-18");
    const [checked, setChecked]   = React.useState(() => new Set());
    const [detailOpen, setDetailOpen] = React.useState(true);
    const [collapsedYears, setCollapsedYears] = React.useState(() => new Set());
    const { openMenu, menuNode } = window.LBB_useRowMenu();

    const scopeStyle  = (tweaks && tweaks.scopeStyle) || "segmented";
    const detailWidth = (tweaks && tweaks.detailWidth) || 380;

    const setView = (v) => {
      setViewState(v);
      const p = VIEW_PRESETS[v] || {};
      const f = EMPTY_FACETS();
      if (p.rating) p.rating.forEach(k => f.rating.add(k));
      if (p.decade) p.decade.forEach(k => f.decade.add(k));
      if (p.source) p.source.forEach(k => f.source.add(k));
      setFacets(f);
      if (p.scope) setScope(p.scope);
      if (v === "all") setScope("all");
    };

    const toggleFacet = (group, key) => {
      setFacets(f => {
        const next = { ...f, [group]: new Set(f[group]) };
        next[group].has(key) ? next[group].delete(key) : next[group].add(key);
        return next;
      });
    };
    const clearFacets = () => { setFacets(EMPTY_FACETS()); setViewState("all"); };
    const activeCount = Object.values(facets).reduce((n, s) => n + s.size, 0);

    const flag = (VIEW_PRESETS[view] || {}).flag;
    const q = query.trim().toLowerCase();

    const rows = LIB.ROWS.filter(r => {
      if (scope === "owned"   && !r.owned) return false;
      if (scope === "unowned" &&  r.owned) return false;
      if (flag && !r[flag]) return false;
      if (q && !(`${r.lb} ${r.loc} ${r.desc} ${r.title || ""} ${r.folder || ""}`.toLowerCase().includes(q))) return false;
      if (facets.decade.size && !facets.decade.has(decadeOf(r.year))) return false;
      if (facets.status.size && !facets.status.has(r.status)) return false;
      if (facets.rating.size && !facets.rating.has(r.rating)) return false;
      if (facets.source.size && !(r.src && facets.source.has(r.src))) return false;
      if (facets.files.size) {
        if (facets.files.has("Unconfirmed") && !r.unconf) return false;
        if (facets.files.has("No FP") && !r.nofp) return false;
        if (facets.files.has("Xref only") && !r.xref) return false;
        if (facets.files.has("Duplicates") && !r.dup) return false;
      }
      return true;
    });

    const viewCounts = {
      wishlist:    LIB.ROWS.filter(r => r.wish).length,
      duplicates:  LIB.ROWS.filter(r => r.dup).length,
      unconfirmed: LIB.ROWS.filter(r => r.unconf).length,
      nofp:        LIB.ROWS.filter(r => r.nofp).length,
    };

    const years = [...new Set(rows.map(r => r.year))].sort((a, b) => a - b);
    const selectedRow = LIB.ROWS.find(r => r.lb === selected) || null;
    const visibleRows = years.flatMap(y => collapsedYears.has(y) ? [] : rows.filter(r => r.year === y));

    React.useEffect(() => {
      const onKey = (e) => {
        if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
        const down = e.key === "ArrowDown" || e.key === "j";
        const up   = e.key === "ArrowUp"   || e.key === "k";
        if (!down && !up) return;
        e.preventDefault();
        if (!visibleRows.length) return;
        const i = visibleRows.findIndex(r => r.lb === selected);
        const next = i < 0 ? 0 : Math.min(Math.max(i + (down ? 1 : -1), 0), visibleRows.length - 1);
        setSelected(visibleRows[next].lb);
      };
      window.addEventListener("keydown", onKey);
      return () => window.removeEventListener("keydown", onKey);
    }, [visibleRows.map(r => r.lb).join(","), selected]);

    const toggleCheck = (lb) => setChecked(c => { const n = new Set(c); n.has(lb) ? n.delete(lb) : n.add(lb); return n; });

    const ownedCols = scope === "owned";
    const colCount = 9;

    const chips = [];
    Object.entries(facets).forEach(([g, set]) => {
      set.forEach(k => chips.push({ g, k, label: `${g === "files" ? "File" : g[0].toUpperCase() + g.slice(1)}: ${k}` }));
    });
    if (flag) chips.push({ g: "view", k: view, label: `View: ${view === "nofp" ? "No fingerprint" : view[0].toUpperCase() + view.slice(1)}` });

    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }} data-screen-label="Library (by recording)">
        {menuNode}

        {/* ── Toolbar ── */}
        <div style={{
          padding: "12px 20px",
          borderBottom: "1px solid var(--lbb-border)",
          display: "flex", alignItems: "center", gap: 10,
          background: "var(--sep-chrome-bg, var(--lbb-surface))", position: "relative", zIndex: 4,
        }}>
          {viewSwitch}
          <span style={{ width: 1, height: 22, background: "var(--lbb-border)" }}></span>
          <ScopeControl value={scope} variant={scopeStyle} onChange={(s) => { setScope(s); setViewState("all"); }} />
          <Input icon="search" placeholder="Search title, location, description, LB#, folder…" size="md"
            value={query} onChange={(e) => setQuery(e.target.value)} style={{ flex: 1, height: 32 }} />
          <Button variant="secondary" size="md" iconRight="chevDown">Columns</Button>
          <IconButton icon="download" title="Export (CSV · HTML · M3U)" />
          <IconButton icon="more" title="More" />
        </div>

        {/* ── Filter bar (replaces the left rail) ── */}
        <div style={{
          padding: "8px 20px", borderBottom: "1px solid var(--lbb-border)",
          display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
          background: "var(--sep-summary-bg, var(--lbb-surface))", position: "relative", zIndex: 3,
        }}>
          <ViewsMenu view={view} setView={setView} viewCounts={viewCounts} />
          <span style={{ width: 1, height: 20, background: "var(--lbb-border)" }}></span>
          <FacetMenu label="Decade" group="decade" facets={facets} toggleFacet={toggleFacet} items={LIB.FACETS.decade} width={220} />
          <FacetMenu label="Status" group="status" facets={facets} toggleFacet={toggleFacet} items={LIB.FACETS.status} />
          <FacetMenu label="Rating" group="rating" facets={facets} toggleFacet={toggleFacet} items={LIB.FACETS.rating} width={220} />
          <FacetMenu label="Source" group="source" facets={facets} toggleFacet={toggleFacet} items={LIB.FACETS.source} />
          {ownedCols && (
            <FacetMenu label="Files" group="files" facets={facets} toggleFacet={toggleFacet}
              items={[{ k: "Unconfirmed" }, { k: "No FP" }, { k: "Xref only" }, { k: "Duplicates" }]} />
          )}
          <div style={{ flex: 1 }}></div>
          {activeCount > 0 && (
            <Button variant="ghost" size="sm" icon="x" onClick={clearFacets}>Clear {activeCount}</Button>
          )}
        </div>

        {/* ── Summary strip ── */}
        <div style={{
          padding: "8px 20px", borderBottom: "1px solid var(--lbb-border)",
          display: "flex", alignItems: "center", gap: 12, fontSize: 12,
          background: "var(--sep-summary-bg, var(--lbb-surface))", minHeight: 36, position: "relative", zIndex: 1,
        }}>
          <span style={{ fontWeight: 700, color: "var(--lbb-fg)", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
            {rows.length} result{rows.length === 1 ? "" : "s"}
          </span>
          <span style={{ color: "var(--lbb-fg3)", whiteSpace: "nowrap" }}>
            of <strong style={{ color: "var(--lbb-fg2)", fontVariantNumeric: "tabular-nums" }}>{LIB.TOTALS.all.toLocaleString()}</strong> in master DB
          </span>

          {(chips.length > 0) && <span style={{ width: 1, height: 14, background: "var(--lbb-border)" }}></span>}
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {chips.map((c, i) => (
              <ActiveFilter key={i} label={c.label}
                onRemove={() => c.g === "view" ? setView("all") : toggleFacet(c.g, c.k)} />
            ))}
          </div>
          {activeCount > 0 && <Button variant="ghost" size="sm" icon="star">Save view</Button>}

          <div style={{ flex: 1 }}></div>
          <span style={{ color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
            You own <strong style={{ color: "var(--lbb-ok-fg)" }}>96%</strong> · 663 to go
          </span>
          <span style={{ width: 1, height: 14, background: "var(--lbb-border)" }}></span>
          <span style={{ color: "var(--lbb-fg3)" }}>Sort:</span>
          <Button variant="ghost" size="sm" iconRight="chevDown">LB# ↑</Button>
        </div>

        {/* ── Body: table · detail (no rail) ── */}
        <div style={{
          flex: 1, display: "flex", minHeight: 0, position: "relative",
          background: "var(--sep-body-bg, transparent)",
          gap: "var(--sep-body-gap, 0px)", padding: "var(--sep-body-pad, 0px)",
        }}>
          <div style={{
            flex: 1, overflow: "auto", minHeight: 0, minWidth: 0, position: "relative",
            background: "var(--sep-table-bg, transparent)",
            borderRadius: "var(--sep-radius, 0px)", boxShadow: "var(--sep-table-shadow, none)",
          }}>
            {rows.length === 0 ? (
              <div style={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, color: "var(--lbb-fg3)" }}>
                <Icon name="search" size={22} />
                <div style={{ fontSize: 13 }}>Nothing matches the current filters</div>
                <Button variant="secondary" size="sm" onClick={() => { clearFacets(); setQuery(""); setScope("all"); }}>Clear everything</Button>
              </div>
            ) : (
              <TableShell>
                {ownedCols ? (
                  <colgroup>
                    <col style={{ width: 3 }} /><col style={{ width: 34 }} />
                    <col style={{ width: 92 }} /><col style={{ width: 88 }} /><col style={{ width: 88 }} />
                    <col /><col style={{ width: 54 }} />
                    <col style={{ width: 250 }} /><col style={{ width: 180 }} />
                    <col style={{ width: 90 }} /><col style={{ width: 44 }} />
                  </colgroup>
                ) : (
                  <colgroup>
                    <col style={{ width: 3 }} /><col style={{ width: 34 }} />
                    <col style={{ width: 92 }} /><col style={{ width: 88 }} /><col style={{ width: 88 }} />
                    <col style={{ width: 240 }} /><col style={{ width: 54 }} />
                    <col /><col style={{ width: 60 }} />
                    <col style={{ width: 52 }} /><col style={{ width: 52 }} />
                  </colgroup>
                )}
                <thead>
                  <tr>
                    <TH> </TH>
                    <TH><input type="checkbox" readOnly checked={false} style={{ accentColor: "var(--lbb-accent-mid)" }} /></TH>
                    <TH>LB#</TH>
                    <TH>Status</TH>
                    <TH>Date</TH>
                    <TH>Location</TH>
                    <TH align="center">★</TH>
                    {ownedCols ? (
                      <React.Fragment>
                        <TH>Folder</TH>
                        <TH>Disk path</TH>
                        <TH>Confirmed</TH>
                        <TH align="center">FP</TH>
                      </React.Fragment>
                    ) : (
                      <React.Fragment>
                        <TH>Description</TH>
                        <TH align="right">Xref</TH>
                        <TH align="center">Own</TH>
                        <TH> </TH>
                      </React.Fragment>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {years.map(y => {
                    const yRows = rows.filter(r => r.year === y);
                    const open = !collapsedYears.has(y);
                    return (
                      <React.Fragment key={y}>
                        <GroupRow label={`${y}`} count={yRows.length} expanded={open} colSpan={colCount + 1}
                          onToggle={() => setCollapsedYears(s => { const n = new Set(s); n.has(y) ? n.delete(y) : n.add(y); return n; })} />
                        {open && yRows.map(r => (
                          <LibraryRow key={r.lb} r={r} ownedCols={ownedCols}
                            selected={selected === r.lb}
                            checked={checked.has(r.lb)}
                            onSelect={() => setSelected(r.lb)}
                            onMenu={(e) => openMenu(e, { title: r.lb + (r.title ? ` · ${r.title}` : ""), actions: window.LBB_recordingActions(r) })}
                            onCheck={() => toggleCheck(r.lb)} />
                        ))}
                      </React.Fragment>
                    );
                  })}
                  <tr><td colSpan={colCount + 2} style={{
                    textAlign: "center", padding: "12px 0", fontSize: 11, color: "var(--lbb-fg3)", fontStyle: "italic",
                  }}>Sample rows — the production table virtual-scrolls all {LIB.TOTALS.all.toLocaleString()} entries</td></tr>
                </tbody>
              </TableShell>
            )}
            <BulkBar count={checked.size} scope={scope} onClear={() => setChecked(new Set())} />
          </div>

          <DetailPanel row={selectedRow} open={detailOpen} onToggle={() => setDetailOpen(o => !o)} width={detailWidth} />
        </div>
      </div>
    );
  }

  function LibraryRow({ r, ownedCols, selected, checked, onSelect, onCheck, onMenu }) {
    const edge = r.status === "Missing" ? "warn"
               : r.status === "New" ? "info"
               : r.status === "Private" ? "info" : undefined;
    const pillTone = r.status === "Public" ? "ok" : edge || "mute";
    return (
      <TR edge={edge} selected={selected} onClick={onSelect} onContextMenu={onMenu}>
        <TD onClick={(e) => e.stopPropagation()} style={{ overflow: "visible" }}>
          <input type="checkbox" checked={checked} onChange={onCheck} onClick={(e) => e.stopPropagation()}
            style={{ accentColor: "var(--lbb-accent-mid)", cursor: "pointer" }} />
        </TD>
        <TD mono style={{ color: "var(--lbb-accent-mid)", fontWeight: 600 }}>{r.lb}</TD>
        <TD><Pill tone={pillTone} soft>{r.status}</Pill></TD>
        <TD mono>{r.date}</TD>
        <TD style={{ color: "var(--lbb-fg)" }}>{r.loc}</TD>
        <TD align="center"><RatingChip value={r.rating} /></TD>
        {ownedCols ? (
          <React.Fragment>
            <TD mono>{r.folder || "—"}</TD>
            <TD mono dim>{r.path || "—"}</TD>
            <TD mono dim>{r.conf || "—"}</TD>
            <TD align="center">
              {r.fp ? <Icon name="check" size={13} style={{ color: "var(--lbb-ok-bar)" }} />
                    : <Icon name="x" size={12} style={{ color: "var(--lbb-fg3)" }} />}
            </TD>
          </React.Fragment>
        ) : (
          <React.Fragment>
            <TD style={{ color: "var(--lbb-fg2)" }}>{r.desc}</TD>
            <TD align="right" mono dim>{r.xref || "—"}</TD>
            <TD align="center">
              {r.owned ? <Icon name="check" size={13} style={{ color: "var(--lbb-ok-bar)" }} />
                : r.wish ? <Icon name="star" size={12} style={{ color: "var(--lbb-warn-bar)" }} />
                : <Icon name="x" size={12} style={{ color: "var(--lbb-fg3)" }} />}
            </TD>
            <TD align="right" style={{ paddingRight: 12 }}>
              <Icon name="more" size={13} style={{ color: "var(--lbb-fg3)", cursor: "pointer" }} />
            </TD>
          </React.Fragment>
        )}
      </TR>
    );
  }

  window.LBB_LibU_Recording = LibURecording;
})();
