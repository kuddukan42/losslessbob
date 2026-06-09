// mounts-routes.jsx
// Setup → Mounts & Routes card. Designs the GUI for the new collection routing
// backend: collection_mounts + collection_routes + pipeline_file_mode.
//
// Newbie-first, advanced-deep:
//   · Storage mounts — named drives with live online status, add/edit/delete.
//   · Year routing  — bulk-fill range row + a per-year table grouped by mount,
//                     a coverage strip that exposes gaps, and a dry-run preview.
//   · Filing mode   — move (default) / copy with a safety note.
//
// Maps 1:1 onto: GET/POST/PATCH/DELETE /api/collection/mounts,
//   GET/POST(bulk)/DELETE /api/collection/routes, /routes/preview/<year>,
//   and pipeline_file_mode in /api/db/settings.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Input, IconButton, TableShell, TH, TR, TD, GroupRow, Banner } = window;

  const YEAR_MIN = 1958, YEAR_MAX = 2026;

  // ── seed data — mirrors the two new tables ────────────────────────
  const SEED_MOUNTS = [
    { id: 1, label: "DYLAN1", root_path: "/mnt/dylan1", notes: "Pre-1980 · misc",       online: true  },
    { id: 2, label: "DYLAN2", root_path: "/mnt/dylan2", notes: "70s – 80s",             online: true  },
    { id: 3, label: "DYLAN3", root_path: "/mnt/dylan3", notes: "90s – 00s",             online: true  },
    { id: 4, label: "DYLAN4", root_path: "/mnt/dylan4", notes: "2010s+ · current pull", online: true  },
    { id: 5, label: "NAS-EXT", root_path: "/Volumes/NAS/dylan", notes: "Cold-storage overflow", online: false },
  ];

  // Build per-year routes. Each year gets sub_path = "{year}" under a decade drive.
  // Two years left unrouted (1973–1974) to demonstrate the gap state.
  function seedRoutes() {
    const r = [];
    for (let y = YEAR_MIN; y <= YEAR_MAX; y++) {
      if (y === 1973 || y === 1974) continue;          // intentional gaps
      let mount_id = 4;
      if (y < 1970) mount_id = 1;
      else if (y < 1990) mount_id = 2;
      else if (y < 2010) mount_id = 3;
      r.push({ year: y, mount_id, sub_path: String(y) });
    }
    return r;
  }

  const lbl = { fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" };
  const mono = "var(--lbb-mono)";

  // Card shell — identical to screen-settings SetupCard.
  function SetupCard({ title, badge, children, style }) {
    return (
      <div style={{ background: "var(--lbb-surface)", border: "1px solid var(--lbb-border)", borderRadius: 10, padding: 18, ...style }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
          <h4 style={{ margin: 0, fontSize: 12, fontWeight: 700, letterSpacing: 0.08, textTransform: "uppercase", color: "var(--lbb-fg)" }}>{title}</h4>
          {badge}
        </div>
        {children}
      </div>
    );
  }

  // Subsection divider with eyebrow label + helper.
  function Sub({ n, title, help, right, children }) {
    return (
      <div style={{ marginTop: 22, paddingTop: 18, borderTop: "1px solid var(--lbb-border)" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 12 }}>
          <span style={{ width: 18, height: 18, flex: "0 0 18px", borderRadius: 5, background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border2)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, color: "var(--lbb-fg2)", fontFamily: mono }}>{n}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--lbb-fg)" }}>{title}</div>
            {help && <div style={{ fontSize: 11.5, color: "var(--lbb-fg3)", marginTop: 2, lineHeight: 1.4 }}>{help}</div>}
          </div>
          {right}
        </div>
        {children}
      </div>
    );
  }

  function OnlineDot({ online }) {
    return (
      <span title={online ? "Online · reachable" : "Offline · not mounted"} style={{
        width: 9, height: 9, flex: "0 0 9px", borderRadius: "50%",
        background: online ? "var(--lbb-ok-bar)" : "var(--lbb-bad-bar)",
        boxShadow: online ? "0 0 0 3px var(--lbb-ok-bg)" : "0 0 0 3px var(--lbb-bad-bg)",
      }} />
    );
  }

  // ── Mount card ────────────────────────────────────────────────────
  function MountCard({ m, routeCount, onEdit, onDelete }) {
    const [hover, setHover] = React.useState(false);
    return (
      <div onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
        style={{ position: "relative", padding: "12px 14px", borderRadius: 9, border: `1px solid ${m.online ? "var(--lbb-border)" : "var(--lbb-bad-bar)"}`, background: m.online ? "var(--lbb-surface)" : "var(--lbb-bad-bg)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
          <OnlineDot online={m.online} />
          <span style={{ fontFamily: mono, fontSize: 13, fontWeight: 700, color: "var(--lbb-fg)" }}>{m.label}</span>
          <div style={{ flex: 1 }} />
          {!m.online && <Pill tone="bad" soft>offline</Pill>}
          <div style={{ display: "flex", gap: 2, opacity: hover ? 1 : 0, transition: "opacity 120ms" }}>
            <IconButton icon="rename" size={24} title="Edit mount" onClick={() => onEdit(m)} />
            <IconButton icon="trash" size={24} title="Delete mount" onClick={() => onDelete(m)} />
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontFamily: mono, fontSize: 11.5, color: "var(--lbb-fg2)", marginBottom: 6 }}>
          <Icon name="folder" size={12} style={{ color: "var(--lbb-fg3)", flex: "0 0 auto" }} />
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.root_path}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, color: "var(--lbb-fg3)", flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.notes || "—"}</span>
          <span style={{ fontSize: 10.5, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums", flex: "0 0 auto" }}>
            {routeCount ? `${routeCount} ${routeCount === 1 ? "year" : "years"}` : "no years"}
          </span>
        </div>
      </div>
    );
  }

  // ── Add / edit mount form ─────────────────────────────────────────
  function MountForm({ initial, onSave, onCancel }) {
    const [label, setLabel] = React.useState(initial?.label || "");
    const [root, setRoot]   = React.useState(initial?.root_path || "");
    const [notes, setNotes] = React.useState(initial?.notes || "");
    const valid = label.trim() && root.trim();
    return (
      <div style={{ padding: "14px 16px", borderRadius: 9, border: "1px solid var(--lbb-accent-mid)", background: "var(--lbb-accent-soft)" }}>
        <div style={{ display: "grid", gridTemplateColumns: "150px 1fr auto", gap: 10, alignItems: "end" }}>
          <div>
            <div style={{ ...lbl, marginBottom: 4 }}>Label</div>
            <Input placeholder="DYLAN5" value={label} onChange={e => setLabel(e.target.value.toUpperCase())} style={{ width: "100%", background: "var(--lbb-surface)" }} />
          </div>
          <div>
            <div style={{ ...lbl, marginBottom: 4 }}>Root path</div>
            <div style={{ display: "flex", gap: 6 }}>
              <Input icon="folder" placeholder="/mnt/dylan5  ·  D:\\Dylan" value={root} onChange={e => setRoot(e.target.value)} style={{ flex: 1, background: "var(--lbb-surface)" }} />
              <Button variant="secondary" icon="reveal" title="Browse… (Electron folder picker)">Browse…</Button>
            </div>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <Button variant="ghost" onClick={onCancel}>Cancel</Button>
            <Button variant="primary" icon="check" disabled={!valid} onClick={() => onSave({ label: label.trim(), root_path: root.trim(), notes: notes.trim() })}>{initial ? "Save" : "Add mount"}</Button>
          </div>
        </div>
        <div style={{ marginTop: 10 }}>
          <div style={{ ...lbl, marginBottom: 4 }}>Notes <span style={{ textTransform: "none", fontWeight: 500 }}>· optional</span></div>
          <Input placeholder="What lives on this drive…" value={notes} onChange={e => setNotes(e.target.value)} style={{ width: "100%", background: "var(--lbb-surface)" }} />
        </div>
      </div>
    );
  }

  // ── Bulk-fill range row — the fast path ───────────────────────────
  function BulkFill({ mounts, onApply }) {
    const [from, setFrom] = React.useState("1958");
    const [to, setTo]     = React.useState("1969");
    const [mountId, setMountId] = React.useState(mounts[0]?.id);
    const [mode, setMode] = React.useState("per-year");   // per-year | flat | custom
    const [custom, setCustom] = React.useState("");
    const mount = mounts.find(m => m.id === mountId);

    const exampleSub = mode === "per-year" ? "{year}" : mode === "flat" ? "" : (custom || "…");
    const exampleDest = `${mount?.root_path || ""}${exampleSub ? "/" + exampleSub : ""}/`;
    const span = Math.max(0, (parseInt(to) || 0) - (parseInt(from) || 0) + 1);

    return (
      <div style={{ padding: "13px 15px", borderRadius: 9, background: "var(--lbb-surface2)", border: "1px dashed var(--lbb-border2)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap" }}>
          <Icon name="filter" size={13} style={{ color: "var(--lbb-fg3)" }} />
          <span style={{ fontSize: 12, color: "var(--lbb-fg2)", fontWeight: 600 }}>Route years</span>
          <Input value={from} onChange={e => setFrom(e.target.value)} size="sm" style={{ width: 60 }} />
          <span style={{ color: "var(--lbb-fg3)" }}>–</span>
          <Input value={to} onChange={e => setTo(e.target.value)} size="sm" style={{ width: 60 }} />
          <span style={{ fontSize: 12, color: "var(--lbb-fg2)", marginLeft: 4 }}>to</span>
          {/* mount select (native, themed) */}
          <div style={{ position: "relative", display: "inline-flex" }}>
            <select value={String(mountId)} onChange={e => setMountId(+e.target.value)} style={selectStyle}>
              {mounts.map(m => <option key={m.id} value={String(m.id)}>{m.label}{m.online ? "" : "  (offline)"}</option>)}
            </select>
            <Icon name="chevDown" size={12} style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", pointerEvents: "none", color: "var(--lbb-fg3)" }} />
          </div>
          <div style={{ flex: 1 }} />
          <Button variant="primary" icon="check"
            onClick={() => onApply({ from: parseInt(from), to: parseInt(to), mount_id: mountId, mode, custom: custom.trim() })}>
            Apply to {span || 0} {span === 1 ? "year" : "years"}
          </Button>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 11, flexWrap: "wrap" }}>
          <span style={lbl}>Sub-path</span>
          <div style={{ display: "flex", gap: 2, padding: 2, background: "var(--lbb-surface)", borderRadius: 7, border: "1px solid var(--lbb-border)" }}>
            {[["per-year", "Per-year", "/2014"], ["flat", "Flat", "root"], ["custom", "Custom", "…"]].map(([k, label]) => (
              <button key={k} onClick={() => setMode(k)} style={{
                padding: "4px 11px", borderRadius: 5, cursor: "pointer", fontFamily: "inherit", fontSize: 11.5,
                fontWeight: mode === k ? 600 : 500, border: "1px solid transparent",
                background: mode === k ? "var(--lbb-accent-soft)" : "transparent",
                color: mode === k ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)",
                borderColor: mode === k ? "var(--lbb-accent-mid)" : "transparent",
              }}>{label}</button>
            ))}
          </div>
          {mode === "custom" && <Input placeholder="1960s/{year}" value={custom} onChange={e => setCustom(e.target.value)} size="sm" style={{ width: 160 }} />}
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 11, color: "var(--lbb-fg3)", fontFamily: mono, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            e.g. <span style={{ color: "var(--lbb-fg2)" }}>{exampleDest}</span><span style={{ opacity: 0.6 }}>folder/</span>
          </span>
        </div>
      </div>
    );
  }

  const selectStyle = {
    appearance: "none", WebkitAppearance: "none",
    height: 24, padding: "0 24px 0 10px", borderRadius: 6,
    border: "1px solid var(--lbb-border2)", background: "var(--lbb-surface)",
    color: "var(--lbb-fg)", fontFamily: mono, fontSize: 11.5, fontWeight: 600,
    cursor: "pointer", outline: "none",
  };

  // ── Routes table, grouped by mount ────────────────────────────────
  function RoutesTable({ routes, mounts, expanded, onToggle, onChangeRow, onDeleteRow }) {
    const byMount = mounts.map(m => ({
      m, rows: routes.filter(r => r.mount_id === m.id).sort((a, b) => a.year - b.year),
    })).filter(g => g.rows.length);

    return (
      <div style={{ border: "1px solid var(--lbb-border)", borderRadius: 8, overflow: "hidden" }}>
        <TableShell stickyHeader={false}>
          <colgroup>
            <col style={{ width: 3 }} /><col style={{ width: 84 }} /><col style={{ width: 150 }} />
            <col style={{ width: 150 }} /><col /><col style={{ width: 44 }} />
          </colgroup>
          <thead><tr>
            <th style={{ width: 3, padding: 0, background: "var(--lbb-surface2)", borderBottom: "1px solid var(--lbb-border2)" }} />
            <TH>Year</TH><TH>Mount</TH><TH>Sub-path</TH><TH>Resolved destination</TH><TH> </TH>
          </tr></thead>
          <tbody>
            {byMount.map(({ m, rows }) => {
              const span = `${rows[0].year}–${rows[rows.length - 1].year}`;
              const open = expanded.has(m.id);
              return (
                <React.Fragment key={m.id}>
                  <tr>
                    <td style={{ width: 3, padding: 0, background: m.online ? "var(--lbb-ok-bar)" : "var(--lbb-bad-bar)" }} />
                    <td colSpan={5} onClick={() => onToggle(m.id)} style={{ padding: "6px 12px", background: "var(--lbb-surface2)", cursor: "pointer", borderBottom: "1px solid var(--lbb-border)", borderTop: "1px solid var(--lbb-border)" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                        <Icon name={open ? "chevDown" : "chevRight"} size={12} style={{ color: "var(--lbb-fg3)" }} />
                        <OnlineDot online={m.online} />
                        <span style={{ fontFamily: mono, fontSize: 12, fontWeight: 700, color: "var(--lbb-fg)" }}>{m.label}</span>
                        <span style={{ fontSize: 11, color: "var(--lbb-fg3)" }}>· {span}</span>
                        <span style={{ fontSize: 11, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums" }}>· {rows.length} {rows.length === 1 ? "year" : "years"}</span>
                        <span style={{ marginLeft: "auto", fontFamily: mono, fontSize: 11, color: "var(--lbb-fg3)" }}>{m.root_path}/<span style={{ color: "var(--lbb-fg2)" }}>{`{year}`}</span>/</span>
                      </div>
                    </td>
                  </tr>
                  {open && rows.map(r => (
                    <RouteRow key={r.year} r={r} m={m} mounts={mounts} onChange={onChangeRow} onDelete={onDeleteRow} />
                  ))}
                </React.Fragment>
              );
            })}
          </tbody>
        </TableShell>
      </div>
    );
  }

  function RouteRow({ r, m, mounts, onChange, onDelete }) {
    const dest = `${m.root_path}${r.sub_path ? "/" + r.sub_path : ""}/`;
    return (
      <TR>
        <TD mono style={{ color: "var(--lbb-fg)", fontWeight: 600 }}>{r.year}</TD>
        <TD>
          <div style={{ position: "relative", display: "inline-flex" }}>
            <select value={String(r.mount_id)} onChange={e => onChange(r.year, { mount_id: +e.target.value })} style={{ ...selectStyle, fontWeight: 500 }}>
              {mounts.map(mm => <option key={mm.id} value={String(mm.id)}>{mm.label}</option>)}
            </select>
            <Icon name="chevDown" size={11} style={{ position: "absolute", right: 7, top: "50%", transform: "translateY(-50%)", pointerEvents: "none", color: "var(--lbb-fg3)" }} />
          </div>
        </TD>
        <TD>
          <input value={r.sub_path} onChange={e => onChange(r.year, { sub_path: e.target.value })} placeholder="(flat)"
            style={{ width: "100%", height: 24, padding: "0 8px", borderRadius: 6, border: "1px solid var(--lbb-border)", background: "var(--lbb-surface)", color: "var(--lbb-fg)", fontFamily: mono, fontSize: 11.5, outline: "none" }} />
        </TD>
        <TD mono dim style={{ color: "var(--lbb-fg3)" }}>{dest}<span style={{ opacity: 0.55 }}>folder/</span></TD>
        <TD align="center"><IconButton icon="x" size={22} title={`Remove ${r.year}`} onClick={() => onDelete(r.year)} /></TD>
      </TR>
    );
  }

  // ── Coverage strip — every year between min/max, gaps exposed ──────
  function Coverage({ routes, mounts }) {
    const tone = { 1: "var(--lbb-ok-bar)", 2: "var(--lbb-info-bar)", 3: "var(--lbb-accent-mid)", 4: "var(--lbb-warn-bar)", 5: "var(--lbb-fg3)" };
    const map = new Map(routes.map(r => [r.year, r.mount_id]));
    const years = [];
    for (let y = YEAR_MIN; y <= YEAR_MAX; y++) years.push(y);
    const gaps = years.filter(y => !map.has(y));
    const total = years.length, routed = total - gaps.length;
    return (
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
          <span style={lbl}>Coverage</span>
          <span style={{ fontSize: 11.5, color: "var(--lbb-fg2)", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{routed} of {total} years routed</span>
          {gaps.length > 0
            ? <Pill tone="warn" soft dot>{gaps.length} unrouted</Pill>
            : <Pill tone="ok" soft dot>complete</Pill>}
          <div style={{ flex: 1 }} />
          {gaps.length > 0 && <span style={{ fontSize: 11, color: "var(--lbb-warn-fg)", fontFamily: mono }}>gap: {gaps.join(", ")}</span>}
        </div>
        <div style={{ display: "flex", gap: 1.5, height: 26, borderRadius: 6, overflow: "hidden", border: "1px solid var(--lbb-border)" }}>
          {years.map(y => {
            const mid = map.get(y);
            const gap = !mid;
            return (
              <div key={y} title={gap ? `${y} · no route` : `${y} · ${mounts.find(m => m.id === mid)?.label}`}
                style={{ flex: 1, background: gap ? "var(--lbb-bad-bg)" : tone[mid] || "var(--lbb-fg3)", position: "relative",
                  borderTop: gap ? "2px solid var(--lbb-bad-bar)" : "none", boxSizing: "border-box" }} />
            );
          })}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 10, color: "var(--lbb-fg3)", fontFamily: mono }}>
          <span>{YEAR_MIN}</span><span>{Math.round((YEAR_MIN + YEAR_MAX) / 2)}</span><span>{YEAR_MAX}</span>
        </div>
        <div style={{ display: "flex", gap: 14, marginTop: 9, flexWrap: "wrap" }}>
          {mounts.filter(m => routes.some(r => r.mount_id === m.id)).map(m => (
            <span key={m.id} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--lbb-fg2)" }}>
              <span style={{ width: 11, height: 11, borderRadius: 3, background: tone[m.id] }} />{m.label}
            </span>
          ))}
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--lbb-fg2)" }}>
            <span style={{ width: 11, height: 11, borderRadius: 3, background: "var(--lbb-bad-bg)", border: "2px solid var(--lbb-bad-bar)", boxSizing: "border-box" }} />unrouted
          </span>
        </div>
      </div>
    );
  }

  // ── Dry-run preview — GET /api/collection/routes/preview/<year> ────
  function PreviewTester({ routes, mounts }) {
    const [year, setYear] = React.useState("1966");
    const r = routes.find(x => x.year === parseInt(year));
    const m = r && mounts.find(x => x.id === r.mount_id);
    let out;
    if (!parseInt(year)) out = { tone: "mute", text: "Enter a year to test the route" };
    else if (!r) out = { tone: "bad", icon: "alert", text: `No route configured for ${year}` };
    else out = { tone: m.online ? "ok" : "warn", icon: m.online ? "check" : "alert",
      dest: `${m.root_path}${r.sub_path ? "/" + r.sub_path : ""}/`, label: m.label, online: m.online };

    return (
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 14px", borderRadius: 8, background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)" }}>
        <span style={lbl}>Test a year</span>
        <Input value={year} onChange={e => setYear(e.target.value)} size="sm" style={{ width: 76 }} />
        <Icon name="chevRight" size={14} style={{ color: "var(--lbb-fg3)" }} />
        {out.dest ? (
          <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0 }}>
            <span style={{ fontFamily: mono, fontSize: 12.5, color: "var(--lbb-fg)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{out.dest}</span>
            <Pill tone={out.online ? "ok" : "warn"} soft dot style={{ flex: "0 0 auto" }}>{out.label} · {out.online ? "online" : "offline"}</Pill>
          </div>
        ) : (
          <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1 }}>
            <Pill tone={out.tone} soft dot={out.tone !== "mute"}>{out.text}</Pill>
          </div>
        )}
      </div>
    );
  }

  // ── Filing mode — pipeline_file_mode ──────────────────────────────
  function FileMode({ mode, onChange }) {
    return (
      <div>
        <div style={{ display: "flex", gap: 10 }}>
          {[["move", "Move", "Source folder is relocated — nothing left behind. Recommended.", "drop"],
            ["copy", "Copy", "Source is duplicated and left in place. Clean up staging yourself.", "copy"]].map(([k, label, desc, icon]) => {
            const on = mode === k;
            return (
              <label key={k} style={{ flex: 1, display: "flex", gap: 11, padding: "12px 14px", borderRadius: 9, cursor: "pointer",
                background: on ? "var(--lbb-accent-soft)" : "var(--lbb-surface)", border: `1px solid ${on ? "var(--lbb-accent-mid)" : "var(--lbb-border)"}` }}>
                <input type="radio" name="filemode" checked={on} onChange={() => onChange(k)} style={{ marginTop: 2 }} />
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                    <Icon name={icon} size={14} style={{ color: on ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)" }} />
                    <span style={{ fontSize: 13, fontWeight: 700, color: on ? "var(--lbb-accent-mid)" : "var(--lbb-fg)" }}>{label}</span>
                    {k === "move" && <Pill tone="mute" soft>default</Pill>}
                  </div>
                  <div style={{ fontSize: 11.5, color: "var(--lbb-fg2)", marginTop: 4, lineHeight: 1.45 }}>{desc}</div>
                </div>
              </label>
            );
          })}
        </div>
        {mode === "copy" && (
          <div style={{ marginTop: 10 }}>
            <Banner tone="warn" icon="alert" title="Copy mode leaves originals in place">
              Filed folders are duplicated to the collection mount; the staging copy is <strong>not removed</strong>. Reclaim space by clearing staging manually once you’ve confirmed the copy.
            </Banner>
          </div>
        )}
      </div>
    );
  }

  // ── Main ──────────────────────────────────────────────────────────
  function MountsRoutes() {
    const [mounts, setMounts] = React.useState(SEED_MOUNTS);
    const [routes, setRoutes] = React.useState(seedRoutes);
    const [adding, setAdding] = React.useState(false);
    const [editId, setEditId] = React.useState(null);
    const [expanded, setExpanded] = React.useState(() => new Set([4]));   // current decade open
    const [showAll, setShowAll] = React.useState(false);
    const [fileMode, setFileMode] = React.useState("move");
    const nextId = React.useRef(6);

    const routeCount = (id) => routes.filter(r => r.mount_id === id).length;
    const toggle = (id) => setExpanded(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

    function saveMount(data) {
      if (editId) { setMounts(ms => ms.map(m => m.id === editId ? { ...m, ...data } : m)); setEditId(null); }
      else { setMounts(ms => [...ms, { id: nextId.current++, online: true, ...data }]); setAdding(false); }
    }
    function deleteMount(m) {
      if (routeCount(m.id)) return;   // backend returns 409 — UI just disables
      setMounts(ms => ms.filter(x => x.id !== m.id));
    }
    function applyBulk({ from, to, mount_id, mode, custom }) {
      if (!from || !to || from > to) return;
      setRoutes(rs => {
        const map = new Map(rs.map(r => [r.year, r]));
        for (let y = from; y <= to; y++) {
          const sub_path = mode === "per-year" ? String(y) : mode === "flat" ? "" : custom;
          map.set(y, { year: y, mount_id, sub_path });
        }
        return [...map.values()].sort((a, b) => a.year - b.year);
      });
      setExpanded(s => new Set([...s, mount_id]));
    }
    const changeRow = (year, patch) => setRoutes(rs => rs.map(r => r.year === year ? { ...r, ...patch } : r));
    const deleteRow = (year) => setRoutes(rs => rs.filter(r => r.year !== year));

    const allOpen = mounts.every(m => !routeCount(m.id) || expanded.has(m.id));
    const offlineCount = mounts.filter(m => !m.online).length;

    return (
      <SetupCard title="Mounts & Routes"
        badge={<Pill tone="info" soft dot>{mounts.length} mounts · {routes.length} routed years</Pill>}>
        <Banner tone="info" icon="info">
          When a folder reaches the <strong>File</strong> step, its show year picks a storage drive and sub-folder from the table below, then the folder is moved (or copied) there and registered in My Collection. Set up your drives once — routing then runs automatically for every filing.
        </Banner>

        {/* 1 · Storage mounts */}
        <Sub n="1" title="Storage mounts" help="The drives, NAS shares, or folders your collection spans. Status updates live from whether each path is currently reachable."
          right={!adding && !editId && <Button variant="secondary" size="sm" icon="plus" onClick={() => { setAdding(true); setEditId(null); }}>Add mount</Button>}>
          {offlineCount > 0 && (
            <div style={{ marginBottom: 10 }}>
              <Banner tone="warn" icon="alert">
                <strong>{offlineCount} mount {offlineCount === 1 ? "is" : "are"} offline.</strong> Folders routed to an offline drive can’t be filed until it’s reconnected — the Pipeline will hold them at the File step.
              </Banner>
            </div>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
            {mounts.map(m => editId === m.id
              ? <div key={m.id} style={{ gridColumn: "span 3" }}><MountForm initial={m} onSave={saveMount} onCancel={() => setEditId(null)} /></div>
              : <MountCard key={m.id} m={m} routeCount={routeCount(m.id)} onEdit={(mm) => { setEditId(mm.id); setAdding(false); }} onDelete={deleteMount} />)}
          </div>
          {adding && <div style={{ marginTop: 10 }}><MountForm onSave={saveMount} onCancel={() => setAdding(false)} /></div>}
        </Sub>

        {/* 2 · Year routing */}
        <Sub n="2" title="Year routing" help="Each concert year maps to one mount + sub-path. Use the range filler for whole decades; fine-tune any single year in the table."
          right={
            <button onClick={() => { setShowAll(v => !v); setExpanded(allOpen ? new Set() : new Set(mounts.map(m => m.id))); }}
              style={{ background: "none", border: "none", color: "var(--lbb-accent-mid)", font: "inherit", fontSize: 11.5, fontWeight: 600, cursor: "pointer" }}>
              {allOpen ? "Collapse all" : "Expand all years"}
            </button>
          }>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <BulkFill mounts={mounts} onApply={applyBulk} />
            <RoutesTable routes={routes} mounts={mounts} expanded={expanded} onToggle={toggle} onChangeRow={changeRow} onDeleteRow={deleteRow} />
            <Coverage routes={routes} mounts={mounts} />
            <PreviewTester routes={routes} mounts={mounts} />
          </div>
        </Sub>

        {/* 3 · Filing mode */}
        <Sub n="3" title="Filing mode" help="What happens to the staging folder once it’s written to the collection mount.">
          <FileMode mode={fileMode} onChange={setFileMode} />
        </Sub>
      </SetupCard>
    );
  }

  window.LBB_MountsRoutes = MountsRoutes;
})();
