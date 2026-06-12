// collect-states.jsx
// Pipeline · Step 5 (File) — the routing-driven states the new backend adds.
// One panel per file.status / error_code, in the CollectStage visual language,
// so each maps straight onto _pipeline_process_folder's row["file"] payload.
//
//   status   dot      row action          source
//   mute     grey     —                   step not selected
//   ready    orange   File →              resolve_destination_for_lb ok + online
//   blocked  red      Resolve →           no_date|no_route|mount_offline|dest_exists|db_error
//   filed    green    In collection chip  file_folder ok

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Banner } = window;
  const mono = "var(--lbb-mono)";
  const lbl = { fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" };

  const DOT = { mute: "var(--lbb-mute-bar)", ready: "var(--lbb-warn-bar)", blocked: "var(--lbb-bad-bar)", filed: "var(--lbb-ok-bar)" };

  // 1–2–3–4–5 stage rail with step 5 painted by status.
  function MiniStepper({ status }) {
    const done = ["var(--lbb-ok-bar)", "var(--lbb-ok-bar)", "var(--lbb-ok-bar)", "var(--lbb-ok-bar)", DOT[status]];
    return (
      <div style={{ display: "inline-flex", alignItems: "center", gap: 0 }}>
        {[1, 2, 3, 4, 5].map((n, i) => (
          <React.Fragment key={n}>
            {i > 0 && <span style={{ width: 16, height: 2, background: i === 4 ? "var(--lbb-ok-bar)" : "var(--lbb-ok-bar)" }} />}
            <span style={{ width: 18, height: 18, borderRadius: "50%", background: done[i], color: "#fff",
              display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700,
              border: n === 5 && status === "mute" ? "1.5px solid var(--lbb-fg3)" : "none", boxSizing: "border-box",
              ...(n === 5 && status === "mute" ? { background: "var(--lbb-surface)", color: "var(--lbb-fg3)" } : {}) }}>
              {i < 4 ? <Icon name="check" size={11} /> : n}
            </span>
          </React.Fragment>
        ))}
      </div>
    );
  }

  // Header for a single state spec card.
  function StateHead({ status, code, title, sub, rowAction }) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 16px", borderBottom: "1px solid var(--lbb-border)", background: "var(--lbb-surface2)" }}>
        <span style={{ width: 10, height: 10, borderRadius: "50%", background: DOT[status], flex: "0 0 auto" }} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--lbb-fg)", whiteSpace: "nowrap" }}>{title}</span>
            <code style={{ fontFamily: mono, fontSize: 11, color: "var(--lbb-fg2)", background: "var(--lbb-surface)", border: "1px solid var(--lbb-border)", borderRadius: 4, padding: "1px 6px", whiteSpace: "nowrap", flex: "0 0 auto" }}>
              status:{status}{code ? ` · ${code}` : ""}
            </code>
          </div>
          {sub && <div style={{ fontSize: 11.5, color: "var(--lbb-fg3)", marginTop: 3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{sub}</div>}
        </div>
        <MiniStepper status={status} />
        <div style={{ width: 1, height: 26, background: "var(--lbb-border2)" }} />
        <div style={{ display: "flex", alignItems: "center", gap: 6, flex: "0 0 auto" }}>
          <span style={{ ...lbl, fontSize: 9.5 }}>row</span>{rowAction}
        </div>
      </div>
    );
  }

  // The staging → destination route box (echoes CollectStage).
  function RouteBox({ src, dest, year, mount, online = true, blocked = false }) {
    return (
      <div style={{ border: "1px solid var(--lbb-border)", borderRadius: 10, overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 14px", background: "var(--lbb-surface)" }}>
          <Icon name="folder" size={14} style={{ color: "var(--lbb-fg3)", flex: "0 0 auto" }} />
          <span style={{ fontFamily: mono, fontSize: 12, color: "var(--lbb-fg2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{src}</span>
          <span style={{ marginLeft: "auto", ...lbl, fontSize: 9.5, flex: "0 0 auto" }}>staging</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "1px 0", background: "var(--lbb-surface)" }}>
          <Icon name="drop" size={14} style={{ color: blocked ? "var(--lbb-bad-bar)" : "var(--lbb-accent-mid)" }} />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 14px", borderTop: "1px solid var(--lbb-border)",
          background: blocked ? "var(--lbb-bad-bg)" : "var(--lbb-accent-soft)" }}>
          <Icon name="collection" size={15} style={{ color: blocked ? "var(--lbb-bad-fg)" : "var(--lbb-accent-mid)", flex: "0 0 auto" }} />
          {dest ? (
            <span style={{ fontFamily: mono, fontSize: 12.5, fontWeight: 600, color: "var(--lbb-fg)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{dest}</span>
          ) : (
            <span style={{ fontSize: 12.5, color: "var(--lbb-bad-fg)", fontStyle: "italic" }}>no destination resolved</span>
          )}
          <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, flex: "0 0 auto" }}>
            {year && <Pill tone={blocked ? "bad" : "info"} soft>year {year}</Pill>}
            {mount && <Pill tone={online ? "ok" : "bad"} soft dot>{mount} · {online ? "online" : "offline"}</Pill>}
          </span>
        </div>
      </div>
    );
  }

  function Field({ k, v, accent }) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 14px", borderBottom: "1px solid var(--lbb-border)" }}>
        <span style={{ ...lbl, width: 110, flex: "0 0 110px" }}>{k}</span>
        <span style={{ fontSize: 12.5, fontFamily: mono, fontWeight: accent ? 700 : 500, color: accent ? "var(--lbb-accent-mid)" : "var(--lbb-fg)" }}>{v}</span>
      </div>
    );
  }

  // ── State bodies ──────────────────────────────────────────────────
  function ReadyBody({ fileMode, onResolve }) {
    return (
      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        <RouteBox src="/mnt/HOPPER/incoming/bd2026-04-08 Chicago IL (LB-16593)"
          dest="/mnt/dylan4/2026/bd2026-04-08 Chicago IL (LB-16593)" year="2026" mount="DYLAN4" online />
        <div style={{ border: "1px solid var(--lbb-border)", borderRadius: 8, overflow: "hidden" }}>
          <Field k="LB#" v="LB-16593" accent />
          <Field k="Route" v="2026 → DYLAN4 · sub-path 2026" />
          <Field k="Filing mode" v={fileMode === "copy" ? "copy · original kept" : "move · default"} />
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 14px" }}>
            <span style={{ ...lbl, width: 110, flex: "0 0 110px" }}>Pre-flight</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--lbb-ok-fg)", fontWeight: 600 }}>
              <Icon name="check" size={13} /> route resolved · mount online · name free
            </span>
          </div>
        </div>
        <Banner tone="info" icon="info" title="What filing does"
          action={<Button variant="primary" size="sm" icon="collection">{fileMode === "copy" ? "Copy into collection" : "File into collection"}</Button>}>
          {fileMode === "copy" ? "Copies" : "Moves"} the folder to <span style={{ fontFamily: mono }}>/mnt/dylan4/2026/</span>, registers it in <strong>my_collection</strong>, and tags it owned. Logged to <span style={{ fontFamily: mono }}>rename_history</span> — reversible for 30 days.
        </Banner>
      </div>
    );
  }

  function BlockedBody({ code, onResolve }) {
    const M = {
      no_route: {
        src: "/mnt/HOPPER/gd1973-07-01 Roosevelt Stadium",
        year: "1973", mount: null, online: true,
        banner: <>No route is configured for <strong>1973</strong>. Add one in <strong>Mounts &amp; Routes</strong> — a quick range fill (e.g. 1970–1979 → DYLAN2) covers it and every neighbouring year at once.</>,
        primary: { icon: "setup", label: "Resolve in Mounts & Routes →", to: "mounts" },
        secondary: null,
        hint: "Pipeline holds the folder here; nothing on disk is touched.",
      },
      mount_offline: {
        src: "/mnt/HOPPER/bd1979-11-16 Nashville TN",
        year: "1979", mount: "DYLAN2", online: false,
        banner: <>The routed mount <strong>DYLAN2</strong> isn’t reachable at <span style={{ fontFamily: mono }}>/mnt/dylan2</span>. Reconnect the drive, then retry — or re-route 1979 to an online mount.</>,
        primary: { icon: "refresh", label: "Retry — check mount", to: null },
        secondary: { icon: "setup", label: "Re-route year →", to: "mounts" },
        hint: "Resolves automatically the moment the drive comes back online.",
      },
      dest_exists: {
        src: "/mnt/HOPPER/bd2026-04-08 Chicago IL (LB-16593)",
        year: "2026", mount: "DYLAN4", online: true,
        dest: "/mnt/dylan4/2026/bd2026-04-08 Chicago IL (LB-16593)",
        banner: <>A folder with this name already exists at the destination. Filing is refused so nothing is overwritten. Reveal the existing folder to compare, or rename one of them.</>,
        primary: { icon: "reveal", label: "Reveal existing folder", to: null },
        secondary: { icon: "rename", label: "Rename & retry", to: null },
        hint: "Strictly non-destructive — the move never runs while a collision exists.",
      },
      no_date: {
        src: "/mnt/HOPPER/bd-xxxx Unknown date soundboard",
        year: null, mount: null, online: true,
        banner: <>The show’s <span style={{ fontFamily: mono }}>date_str</span> has no usable year, so no route can be picked. Set the date on the LB entry — the route resolves on the next pass.</>,
        primary: { icon: "dbeditor", label: "Set date on LB entry", to: null },
        secondary: { icon: "lookup", label: "Re-run lookup", to: null },
        hint: "All other folders in the batch file normally — this one waits for a date.",
      },
      db_error: {
        src: "/mnt/HOPPER/bd2026-05-15 Denver CO",
        year: "2026", mount: "DYLAN4", online: true,
        banner: <>The collection database couldn’t be read while resolving the route. This is usually transient — retry, and check the log if it persists.</>,
        primary: { icon: "refresh", label: "Retry", to: null },
        secondary: { icon: "reveal", label: "Open log", to: null },
        hint: "No filesystem operation was attempted.",
      },
    }[code];

    return (
      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        <RouteBox src={M.src} dest={M.dest || null} year={M.year} mount={M.mount} online={M.online} blocked />
        <Banner tone={code === "mount_offline" || code === "no_date" ? "warn" : "bad"} icon="alert">{M.banner}</Banner>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Button variant={M.primary.to ? "primary" : "secondary"} size="md" icon={M.primary.icon}
            onClick={() => M.primary.to && onResolve && onResolve(M.primary.to, M.year)}>{M.primary.label}</Button>
          {M.secondary && <Button variant="ghost" size="md" icon={M.secondary.icon}
            onClick={() => M.secondary.to && onResolve && onResolve(M.secondary.to, M.year)}>{M.secondary.label}</Button>}
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 11, color: "var(--lbb-fg3)" }}>{M.hint}</span>
        </div>
      </div>
    );
  }

  function FiledBody({ fileMode }) {
    return (
      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "16px 18px", background: "var(--lbb-ok-bg)", border: "1px solid var(--lbb-ok-bar)", borderRadius: 10 }}>
          <div style={{ width: 42, height: 42, borderRadius: 10, flex: "0 0 42px", background: "var(--lbb-ok-bar)", color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center" }}><Icon name="collection" size={22} /></div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>{fileMode === "copy" ? "Copied to DYLAN4 · tagged owned" : "Filed to DYLAN4 · tagged owned"}</div>
            <div style={{ fontSize: 12, fontFamily: mono, color: "var(--lbb-fg2)", marginTop: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>/mnt/dylan4/2026/bd2026-03-27 La Crosse WI (LB-16588)</div>
          </div>
          <div style={{ display: "flex", gap: 6, flex: "0 0 auto" }}><Pill tone="ok" soft dot>Owned</Pill><Pill tone="ok" soft>Public</Pill></div>
        </div>
        <div style={{ border: "1px solid var(--lbb-border)", borderRadius: 8, overflow: "hidden" }}>
          <Field k="LB#" v="LB-16588" accent />
          <Field k="Filed to" v="DYLAN4 · /mnt/dylan4/2026/" />
          <Field k="Mode" v={fileMode === "copy" ? "copy" : "move"} />
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 14px" }}>
            <span style={{ ...lbl, width: 110, flex: "0 0 110px" }}>my_collection</span>
            <span style={{ fontSize: 12, color: "var(--lbb-fg2)" }}>15,967 → <strong style={{ color: "var(--lbb-ok-fg)" }}>15,968</strong> items</span>
          </div>
        </div>
        <Banner tone="info" icon="info">Registered in <span style={{ fontFamily: mono }}>my_collection</span> with its on-disk path. Reversible for 30 days via <span style={{ fontFamily: mono }}>rename_history</span>.</Banner>
      </div>
    );
  }

  // Compact batch-row action chips used in the header.
  const RowAction = {
    mute:   <span style={{ fontSize: 12, color: "var(--lbb-fg3)" }}>—</span>,
    ready:  <Button size="sm" variant="primary" icon="collection">File</Button>,
    blocked:<Button size="sm" variant="secondary" iconRight="chevRight">Resolve</Button>,
    filed:  <Pill tone="ok" soft dot>In collection</Pill>,
  };

  const STATES = [
    { id: "ready",    status: "ready",   title: "Ready to file",  sub: "Route resolved, mount online, destination name free — the happy path." },
    { id: "no_route", status: "blocked", code: "no_route",      title: "Blocked · no route for year", sub: "The show’s year has no row in collection_routes." },
    { id: "mount_offline", status: "blocked", code: "mount_offline", title: "Blocked · mount offline", sub: "The routed drive isn’t currently reachable." },
    { id: "dest_exists", status: "blocked", code: "dest_exists", title: "Blocked · destination exists", sub: "A folder of the same name is already at the destination." },
    { id: "no_date",  status: "blocked", code: "no_date",       title: "Blocked · no date", sub: "date_str has no usable year to route on." },
    { id: "filed",    status: "filed",   title: "In collection",  sub: "Moved/copied to its mount and registered — the bridge has run." },
  ];

  function CollectStates({ fileMode = "move", onResolve }) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {/* legend / batch bar */}
        <div style={{ background: "var(--lbb-surface)", border: "1px solid var(--lbb-border)", borderRadius: 10, padding: "14px 18px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 34, height: 34, borderRadius: 9, background: "var(--lbb-accent-mid)", color: "var(--lbb-accent-onMid)", display: "inline-flex", alignItems: "center", justifyContent: "center" }}><Icon name="collection" size={17} /></div>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700 }}>Step 5 · File into collection</div>
                <div style={{ fontSize: 11.5, color: "var(--lbb-fg3)" }}>Routing-driven states the new filer adds to the pipeline.</div>
              </div>
            </div>
            <div style={{ flex: 1 }} />
            <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
              {[["mute", "Mute · not selected"], ["ready", "Ready · file"], ["blocked", "Blocked · resolve"], ["filed", "Filed · in collection"]].map(([k, t]) => (
                <span key={k} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11.5, color: "var(--lbb-fg2)" }}>
                  <span style={{ width: 9, height: 9, borderRadius: "50%", background: DOT[k], border: k === "mute" ? "1.5px solid var(--lbb-fg3)" : "none", boxSizing: "border-box" }} />{t}
                </span>
              ))}
            </div>
            <div style={{ width: 1, height: 28, background: "var(--lbb-border2)" }} />
            <Button variant="primary" size="md" icon="collection">File all 4 ready</Button>
          </div>
          <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--lbb-border)", fontSize: 11.5, color: "var(--lbb-fg2)", display: "flex", alignItems: "center", gap: 8 }}>
            <Icon name="info" size={13} style={{ color: "var(--lbb-fg3)" }} />
            Batch filing processes folders independently — any that fail surface back in <strong style={{ color: "var(--lbb-bad-fg)" }}>Needs you</strong> with their own <span style={{ fontFamily: mono }}>file.error</span>, the rest still file.
          </div>
        </div>

        {/* state spec cards */}
        {STATES.map(s => (
          <div key={s.id} style={{ background: "var(--lbb-surface)", border: "1px solid var(--lbb-border)", borderRadius: 10, overflow: "hidden", boxShadow: "var(--lbb-shadow)" }}>
            <StateHead status={s.status} code={s.code} title={s.title} sub={s.sub} rowAction={RowAction[s.status]} />
            {s.status === "ready" ? <ReadyBody fileMode={fileMode} onResolve={onResolve} />
              : s.status === "filed" ? <FiledBody fileMode={fileMode} />
              : <BlockedBody code={s.code} onResolve={onResolve} />}
          </div>
        ))}
      </div>
    );
  }

  window.LBB_CollectStates = CollectStates;
})();
