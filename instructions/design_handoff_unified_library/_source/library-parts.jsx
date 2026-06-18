// library-parts.jsx
// Sub-components for the unified Library screen:
// ScopeControl, FacetRail, DetailPanel, BulkBar + small helpers.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Chip, IconButton, Banner } = window;
  const LIB = window.LBB_LIB;

  // ── Rating chip ─────────────────────────────────────────────────────
  function RatingChip({ value }) {
    if (!value || value === "—") return <span style={{ color: "var(--lbb-fg3)" }}>—</span>;
    const tone = (value === "A" || value === "A−") ? "ok"
               : (value === "B+" || value === "B") ? "info"
               : value === "B−" ? "warn" : "mute";
    return <Pill tone={tone} soft>{value}</Pill>;
  }

  // ── Scope control — the ownership lens ──────────────────────────────
  const SCOPES = [
    { id: "all",     label: "Everything",    n: LIB.TOTALS.all },
    { id: "owned",   label: "My collection", n: LIB.TOTALS.owned },
    { id: "unowned", label: "Not owned",     n: LIB.TOTALS.unowned },
  ];

  function ScopeControl({ value, onChange, variant = "segmented" }) {
    if (variant === "chips") {
      return (
        <div style={{ display: "flex", gap: 6 }}>
          {SCOPES.map(s => (
            <Chip key={s.id} active={value === s.id} count={s.n} onClick={() => onChange(s.id)}>{s.label}</Chip>
          ))}
        </div>
      );
    }
    return (
      <div style={{
        display: "flex", padding: 2, borderRadius: 8, flex: "0 0 auto",
        background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)",
      }}>
        {SCOPES.map(s => {
          const active = value === s.id;
          return (
            <button key={s.id} type="button" onClick={() => onChange(s.id)} style={{
              display: "inline-flex", alignItems: "center", gap: 7,
              height: 28, padding: "0 12px", borderRadius: 6,
              background: active ? "var(--lbb-surface)" : "transparent",
              color: active ? "var(--lbb-fg)" : "var(--lbb-fg2)",
              border: active ? "1px solid var(--lbb-border2)" : "1px solid transparent",
              boxShadow: active ? "var(--lbb-shadow)" : "none",
              fontSize: 12, fontWeight: active ? 650 : 500,
              cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap",
            }}>
              {s.label}
              <span style={{
                fontSize: 10.5, fontVariantNumeric: "tabular-nums",
                color: active ? "var(--lbb-accent-mid)" : "var(--lbb-fg3)",
                fontWeight: 600,
              }}>{s.n.toLocaleString()}</span>
            </button>
          );
        })}
      </div>
    );
  }

  // ── Active-filter chip (summary strip) ──────────────────────────────
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
          width: 16, height: 16, borderRadius: 3, padding: 0,
          background: "transparent", border: "none", color: "currentColor",
          cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center",
        }}><Icon name="x" size={10} /></button>
      </span>
    );
  }

  // ── Facet rail ──────────────────────────────────────────────────────
  function FacetGroup({ title, open = true, onToggle, children }) {
    return (
      <div style={{ marginTop: 16 }}>
        <button type="button" onClick={onToggle} style={{
          display: "flex", alignItems: "center", width: "100%", marginBottom: open ? 8 : 0,
          fontSize: 10.5, fontWeight: 700, letterSpacing: 0.1, textTransform: "uppercase",
          color: "var(--lbb-fg3)", background: "transparent", border: "none",
          padding: 0, cursor: "pointer", fontFamily: "inherit",
        }}>
          <span style={{ flex: 1, textAlign: "left" }}>{title}</span>
          <Icon name={open ? "chevDown" : "chevRight"} size={11} />
        </button>
        {open && <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>{children}</div>}
      </div>
    );
  }

  function ViewRow({ icon, label, count, active, onClick, dashed }) {
    return (
      <button type="button" onClick={onClick} style={{
        display: "flex", alignItems: "center", gap: 8, padding: "5px 8px", width: "100%",
        background: active ? "var(--lbb-accent-soft)" : "transparent",
        color: active ? "var(--lbb-accent-mid)" : dashed ? "var(--lbb-fg3)" : "var(--lbb-fg2)",
        border: dashed ? "1px dashed var(--lbb-border2)" : "1px solid transparent",
        borderRadius: 6, cursor: "pointer", fontFamily: "inherit", textAlign: "left",
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

  function FacetRail({ open, onToggle, scope, facets, toggleFacet, clearFacets,
                       view, setView, viewCounts, activeCount }) {
    const [groupOpen, setGroupOpen] = React.useState({ decade: true, status: true, rating: true, source: true, files: true });
    const flip = k => setGroupOpen(g => ({ ...g, [k]: !g[k] }));

    if (!open) {
      return (
        <aside style={{
          width: 40, flex: "0 0 40px",
          background: "var(--sep-rail-bg, var(--lbb-surface))",
          borderRight: "var(--sep-rail-bw, 1px) solid var(--sep-rail-edge, var(--lbb-border))",
          borderRadius: "var(--sep-radius, 0px)",
          boxShadow: "var(--sep-rail-shadow, none)",
          display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 8, gap: 6,
        }}>
          <IconButton icon="filter" title="Show filters" onClick={onToggle} />
          {activeCount > 0 && (
            <span style={{
              minWidth: 18, height: 18, borderRadius: 9, padding: "0 5px",
              background: "var(--lbb-accent-mid)", color: "var(--lbb-accent-onMid)",
              fontSize: 10.5, fontWeight: 700, display: "inline-flex",
              alignItems: "center", justifyContent: "center",
            }}>{activeCount}</span>
          )}
        </aside>
      );
    }

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

    return (
      <aside style={{
        width: 248, flex: "0 0 248px",
        background: "var(--sep-rail-bg, var(--lbb-surface))",
        borderRight: "var(--sep-rail-bw, 1px) solid var(--sep-rail-edge, var(--lbb-border))",
        borderRadius: "var(--sep-radius, 0px)",
        boxShadow: "var(--sep-rail-shadow, none)",
        display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden",
      }}>
        {/* Rail header */}
        <div style={{
          padding: "10px 10px 10px 16px", borderBottom: "1px solid var(--lbb-border)",
          display: "flex", alignItems: "center", gap: 8,
        }}>
          <span style={{ flex: 1, fontSize: 10.5, fontWeight: 700, letterSpacing: 0.1, textTransform: "uppercase", color: "var(--lbb-fg3)" }}>
            Views &amp; filters
          </span>
          {activeCount > 0 && (
            <button type="button" onClick={clearFacets} style={{
              background: "transparent", border: "none", color: "var(--lbb-accent-mid)",
              fontSize: 11, fontWeight: 600, cursor: "pointer", fontFamily: "inherit", padding: 0,
            }}>Clear {activeCount}</button>
          )}
          <IconButton icon="chevLeft" size={24} title="Collapse filters" onClick={onToggle} />
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px 16px" }}>
          {/* Views — saved searches + collection health, one list */}
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <ViewRow icon="library" label="All entries" active={view === "all"} onClick={() => setView("all")} />
            {SAVED.map(v => (
              <ViewRow key={v.id} icon={view === v.id ? "starFill" : "star"} label={v.label} count={v.count}
                active={view === v.id} onClick={() => setView(v.id)} />
            ))}
          </div>

          <div style={{
            margin: "12px 0 4px", fontSize: 10, fontWeight: 700, letterSpacing: 0.12,
            textTransform: "uppercase", color: "var(--lbb-fg3)",
          }}>Collection health</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {HEALTH.map(v => (
              <ViewRow key={v.id} icon={v.icon} label={v.label} count={viewCounts[v.id]}
                active={view === v.id} onClick={() => setView(v.id)} />
            ))}
          </div>

          <div style={{ marginTop: 10 }}>
            <ViewRow icon="plus" label="Save current filters as view" dashed onClick={() => {}} />
          </div>

          <div style={{ height: 1, background: "var(--lbb-border)", margin: "16px -16px 0" }}></div>

          {/* Facets */}
          <FacetGroup title="Decade" open={groupOpen.decade} onToggle={() => flip("decade")}>
            {LIB.FACETS.decade.map(f => (
              <Chip key={f.k} size="sm" count={f.n} active={facets.decade.has(f.k)} onClick={() => toggleFacet("decade", f.k)}>{f.k}</Chip>
            ))}
          </FacetGroup>
          <FacetGroup title="Status" open={groupOpen.status} onToggle={() => flip("status")}>
            {LIB.FACETS.status.map(f => (
              <Chip key={f.k} size="sm" count={f.n} active={facets.status.has(f.k)} onClick={() => toggleFacet("status", f.k)}>{f.k}</Chip>
            ))}
          </FacetGroup>
          <FacetGroup title="Rating" open={groupOpen.rating} onToggle={() => flip("rating")}>
            {LIB.FACETS.rating.map(f => (
              <Chip key={f.k} size="sm" count={f.n} active={facets.rating.has(f.k)} onClick={() => toggleFacet("rating", f.k)}>{f.k}</Chip>
            ))}
          </FacetGroup>
          <FacetGroup title="Source" open={groupOpen.source} onToggle={() => flip("source")}>
            {LIB.FACETS.source.map(f => (
              <Chip key={f.k} size="sm" count={f.n} active={facets.source.has(f.k)} onClick={() => toggleFacet("source", f.k)}>{f.k}</Chip>
            ))}
          </FacetGroup>

          {/* File facets — only meaningful inside your collection */}
          {scope === "owned" && (
            <FacetGroup title="Files" open={groupOpen.files} onToggle={() => flip("files")}>
              <Chip size="sm" active={facets.files.has("Unconfirmed")} onClick={() => toggleFacet("files", "Unconfirmed")}>Unconfirmed</Chip>
              <Chip size="sm" active={facets.files.has("No FP")} onClick={() => toggleFacet("files", "No FP")}>No FP</Chip>
              <Chip size="sm" active={facets.files.has("Xref only")} onClick={() => toggleFacet("files", "Xref only")}>Xref only</Chip>
              <Chip size="sm" active={facets.files.has("Duplicates")} onClick={() => toggleFacet("files", "Duplicates")}>Duplicates</Chip>
            </FacetGroup>
          )}

          {/* Year range */}
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: 0.1, textTransform: "uppercase", color: "var(--lbb-fg3)", marginBottom: 8 }}>
              Year range · 1980 – 2026
            </div>
            <div style={{ position: "relative", height: 24, padding: "10px 0" }}>
              <div style={{ height: 4, borderRadius: 2, background: "var(--lbb-surface2)" }}></div>
              <div style={{ position: "absolute", top: 10, left: "26%", right: "2%", height: 4, borderRadius: 2, background: "var(--lbb-accent-mid)" }}></div>
              <span style={{ position: "absolute", top: 6, left: "calc(26% - 6px)", width: 12, height: 12, borderRadius: "50%", background: "var(--lbb-surface)", border: "2px solid var(--lbb-accent-mid)" }}></span>
              <span style={{ position: "absolute", top: 6, left: "calc(98% - 6px)", width: 12, height: 12, borderRadius: "50%", background: "var(--lbb-surface)", border: "2px solid var(--lbb-accent-mid)" }}></span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 10.5, color: "var(--lbb-fg3)", fontFamily: "var(--lbb-mono)" }}>
              <span>1961</span><span>2030</span>
            </div>
          </div>
        </div>
      </aside>
    );
  }

  // ── Setlist (the detail-panel crown jewel) ──────────────────────────
  function Setlist({ lb }) {
    const sl = LIB.SETLISTS[lb];
    if (!sl) {
      return (
        <div style={{
          padding: "14px 12px", borderRadius: 6, textAlign: "center",
          border: "1px dashed var(--lbb-border2)", color: "var(--lbb-fg3)", fontSize: 11.5,
        }}>
          Setlist not yet scraped for this entry
        </div>
      );
    }
    return (
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.08, textTransform: "uppercase", color: "var(--lbb-fg3)" }}>Setlist</span>
          <span style={{ fontSize: 11, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
            {sl.tracks} tracks · {sl.length}
          </span>
          <div style={{ flex: 1 }}></div>
          <IconButton icon="copy" size={22} title="Copy setlist" />
        </div>
        <div style={{ border: "1px solid var(--lbb-border)", borderRadius: 6, overflow: "hidden" }}>
          {sl.discs.map((disc, di) => (
            <React.Fragment key={di}>
              <div style={{
                padding: "5px 10px", background: "var(--lbb-surface2)",
                display: "flex", alignItems: "center", gap: 8,
                fontSize: 10.5, fontWeight: 700, letterSpacing: 0.06, textTransform: "uppercase",
                color: "var(--lbb-fg2)",
                borderTop: di > 0 ? "1px solid var(--lbb-border)" : "none",
                borderBottom: "1px solid var(--lbb-border)",
              }}>
                <span style={{ flex: 1 }}>{disc.label}</span>
                <span style={{ fontFamily: "var(--lbb-mono)", color: "var(--lbb-fg3)", fontWeight: 500 }}>{disc.time}</span>
              </div>
              {disc.tracks.map((t, ti) => (
                <div key={ti} style={{
                  display: "flex", alignItems: "baseline", gap: 8, padding: "3.5px 10px",
                  fontSize: 11.5, lineHeight: 1.45,
                  background: ti % 2 === 1 ? "color-mix(in srgb, var(--lbb-surface2) 40%, transparent)" : "transparent",
                }}>
                  <span style={{ width: 18, textAlign: "right", fontFamily: "var(--lbb-mono)", fontSize: 10.5, color: "var(--lbb-fg3)" }}>{ti + 1}</span>
                  <span style={{ flex: 1, color: "var(--lbb-fg)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t[0]}</span>
                  {t[2] && <Pill tone={t[2] === "debut" ? "warn" : "info"} soft style={{ fontSize: 9, padding: "0 5px" }}>{t[2]}</Pill>}
                  <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 10.5, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums" }}>{t[1]}</span>
                </div>
              ))}
            </React.Fragment>
          ))}
        </div>
      </div>
    );
  }

  // ── Detail panel ────────────────────────────────────────────────────
  function MetaRow({ label, children, mono }) {
    return (
      <React.Fragment>
        <span style={{ color: "var(--lbb-fg3)" }}>{label}</span>
        <span style={{ fontFamily: mono ? "var(--lbb-mono)" : "inherit", color: "var(--lbb-fg2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{children}</span>
      </React.Fragment>
    );
  }

  function DetailPanel({ row, open, onToggle, width = 380 }) {
    const [histTab, setHistTab] = React.useState("torrents");
    if (!open) {
      return (
        <aside style={{
          width: 40, flex: "0 0 40px",
          background: "var(--sep-detail-bg, var(--lbb-surface))",
          borderLeft: "var(--sep-detail-bw, 1px) solid var(--sep-detail-edge, var(--lbb-border))",
          borderRadius: "var(--sep-radius, 0px)",
          boxShadow: "var(--sep-detail-shadow, none)",
          display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 8,
        }}>
          <IconButton icon="info" title="Show details" onClick={onToggle} />
        </aside>
      );
    }

    const hist = row ? window.LBB_LIB.HISTORY[row.lb] : null;
    const related = row ? window.LBB_LIB.RELATED[row.lb] : null;

    return (
      <aside style={{
        width, flex: `0 0 ${width}px`,
        background: "var(--sep-detail-bg, var(--lbb-surface))",
        borderLeft: "var(--sep-detail-bw, 1px) solid var(--sep-detail-edge, var(--lbb-border))",
        borderRadius: "var(--sep-radius, 0px)",
        boxShadow: "var(--sep-detail-shadow, none)",
        display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden",
      }}>
        <div style={{
          padding: "10px 10px 10px 16px", borderBottom: "1px solid var(--lbb-border)",
          display: "flex", alignItems: "center", gap: 8,
        }}>
          <span style={{ flex: 1, fontSize: 10.5, fontWeight: 700, letterSpacing: 0.1, textTransform: "uppercase", color: "var(--lbb-fg3)" }}>Details</span>
          {row && <Button size="sm" variant="ghost" icon="reveal">Open LB page</Button>}
          <IconButton icon="chevRight" size={24} title="Collapse details" onClick={onToggle} />
        </div>

        {!row ? (
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--lbb-fg3)", fontSize: 12 }}>
            Select a row to see details
          </div>
        ) : (
          <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
            {/* Pills */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10, flexWrap: "wrap" }}>
              {row.owned
                ? <Pill tone="ok" soft dot>Owned</Pill>
                : <Pill tone="warn" soft dot>Not owned</Pill>}
              <Pill tone={row.status === "Public" ? "info" : row.status === "Missing" ? "warn" : "mute"} soft>{row.status}</Pill>
              {row.owned && row.format && <Pill tone="mute" soft>{row.format}</Pill>}
              {row.wish && <Pill tone="warn" soft>Wishlist</Pill>}
            </div>

            {/* Identity */}
            <div style={{ fontFamily: "var(--lbb-mono)", fontSize: 16, fontWeight: 700, color: "var(--lbb-accent-mid)", marginBottom: 2 }}>{row.lb}</div>
            {row.title && <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 2, color: "var(--lbb-fg)" }}>{row.title}</div>}
            <div style={{ fontSize: 12, color: "var(--lbb-fg2)" }}>
              {row.date} · {row.loc}{row.cds ? ` · ${row.cds} CD${row.cds > 1 ? "s" : ""}` : ""}
            </div>
            {row.desc && row.desc !== "—" && (
              <div style={{ fontSize: 11.5, color: "var(--lbb-fg3)", marginTop: 6, lineHeight: 1.5 }}>{row.desc}</div>
            )}

            {/* Action bar — the SAME vocabulary as the right-click row menu */}
            <window.LBB_ActionBar actions={window.LBB_recordingActions(row)} />

            {/* Owned: file card */}
            {row.owned && (
              <div style={{
                marginTop: 14, padding: "10px 12px", borderRadius: 6,
                background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)",
              }}>
                <div style={{ display: "grid", gridTemplateColumns: "86px 1fr", gap: "4px 10px", fontSize: 11.5 }}>
                  <MetaRow label="Folder" mono>{row.folder}</MetaRow>
                  <MetaRow label="Disk path" mono>{row.path}</MetaRow>
                  <MetaRow label="Size">
                    <strong style={{ color: "var(--lbb-fg)" }}>{row.size}</strong> · {row.files} files · {row.format}
                  </MetaRow>
                  <MetaRow label="Confirmed" mono>{row.conf}</MetaRow>
                  <span style={{ color: "var(--lbb-fg3)" }}>Fingerprint</span>
                  <span>{row.fp ? <Pill tone="ok" soft>Yes · acoustid</Pill> : <Pill tone="warn" soft>Missing</Pill>}</span>
                  <span style={{ color: "var(--lbb-fg3)" }}>Rating</span>
                  <span><RatingChip value={row.rating} /></span>
                </div>
              </div>
            )}

            {/* Unowned: acquisition block */}
            {!row.owned && (
              <div style={{ marginTop: 14 }}>
                <Banner tone="info" icon="info" title="Not in your collection">
                  Catalog metadata shown from the master DB.
                </Banner>
                {related && related.length > 0 && (
                  <div style={{ marginTop: 14 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.08, textTransform: "uppercase", color: "var(--lbb-fg3)", marginBottom: 6 }}>
                      You own related
                    </div>
                    <div style={{ border: "1px solid var(--lbb-border)", borderRadius: 6, overflow: "hidden" }}>
                      {related.map((r, i) => (
                        <div key={i} style={{
                          padding: "8px 10px", display: "flex", alignItems: "center", gap: 8, fontSize: 11.5,
                          borderBottom: i < related.length - 1 ? "1px solid var(--lbb-border)" : "none",
                        }}>
                          <span style={{ fontFamily: "var(--lbb-mono)", fontWeight: 600, color: "var(--lbb-accent-mid)" }}>{r.lb}</span>
                          <span style={{ flex: 1, color: "var(--lbb-fg2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.note}</span>
                          <Icon name="check" size={12} style={{ color: "var(--lbb-ok-bar)" }} />
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Assets (owned) — state-bearing chips, not equal-weight buttons */}
            {row.owned && <window.LBB_AssetStrip />}

            {/* Setlist — for everything, owned or not */}
            <div style={{ marginTop: 18 }}>
              <Setlist lb={row.lb} />
            </div>

            {/* Share & seed (owned) — unified torrent + forum distribution */}
            {row.owned && <window.LBB_ShareSeed lb={row.lb} hist={hist} />}
          </div>
        )}
      </aside>
    );
  }

  // ── Bulk action bar ─────────────────────────────────────────────────
  function BulkBar({ count, scope, onClear }) {
    if (!count) return null;
    return (
      <div style={{
        position: "absolute", bottom: 14, left: "50%", transform: "translateX(-50%)",
        display: "flex", alignItems: "center", gap: 8, padding: "8px 10px 8px 14px",
        background: "var(--lbb-surface)", border: "1px solid var(--lbb-border2)",
        borderRadius: 10, boxShadow: "var(--lbb-shadowLg)", zIndex: 5, whiteSpace: "nowrap",
      }}>
        <span style={{ fontSize: 12, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{count} selected</span>
        <span style={{ width: 1, height: 18, background: "var(--lbb-border)" }}></span>
        {scope !== "unowned" ? (
          <React.Fragment>
            <Button size="sm" variant="ghost" icon="download">Export M3U</Button>
            <Button size="sm" variant="secondary" icon="copy">Create torrent</Button>
            <Button size="sm" variant="primary" icon="upload">Add to qBittorrent</Button>
            <Button size="sm" variant="ghost" icon="reveal">Update location</Button>
            <Button size="sm" variant="danger" icon="trash">Remove</Button>
          </React.Fragment>
        ) : (
          <Button size="sm" variant="primary" icon="star">Add to wishlist</Button>
        )}
        <IconButton icon="x" size={24} title="Clear selection" onClick={onClear} />
      </div>
    );
  }

  Object.assign(window, {
    LBB_RatingChip: RatingChip,
    LBB_ScopeControl: ScopeControl,
    LBB_ActiveFilter: ActiveFilter,
    LBB_FacetRail: FacetRail,
    LBB_DetailPanel: DetailPanel,
    LBB_BulkBar: BulkBar,
  });
})();
