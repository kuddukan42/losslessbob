// libu-performance.jsx
// Unified Library — "By performance" lens. Same data, grouped by show
// (date + venue); recordings/families nest underneath. Shares chrome 1:1
// with the "By recording" lens: top filter bar (Views menu + per-facet
// dropdowns), removable chips in the summary strip, no left rail.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Chip, Input, IconButton, TableShell, TH, TR, TD, GroupRow,
          FilterMenu, MenuLabel } = window;
  const { PERF_RatingChip: RatingChip, PERF_SourceBadge: SourceBadge, PERF_SourceStrip: SourceStrip,
          PERF_FamilyStrip: FamilyStrip, PERF_MatchChip: MatchChip,
          PERF_CoverageChip: CoverageChip, PERF_DetailPanel: DetailPanel, PERF_BulkBar: BulkBar } = window;
  const PERF = window.LBB_PERF;

  const decadeOf = (year) => {
    if (!year) return null;
    const d = Math.floor((year % 100) / 10) * 10;
    return `${d === 0 ? "00" : d}s`;
  };

  const EMPTY_FACETS = () => ({
    decade: new Set(), coverage: new Set(), recordings: new Set(), source: new Set(), rating: new Set(),
  });

  const VIEW_PRESETS = {
    all:         {},
    next:        { coverage: ["Upgrade"] },
    sbdgap:      { recordings: ["Soundboard exists"], flag: "sbdUnowned" },
    multi:       { recordings: ["Multiple sources"] },
    gaps:        { coverage: ["Gap"] },
    wishlist:    { flag: "wish" },
    duplicates:  { flag: "dup" },
    unconfirmed: { flag: "unconf" },
  };

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
      { id: "next",   label: "Upgrade targets",     icon: "upload", count: 612 },
      { id: "sbdgap", label: "SBD exists, unowned",  icon: "spectro", count: 1980 },
      { id: "multi",  label: "Multi-source shows",   icon: "copy", count: 2210 },
    ];
    const HEALTH = [
      { id: "gaps",        label: "Coverage gaps",  icon: "alert" },
      { id: "wishlist",    label: "Wishlist shows", icon: "star" },
      { id: "duplicates",  label: "Has duplicates", icon: "copy" },
      { id: "unconfirmed", label: "Unconfirmed",    icon: "info" },
    ];
    const label = view === "all" ? "All performances"
      : (SAVED.find(v => v.id === view) || HEALTH.find(v => v.id === view) || {}).label || "Views";
    const lit = view !== "all";
    return (
      <FilterMenu label={label} icon="collection" count={0} width={252}
        buttonStyle={lit ? { background: "var(--lbb-accent-soft)", color: "var(--lbb-accent-mid)", borderColor: "var(--lbb-accent-mid)", fontWeight: 650 } : undefined}>
        {(close) => (
          <div>
            <MenuLabel>Saved views</MenuLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <ViewRow icon="library" label="All performances" active={view === "all"} onClick={() => { setView("all"); close(); }} />
              {SAVED.map(v => (
                <ViewRow key={v.id} icon={v.icon} label={v.label} count={v.count}
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

  function LibUPerformance({ tweaks, viewSwitch }) {
    const [view, setViewState]   = React.useState("all");
    const [facets, setFacets]    = React.useState(EMPTY_FACETS);
    const [query, setQuery]      = React.useState("");
    const [selected, setSelected]= React.useState("1981-06-29-earlscourt");
    const [checked, setChecked]  = React.useState(() => new Set());
    const [expanded, setExpanded]= React.useState(() => new Set(["1981-06-29-earlscourt"]));
    const [collapsedFams, setCollapsedFams] = React.useState(() => new Set());
    const [detailOpen, setDetailOpen] = React.useState(true);
    const [collapsedYears, setCollapsedYears] = React.useState(() => new Set());
    const { openMenu, menuNode } = window.LBB_useRowMenu();

    const detailWidth   = (tweaks && tweaks.detailWidth) || 400;
    const autoExpand     = tweaks ? tweaks.autoExpandMulti : false;
    const showLBColumn   = tweaks ? tweaks.showLBColumn !== false : true;
    const groupFamilies  = tweaks ? tweaks.groupFamilies !== false : true;
    const showMatch      = tweaks ? tweaks.showMatch !== false : true;

    const setView = (v) => {
      setViewState(v);
      const p = VIEW_PRESETS[v] || {};
      const f = EMPTY_FACETS();
      ["decade", "coverage", "recordings", "source", "rating"].forEach(g => (p[g] || []).forEach(k => f[g].add(k)));
      setFacets(f);
    };

    const toggleFacet = (group, key) => {
      setFacets(f => {
        const next = { ...f, [group]: new Set(f[group]) };
        next[group].has(key) ? next[group].delete(key) : next[group].add(key);
        return next;
      });
      setViewState("all");
    };
    const clearFacets = () => { setFacets(EMPTY_FACETS()); setViewState("all"); };
    const activeCount = Object.values(facets).reduce((n, s) => n + s.size, 0);

    const flag = (VIEW_PRESETS[view] || {}).flag;
    const q = query.trim().toLowerCase();

    const perfs = PERF.PERFS.filter(p => {
      const ru = PERF.rollup(p);
      const recs = p.recordings || [];
      if (q) {
        const hay = `${p.disp} ${p.venue} ${p.city} ${p.tour} ${p.leg || ""} ${p.title || ""} ${recs.map(r => `${r.lb} ${r.lineage || ""}`).join(" ")}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      if (facets.decade.size && !facets.decade.has(decadeOf(p.year))) return false;
      if (facets.coverage.size && !facets.coverage.has(ru.coverage)) return false;
      if (facets.source.size && !recs.some(r => r.src && facets.source.has(r.src))) return false;
      if (facets.rating.size && !facets.rating.has(ru.bestRating)) return false;
      if (facets.recordings.size) {
        const tests = {
          "Multiple sources": ru.multi,
          "Single recording": !ru.multi,
          "Soundboard exists": ru.hasSBD,
          "Audience only": recs.length > 0 && recs.every(r => r.src === "Audience"),
        };
        if (![...facets.recordings].every(k => tests[k])) return false;
      }
      if (flag === "sbdUnowned" && !recs.some(r => r.src === "Soundboard" && !r.owned)) return false;
      if (flag === "wish" && !recs.some(r => r.wish)) return false;
      if (flag === "dup" && !recs.some(r => r.dup)) return false;
      if (flag === "unconf" && !recs.some(r => r.unconf)) return false;
      return true;
    });

    const viewCounts = {
      gaps:        PERF.PERFS.filter(p => PERF.rollup(p).coverage === "Gap").length,
      wishlist:    PERF.PERFS.filter(p => p.recordings.some(r => r.wish)).length,
      duplicates:  PERF.PERFS.filter(p => p.recordings.some(r => r.dup)).length,
      unconfirmed: PERF.PERFS.filter(p => p.recordings.some(r => r.unconf)).length,
    };

    const years = [...new Set(perfs.map(p => p.year))].sort((a, b) => a - b);
    const selectedPerf = PERF.PERFS.find(p => p.id === selected) || null;
    const visiblePerfs = years.flatMap(y => collapsedYears.has(y) ? [] : perfs.filter(p => p.year === y));

    React.useEffect(() => {
      const onKey = (e) => {
        if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
        const down = e.key === "ArrowDown" || e.key === "j";
        const up   = e.key === "ArrowUp"   || e.key === "k";
        if (!down && !up) return;
        e.preventDefault();
        if (!visiblePerfs.length) return;
        const i = visiblePerfs.findIndex(p => p.id === selected);
        const next = i < 0 ? 0 : Math.min(Math.max(i + (down ? 1 : -1), 0), visiblePerfs.length - 1);
        setSelected(visiblePerfs[next].id);
      };
      window.addEventListener("keydown", onKey);
      return () => window.removeEventListener("keydown", onKey);
    }, [visiblePerfs.map(p => p.id).join(","), selected]);

    const toggleExpand = (id) => setExpanded(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
    const toggleCheck  = (id) => setChecked(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
    const toggleFam    = (key) => setCollapsedFams(s => { const n = new Set(s); n.has(key) ? n.delete(key) : n.add(key); return n; });
    const isExpanded = (p) => expanded.has(p.id) || (autoExpand && p.recordings.length > 1);

    const colCount = showLBColumn ? 9 : 8;

    const chips = [];
    Object.entries(facets).forEach(([g, set]) => {
      set.forEach(k => chips.push({ g, k, label: `${g === "recordings" ? "Recordings" : g[0].toUpperCase() + g.slice(1)}: ${k}` }));
    });

    const totalRecs = perfs.reduce((n, p) => n + p.recordings.length, 0);
    const totalFams = perfs.reduce((n, p) => n + PERF.families(p).length, 0);
    const gapsShown = perfs.filter(p => PERF.rollup(p).coverage === "Gap").length;

    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }} data-screen-label="Library (by performance)">
        {menuNode}

        {/* ── Toolbar ── */}
        <div style={{
          padding: "12px 20px", borderBottom: "1px solid var(--lbb-border)",
          display: "flex", alignItems: "center", gap: 10,
          background: "var(--sep-chrome-bg, var(--lbb-surface))", position: "relative", zIndex: 4,
        }}>
          {viewSwitch}
          <span style={{ width: 1, height: 22, background: "var(--lbb-border)" }}></span>
          <Input icon="search" placeholder="Search date, venue, city, tour, LB#, lineage…" size="md"
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
          <FacetMenu label="Decade" group="decade" facets={facets} toggleFacet={toggleFacet} items={PERF.FACETS.decade} width={220} />
          <FacetMenu label="Coverage" group="coverage" facets={facets} toggleFacet={toggleFacet} items={PERF.FACETS.coverage} />
          <FacetMenu label="Recordings" group="recordings" facets={facets} toggleFacet={toggleFacet} items={PERF.FACETS.recordings} width={250} />
          <FacetMenu label="Source" group="source" facets={facets} toggleFacet={toggleFacet} items={PERF.FACETS.source}
            width={250} render={(k) => (PERF.SOURCES[k] || {}).full || k} />
          <FacetMenu label="Rating" group="rating" facets={facets} toggleFacet={toggleFacet} items={PERF.FACETS.rating} width={220} />
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
            {perfs.length} show{perfs.length === 1 ? "" : "s"}
          </span>
          <span style={{ color: "var(--lbb-fg3)", whiteSpace: "nowrap" }}>
            · <strong style={{ color: "var(--lbb-fg2)", fontVariantNumeric: "tabular-nums" }}>{totalRecs}</strong> recordings
          </span>
          {groupFamilies && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5, color: "var(--lbb-info-fg)", whiteSpace: "nowrap", fontWeight: 600 }}>
              <Icon name="tapematch" size={12} />
              {totalFams} {totalFams === 1 ? "family" : "families"}
            </span>
          )}
          {gapsShown > 0 && (
            <span style={{ color: "var(--lbb-warn-fg)", whiteSpace: "nowrap", fontWeight: 600 }}>
              · {gapsShown} gap{gapsShown === 1 ? "" : "s"}
            </span>
          )}

          {(chips.length > 0) && <span style={{ width: 1, height: 14, background: "var(--lbb-border)" }}></span>}
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {chips.map((c, i) => (
              <ActiveFilter key={i} label={c.label} onRemove={() => toggleFacet(c.g, c.k)} />
            ))}
          </div>
          {activeCount > 0 && <Button variant="ghost" size="sm" icon="star">Save view</Button>}

          <div style={{ flex: 1 }}></div>
          <span style={{ color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
            Shows covered <strong style={{ color: "var(--lbb-ok-fg)" }}>85%</strong>
          </span>
          <span style={{ width: 1, height: 14, background: "var(--lbb-border)" }}></span>
          <span style={{ color: "var(--lbb-fg3)" }}>Sort:</span>
          <Button variant="ghost" size="sm" iconRight="chevDown">Date ↑</Button>
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
            {perfs.length === 0 ? (
              <div style={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, color: "var(--lbb-fg3)" }}>
                <Icon name="search" size={22} />
                <div style={{ fontSize: 13 }}>No performances match the current filters</div>
                <Button variant="secondary" size="sm" onClick={() => { clearFacets(); setQuery(""); }}>Clear everything</Button>
              </div>
            ) : (
              <TableShell>
                <colgroup>
                  <col style={{ width: 3 }} />
                  <col style={{ width: 30 }} /><col style={{ width: 32 }} />
                  <col style={{ width: 116 }} />
                  <col />
                  <col style={{ width: 210 }} />
                  <col style={{ width: 132 }} />
                  <col style={{ width: 56 }} />
                  <col style={{ width: 56 }} />
                  <col style={{ width: 150 }} />
                </colgroup>
                <thead>
                  <tr>
                    <TH> </TH>
                    <TH> </TH>
                    <TH><input type="checkbox" readOnly checked={false} style={{ accentColor: "var(--lbb-accent-mid)" }} /></TH>
                    <TH>Date</TH>
                    <TH>Performance</TH>
                    <TH>Tour · leg</TH>
                    <TH>{groupFamilies ? "Families" : "Sources"}</TH>
                    <TH align="center">Recs</TH>
                    <TH align="center">★</TH>
                    <TH>Coverage</TH>
                  </tr>
                </thead>
                <tbody>
                  {years.map(y => {
                    const yPerfs = perfs.filter(p => p.year === y);
                    const open = !collapsedYears.has(y);
                    const yRecs = yPerfs.reduce((n, p) => n + p.recordings.length, 0);
                    return (
                      <React.Fragment key={y}>
                        <GroupRow label={`${y} · ${yPerfs.length} show${yPerfs.length > 1 ? "s" : ""}`} count={yRecs} expanded={open} colSpan={colCount + 1}
                          onToggle={() => setCollapsedYears(s => { const n = new Set(s); n.has(y) ? n.delete(y) : n.add(y); return n; })} />
                        {open && yPerfs.map(p => (
                          <PerfRow key={p.id} p={p} showLB={showLBColumn}
                            group={groupFamilies} showMatch={showMatch}
                            collapsedFams={collapsedFams} onToggleFam={toggleFam}
                            selected={selected === p.id}
                            checked={checked.has(p.id)}
                            expanded={isExpanded(p)}
                            onSelect={() => setSelected(p.id)}
                            onToggleExpand={() => toggleExpand(p.id)}
                            onCheck={() => toggleCheck(p.id)}
                            onMenu={(e) => openMenu(e, { title: `${p.disp} · ${p.venue}`, actions: window.LBB_performanceActions(p, PERF.rollup(p)) })}
                            onSelectRec={() => setSelected(p.id)} />
                        ))}
                      </React.Fragment>
                    );
                  })}
                  <tr><td colSpan={colCount + 2} style={{
                    textAlign: "center", padding: "12px 0", fontSize: 11, color: "var(--lbb-fg3)", fontStyle: "italic",
                  }}>Sample shows — the production view virtual-scrolls all {PERF.TOTALS.performances.toLocaleString()} catalogued performances</td></tr>
                </tbody>
              </TableShell>
            )}
            <BulkBar count={checked.size} onClear={() => setChecked(new Set())} />
          </div>

          <DetailPanel perf={selectedPerf} open={detailOpen} onToggle={() => setDetailOpen(o => !o)} width={detailWidth} group={groupFamilies} />
        </div>
      </div>
    );
  }

  function ActiveFilter({ label, onRemove }) {
    return (
      <span style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        padding: "2px 4px 2px 8px", borderRadius: 4,
        background: "var(--lbb-accent-soft)", color: "var(--lbb-accent-mid)",
        fontSize: 11, fontWeight: 600, whiteSpace: "nowrap",
      }}>
        {label}
        <button type="button" onClick={onRemove} style={{
          width: 16, height: 16, borderRadius: 3, padding: 0, background: "transparent",
          border: "none", color: "currentColor", cursor: "pointer",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
        }}><Icon name="x" size={10} /></button>
      </span>
    );
  }

  function PerfRow({ p, showLB, group, showMatch, collapsedFams, onToggleFam, selected, checked, expanded, onSelect, onToggleExpand, onCheck, onSelectRec, onMenu }) {
    const ru = PERF.rollup(p);
    const fams = PERF.families(p);
    const edge = p.status === "Missing" ? "warn" : p.status === "New" ? "info" : undefined;
    const multi = p.recordings.length > 1;

    return (
      <React.Fragment>
        <TR edge={edge} selected={selected} onClick={onSelect} onContextMenu={onMenu}>
          <TD onClick={(e) => { e.stopPropagation(); if (multi) onToggleExpand(); }} style={{ overflow: "visible", paddingRight: 0, cursor: multi ? "pointer" : "default" }}>
            {multi && <Icon name={expanded ? "chevDown" : "chevRight"} size={13} style={{ color: "var(--lbb-fg3)" }} />}
          </TD>
          <TD onClick={(e) => e.stopPropagation()} style={{ overflow: "visible" }}>
            <input type="checkbox" checked={checked} onChange={onCheck} onClick={(e) => e.stopPropagation()}
              style={{ accentColor: "var(--lbb-accent-mid)", cursor: "pointer" }} />
          </TD>
          <TD mono style={{ color: "var(--lbb-fg)", fontWeight: 600 }}>
            <span style={{ display: "inline-flex", flexDirection: "column", lineHeight: 1.2 }}>
              <span>{p.disp}</span>
              <span style={{ fontSize: 9.5, color: "var(--lbb-fg3)", textTransform: "uppercase", letterSpacing: 0.4 }}>{p.dow}</span>
            </span>
          </TD>
          <TD style={{ color: "var(--lbb-fg)" }}>
            <span style={{ display: "inline-flex", flexDirection: "column", lineHeight: 1.25, minWidth: 0 }}>
              <span style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {p.venue}
                {p.title && <span style={{ marginLeft: 6, fontWeight: 500, fontStyle: "italic", color: "var(--lbb-accent-mid)", fontSize: 11.5 }}>“{p.title}”</span>}
              </span>
              <span style={{ fontSize: 11, color: "var(--lbb-fg3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.city}</span>
            </span>
          </TD>
          <TD dim style={{ fontSize: 11.5 }}>
            <span style={{ display: "inline-flex", flexDirection: "column", lineHeight: 1.25 }}>
              <span style={{ color: "var(--lbb-fg2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.tour}</span>
              <span style={{ fontSize: 10.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.leg}</span>
            </span>
          </TD>
          <TD style={{ overflow: "visible" }}>
            {group ? <FamilyStrip perf={p} /> : <SourceStrip recordings={p.recordings} />}
          </TD>
          <TD align="center" mono style={{ color: multi ? "var(--lbb-fg)" : "var(--lbb-fg3)", fontWeight: multi ? 700 : 500 }}>
            {group ? (
              <span style={{ display: "inline-flex", flexDirection: "column", lineHeight: 1.08, alignItems: "center" }}>
                <span>{ru.famTotal}</span>
                <span style={{ fontSize: 9, fontWeight: 500, color: "var(--lbb-fg3)" }}>{ru.total} rec</span>
              </span>
            ) : ru.total}
          </TD>
          <TD align="center"><RatingChip value={ru.bestRating} /></TD>
          <TD style={{ overflow: "visible" }}><CoverageChip coverage={ru.coverage} ownedCount={ru.ownedCount} total={ru.total} /></TD>
        </TR>

        {expanded && multi && group && fams.map((fam) => (
          <FamilyBlock key={fam.id} fam={fam} pid={p.id} showLB={showLB} showMatch={showMatch}
            collapsed={collapsedFams.has(`${p.id}::${fam.id}`)}
            onToggleFam={() => onToggleFam(`${p.id}::${fam.id}`)}
            onSelectRec={onSelectRec} />
        ))}

        {expanded && multi && !group && p.recordings.map((r, i) => (
          <tr key={i} onClick={onSelectRec} style={{ cursor: "pointer", background: "color-mix(in srgb, var(--lbb-surface2) 45%, transparent)" }}>
            <td style={{ width: 3, padding: 0, background: r.owned ? "var(--lbb-ok-bar)" : "transparent", borderBottom: "1px solid var(--lbb-border)" }}></td>
            <td style={{ borderBottom: "1px solid var(--lbb-border)" }}></td>
            <td style={{ borderBottom: "1px solid var(--lbb-border)" }}></td>
            <TD mono dim style={{ paddingLeft: 8 }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <span style={{ color: "var(--lbb-fg3)" }}>└</span>
                {showLB && <span style={{ color: "var(--lbb-accent-mid)", fontWeight: 600 }}>{r.lb}</span>}
              </span>
            </TD>
            <TD dim style={{ fontSize: 11.5 }}>{r.lineage}</TD>
            <TD dim style={{ fontSize: 11 }}>{r.src ? (PERF.SOURCES[r.src] || {}).full || r.src : "—"}</TD>
            <TD style={{ overflow: "visible" }}><SourceBadge src={r.src} owned={r.owned} /></TD>
            <TD align="center" mono dim style={{ fontSize: 10.5 }}>{r.owned ? r.size : "—"}</TD>
            <TD align="center"><RatingChip value={r.rating} /></TD>
            <TD style={{ overflow: "visible" }}>
              {r.owned ? <Pill tone="ok" soft dot>Owned</Pill>
                : r.wish ? <Pill tone="warn" soft>Wishlist</Pill> : <Pill tone="mute" soft>Not owned</Pill>}
            </TD>
          </tr>
        ))}
      </React.Fragment>
    );
  }

  function FamilyBlock({ fam, pid, showLB, showMatch, collapsed, onToggleFam, onSelectRec }) {
    const open = !collapsed;
    const headBg = fam.owned
      ? "color-mix(in srgb, var(--lbb-ok-bg) 26%, transparent)"
      : "color-mix(in srgb, var(--lbb-surface2) 55%, transparent)";
    const bar = fam.owned ? "var(--lbb-ok-bar)" : "var(--lbb-border2)";
    const single = !fam.multi;
    const lone = fam.members[0];

    return (
      <React.Fragment>
        <tr onClick={onSelectRec} style={{ cursor: "pointer", background: headBg }}>
          <td style={{ width: 3, padding: 0, background: bar, borderBottom: "1px solid var(--lbb-border)" }}></td>
          <td onClick={(e) => { e.stopPropagation(); if (fam.multi) onToggleFam(); }}
            style={{ borderBottom: "1px solid var(--lbb-border)", textAlign: "center", cursor: fam.multi ? "pointer" : "default" }}>
            {fam.multi && <Icon name={open ? "chevDown" : "chevRight"} size={12} style={{ color: "var(--lbb-fg3)" }} />}
          </td>
          <td style={{ borderBottom: "1px solid var(--lbb-border)" }}></td>
          <td colSpan={4} style={{ borderBottom: "1px solid var(--lbb-border)", padding: "4px 10px 4px var(--lbb-d-pad)", overflow: "hidden" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8, minWidth: 0, maxWidth: "100%" }}>
              <span style={{ color: "var(--lbb-fg3)", fontFamily: "var(--lbb-mono)", fontSize: 11, flex: "0 0 auto" }}>{fam.multi ? "├" : "└"}</span>
              <span style={{ flex: "0 0 auto" }}><SourceBadge src={fam.src} owned={fam.owned} /></span>
              <span style={{ fontSize: 12, fontWeight: 700, color: "var(--lbb-fg)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", flex: "0 1 auto", minWidth: 0 }}>{fam.label}</span>
              {single && showLB && (
                <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 11, fontWeight: 600, color: fam.owned ? "var(--lbb-accent-mid)" : "var(--lbb-fg3)", whiteSpace: "nowrap", flex: "0 0 auto" }}>{lone.lb}</span>
              )}
              {showMatch && fam.multi && <MatchChip by={fam.by} conf={fam.conf} />}
              {fam.dupes > 0 && <Pill tone="mute" soft style={{ fontSize: 9, padding: "0 5px" }}>{fam.dupes} dup</Pill>}
            </span>
          </td>
          <td style={{ borderBottom: "1px solid var(--lbb-border)", textAlign: "center", fontFamily: "var(--lbb-mono)", fontSize: 11, color: "var(--lbb-fg2)" }}>
            {fam.multi ? `×${fam.total}` : ""}
          </td>
          <td style={{ borderBottom: "1px solid var(--lbb-border)", textAlign: "center" }}><RatingChip value={fam.bestRating} /></td>
          <td style={{ borderBottom: "1px solid var(--lbb-border)", padding: "0 var(--lbb-d-pad)", overflow: "visible" }}>
            {fam.owned
              ? (fam.ownedCount < fam.total
                  ? <Pill tone="ok" soft dot>Own {fam.ownedCount}/{fam.total}</Pill>
                  : <Pill tone="ok" soft dot>Owned</Pill>)
              : lone && lone.wish ? <Pill tone="warn" soft>Wishlist</Pill> : <Pill tone="mute" soft>Not owned</Pill>}
          </td>
        </tr>

        {fam.multi && open && fam.members.map((r, i) => {
          const isCanon = r === fam.canonical;
          return (
            <tr key={i} onClick={onSelectRec} style={{ cursor: "pointer", background: "color-mix(in srgb, var(--lbb-surface2) 35%, transparent)" }}>
              <td style={{ width: 3, padding: 0, background: r.owned ? "var(--lbb-ok-bar)" : "transparent", borderBottom: "1px solid var(--lbb-border)" }}></td>
              <td style={{ borderBottom: "1px solid var(--lbb-border)" }}></td>
              <td style={{ borderBottom: "1px solid var(--lbb-border)" }}></td>
              <TD mono dim style={{ paddingLeft: 22 }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <span style={{ color: "var(--lbb-fg3)" }}>{i === fam.members.length - 1 ? "└" : "├"}</span>
                  {showLB && <span style={{ color: r.owned ? "var(--lbb-accent-mid)" : "var(--lbb-fg3)", fontWeight: 600 }}>{r.lb}</span>}
                </span>
              </TD>
              <TD dim style={{ fontSize: 11.5 }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6, minWidth: 0 }}>
                  {isCanon && <Pill tone="info" soft style={{ fontSize: 9, padding: "0 5px" }}>Best</Pill>}
                  {r.dup && <Pill tone="mute" soft style={{ fontSize: 9, padding: "0 5px" }}>dup</Pill>}
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.lineage}</span>
                </span>
              </TD>
              <TD dim style={{ fontSize: 11 }}>{r.src ? (PERF.SOURCES[r.src] || {}).full || r.src : "—"}</TD>
              <TD style={{ overflow: "visible" }}><SourceBadge src={r.src} owned={r.owned} /></TD>
              <TD align="center" mono dim style={{ fontSize: 10.5 }}>{r.owned ? r.size : "—"}</TD>
              <TD align="center"><RatingChip value={r.rating} /></TD>
              <TD style={{ overflow: "visible" }}>
                {r.owned ? <Pill tone="ok" soft dot>Owned</Pill>
                  : r.wish ? <Pill tone="warn" soft>Wishlist</Pill> : <Pill tone="mute" soft>Not owned</Pill>}
              </TD>
            </tr>
          );
        })}
      </React.Fragment>
    );
  }

  window.LBB_LibU_Performance = LibUPerformance;
})();
