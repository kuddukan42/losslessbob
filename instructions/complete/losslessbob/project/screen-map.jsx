// screen-map.jsx
// Map · Geocoded concert venues. Backend /api/map/data + /api/geocode/*.
// Static preview here; live Leaflet map opens at localhost:5174/map.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Chip, Input, IconButton,
          TableShell, TH, TR, TD } = window;

  // Pins on the world preview
  const PINS = [
    { x: 22, y: 28, c: "#3b6a99",            n: 3,   l: "Hibbing, MN",            era: "1957"        },
    { x: 36, y: 36, c: "#2a8b6f",            n: 87,  l: "Greenwich Village, NY",  era: "1961–63"     },
    { x: 28, y: 48, c: "var(--lbb-accent-mid)", n: 124, l: "San Francisco Bay",    era: "1965–80"     },
    { x: 44, y: 42, c: "#c25a48",            n: 56,  l: "Texas (Houston / Dallas)", era: "1981–86"   },
    { x: 56, y: 30, c: "var(--lbb-accent-mid)", n: 290, l: "NYC area",              era: "1980s"       },
    { x: 60, y: 50, c: "#b58a3a",            n: 67,  l: "Florida",                era: "2000s+"      },
    { x: 72, y: 28, c: "#2a8b6f",            n: 32,  l: "London / Earl's Court",  era: "1978–81"     },
    { x: 78, y: 36, c: "#c25a48",            n: 22,  l: "Paris / Avignon",        era: "1990s"       },
    { x: 82, y: 50, c: "#b58a3a",            n: 14,  l: "Cairo",                  era: "1995"        },
    { x: 50, y: 68, c: "#2a8b6f",            n: 9,   l: "Sydney",                 era: "1986"        },
    { x: 30, y: 64, c: "var(--lbb-accent-mid)", n: 18, l: "Buenos Aires",          era: "1990s"       },
  ];

  // Selected location's LBs (for the right side panel)
  const SELECTED_LBS = [
    { lb: "LB-280",  d: "1980-11-09", v: "Fox Warfield, San Francisco", owned: true,  status: "current" },
    { lb: "LB-281",  d: "1980-11-10", v: "Fox Warfield, San Francisco", owned: true,  status: "current" },
    { lb: "LB-282",  d: "1980-11-11", v: "Fox Warfield, San Francisco", owned: true,  status: "current" },
    { lb: "LB-283",  d: "1980-11-12", v: "Fox Warfield, San Francisco", owned: false, status: "current" },
    { lb: "LB-294",  d: "1980-11-22", v: "Berkeley Comm. Theatre",      owned: true,  status: "current" },
    { lb: "LB-2841", d: "1986-09-13", v: "Greek Theatre, Berkeley",     owned: true,  status: "current" },
    { lb: "LB-7710", d: "2002-10-13", v: "Berkeley Comm. Theatre",      owned: false, status: "missing" },
    { lb: "LB-7716", d: "2002-10-15", v: "Berkeley Comm. Theatre",      owned: false, status: "current" },
  ];

  function ScreenMap() {
    const [yearMin, setYearMin] = React.useState(1980);
    const [yearMax, setYearMax] = React.useState(1989);
    const [owned,   setOwned]   = React.useState("all");
    const [status,  setStatus]  = React.useState("all");
    const [selectedPin, setSelectedPin] = React.useState(2); // Bay Area

    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
        {/* Header */}
        <div style={{
          padding: "14px 24px", borderBottom: "1px solid var(--lbb-border)",
          display: "flex", alignItems: "center", gap: 14,
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: "var(--lbb-surface2)", border: "1px solid var(--lbb-border)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
          }}><Icon name="map" size={18} /></div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, letterSpacing: -0.01 }}>Concert map</h1>
              <Pill tone="ok" soft>6,676 geocoded</Pill>
              <Pill tone="warn" soft>9,954 awaiting geocoding</Pill>
            </div>
            <div style={{ fontSize: 12, color: "var(--lbb-fg3)", marginTop: 2 }}>
              Filter venues by year, ownership, or status. Live map opens in your browser at <span style={{ fontFamily: "var(--lbb-mono)" }}>localhost:5174/map</span>.
            </div>
          </div>
          <div style={{ flex: 1 }} />
          <Button variant="ghost" size="sm" icon="copy">Copy share URL</Button>
          <Button variant="primary" size="sm" icon="reveal">Open live map ↗</Button>
        </div>

        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "300px 1fr 320px", minHeight: 0 }}>
          {/* Filter rail */}
          <aside style={{
            background: "var(--lbb-surface)", borderRight: "1px solid var(--lbb-border)",
            padding: 18, display: "flex", flexDirection: "column", gap: 18, overflowY: "auto",
          }}>
            {/* Year range */}
            <section>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>Year range</span>
                <div style={{ flex: 1 }} />
                <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 11.5, fontWeight: 600, color: "var(--lbb-accent-mid)" }}>{yearMin} – {yearMax}</span>
              </div>
              {/* Dual handle slider (visual stand-in) */}
              <div style={{ position: "relative", height: 28, padding: "10px 0" }}>
                <div style={{ position: "absolute", top: 13, left: 0, right: 0, height: 4, background: "var(--lbb-border)", borderRadius: 2 }} />
                <div style={{ position: "absolute", top: 13, left: "28%", right: "33%", height: 4, background: "var(--lbb-accent-mid)", borderRadius: 2 }} />
                <div style={{ position: "absolute", top: 7, left: "28%", width: 14, height: 14, borderRadius: "50%", background: "#fff", border: "2px solid var(--lbb-accent-mid)", transform: "translateX(-50%)" }} />
                <div style={{ position: "absolute", top: 7, left: "67%", width: 14, height: 14, borderRadius: "50%", background: "#fff", border: "2px solid var(--lbb-accent-mid)", transform: "translateX(-50%)" }} />
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                <Input size="sm" placeholder="1961" style={{ flex: 1 }} />
                <span style={{ alignSelf: "center", color: "var(--lbb-fg3)" }}>–</span>
                <Input size="sm" placeholder="2030" style={{ flex: 1 }} />
              </div>
              <div style={{ display: "flex", gap: 4, marginTop: 6, flexWrap: "wrap" }}>
                {[["60s","1960","1969"],["70s","1970","1979"],["80s","1980","1989"],["90s","1990","1999"],["00s","2000","2009"],["10s+","2010","2030"]].map(([l,a,b]) => (
                  <Chip key={l} size="sm" active={yearMin === +a && yearMax === +b} onClick={() => { setYearMin(+a); setYearMax(+b); }}>{l}</Chip>
                ))}
              </div>
            </section>

            {/* Ownership */}
            <section>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 8 }}>Ownership</div>
              <div style={{ display: "flex", padding: 2, background: "var(--lbb-surface2)", borderRadius: 6, border: "1px solid var(--lbb-border)" }}>
                {[["all","All"],["owned","Owned"],["unowned","Not owned"]].map(([k,l]) => (
                  <button key={k} onClick={() => setOwned(k)}
                    style={{
                      flex: 1, padding: "5px 8px", borderRadius: 4,
                      background: owned === k ? "var(--lbb-surface)" : "transparent",
                      color: owned === k ? "var(--lbb-fg)" : "var(--lbb-fg2)",
                      fontWeight: owned === k ? 600 : 500, fontSize: 11.5,
                      border: owned === k ? "1px solid var(--lbb-border2)" : "1px solid transparent",
                      cursor: "pointer", fontFamily: "inherit",
                    }}>{l}</button>
                ))}
              </div>
            </section>

            {/* Status */}
            <section>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 8 }}>LB status</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {[
                  { k: "all",     l: "All entries",       n: 6676 },
                  { k: "public",  l: "Public",            n: 5184 },
                  { k: "private", l: "Private",           n: 1404 },
                  { k: "missing", l: "Missing on archive", n: 88 },
                ].map(o => (
                  <label key={o.k} style={{
                    display: "flex", alignItems: "center", gap: 8, padding: "5px 8px", borderRadius: 6,
                    background: status === o.k ? "var(--lbb-accent-soft)" : "transparent",
                    cursor: "pointer", fontSize: 12,
                  }}>
                    <input type="radio" name="status" checked={status === o.k} onChange={() => setStatus(o.k)} />
                    <span style={{ flex: 1, color: status === o.k ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)", fontWeight: status === o.k ? 600 : 500 }}>{o.l}</span>
                    <span style={{ fontSize: 10.5, color: "var(--lbb-fg3)", fontFamily: "var(--lbb-mono)" }}>{o.n.toLocaleString()}</span>
                  </label>
                ))}
              </div>
            </section>

            {/* Free-text */}
            <section>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 8 }}>Search</div>
              <Input size="sm" icon="search" placeholder="Location or LB#…" style={{ width: "100%" }} />
            </section>

            {/* Display */}
            <section>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 8 }}>Display</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {[
                  { l: "Cluster markers",   v: true  },
                  { l: "Color by decade",   v: true  },
                  { l: "Heatmap overlay",   v: false },
                  { l: "Show venue labels", v: false },
                ].map((opt, i) => (
                  <label key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--lbb-fg2)" }}>
                    <input type="checkbox" defaultChecked={opt.v} />
                    {opt.l}
                  </label>
                ))}
              </div>
            </section>

            <div style={{ flex: 1 }} />

            {/* Footer actions */}
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <Button variant="primary" size="sm" icon="map" block>Apply filters</Button>
              <Button variant="ghost" size="sm" block>Reset to defaults</Button>
            </div>
          </aside>

          {/* Map preview */}
          <section style={{ position: "relative", minHeight: 0, overflow: "hidden" }}>
            <div className="lbb-map-canvas" style={{ position: "absolute", inset: 0 }} />

            {/* Pins */}
            {PINS.map((p, i) => (
              <button key={i} onClick={() => setSelectedPin(i)}
                style={{
                  position: "absolute", left: `${p.x}%`, top: `${p.y}%`,
                  transform: "translate(-50%, -50%) scale(" + (i === selectedPin ? 1.18 : 1) + ")",
                  border: "none", background: "transparent", padding: 0, cursor: "pointer",
                  zIndex: i === selectedPin ? 5 : 1,
                  transition: "transform 120ms ease",
                }}>
                <div style={{
                  minWidth: 26, height: 26, padding: "0 7px",
                  borderRadius: 999, background: p.c, color: "#fff",
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                  fontSize: 11.5, fontWeight: 700, fontFamily: "var(--lbb-mono)",
                  boxShadow: i === selectedPin
                    ? "0 0 0 4px rgba(255,255,255,0.5), 0 8px 24px rgba(0,0,0,0.35)"
                    : "0 1px 0 rgba(255,255,255,0.3) inset, 0 4px 12px rgba(0,0,0,0.25)",
                  border: "2px solid #fff",
                }}>{p.n}</div>
                {i === selectedPin && (
                  <div style={{
                    position: "absolute", top: "100%", left: "50%", transform: "translateX(-50%)",
                    marginTop: 6, padding: "5px 9px",
                    background: "var(--lbb-surface)", border: "1px solid var(--lbb-border)",
                    borderRadius: 6, fontSize: 11, color: "var(--lbb-fg)", whiteSpace: "nowrap",
                    boxShadow: "var(--lbb-shadow)",
                    fontFamily: "inherit",
                  }}>{p.l} <span style={{ color: "var(--lbb-fg3)" }}>· {p.era}</span></div>
                )}
              </button>
            ))}

            {/* Top-left summary card */}
            <div style={{
              position: "absolute", top: 16, left: 16,
              padding: "12px 14px", background: "var(--lbb-surface)",
              border: "1px solid var(--lbb-border)", borderRadius: 8,
              boxShadow: "var(--lbb-shadow)", maxWidth: 320,
            }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 4 }}>Visible</div>
              <div style={{ fontSize: 22, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>1,842 <span style={{ fontSize: 12, fontWeight: 500, color: "var(--lbb-fg3)" }}>pins</span></div>
              <div style={{ fontSize: 11.5, color: "var(--lbb-fg2)", marginTop: 2 }}>{yearMin} – {yearMax} · {owned === "all" ? "all owners" : owned === "owned" ? "owned only" : "not owned"} · 312 venues</div>
              <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--lbb-border)", display: "flex", gap: 12, fontSize: 11, color: "var(--lbb-fg3)" }}>
                <span><strong style={{ color: "var(--lbb-fg2)" }}>137</strong> owned</span>
                <span><strong style={{ color: "var(--lbb-fg2)" }}>1,705</strong> wishlist</span>
              </div>
            </div>

            {/* Top-right legend */}
            <div style={{
              position: "absolute", top: 16, right: 16,
              padding: "12px 14px", background: "var(--lbb-surface)",
              border: "1px solid var(--lbb-border)", borderRadius: 8,
              boxShadow: "var(--lbb-shadow)",
            }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 6 }}>Decades</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11.5 }}>
                {[
                  { c: "#3b6a99", l: "1960s" },
                  { c: "#2a8b6f", l: "1970s" },
                  { c: "var(--lbb-accent-mid)", l: "1980s" },
                  { c: "#c25a48", l: "1990s" },
                  { c: "#b58a3a", l: "2000s+" },
                ].map((d, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ width: 11, height: 11, borderRadius: "50%", background: d.c, border: "2px solid var(--lbb-surface)", boxShadow: "0 0 0 1px var(--lbb-border2)" }} />
                    <span style={{ color: "var(--lbb-fg2)" }}>{d.l}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Zoom */}
            <div style={{
              position: "absolute", bottom: 18, right: 18,
              display: "flex", flexDirection: "column", borderRadius: 8, overflow: "hidden",
              background: "var(--lbb-surface)", border: "1px solid var(--lbb-border)",
              boxShadow: "var(--lbb-shadow)",
            }}>
              <button style={{ width: 32, height: 32, background: "transparent", border: "none", borderBottom: "1px solid var(--lbb-border)", color: "var(--lbb-fg2)", cursor: "pointer" }}><Icon name="plus" size={14} /></button>
              <button style={{ width: 32, height: 32, background: "transparent", border: "none", color: "var(--lbb-fg2)", cursor: "pointer", fontSize: 16, fontWeight: 700 }}>−</button>
            </div>

            {/* Unplottable banner */}
            <div style={{
              position: "absolute", bottom: 18, left: 18,
              padding: "8px 12px", background: "var(--lbb-surface)",
              border: "1px solid var(--lbb-border)", borderRadius: 8,
              fontSize: 11, color: "var(--lbb-fg2)",
              display: "flex", alignItems: "center", gap: 8,
            }}>
              <Icon name="info" size={12} style={{ color: "var(--lbb-info-fg)" }} />
              <span><strong>9,954 entries</strong> have no coordinates yet</span>
              <Button size="sm" variant="ghost">View in Curator</Button>
            </div>
          </section>

          {/* Selected venue panel */}
          <aside style={{
            background: "var(--lbb-surface)", borderLeft: "1px solid var(--lbb-border)",
            display: "flex", flexDirection: "column", minHeight: 0,
          }}>
            <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--lbb-border)" }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase", marginBottom: 6 }}>
                Selected · {PINS[selectedPin].era}
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, color: "var(--lbb-fg)" }}>{PINS[selectedPin].l}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
                <Pill tone="info" soft>{PINS[selectedPin].n} shows</Pill>
                <span style={{ fontSize: 11, color: "var(--lbb-fg3)" }}>· 4 owned · 3 wishlist · 1 missing</span>
              </div>
              <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
                <Button size="sm" variant="primary" icon="search" block>Open list in Search</Button>
                <Button size="sm" variant="ghost" icon="copy">Copy</Button>
              </div>
            </div>

            <div style={{ padding: "10px 14px 4px", fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>
              Entries at this location
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "0 6px 8px" }}>
              {SELECTED_LBS.map((r, i) => (
                <button key={i} style={{
                  width: "100%", display: "flex", alignItems: "center", gap: 8,
                  padding: "7px 10px", marginBottom: 1, borderRadius: 6,
                  background: "transparent", color: "var(--lbb-fg2)",
                  border: "1px solid transparent", textAlign: "left",
                  fontFamily: "inherit", cursor: "pointer",
                }}>
                  <span style={{
                    width: 6, height: 6, borderRadius: "50%",
                    background: r.status === "missing" ? "var(--lbb-bad-bar)" : "var(--lbb-ok-bar)",
                  }} />
                  <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ fontFamily: "var(--lbb-mono)", fontWeight: 600, fontSize: 11.5, color: "var(--lbb-accent-mid)" }}>{r.lb}</span>
                      <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 10.5, color: "var(--lbb-fg3)" }}>{r.d}</span>
                      {r.owned && <Icon name="check" size={10} style={{ color: "var(--lbb-ok-bar)" }} />}
                    </span>
                    <span style={{ fontSize: 10.5, color: "var(--lbb-fg3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.v}</span>
                  </span>
                </button>
              ))}
            </div>

            <div style={{ padding: 12, borderTop: "1px solid var(--lbb-border)" }}>
              <div style={{
                padding: "8px 10px", borderRadius: 6,
                background: "var(--lbb-info-bg)", border: "1px solid var(--lbb-info-bar)",
                fontSize: 11, color: "var(--lbb-fg2)",
                display: "flex", alignItems: "flex-start", gap: 8,
              }}>
                <Icon name="info" size={11} style={{ color: "var(--lbb-info-fg)", marginTop: 2 }} />
                <span>Double-click any entry to open it on losslessbob.com. Use <strong>Open in Search</strong> to bring this list into the main search view.</span>
              </div>
            </div>
          </aside>
        </div>
      </div>
    );
  }

  window.LBB_ScreenMap = ScreenMap;
})();
