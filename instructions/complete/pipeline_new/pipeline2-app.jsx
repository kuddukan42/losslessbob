// pipeline2-app.jsx
// The refined Pipeline Workspace. One screen, master/detail:
//   left  = folder queue (the batch)
//   main  = OVERVIEW (grouped batch table) ⇄ DETAIL (one folder's journey)
// The four old sub-tools live inside the detail view as stages — you never
// leave the pipeline to resolve a problem.

(() => {
  const Icon = window.LBB_Icon;
  const { Button, Pill, Input, Chip, IconButton, TableShell, TH, TR, TD, GroupRow, Banner } = window;
  const P2 = window.LBB_P2;
  const { StatusTag, StageTracker, StageStepper, QueueRow } = window.LBB_P2_Parts;
  const { VerifyStage, LookupStage, RenameStage, LBDIRStage, CollectStage } = window.LBB_P2_Stages;
  const { STATE, BUCKET, STAGES } = P2;

  const BUCKET_ORDER = ["needs", "ready", "running", "shelf", "done"];

  // Believable "incoming" folders fabricated when the user drops/adds folders.
  const INCOMING_POOL = [
    { name: "bd2026-05-30 Eugene OR",        path: "/mnt/HOPPER/bd2026-05-30 Eugene OR",        fmt: "FLAC", tracks: 21 },
    { name: "bd2026-05-28 Portland OR",      path: "/mnt/HOPPER/bd2026-05-28 Portland OR",      fmt: "FLAC", tracks: 18 },
    { name: "bd2026-05-24 Berkeley CA",      path: "/mnt/HOPPER/bd2026-05-24 Berkeley CA",      fmt: "FLAC", tracks: 24 },
    { name: "gd1972-05-04 Olympia WA SBD",   path: "/mnt/HOPPER/gd1972-05-04 Olympia WA SBD",   fmt: "FLAC", tracks: 16 },
    { name: "bd2026-05-19 Salt Lake City UT",path: "/mnt/HOPPER/bd2026-05-19 Salt Lake City UT",fmt: "FLAC", tracks: 20 },
    { name: "bd2026-05-15 Denver CO",        path: "/mnt/HOPPER/bd2026-05-15 Denver CO",        fmt: "FLAC", tracks: 22 },
  ];

  // The single plain-language folder status (what the user should read).
  function folderStatus(f) {
    if (f.bucket === "done")    return { state: "pass",    label: "In collection", reason: f.collected ? `Filed to ${f.collected.mount} · tagged owned` : "Filed & tagged" };
    if (f.bucket === "shelf")   return { state: "action",  label: "Ready to file",  reason: "Archive-clean — file into the collection for final storage" };
    if (f.bucket === "running") return { state: "running", label: "Running",    reason: f.progress ? `Verifying ${f.progress.done}/${f.progress.total}…` : "In progress" };
    if (f.bucket === "ready")   return { state: "action",  label: "Ready to apply", reason: "Confident match — just apply the rename" };
    // needs
    const s = f.steps[f.stuckAt];
    return { state: s.state, label: s.state === "blocked" ? "Blocked" : "Needs you", reason: s.reason };
  }

  function App() {
    const [folders, setFolders] = React.useState(() => JSON.parse(JSON.stringify(P2.FOLDERS)));
    const [filter, setFilter]   = React.useState("all");
    const [openId, setOpenId]   = React.useState(null);     // null = overview
    const [activeStage, setActiveStage] = React.useState("verify");
    const [sel, setSel]         = React.useState(() => new Set());
    const [autorun, setAutorun] = React.useState(true);
    const [toast, setToast]     = React.useState(null);
    const [railOpen, setRailOpen] = React.useState(true);
    const [query, setQuery]     = React.useState("");
    const [confirm, ConfirmHost] = window.LBB_P2_useConfirm();

    const counts = BUCKET_ORDER.reduce((a, b) => (a[b] = folders.filter(f => f.bucket === b).length, a), {});
    const readyIds = folders.filter(f => f.bucket === "ready").map(f => f.id);
    const open = folders.find(f => f.id === openId) || null;
    const q = query.trim().toLowerCase();
    const matchQ = (f) => !q || f.name.toLowerCase().includes(q) || (f.lb && f.lb.toLowerCase().includes(q));
    const shown = folders.filter(matchQ);
    const visibleCount = shown.filter(f => filter === "all" || f.bucket === filter).length;

    const flash = (msg) => { setToast(msg); clearTimeout(window.__p2t); window.__p2t = setTimeout(() => setToast(null), 2600); };

    // ── drag-to-queue ──
    const [dragging, setDragging] = React.useState(false);
    const dragDepth = React.useRef(0);
    const seq = React.useRef(0);
    const isFileDrag = (e) => e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files");

    // Fabricate a believable freshly-queued folder. When auto-run is on it lands
    // mid-verify (running); otherwise it waits for a manual verify.
    function makeIncoming(spec, running) {
      const total = spec.tracks;
      const done = running ? Math.max(1, Math.round(total * 0.35)) : 0;
      const files = Array.from({ length: total }, (_, i) => ({ n: `d01t${String(i + 1).padStart(2, "0")}.flac`, ok: "pass", disk: true }));
      return {
        id: `f-new-${++seq.current}`,
        bucket: running ? "running" : "needs",
        name: spec.name, path: spec.path, fmt: spec.fmt, tracks: total, lb: null,
        stuckAt: "verify",
        progress: running ? { done, total } : undefined,
        steps: {
          verify: running
            ? { state: "running", reason: `Hashing ${done} / ${total} files…` }
            : { state: "action",  reason: "Just queued — run verify to start the pipeline" },
          lookup: { state: "pending", reason: running ? "Queued behind verify" : "Waiting on a clean verify" },
          rename: { state: "pending", reason: "Needs an LB# first" },
          lbdir:  { state: "pending", reason: "—" },
          collect:{ state: "pending", reason: "Files into the collection after the sidecar reconciles" },
        },
        dest: P2.proposeDest({ name: spec.name }),
        verify: { total, pass: done, miss: 0, mism: 0, extra: 0, files },
      };
    }

    // Queue N fresh incoming folders (drop target + Add folders…)
    function queueIncoming(n) {
      const count = n || (1 + Math.floor(Math.random() * 2)); // 1–2
      const start = seq.current % INCOMING_POOL.length;
      const news = Array.from({ length: count }, (_, i) => makeIncoming(INCOMING_POOL[(start + i) % INCOMING_POOL.length], autorun));
      setFolders(fs => [...news, ...fs]);
      setFilter("all"); setQuery(""); setOpenId(null);
      flash(autorun
        ? `Queued ${count} folder${count === 1 ? "" : "s"} — verifying + looking up automatically`
        : `Queued ${count} folder${count === 1 ? "" : "s"} — auto-run is off, run verify when ready`);
    }

    // Bring back the full sample batch (escape hatch from the empty state)
    function seedSample() {
      setFolders(JSON.parse(JSON.stringify(P2.FOLDERS)));
      setFilter("all"); setQuery(""); setSel(new Set()); setOpenId(null);
      flash(`Restored the sample batch — ${P2.FOLDERS.length} folders`);
    }

    function onDragEnter(e) { if (!isFileDrag(e)) return; e.preventDefault(); dragDepth.current++; setDragging(true); }
    function onDragOver(e)  { if (!isFileDrag(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = "copy"; }
    function onDragLeave(e) { if (!dragging) return; dragDepth.current = Math.max(0, dragDepth.current - 1); if (dragDepth.current === 0) setDragging(false); }
    function onDrop(e)      { if (!dragging && !isFileDrag(e)) return; e.preventDefault(); dragDepth.current = 0; setDragging(false); queueIncoming(); }

    // ── mutations ──
    // A reconciled folder now lands on the SHELF (ready to file), not Done.
    // "Done" means it's been filed into the collection.
    function reconciledShelf(f) {
      return { ...f, bucket: "shelf", stuckAt: "collect",
        dest: f.dest || P2.proposeDest(f),
        steps: { ...f.steps,
          rename:  { state: "pass",   reason: "Renamed · reversible for 30 days" },
          lbdir:   { state: "pass",   reason: `Sidecar reconciled · ${f.verify.total}/${f.verify.total}` },
          collect: { state: "action", reason: "Reconciled — file into the collection for final storage" } } };
    }
    function applyRename(id) {
      setFolders(fs => fs.map(f => f.id === id ? reconciledShelf(f) : f));
      setSel(s => { const n = new Set(s); n.delete(id); return n; });
      flash("Rename applied & reconciled — ready to file into the collection");
    }
    function applyAllReady() {
      const ids = folders.filter(f => f.bucket === "ready").map(f => f.id);
      setFolders(fs => fs.map(f => f.bucket === "ready" ? reconciledShelf(f) : f));
      setSel(new Set());
      flash(`Applied ${ids.length} renames — ready to file into the collection`);
    }
    function resolveLookup(id, lb) {
      setFolders(fs => fs.map(f => {
        if (f.id !== id) return f;
        const proposed = `${f.name} (${lb})`;
        return { ...f, bucket: "ready", lb, proposed, confident: true, stuckAt: "rename",
          resolution: "single", resHint: `Pinned ${lb} · folder_lb_link updated`,
          steps: { ...f.steps,
            lookup: { state: "pass", reason: `Pinned to ${lb}` },
            rename: { state: "action", reason: "Confident rename proposed — review & apply" } } };
      }));
      setActiveStage("rename");
      flash(`Pinned ${lb} — rename ready to apply`);
    }

    // Verify · generate missing checksums, then hand off to auto-lookup
    function generateChecksums(id) {
      setFolders(fs => fs.map(f => {
        if (f.id !== id) return f;
        return { ...f, bucket: "running", stuckAt: "lookup",
          verify: { ...f.verify, noChecksums: false, pass: f.verify.total },
          steps: { ...f.steps,
            verify: { state: "pass",    reason: `Generated ${f.verify.total} checksums · ${f.verify.total}/${f.verify.total} match` },
            lookup: { state: "running", reason: "Identifying against the master DB…" } } };
      }));
      setActiveStage("lookup");
      flash("Checksums generated — looking up automatically");
    }

    // LBDIR · apply reconcile moves → lands on the shelf when clean
    function reconcileLbdir(id) {
      setFolders(fs => fs.map(f => {
        if (f.id !== id || !f.lbdir) return f;
        const L = { ...f.lbdir, recon: [], present: f.lbdir.sidecarTotal, missing: 0 };
        const clean = (L.extras || []).length === 0;
        if (clean) return reconciledShelf({ ...f, lbdir: L });
        return { ...f, lbdir: L, bucket: "needs", stuckAt: "lbdir",
          steps: { ...f.steps, lbdir: { state: "action", reason: `${L.extras.length} files not in the sidecar` } } };
      }));
      flash("Moves applied — files reconciled into place");
    }

    // LBDIR · move extras to /extras (NOT deleted)
    function moveExtras(id, n) {
      setFolders(fs => fs.map(f => {
        if (f.id !== id || !f.lbdir) return f;
        const L = { ...f.lbdir, extras: [] };
        const clean = (L.recon || []).length === 0;
        if (clean) return reconciledShelf({ ...f, lbdir: L });
        return { ...f, lbdir: L, bucket: "needs", stuckAt: "lbdir",
          steps: { ...f.steps, lbdir: { state: "action", reason: `${L.recon.length} files moved/misnamed on disk` } } };
      }));
      flash(`Moved ${n} file${n === 1 ? "" : "s"} to /extras — logged & reversible`);
    }

    // LBDIR · move extras to /extras (NOT deleted) — gated by confirm
    async function confirmMoveExtras(id, files) {
      const n = files.length;
      const ok = await confirm({
        tone: "warn",
        icon: "folder",
        title: `Move ${n} file${n === 1 ? "" : "s"} to /extras?`,
        body: <>These files aren’t referenced by the archive sidecar. They’ll be relocated into an <span style={{ fontFamily: "var(--lbb-mono)" }}>/extras</span> subfolder — still on disk, just out of the way.</>,
        items: files.map(f => ({ icon: f.sys ? "x" : "folder", label: f.p, meta: f.sz })),
        note: "Nothing is deleted. The move is logged to rename_history, so you can pull these files back out at any time.",
        confirmLabel: `Move ${n} to /extras`,
        confirmIcon: "folder",
      });
      if (ok) moveExtras(id, n);
    }

    // Reverse an applied rename — rewrites the folder back on disk, gated by confirm
    function reverseRename(id) {
      setFolders(fs => fs.map(f => {
        if (f.id !== id) return f;
        return { ...f, bucket: "ready", stuckAt: "rename",
          steps: { ...f.steps,
            rename: { state: "action", reason: "Rename reversed — review & re-apply" },
            lbdir:  { state: "pending", reason: "Re-apply the rename to reconcile the sidecar" } } };
      }));
      setActiveStage("rename");
      flash("Rename reversed — folder restored and moved back to Ready");
    }
    async function confirmReverseRename(id) {
      const f = folders.find(x => x.id === id);
      if (!f) return;
      const ok = await confirm({
        tone: "warn",
        icon: "refresh",
        title: `Reverse the rename on ${f.name}?`,
        body: <>This restores the original folder name and strips the <span style={{ fontFamily: "var(--lbb-mono)" }}>{f.lb}</span> tag that was written on apply. The folder moves back to <strong>Ready</strong> so you can re-apply later.</>,
        note: "The original name is restored from rename_history — no files are lost. You can re-apply the proposed rename at any time.",
        confirmLabel: "Reverse rename",
        confirmIcon: "refresh",
      });
      if (ok) reverseRename(id);
    }

    // ── THE BRIDGE: file a reconciled folder into the collection ──
    // Moves it to its final-storage mount and tags it owned/public → Done.
    function fileToCollection(id, opts) {
      const { mount, path } = opts || {};
      setFolders(fs => fs.map(f => {
        if (f.id !== id) return f;
        const dest = f.dest || P2.proposeDest(f);
        const finalPath = path || (P2.destPath(mount || dest.mount, dest) + dest.finalName);
        return { ...f, bucket: "done", stuckAt: null,
          path: finalPath,
          collected: { at: "today · just now", mount: mount || dest.mount, path: finalPath, status: "Public", confirmed: "today", fp: false },
          steps: { ...f.steps,
            collect: { state: "pass", reason: `Filed to /mnt/${mount || dest.mount}/${dest.year}/ · added to the collection` } } };
      }));
      setSel(s => { const n = new Set(s); n.delete(id); return n; });
      flash("Filed into the collection — tagged owned · public");
    }
    async function confirmFileToCollection(id, opts) {
      const f = folders.find(x => x.id === id);
      if (!f) return;
      const dest = f.dest || P2.proposeDest(f);
      const mount = (opts && opts.mount) || dest.mount;
      const ok = await confirm({
        tone: "info",
        icon: "collection",
        title: `File ${f.name} into the collection?`,
        body: <>Moves this folder to <span style={{ fontFamily: "var(--lbb-mono)" }}>{P2.destPath(mount, dest)}</span> for final storage and tags it <strong>owned · public</strong> so it appears in My Collection.</>,
        items: [{ icon: "collection", label: P2.destPath(mount, dest) + dest.finalName, meta: mount }],
        note: "Logged to rename_history as a collection move — reversible for 30 days. The collection row links back to the folder on disk.",
        confirmLabel: "File into collection",
        confirmIcon: "collection",
      });
      if (ok) fileToCollection(id, { ...opts, mount });
    }
    // File every shelf folder at once (each to its own routed mount)
    async function confirmFileAll() {
      const shelf = folders.filter(f => f.bucket === "shelf");
      if (shelf.length === 0) return;
      const ok = await confirm({
        tone: "info",
        icon: "collection",
        title: `File all ${shelf.length} ready folder${shelf.length === 1 ? "" : "s"} into the collection?`,
        body: <>Each folder is moved to its routed final-storage mount and tagged <strong>owned · public</strong>. Mounts are chosen automatically by show year.</>,
        items: shelf.slice(0, 6).map(f => { const d = f.dest || P2.proposeDest(f); return { icon: "collection", label: f.name, meta: d.mount }; }),
        note: shelf.length > 6 ? `…and ${shelf.length - 6} more. All logged to rename_history — reversible for 30 days.` : "All logged to rename_history — reversible for 30 days.",
        confirmLabel: `File ${shelf.length} into collection`,
        confirmIcon: "collection",
      });
      if (ok) {
        setFolders(fs => fs.map(f => {
          if (f.bucket !== "shelf") return f;
          const dest = f.dest || P2.proposeDest(f);
          const finalPath = P2.destPath(dest.mount, dest) + dest.finalName;
          return { ...f, bucket: "done", stuckAt: null, path: finalPath,
            collected: { at: "today · just now", mount: dest.mount, path: finalPath, status: "Public", confirmed: "today", fp: false },
            steps: { ...f.steps, collect: { state: "pass", reason: `Filed to /mnt/${dest.mount}/${dest.year}/ · added to the collection` } } };
        }));
        setSel(new Set());
        flash(`Filed ${shelf.length} folder${shelf.length === 1 ? "" : "s"} into the collection`);
      }
    }

    // ── OVERRIDE: mark a stage complete, bypassing the locks ──
    // Forces this stage and every earlier pipeline stage to pass, then drops the
    // folder on the shelf so it can be filed into the collection from here.
    const PIPE = ["verify", "lookup", "rename", "lbdir"];
    function markComplete(id, fromStage) {
      setFolders(fs => fs.map(f => {
        if (f.id !== id) return f;
        const upto = PIPE.indexOf(fromStage) === -1 ? PIPE.length - 1 : PIPE.indexOf(fromStage);
        const steps = { ...f.steps };
        PIPE.forEach((k, i) => {
          if (i <= upto && steps[k].state !== "pass") {
            steps[k] = { state: "pass", reason: "Marked complete (override)" };
          }
        });
        steps.collect = { state: "action", reason: "Marked complete — file into the collection for final storage" };
        return { ...f, overridden: true, bucket: "shelf", stuckAt: "collect", dest: f.dest || P2.proposeDest(f), steps };
      }));
      setActiveStage("collect");
      flash("Marked complete — locks bypassed, ready to file");
    }
    async function confirmMarkComplete(id, fromStage) {
      const f = folders.find(x => x.id === id);
      if (!f) return;
      const label = (STAGES.find(s => s.key === fromStage) || {}).label || fromStage;
      const ok = await confirm({
        tone: "warn",
        icon: "shield",
        title: `Mark ${f.name} complete from ${label}?`,
        body: <>This <strong>bypasses the remaining pipeline checks</strong>. Every stage up to and including <strong>{label}</strong> is forced to pass and the folder jumps straight to <strong>Ready to file</strong>.</>,
        note: "Use this when you've verified the folder by hand. The override is logged, the steps are tagged “marked complete”, and you can still reverse it before filing.",
        confirmLabel: "Mark complete & unlock filing",
        confirmIcon: "check",
      });
      if (ok) markComplete(id, fromStage);
    }

    // Clear the whole folder queue — irreversible, gated by confirm
    async function confirmClearQueue() {
      const n = folders.length;
      if (n === 0) return;
      const unfinished = folders.filter(f => f.bucket !== "done").length;
      const ok = await confirm({
        tone: "danger",
        icon: "trash",
        title: `Clear all ${n} folders from the queue?`,
        body: <>This empties the workspace and drops every folder’s in-progress pipeline state.{unfinished > 0 && <> <strong>{unfinished}</strong> {unfinished === 1 ? "folder hasn’t" : "folders haven’t"} finished yet.</>}</>,
        note: "This only clears the queue — your folders and files on disk are untouched. But progress here (matches, picks, reconcile state) is lost and can’t be undone.",
        confirmLabel: "Clear queue",
        confirmIcon: "trash",
      });
      if (ok) {
        setFolders([]);
        setSel(new Set());
        setOpenId(null);
        flash(`Cleared ${n} folder${n === 1 ? "" : "s"} from the queue`);
      }
    }

    function openFolder(id) {
      const f = folders.find(x => x.id === id);
      setOpenId(id);
      setActiveStage(f.stuckAt || "verify");
    }

    // ── DETAIL ───────────────────────────────────────────────────────
    function Detail({ f }) {
      const StagePanel = { verify: VerifyStage, lookup: LookupStage, rename: RenameStage, lbdir: LBDIRStage, collect: CollectStage }[activeStage];
      const applied = f.bucket === "done";
      // "Mark complete" override — available on any pipeline stage that hasn't
      // already been filed/shelved, so you can bypass the locks from anywhere.
      const canOverride = f.bucket !== "done" && f.bucket !== "shelf" && f.bucket !== "running" && activeStage !== "collect";
      // context footer action
      let footer = null;
      if (f.bucket === "shelf") {
        footer = <Button variant="primary" size="md" icon="collection" onClick={() => confirmFileToCollection(f.id, { mount: (f.dest || P2.proposeDest(f)).mount })}>File into collection</Button>;
      } else if (f.bucket === "ready") {
        footer = <Button variant="primary" size="md" icon="check" onClick={() => applyRename(f.id)}>Apply rename → {f.lb}</Button>;
      } else if (f.bucket === "needs" && f.stuckAt === "verify" && f.steps.verify.state === "action") {
        footer = <span style={{ fontSize: 12, color: "var(--lbb-fg2)" }}>Resolve the verify step above to continue.</span>;
      } else if (f.bucket === "needs" && f.stuckAt === "verify") {
        footer = <Button variant="secondary" size="md" icon="refresh">Re-verify after fixing files</Button>;
      } else if (f.bucket === "needs" && f.candidates) {
        footer = <span style={{ fontSize: 12, color: "var(--lbb-fg2)" }}>Pick an LB# above to unblock the rename.</span>;
      } else if (f.bucket === "needs" && f.stuckAt === "lookup") {
        footer = <Button variant="secondary" size="md" icon="plus">Mark as new entry…</Button>;
      } else if (f.bucket === "needs" && f.stuckAt === "lbdir") {
        footer = <span style={{ fontSize: 12, color: "var(--lbb-fg2)" }}>Apply the moves and clear extras above to finish.</span>;
      } else if (f.bucket === "done") {
        footer = <div style={{ display: "flex", gap: 8 }}>
          <Button variant="ghost" size="md" icon="refresh" onClick={() => confirmReverseRename(f.id)}>Reverse rename</Button>
          <Button variant="secondary" size="md" icon="collection">Open in My Collection</Button>
        </div>;
      }

      return (
        <div style={{ display: "flex", flexDirection: "column", minHeight: 0, height: "100%" }}>
          {/* Detail header */}
          <div style={{ padding: "14px 24px 0", borderBottom: "1px solid var(--lbb-border)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <button onClick={() => setOpenId(null)} style={{ display: "inline-flex", alignItems: "center", gap: 5, background: "none", border: "1px solid var(--lbb-border2)", borderRadius: 6, padding: "4px 10px", color: "var(--lbb-fg2)", fontFamily: "inherit", fontSize: 12, cursor: "pointer" }}>
                <Icon name="chevLeft" size={13} /> Batch
              </button>
              <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 14, fontWeight: 600, color: "var(--lbb-fg)" }}>{f.name}</span>
              <Pill tone="mute" soft>{f.fmt}</Pill>
              {f.lb && <Pill tone="info" soft style={{ fontFamily: "var(--lbb-mono)" }}>{f.lb}</Pill>}
              <div style={{ flex: 1 }} />
              <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 11, color: "var(--lbb-fg3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 360 }}>{f.path}</span>
              <IconButton icon="reveal" title="Reveal in Finder" />
            </div>
            <div style={{ paddingBottom: 12 }}>
              <StageStepper folder={f} stages={STAGES} activeKey={activeStage} onPick={setActiveStage} />
            </div>
          </div>
          {/* Active stage panel */}
          <div style={{ flex: 1, overflow: "auto", minHeight: 0, padding: "20px 24px" }}>
            <StagePanel folder={f} applied={applied}
              onApply={() => applyRename(f.id)}
              onResolve={(lb) => resolveLookup(f.id, lb)}
              onGenerate={() => generateChecksums(f.id)}
              onInstallTool={() => flash("Installing shntool… (demo)")}
              onRetrieve={() => flash("Retrieving sidecar from cache… (demo)")}
              onReconcile={() => reconcileLbdir(f.id)}
              onFile={(opts) => confirmFileToCollection(f.id, opts)}
              onMoveExtras={(files) => confirmMoveExtras(f.id, files)} />
          </div>
          {/* Sticky footer */}
          <div style={{ padding: "12px 24px", borderTop: "1px solid var(--lbb-border)", background: "var(--lbb-surface)", display: "flex", alignItems: "center", gap: 12 }}>
            <StatusTag state={folderStatus(f).state}>{folderStatus(f).label}</StatusTag>
            <span style={{ fontSize: 12, color: "var(--lbb-fg2)" }}>{folderStatus(f).reason}</span>
            <div style={{ flex: 1 }} />
            {canOverride && (
              <button onClick={() => confirmMarkComplete(f.id, activeStage)} title="Bypass the locks: force this stage (and earlier ones) complete and jump to filing" style={{
                display: "inline-flex", alignItems: "center", gap: 6, padding: "7px 12px", borderRadius: 8, cursor: "pointer", fontFamily: "inherit", fontSize: 12.5, fontWeight: 600,
                background: "var(--lbb-surface)", border: "1px dashed var(--lbb-warn-bar)", color: "var(--lbb-warn-fg)",
              }}>
                <Icon name="shield" size={14} /> Mark complete
              </button>
            )}
            {footer}
          </div>
        </div>
      );
    }

    // ── OVERVIEW ROW ──────────────────────────────────────────────────
    function Row({ f }) {
      const status = folderStatus(f);
      const checked = sel.has(f.id);
      const selectable = f.bucket === "ready";
      return (
        <TR edge={STATE[status.state].tone} selected={checked} onClick={() => openFolder(f.id)}>
          <TD onClick={(e) => e.stopPropagation()} style={{ cursor: selectable ? "pointer" : "default" }}>
            {selectable && <input type="checkbox" checked={checked} onChange={() => setSel(s => { const n = new Set(s); n.has(f.id) ? n.delete(f.id) : n.add(f.id); return n; })} />}
          </TD>
          <TD mono style={{ color: "var(--lbb-fg)" }}>{f.name}</TD>
          <TD><div style={{ width: "100%", maxWidth: 212 }}><StageTracker folder={f} stages={STAGES} currentKey={f.stuckAt} /></div></TD>
          <TD style={{ whiteSpace: "normal" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              <StatusTag state={status.state}>{status.label}</StatusTag>
              <span style={{ fontSize: 10.5, color: "var(--lbb-fg3)", lineHeight: 1.35 }}>{status.reason}</span>
            </div>
          </TD>
          <TD mono style={{ color: f.lb ? "var(--lbb-accent-mid)" : "var(--lbb-fg3)", fontWeight: f.lb ? 600 : 400 }}>{f.lb || "—"}</TD>
          <TD align="right" onClick={(e) => e.stopPropagation()}>
            {f.bucket === "ready"   && <Button size="sm" variant="primary" icon="check" onClick={() => applyRename(f.id)}>Apply</Button>}
            {f.bucket === "shelf"   && <Button size="sm" variant="primary" icon="collection" onClick={() => confirmFileToCollection(f.id, { mount: (f.dest || P2.proposeDest(f)).mount })}>File</Button>}
            {f.bucket === "needs"   && <Button size="sm" variant="secondary" icon="chevRight" iconRight="chevRight" onClick={() => openFolder(f.id)}>Resolve</Button>}
            {f.bucket === "running" && <Pill tone="info" soft dot>Running</Pill>}
            {f.bucket === "done"    && <Pill tone="ok" soft>In collection</Pill>}
          </TD>
        </TR>
      );
    }

    // ── EMPTY QUEUE — the drag-to-start moment ────────────────────────
    function EmptyState() {
      return (
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 40, minHeight: 0 }}>
          <div style={{ width: "100%", maxWidth: 560, textAlign: "center" }}>
            <div style={{
              border: `2px dashed ${dragging ? "var(--lbb-accent-mid)" : "var(--lbb-border2)"}`,
              borderRadius: 16, padding: "48px 40px",
              background: dragging ? "var(--lbb-accent-soft)" : "var(--lbb-surface)",
              transition: "background 120ms, border-color 120ms",
            }}>
              <div style={{
                width: 64, height: 64, borderRadius: 16, margin: "0 auto 20px",
                background: "var(--lbb-accent-soft)", color: "var(--lbb-accent-mid)",
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                border: "1px solid var(--lbb-accent-mid)",
              }}><Icon name="drop" size={30} /></div>
              <h2 style={{ margin: "0 0 8px", fontSize: 22, fontWeight: 700, letterSpacing: -0.02 }}>Drop folders to start</h2>
              <p style={{ margin: "0 auto 22px", fontSize: 13.5, color: "var(--lbb-fg2)", lineHeight: 1.55, maxWidth: 420 }}>
                Drag one or more show folders anywhere onto this window. Each one
                {autorun ? <> <strong style={{ color: "var(--lbb-accent-mid)" }}>verifies → identifies → proposes a rename</strong> on its own</> : <> waits for you to run each step</> } — you resolve only what needs a decision.
              </p>
              <div style={{ display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap" }}>
                <Button variant="primary" size="md" icon="folderPlus" onClick={() => queueIncoming(2)}>Add folders…</Button>
                <Button variant="secondary" size="md" icon="search">Scan a tree…</Button>
                <Button variant="ghost" size="md" icon="lookup" onClick={() => setOpenId("quick")}>Quick lookup</Button>
              </div>
              <div style={{ marginTop: 22, paddingTop: 18, borderTop: "1px solid var(--lbb-border)", fontSize: 11.5, color: "var(--lbb-fg3)" }}>
                Just exploring? <button onClick={seedSample} style={{ background: "none", border: "none", padding: 0, color: "var(--lbb-accent-mid)", font: "inherit", fontWeight: 600, cursor: "pointer", textDecoration: "underline", textUnderlineOffset: 2 }}>Restore the sample batch</button> to see every pipeline state.
              </div>
            </div>
          </div>
        </div>
      );
    }

    const visibleBuckets = BUCKET_ORDER.filter(b => (filter === "all" || filter === b) && shown.some(f => f.bucket === b));

    // ── render ─────────────────────────────────────────────────────────
    return (
      <div onDragEnter={onDragEnter} onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
        style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0, position: "relative" }}>
        {/* Banner */}
        <div style={{
          padding: "12px 24px", borderBottom: "1px solid var(--lbb-border)",
          background: "linear-gradient(180deg, var(--lbb-accent-soft) 0%, transparent 140%)",
          display: "flex", alignItems: "center", gap: 16,
        }}>
          <div style={{ width: 36, height: 36, borderRadius: 9, background: "var(--lbb-accent-mid)", color: "var(--lbb-accent-onMid)", display: "inline-flex", alignItems: "center", justifyContent: "center", boxShadow: "0 1px 0 rgba(255,255,255,0.18) inset" }}><Icon name="pipeline" size={18} /></div>
          <div style={{ minWidth: 230 }}>
            <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: -0.01 }}>Pipeline · {folders.length} folders</div>
            <div style={{ fontSize: 12, color: "var(--lbb-fg2)", marginTop: 2 }}>Drop a folder and it verifies → identifies → proposes a rename on its own.</div>
          </div>
          <div style={{ display: "flex", gap: 7, marginLeft: 8 }}>
            {BUCKET_ORDER.map(b => counts[b] > 0 && (
              <button key={b} onClick={() => setFilter(filter === b ? "all" : b)} style={{
                display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 10px", borderRadius: 999, cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap",
                background: filter === b ? `var(--lbb-${BUCKET[b].tone}-bg)` : "var(--lbb-surface)",
                border: `1px solid ${filter === b ? `var(--lbb-${BUCKET[b].tone}-bar)` : "var(--lbb-border2)"}`,
                color: `var(--lbb-${BUCKET[b].tone}-fg)`, fontSize: 11.5, fontWeight: 600,
              }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: `var(--lbb-${BUCKET[b].tone}-bar)` }} />
                {counts[b]} {BUCKET[b].label.toLowerCase()}
              </button>
            ))}
          </div>
          <div style={{ flex: 1 }} />
          {/* auto-run toggle */}
          <button onClick={() => setAutorun(a => !a)} title="When on, dropped folders verify + look up automatically" style={{
            display: "inline-flex", alignItems: "center", gap: 8, padding: "5px 10px", borderRadius: 8, cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap",
            background: autorun ? "var(--lbb-accent-soft)" : "var(--lbb-surface)",
            border: `1px solid ${autorun ? "var(--lbb-accent-mid)" : "var(--lbb-border2)"}`,
            color: autorun ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)", fontSize: 12, fontWeight: 600,
          }}>
            <span style={{ width: 26, height: 15, borderRadius: 999, background: autorun ? "var(--lbb-accent-mid)" : "var(--lbb-border2)", position: "relative", transition: "background 120ms" }}>
              <span style={{ position: "absolute", top: 2, left: autorun ? 13 : 2, width: 11, height: 11, borderRadius: "50%", background: "#fff", transition: "left 120ms" }} />
            </span>
            Auto-run on drop
          </button>
          <Button variant="primary" size="md" icon="check" disabled={readyIds.length === 0} onClick={applyAllReady}>
            Apply all {readyIds.length} ready
          </Button>
          {counts.shelf > 0 && (
            <Button variant="primary" size="md" icon="collection" onClick={confirmFileAll}>
              File all {counts.shelf} into collection
            </Button>
          )}
        </div>

        {/* Body */}
        <div style={{ flex: 1, display: "grid", gridTemplateColumns: railOpen ? "272px 1fr" : "46px 1fr", minHeight: 0 }}>
          {/* Collapsed rail strip */}
          {!railOpen && (
            <button onClick={() => setRailOpen(true)} title="Show folder queue" style={{ background: "var(--lbb-surface)", borderRight: "1px solid var(--lbb-border)", borderTop: 0, borderBottom: 0, borderLeft: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 12, paddingTop: 14, cursor: "pointer", fontFamily: "inherit" }}>
              <span style={{ width: 26, height: 26, borderRadius: 6, border: "1px solid var(--lbb-border2)", display: "inline-flex", alignItems: "center", justifyContent: "center", color: "var(--lbb-fg2)" }}><Icon name="chevRight" size={14} /></span>
              <span style={{ writingMode: "vertical-rl", transform: "rotate(180deg)", fontSize: 10.5, fontWeight: 700, letterSpacing: 0.12, textTransform: "uppercase", color: "var(--lbb-fg3)" }}>Folder queue · {folders.length}</span>
            </button>
          )}
          {/* Queue rail */}
          {railOpen && (
          <aside style={{ background: "var(--lbb-surface)", borderRight: "1px solid var(--lbb-border)", display: "flex", flexDirection: "column", minHeight: 0 }}>
            <div style={{ padding: "14px 14px 10px", borderBottom: "1px solid var(--lbb-border)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Icon name="folder" size={13} style={{ color: "var(--lbb-fg3)" }} />
                <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.1, textTransform: "uppercase" }}>Folder queue</span>
                <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 600, color: "var(--lbb-fg2)", fontVariantNumeric: "tabular-nums" }}>{folders.length}</span>
                <button onClick={() => setRailOpen(false)} title="Collapse queue" style={{ width: 22, height: 22, marginLeft: 2, borderRadius: 5, border: "1px solid var(--lbb-border2)", background: "var(--lbb-surface)", color: "var(--lbb-fg3)", cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center" }}><Icon name="chevLeft" size={13} /></button>
              </div>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "8px 8px" }}>
              {shown.map(f => <QueueRow key={f.id} folder={f} active={openId === f.id} onClick={() => openFolder(f.id)} />)}
              {shown.length === 0 && (
                folders.length === 0
                  ? <div style={{ padding: "20px 12px", textAlign: "center", fontSize: 11, color: "var(--lbb-fg3)", lineHeight: 1.5 }}>Queue is empty.<br />Drop folders to begin.</div>
                  : <div style={{ padding: "20px 12px", textAlign: "center", fontSize: 11, color: "var(--lbb-fg3)" }}>No folders match “{query}”.</div>
              )}
            </div>
            <div style={{ padding: 12, borderTop: "1px solid var(--lbb-border)", display: "flex", flexDirection: "column", gap: 6 }}>
              <Button variant="primary" size="sm" icon="folderPlus" block onClick={() => queueIncoming()}>Add folders…</Button>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                <Button variant="secondary" size="sm" icon="search">Scan tree…</Button>
                <Button variant="ghost" size="sm" icon="trash" onClick={confirmClearQueue}>Clear</Button>
              </div>
              <button onClick={() => { setOpenId("quick"); }} style={{
                display: "flex", alignItems: "center", gap: 8, width: "100%", padding: "8px 10px", borderRadius: 7, cursor: "pointer", fontFamily: "inherit", textAlign: "left",
                background: openId === "quick" ? "var(--lbb-accent-soft)" : "var(--lbb-surface2)",
                border: `1px solid ${openId === "quick" ? "var(--lbb-accent-mid)" : "var(--lbb-border2)"}`,
                color: openId === "quick" ? "var(--lbb-accent-mid)" : "var(--lbb-fg2)", fontSize: 12, fontWeight: 600,
              }}>
                <Icon name="lookup" size={14} />
                <span style={{ flex: 1 }}>Quick lookup</span>
                <span style={{ fontSize: 10, color: "var(--lbb-fg3)", fontWeight: 500 }}>no folder</span>
              </button>
              <div style={{ marginTop: 4, padding: "9px 11px", background: "var(--lbb-surface2)", borderRadius: 7, border: "1px dashed var(--lbb-border2)", fontSize: 10.5, color: "var(--lbb-fg3)", lineHeight: 1.45, display: "flex", gap: 8, alignItems: "flex-start" }}>
                <Icon name="drop" size={13} style={{ marginTop: 1, flex: "0 0 auto" }} />
                <span>Drag folders anywhere to queue them. {autorun ? <>They’ll <strong style={{ color: "var(--lbb-accent-mid)" }}>verify + look up automatically</strong>.</> : "Auto-run is off — run steps manually."}</span>
              </div>
            </div>
          </aside>
          )}

          {/* Main */}
          <section style={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, position: "relative" }}>
            {open ? <Detail f={open} /> : openId === "quick" ? (
              <window.LBB_P2_QuickLookup onBack={() => setOpenId(null)} />
            ) : folders.length === 0 ? (
              <EmptyState />
            ) : (
              <>
                {/* selection bar */}
                {sel.size > 0 ? (
                  <div style={{ padding: "10px 24px", display: "flex", alignItems: "center", gap: 12, borderBottom: "1px solid var(--lbb-border)", background: "var(--lbb-accent-soft)", fontSize: 12 }}>
                    <span style={{ fontWeight: 600, color: "var(--lbb-accent-mid)" }}>{sel.size} selected</span>
                    <span style={{ color: "var(--lbb-fg2)" }}>· of {counts.ready} ready to apply</span>
                    <div style={{ flex: 1 }} />
                    <Button size="sm" variant="ghost" onClick={() => setSel(new Set())}>Clear</Button>
                    <Button size="sm" variant="primary" icon="check" onClick={() => { sel.forEach(id => applyRename(id)); }}>Apply {sel.size} renames</Button>
                  </div>
                ) : (
                  <div style={{ padding: "12px 24px", display: "flex", alignItems: "center", gap: 10, borderBottom: "1px solid var(--lbb-border)" }}>
                    <Input icon="filter" placeholder="Filter folders…" size="sm" value={query} onChange={e => setQuery(e.target.value)} style={{ width: 260 }} />
                    {filter !== "all" && (
                      <button onClick={() => setFilter("all")} title="Clear status filter" style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 8px 3px 10px", borderRadius: 999, cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap", background: `var(--lbb-${BUCKET[filter].tone}-bg)`, border: `1px solid var(--lbb-${BUCKET[filter].tone}-bar)`, color: `var(--lbb-${BUCKET[filter].tone}-fg)`, fontSize: 11.5, fontWeight: 600 }}>
                        {BUCKET[filter].label} <Icon name="x" size={11} />
                      </button>
                    )}
                    {(query || filter !== "all") && <span style={{ fontSize: 11.5, color: "var(--lbb-fg3)" }}>{visibleCount} shown</span>}
                    <div style={{ flex: 1 }} />
                    {counts.ready > 0 && <Button size="sm" variant="secondary" onClick={() => setSel(new Set(readyIds))}>Select all ready</Button>}
                  </div>
                )}

                {/* table */}
                <div style={{ flex: 1, overflow: "auto", minHeight: 0 }}>
                  <TableShell>
                    <colgroup>
                      <col style={{ width: 3 }} /><col style={{ width: 36 }} /><col style={{ width: 380 }} /><col style={{ width: 232 }} /><col /><col style={{ width: 104 }} /><col style={{ width: 128 }} />
                    </colgroup>
                    <thead><tr>
                      <th style={{ width: 3, padding: 0, background: "var(--lbb-surface2)", borderBottom: "1px solid var(--lbb-border2)" }} /><TH><span /></TH><TH>Folder</TH><TH>Stages</TH><TH>Status</TH><TH>LB#</TH><TH align="right"> </TH>
                    </tr></thead>
                    <tbody>
                      {visibleBuckets.map(b => {
                        const rows = shown.filter(f => f.bucket === b);
                        return (
                        <React.Fragment key={b}>
                          <GroupRow label={BUCKET[b].label} count={rows.length} colSpan={6} />
                          {rows.map(f => <Row key={f.id} f={f} />)}
                        </React.Fragment>
                        );
                      })}
                    </tbody>
                  </TableShell>
                  {visibleBuckets.length === 0 && (
                    <div style={{ padding: "60px 24px", textAlign: "center", color: "var(--lbb-fg3)" }}>No folders in this view.</div>
                  )}
                  {/* legend */}
                  <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "14px 24px", flexWrap: "wrap", borderTop: "1px solid var(--lbb-border)", marginTop: 4 }}>
                    <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--lbb-fg3)", letterSpacing: 0.08, textTransform: "uppercase" }}>Status key</span>
                    {Object.entries(STATE).map(([k, s]) => (
                      <span key={k} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--lbb-fg2)" }}>
                        <span style={{ width: 9, height: 9, borderRadius: "50%", background: `var(--lbb-${s.tone}-bar)`, border: k === "pending" ? "1.5px solid var(--lbb-fg3)" : "none", boxSizing: "border-box" }} />
                        {s.label}
                      </span>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* toast */}
            {toast && (
              <div style={{ position: "absolute", bottom: 18, left: "50%", transform: "translateX(-50%)", background: "var(--lbb-fg)", color: "var(--lbb-bg)", padding: "9px 16px", borderRadius: 8, fontSize: 12.5, fontWeight: 600, boxShadow: "var(--lbb-shadowLg)", display: "flex", alignItems: "center", gap: 8, zIndex: 20 }}>
                <Icon name="check" size={14} /> {toast}
              </div>
            )}
          </section>
        </div>

        {/* Drag-to-queue overlay */}
        {dragging && (
          <div style={{
            position: "absolute", inset: 0, zIndex: 50, pointerEvents: "none",
            background: "color-mix(in oklab, var(--lbb-accent-soft) 90%, transparent)",
            display: "flex", alignItems: "center", justifyContent: "center",
            animation: "p2cfade 120ms ease",
          }}>
            <div style={{
              display: "flex", flexDirection: "column", alignItems: "center", gap: 14,
              padding: "40px 56px", borderRadius: 18,
              border: "2.5px dashed var(--lbb-accent-mid)", background: "var(--lbb-surface)",
              boxShadow: "var(--lbb-shadowLg)",
            }}>
              <div style={{ width: 60, height: 60, borderRadius: 15, background: "var(--lbb-accent-mid)", color: "var(--lbb-accent-onMid)", display: "inline-flex", alignItems: "center", justifyContent: "center" }}><Icon name="drop" size={28} /></div>
              <div style={{ fontSize: 19, fontWeight: 700, letterSpacing: -0.01, whiteSpace: "nowrap" }}>Drop to queue these folders</div>
              <div style={{ fontSize: 12.5, color: "var(--lbb-fg2)" }}>
                {autorun ? "They'll verify + look up automatically." : "Auto-run is off — you'll run each step."}
              </div>
            </div>
          </div>
        )}

        <ConfirmHost />
      </div>
    );
  }

  window.LBB_ScreenPipeline2 = App;
})();
