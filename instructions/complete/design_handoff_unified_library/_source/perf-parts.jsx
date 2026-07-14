// perf-parts.jsx
// Sub-components for the performance-centric Library:
// RatingChip, SourceBadge, CoverageChip, SourceStrip, FacetRail, DetailPanel.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Chip, IconButton, Banner } = window;
  const PERF = window.LBB_PERF;

  // ── Tone mapping per facet group (mirrors the flat-Library refinement) ─
  // Semantic groups get a tone + leading dot so they read at a glance;
  // neutral groups (decade, recordings) fall back to the accent.
  const facetTone = {
    decade:     () => null,
    coverage:   (k) => k === "Covered" ? "ok" : k === "Gap" ? "mute" : "warn",
    recordings: () => null,
    source:     () => "info",
    rating:     (k) => (k === "A" || k === "A−") ? "ok" : (k === "B+" || k === "B") ? "info" : k === "B−" ? "warn" : "mute",
  };

  // ── Toned facet chip — leading dot + tone fill on active ──────────
  function FacetChip({ children, count, active, tone, onClick }) {
    const bar = tone ? `var(--lbb-${tone}-bar)` : "var(--lbb-accent-mid)";
    const skin = active
      ? (tone
          ? { background: `var(--lbb-${tone}-bg)`, color: `var(--lbb-${tone}-fg)`, borderColor: bar }
          : { background: "var(--lbb-accent-soft)", color: "var(--lbb-accent-mid)", borderColor: "var(--lbb-accent-mid)" })
      : { background: "var(--lbb-surface2)", color: "var(--lbb-fg2)", borderColor: "var(--lbb-border)" };
    return (
      <button type="button" onClick={onClick} style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        padding: "3px 9px 3px 8px", fontSize: 11.5, fontFamily: "inherit",
        borderRadius: 7, cursor: "pointer", lineHeight: 1.4,
        border: "1px solid", fontWeight: active ? 650 : 500,
        ...skin,
      }}>
        {tone && <span style={{ width: 6, height: 6, borderRadius: "50%", background: bar, flex: "0 0 auto" }} />}
        {children}
        {count !== undefined && (
          <span style={{ fontSize: 10, fontVariantNumeric: "tabular-nums", opacity: 0.7, fontWeight: 600 }}>
            {count.toLocaleString()}
          </span>
        )}
      </button>
    );
  }

  // ── Rating chip ─────────────────────────────────────────────────────
  function RatingChip({ value, size }) {
    if (!value || value === "—") return <span style={{ color: "var(--lbb-fg3)" }}>—</span>;
    const tone = (value === "A" || value === "A−") ? "ok"
               : (value === "B+" || value === "B") ? "info"
               : value === "B−" ? "warn" : "mute";
    return <Pill tone={tone} soft style={size === "sm" ? { fontSize: 10, padding: "0 5px" } : undefined}>{value}</Pill>;
  }

  // ── Source badge — the compact 2–3 letter code, owned = filled ──────
  const SRC_HUE = {
    Soundboard:  "var(--lbb-ok-fg)",
    "FM/Pre-FM": "var(--lbb-info-fg)",
    Audience:    "var(--lbb-fg2)",
    Master:      "var(--lbb-accent-mid)",
    Mixed:       "var(--lbb-warn-fg)",
  };

  function SourceBadge({ src, owned, title }) {
    if (!src) {
      return (
        <span title="No recording catalogued" style={{
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          minWidth: 30, height: 18, padding: "0 5px", borderRadius: 4,
          fontFamily: "var(--lbb-mono)", fontSize: 10, fontWeight: 700, letterSpacing: 0.3,
          border: "1px dashed var(--lbb-border2)", color: "var(--lbb-fg3)",
        }}>—</span>
      );
    }
    const code = (PERF.SOURCES[src] || {}).code || src.slice(0, 3).toUpperCase();
    const hue = SRC_HUE[src] || "var(--lbb-fg2)";
    return (
      <span title={title || `${PERF.SOURCES[src]?.full || src}${owned ? " · owned" : " · not owned"}`} style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        minWidth: 30, height: 18, padding: "0 5px", borderRadius: 4,
        fontFamily: "var(--lbb-mono)", fontSize: 10, fontWeight: 700, letterSpacing: 0.3,
        background: owned ? `color-mix(in srgb, ${hue} 18%, transparent)` : "transparent",
        color: owned ? hue : "var(--lbb-fg3)",
        border: `1px solid ${owned ? `color-mix(in srgb, ${hue} 45%, transparent)` : "var(--lbb-border2)"}`,
        opacity: owned ? 1 : 0.72,
      }}>{code}</span>
    );
  }

  // Strip of source badges for a performance row
  function SourceStrip({ recordings }) {
    return (
      <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
        {recordings.map((r, i) => <SourceBadge key={i} src={r.src} owned={r.owned} />)}
      </span>
    );
  }

  // ── TapeMatch confidence chip ───────────────────────────────────────
  // Shows HOW a family was clustered: AI fingerprint, LB cross-ref, or both.
  function MatchChip({ by, conf, size, title }) {
    const m = PERF.MATCH[by] || PERF.MATCH.lb;
    const pct = conf != null ? `${Math.round(conf * 100)}%` : null;
    const sm = size === "sm";
    return (
      <span title={title || "TapeMatch grouping"} style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        padding: sm ? "0 5px" : "1px 7px 1px 5px", height: sm ? 16 : 18, borderRadius: 4,
        background: `var(--lbb-${m.tone}-bg)`, color: `var(--lbb-${m.tone}-fg)`,
        border: `1px solid color-mix(in srgb, var(--lbb-${m.tone}-bar) 55%, transparent)`,
        fontSize: sm ? 9.5 : 10, fontWeight: 700, letterSpacing: 0.02, whiteSpace: "nowrap",
        fontVariantNumeric: "tabular-nums",
      }}>
        <Icon name={m.icon} size={sm ? 9 : 10.5} />
        {m.code}{pct && <span style={{ opacity: 0.85, fontWeight: 600 }}>· {pct}</span>}
      </span>
    );
  }

  // ── Family chip — one source FAMILY, with its member count ──────────
  // owned family = filled; ×N badge when the family clusters >1 LB#.
  function FamilyChip({ fam }) {
    const code = (PERF.SOURCES[fam.src] || {}).code || (fam.src ? fam.src.slice(0, 3).toUpperCase() : "—");
    const hue = SRC_HUE[fam.src] || "var(--lbb-fg2)";
    const owned = fam.owned;
    return (
      <span title={`${fam.label} · ${fam.total} recording${fam.total > 1 ? "s" : ""}${owned ? " · owned" : " · not owned"}`} style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        height: 18, padding: "0 4px 0 6px", borderRadius: 4,
        fontFamily: "var(--lbb-mono)", fontSize: 10, fontWeight: 700, letterSpacing: 0.3,
        background: owned ? `color-mix(in srgb, ${hue} 18%, transparent)` : "transparent",
        color: owned ? hue : "var(--lbb-fg3)",
        border: `1px solid ${owned ? `color-mix(in srgb, ${hue} 45%, transparent)` : "var(--lbb-border2)"}`,
        opacity: owned ? 1 : 0.78,
      }}>
        {code}
        {fam.multi && (
          <span style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            minWidth: 14, height: 13, padding: "0 3px", borderRadius: 3,
            background: owned ? `color-mix(in srgb, ${hue} 30%, transparent)` : "var(--lbb-surface2)",
            color: owned ? hue : "var(--lbb-fg3)", fontSize: 9, fontWeight: 800, letterSpacing: 0,
          }}>×{fam.total}</span>
        )}
      </span>
    );
  }

  // Strip of FAMILY chips for a performance row (replaces SourceStrip when grouping).
  function FamilyStrip({ perf }) {
    const fams = PERF.families(perf);
    return (
      <span style={{ display: "inline-flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
        {fams.map((f) => <FamilyChip key={f.id} fam={f} />)}
      </span>
    );
  }

  // ── Coverage chip — the performance-centric status ──────────────────
  // Covered (own best) · Upgrade (better source unowned) · Gap (own none) · Undocumented
  function CoverageChip({ coverage, ownedCount, total }) {
    const map = {
      Covered:      { tone: "ok",   label: total > 1 ? `Owned ${ownedCount}/${total}` : "Owned", icon: "check" },
      Upgrade:      { tone: "warn", label: `Upgrade ${ownedCount}/${total}`, icon: "upload" },
      Gap:          { tone: "mute", label: "Gap", icon: "x" },
      Undocumented: { tone: "warn", label: "No source", icon: "alert" },
    };
    const m = map[coverage] || map.Gap;
    return (
      <span style={{
        display: "inline-flex", alignItems: "center", gap: 5,
        padding: "1px 8px 1px 6px", borderRadius: 999, whiteSpace: "nowrap",
        background: `var(--lbb-${m.tone}-bg)`, color: `var(--lbb-${m.tone}-fg)`,
        border: `1px solid color-mix(in srgb, var(--lbb-${m.tone}-bar) 50%, transparent)`,
        fontSize: 11, fontWeight: 650, fontVariantNumeric: "tabular-nums",
      }}>
        <Icon name={m.icon} size={11} />
        {m.label}
      </span>
    );
  }

  // Small segmented coverage meter (detail panel)
  function CoverageMeter({ recordings }) {
    return (
      <div style={{ display: "flex", gap: 3 }}>
        {recordings.map((r, i) => (
          <span key={i} style={{
            flex: 1, height: 6, borderRadius: 3,
            background: r.owned ? "var(--lbb-ok-bar)" : "var(--lbb-surface2)",
            border: r.owned ? "none" : "1px solid var(--lbb-border2)",
          }}></span>
        ))}
      </div>
    );
  }

  // Family-level meter — one segment per FAMILY, owned families filled.
  function FamilyMeter({ families }) {
    return (
      <div style={{ display: "flex", gap: 3 }}>
        {families.map((f) => (
          <span key={f.id} title={`${f.label} · ${f.total} upload${f.total > 1 ? "s" : ""}`} style={{
            flex: f.total, height: 6, borderRadius: 3,
            background: f.owned ? "var(--lbb-ok-bar)" : "var(--lbb-surface2)",
            border: f.owned ? "none" : "1px solid var(--lbb-border2)",
          }}></span>
        ))}
      </div>
    );
  }

  // ── Active-filter chip ──────────────────────────────────────────────
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

  function FacetRail({ open, onToggle, facets, toggleFacet, clearFacets, view, setView, viewCounts, activeCount }) {
    const [groupOpen, setGroupOpen] = React.useState({ decade: true, coverage: true, recordings: true, source: true, rating: false });
    const flip = k => setGroupOpen(g => ({ ...g, [k]: !g[k] }));

    if (!open) {
      return (
        <aside style={{
          width: 40, flex: "0 0 40px",
          background: "var(--sep-rail-bg, var(--lbb-surface))",
          borderRight: "var(--sep-rail-edge, 1px solid var(--lbb-border))",
          borderRadius: "var(--sep-radius, 0px)", boxShadow: "var(--sep-rail-shadow, none)",
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
      { id: "next",   label: "Upgrade targets",   icon: "upload", count: 612 },
      { id: "sbdgap", label: "SBD exists, unowned", icon: "spectro", count: 1980 },
      { id: "multi",  label: "Multi-source shows",  icon: "copy", count: 2210 },
    ];
    const HEALTH = [
      { id: "gaps",        label: "Coverage gaps",  icon: "alert" },
      { id: "wishlist",    label: "Wishlist shows", icon: "star" },
      { id: "duplicates",  label: "Has duplicates", icon: "copy" },
      { id: "unconfirmed", label: "Unconfirmed",    icon: "info" },
    ];

    return (
      <aside style={{
        width: 252, flex: "0 0 252px",
        background: "var(--sep-rail-bg, var(--lbb-surface))",
        borderRight: "var(--sep-rail-edge, 1px solid var(--lbb-border))",
        borderRadius: "var(--sep-radius, 0px)", boxShadow: "var(--sep-rail-shadow, none)",
        display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden",
      }}>
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
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <ViewRow icon="library" label="All performances" active={view === "all"} onClick={() => setView("all")} />
            {SAVED.map(v => (
              <ViewRow key={v.id} icon={v.icon} label={v.label} count={v.count}
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

          <div style={{ height: 1, background: "var(--lbb-border)", margin: "16px -16px 0" }}></div>

          <FacetGroup title="Decade" open={groupOpen.decade} onToggle={() => flip("decade")}>
            {PERF.FACETS.decade.map(f => (
              <FacetChip key={f.k} count={f.n} tone={facetTone.decade(f.k)} active={facets.decade.has(f.k)} onClick={() => toggleFacet("decade", f.k)}>{f.k}</FacetChip>
            ))}
          </FacetGroup>
          <FacetGroup title="Coverage" open={groupOpen.coverage} onToggle={() => flip("coverage")}>
            {PERF.FACETS.coverage.map(f => (
              <FacetChip key={f.k} count={f.n} tone={facetTone.coverage(f.k)} active={facets.coverage.has(f.k)} onClick={() => toggleFacet("coverage", f.k)}>{f.k}</FacetChip>
            ))}
          </FacetGroup>
          <FacetGroup title="Recordings" open={groupOpen.recordings} onToggle={() => flip("recordings")}>
            {PERF.FACETS.recordings.map(f => (
              <FacetChip key={f.k} count={f.n} tone={facetTone.recordings(f.k)} active={facets.recordings.has(f.k)} onClick={() => toggleFacet("recordings", f.k)}>{f.k}</FacetChip>
            ))}
          </FacetGroup>
          <FacetGroup title="Source available" open={groupOpen.source} onToggle={() => flip("source")}>
            {PERF.FACETS.source.map(f => (
              <FacetChip key={f.k} count={f.n} tone={facetTone.source(f.k)} active={facets.source.has(f.k)} onClick={() => toggleFacet("source", f.k)}>
                {(PERF.SOURCES[f.k] || {}).full || f.k}
              </FacetChip>
            ))}
          </FacetGroup>
          <FacetGroup title="Best rating" open={groupOpen.rating} onToggle={() => flip("rating")}>
            {PERF.FACETS.rating.map(f => (
              <FacetChip key={f.k} count={f.n} tone={facetTone.rating(f.k)} active={facets.rating.has(f.k)} onClick={() => toggleFacet("rating", f.k)}>{f.k}</FacetChip>
            ))}
          </FacetGroup>

          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: 0.1, textTransform: "uppercase", color: "var(--lbb-fg3)", marginBottom: 8 }}>
              Date range · 1961 – 2026
            </div>
            <div style={{ position: "relative", height: 24, padding: "10px 0" }}>
              <div style={{ height: 4, borderRadius: 2, background: "var(--lbb-surface2)" }}></div>
              <div style={{ position: "absolute", top: 10, left: "26%", right: "2%", height: 4, borderRadius: 2, background: "var(--lbb-accent-mid)" }}></div>
              <span style={{ position: "absolute", top: 6, left: "calc(26% - 6px)", width: 12, height: 12, borderRadius: "50%", background: "var(--lbb-surface)", border: "2px solid var(--lbb-accent-mid)" }}></span>
              <span style={{ position: "absolute", top: 6, left: "calc(98% - 6px)", width: 12, height: 12, borderRadius: "50%", background: "var(--lbb-surface)", border: "2px solid var(--lbb-accent-mid)" }}></span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 10.5, color: "var(--lbb-fg3)", fontFamily: "var(--lbb-mono)" }}>
              <span>1961</span><span>2026</span>
            </div>
          </div>
        </div>
      </aside>
    );
  }

  // ── Setlist ─────────────────────────────────────────────────────────
  function Setlist({ setlistKey }) {
    const sl = setlistKey ? PERF.SETLISTS[setlistKey] : null;
    if (!sl) {
      return (
        <div style={{
          padding: "14px 12px", borderRadius: 6, textAlign: "center",
          border: "1px dashed var(--lbb-border2)", color: "var(--lbb-fg3)", fontSize: 11.5,
        }}>
          Setlist not yet scraped for this performance
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

  // ── Recording card (inside the performance detail) ──────────────────
  function RecordingCard({ r, isBest }) {
    return (
      <div style={{
        padding: "10px 12px", borderRadius: 8,
        background: r.owned ? "var(--lbb-surface2)" : "transparent",
        border: `1px solid ${isBest ? "color-mix(in srgb, var(--lbb-accent-mid) 45%, transparent)" : "var(--lbb-border)"}`,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <SourceBadge src={r.src} owned={r.owned} />
          <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 12, fontWeight: 600, color: "var(--lbb-accent-mid)" }}>{r.lb}</span>
          <div style={{ flex: 1 }}></div>
          {isBest && <Pill tone="info" soft style={{ fontSize: 9, padding: "0 5px" }}>Best</Pill>}
          {r.owned
            ? <Pill tone="ok" soft dot>Owned</Pill>
            : r.wish ? <Pill tone="warn" soft>Wishlist</Pill> : <Pill tone="mute" soft>Not owned</Pill>}
          <RatingChip value={r.rating} size="sm" />
        </div>
        <div style={{ fontSize: 11.5, color: "var(--lbb-fg3)", marginTop: 6, lineHeight: 1.5 }}>{r.lineage}</div>
        {r.owned ? (
          <div style={{ display: "grid", gridTemplateColumns: "70px 1fr", gap: "3px 10px", fontSize: 11, marginTop: 8 }}>
            <span style={{ color: "var(--lbb-fg3)" }}>Folder</span>
            <span style={{ fontFamily: "var(--lbb-mono)", color: "var(--lbb-fg2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.folder}</span>
            <span style={{ color: "var(--lbb-fg3)" }}>On disk</span>
            <span style={{ color: "var(--lbb-fg2)" }}>
              <strong style={{ color: "var(--lbb-fg)" }}>{r.size}</strong> · {r.files} files · {r.format}
            </span>
            <span style={{ color: "var(--lbb-fg3)" }}>Fingerprint</span>
            <span>{r.fp ? <Pill tone="ok" soft style={{ fontSize: 9, padding: "0 5px" }}>Yes</Pill> : <Pill tone="warn" soft style={{ fontSize: 9, padding: "0 5px" }}>Missing</Pill>}</span>
          </div>
        ) : (
          <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
            <Button size="sm" variant={r.wish ? "secondary" : "primary"} icon={r.wish ? "starFill" : "star"}>
              {r.wish ? "On wishlist" : "Add to wishlist"}
            </Button>
            <Button size="sm" variant="ghost" icon="globe">Find sources</Button>
          </div>
        )}
        {r.owned && (
          <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
            <Button size="sm" variant="secondary" icon="reveal">Reveal</Button>
            <Button size="sm" variant="ghost" icon="play">Play</Button>
          </div>
        )}
      </div>
    );
  }

  // ── Member row inside a family card (one LB# upload) ────────────────
  function MemberRow({ r, isCanonical }) {
    const tag = isCanonical ? { tone: "info", label: "Best in family" }
              : r.dup       ? { tone: "mute", label: "Duplicate" }
              : null;
    return (
      <div style={{
        display: "flex", alignItems: "baseline", gap: 8, padding: "7px 10px",
        background: isCanonical ? "color-mix(in srgb, var(--lbb-accent-soft) 60%, transparent)" : "transparent",
        borderTop: "1px solid var(--lbb-border)",
      }}>
        <span style={{ color: "var(--lbb-fg3)", fontFamily: "var(--lbb-mono)", fontSize: 11 }}>{isCanonical ? "●" : "└"}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 11.5, fontWeight: 600, color: r.owned ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)" }}>{r.lb}</span>
            {tag && <Pill tone={tag.tone} soft style={{ fontSize: 9, padding: "0 5px" }}>{tag.label}</Pill>}
            <div style={{ flex: 1 }}></div>
            <RatingChip value={r.rating} size="sm" />
            {r.owned
              ? <Pill tone="ok" soft dot style={{ fontSize: 9, padding: "0 5px" }}>Owned</Pill>
              : r.wish ? <Pill tone="warn" soft style={{ fontSize: 9, padding: "0 5px" }}>Wishlist</Pill>
              : <Pill tone="mute" soft style={{ fontSize: 9, padding: "0 5px" }}>Not owned</Pill>}
          </div>
          <div style={{ fontSize: 11, color: "var(--lbb-fg3)", marginTop: 3, lineHeight: 1.45, whiteSpace: "normal" }}>{r.lineage}</div>
          {r.owned && (
            <div style={{ fontSize: 10.5, color: "var(--lbb-fg3)", marginTop: 4, fontFamily: "var(--lbb-mono)" }}>
              <strong style={{ color: "var(--lbb-fg2)" }}>{r.size}</strong> · {r.files} files · {r.format}
              {r.fp
                ? <span style={{ color: "var(--lbb-ok-fg)" }}> · fingerprinted</span>
                : <span style={{ color: "var(--lbb-warn-fg)" }}> · no fingerprint</span>}
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── Family card — one TapeMatch family, with its member uploads ─────
  function FamilyCard({ fam }) {
    const accent = fam.owned;
    return (
      <div style={{
        borderRadius: 8, overflow: "hidden",
        border: `1px solid ${accent ? "color-mix(in srgb, var(--lbb-accent-mid) 40%, transparent)" : "var(--lbb-border)"}`,
        background: accent ? "var(--lbb-surface2)" : "transparent",
      }}>
        {/* family header */}
        <div style={{ padding: "9px 10px", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <SourceBadge src={fam.src} owned={fam.owned} />
          <span style={{ fontSize: 12.5, fontWeight: 700, color: "var(--lbb-fg)" }}>{fam.label}</span>
          <MatchChip by={fam.by} conf={fam.conf} />
          <div style={{ flex: 1 }}></div>
          <span style={{ fontSize: 10.5, color: "var(--lbb-fg3)", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
            {fam.total} upload{fam.total > 1 ? "s" : ""}
          </span>
        </div>
        {/* match reasoning */}
        {fam.note && (
          <div style={{
            display: "flex", alignItems: "flex-start", gap: 6, padding: "0 10px 8px 10px",
            fontSize: 11, color: "var(--lbb-fg3)", lineHeight: 1.45,
          }}>
            <Icon name="tapematch" size={12} style={{ marginTop: 2, color: "var(--lbb-info-fg)", flex: "0 0 auto" }} />
            <span>{fam.note}</span>
          </div>
        )}
        {/* members */}
        <div>
          {fam.members.map((r, i) => (
            <MemberRow key={i} r={r} isCanonical={fam.multi && r === fam.canonical} />
          ))}
        </div>
      </div>
    );
  }

  // ── Detail panel — a PERFORMANCE, with all its recordings ───────────
  function DetailPanel({ perf, open, onToggle, width = 400, group = true }) {
    if (!open) {
      return (
        <aside style={{
          width: 40, flex: "0 0 40px",
          background: "var(--sep-detail-bg, var(--lbb-surface))",
          borderLeft: "var(--sep-detail-edge, 1px solid var(--lbb-border))",
          borderRadius: "var(--sep-radius, 0px)", boxShadow: "var(--sep-detail-shadow, none)",
          display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 8,
        }}>
          <IconButton icon="info" title="Show details" onClick={onToggle} />
        </aside>
      );
    }

    const ru = perf ? PERF.rollup(perf) : null;
    const fams = perf ? PERF.families(perf) : [];
    const bestOwned = perf
      ? perf.recordings.filter(r => r.owned).reduce((b, r) => (PERF.RATING_RANK[r.rating] || 0) > (PERF.RATING_RANK[b ? b.rating : "—"] || -1) ? r : b, null)
      : null;

    return (
      <aside style={{
        width, flex: `0 0 ${width}px`,
        background: "var(--sep-detail-bg, var(--lbb-surface))",
        borderLeft: "var(--sep-detail-edge, 1px solid var(--lbb-border))",
        borderRadius: "var(--sep-radius, 0px)", boxShadow: "var(--sep-detail-shadow, none)",
        display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden",
      }}>
        <div style={{
          padding: "10px 10px 10px 16px", borderBottom: "1px solid var(--lbb-border)",
          display: "flex", alignItems: "center", gap: 8,
        }}>
          <span style={{ flex: 1, fontSize: 10.5, fontWeight: 700, letterSpacing: 0.1, textTransform: "uppercase", color: "var(--lbb-fg3)" }}>Performance</span>
          {perf && <Button size="sm" variant="ghost" icon="reveal">LB page</Button>}
          <IconButton icon="chevRight" size={24} title="Collapse details" onClick={onToggle} />
        </div>

        {!perf ? (
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--lbb-fg3)", fontSize: 12 }}>
            Select a performance to see its recordings
          </div>
        ) : (
          <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
            {/* Identity */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 11, color: "var(--lbb-fg3)", textTransform: "uppercase", letterSpacing: 0.5 }}>{perf.dow}</span>
              <CoverageChip coverage={ru.coverage} ownedCount={ru.ownedCount} total={ru.total} />
              {perf.status === "New" && <Pill tone="info" soft dot>New</Pill>}
            </div>
            <div style={{ fontSize: 24, fontWeight: 800, color: "var(--lbb-fg)", letterSpacing: -0.02, lineHeight: 1.05 }}>{perf.disp}</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--lbb-fg)", marginTop: 4 }}>{perf.venue}</div>
            <div style={{ fontSize: 12.5, color: "var(--lbb-fg2)" }}>{perf.city}</div>
            <div style={{ fontSize: 11.5, color: "var(--lbb-fg3)", marginTop: 6 }}>
              {perf.tour}{perf.leg ? ` · ${perf.leg}` : ""}
            </div>
            {perf.title && (
              <div style={{ fontSize: 12, fontStyle: "italic", color: "var(--lbb-fg2)", marginTop: 6 }}>
                Released as “{perf.title}”
              </div>
            )}

            {/* Action bar — the SAME vocabulary as the right-click row menu */}
            <window.LBB_ActionBar actions={window.LBB_performanceActions(perf, ru)} />

            {/* Coverage summary */}
            <div style={{
              marginTop: 14, padding: "10px 12px", borderRadius: 8,
              background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)",
            }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 12.5, fontWeight: 700, color: "var(--lbb-fg)" }}>
                  {ru.ownedCount === 0
                    ? "No recording in your collection"
                    : group
                      ? `You hold ${ru.famOwned} of ${ru.famTotal} source famil${ru.famTotal > 1 ? "ies" : "y"}`
                      : `You hold ${ru.ownedCount} of ${ru.total} recording${ru.total > 1 ? "s" : ""}`}
                </span>
                <div style={{ flex: 1 }}></div>
                {ru.bestOwnedRating && <span style={{ fontSize: 11, color: "var(--lbb-fg3)" }}>best owned <strong style={{ color: "var(--lbb-fg2)" }}>{ru.bestOwnedRating}</strong></span>}
              </div>
              {group
                ? <FamilyMeter families={fams} />
                : <CoverageMeter recordings={perf.recordings} />}
              {group && ru.dupeCount > 0 && (
                <div style={{ marginTop: 8, fontSize: 11, color: "var(--lbb-fg3)", display: "flex", alignItems: "center", gap: 6 }}>
                  <Icon name="copy" size={12} /> TapeMatch folded {ru.total} uploads into {ru.famTotal} famil{ru.famTotal > 1 ? "ies" : "y"} · {ru.dupeCount} flagged as duplicate{ru.dupeCount > 1 ? "s" : ""}.
                </div>
              )}
              {ru.coverage === "Upgrade" && (
                <div style={{ marginTop: 8, fontSize: 11, color: "var(--lbb-warn-fg)", display: "flex", alignItems: "center", gap: 6 }}>
                  <Icon name="upload" size={12} /> A higher-rated {group ? "family" : "source"} ({ru.bestRating}) circulates that you don't own.
                </div>
              )}
            </div>

            {/* Performance facts */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginTop: 14 }}>
              <Fact label={group ? "Families" : "Recordings"} value={group ? ru.famTotal : ru.total} sub={group ? `of ${ru.total} rec` : ""} />
              <Fact label="Setlist" value={perf.tracks ? `${perf.tracks}` : "—"} sub={perf.tracks ? "tracks" : ""} />
              <Fact label="Length" value={perf.length} />
            </div>

            {/* Recordings / families list */}
            <div style={{ marginTop: 18 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.08, textTransform: "uppercase", color: "var(--lbb-fg3)" }}>
                  {group ? `Recording families · ${fams.length}` : `Circulating recordings · ${ru.total}`}
                </span>
                {group && (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, color: "var(--lbb-fg3)" }}>
                    <Icon name="tapematch" size={11} style={{ color: "var(--lbb-info-fg)" }} /> grouped by TapeMatch
                  </span>
                )}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {group
                  ? fams.map((f) => <FamilyCard key={f.id} fam={f} />)
                  : perf.recordings.map((r, i) => {
                      const isBest = perf.recordings.length > 1 &&
                        (PERF.RATING_RANK[r.rating] || 0) === Math.max(...perf.recordings.map(x => PERF.RATING_RANK[x.rating] || 0));
                      return <RecordingCard key={i} r={r} isBest={isBest} />;
                    })}
              </div>
            </div>

            {/* Setlist */}
            <div style={{ marginTop: 18 }}>
              <Setlist setlistKey={perf.setlist} />
            </div>

            {/* Assets + distribution — scoped to the best owned source */}
            {bestOwned && <window.LBB_AssetStrip />}
            {bestOwned && (
              <div style={{ marginTop: 18 }}>
                <div style={{ fontSize: 10.5, color: "var(--lbb-fg3)", marginBottom: 6 }}>
                  Distribution for best owned source · <span style={{ fontFamily: "var(--lbb-mono)", color: "var(--lbb-accent-mid)", fontWeight: 600 }}>{bestOwned.lb}</span>
                </div>
                <window.LBB_ShareSeed lb={bestOwned.lb} hist={window.LBB_LIB.HISTORY[bestOwned.lb] || null} />
              </div>
            )}
          </div>
        )}
      </aside>
    );
  }

  function Fact({ label, value, sub }) {
    return (
      <div style={{ padding: "8px 10px", borderRadius: 8, background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)" }}>
        <div style={{ fontSize: 18, fontWeight: 700, color: "var(--lbb-fg)", fontVariantNumeric: "tabular-nums", letterSpacing: -0.01 }}>
          {value}{sub && <span style={{ fontSize: 10.5, fontWeight: 500, color: "var(--lbb-fg3)", marginLeft: 3 }}>{sub}</span>}
        </div>
        <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: 0.06, textTransform: "uppercase", color: "var(--lbb-fg3)", marginTop: 2 }}>{label}</div>
      </div>
    );
  }

  // ── Bulk bar ────────────────────────────────────────────────────────
  function BulkBar({ count, onClear }) {
    if (!count) return null;
    return (
      <div style={{
        position: "absolute", bottom: 14, left: "50%", transform: "translateX(-50%)",
        display: "flex", alignItems: "center", gap: 8, padding: "8px 10px 8px 14px",
        background: "var(--lbb-surface)", border: "1px solid var(--lbb-border2)",
        borderRadius: 10, boxShadow: "var(--lbb-shadowLg)", zIndex: 5, whiteSpace: "nowrap",
      }}>
        <span style={{ fontSize: 12, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{count} performance{count > 1 ? "s" : ""}</span>
        <span style={{ width: 1, height: 18, background: "var(--lbb-border)" }}></span>
        <Button size="sm" variant="ghost" icon="download">Export M3U</Button>
        <Button size="sm" variant="secondary" icon="star">Wishlist gaps</Button>
        <Button size="sm" variant="primary" icon="upload">Add to qBittorrent</Button>
        <IconButton icon="x" size={24} title="Clear selection" onClick={onClear} />
      </div>
    );
  }

  Object.assign(window, {
    PERF_RatingChip: RatingChip,
    PERF_SourceBadge: SourceBadge,
    PERF_SourceStrip: SourceStrip,
    PERF_FamilyStrip: FamilyStrip,
    PERF_FamilyChip: FamilyChip,
    PERF_MatchChip: MatchChip,
    PERF_CoverageChip: CoverageChip,
    PERF_FacetRail: FacetRail,
    PERF_DetailPanel: DetailPanel,
    PERF_BulkBar: BulkBar,
  });
})();
