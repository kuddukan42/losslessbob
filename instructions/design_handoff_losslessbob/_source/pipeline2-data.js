// pipeline2-data.js
// Refined Pipeline Workspace — ONE consistent status vocabulary + a realistic
// sample batch. Every stage of every folder resolves to exactly one STATE,
// rendered identically in the overview tracker and the detail panels.

window.LBB_P2 = (() => {

  // ── The single status vocabulary ──────────────────────────────────
  // Used by all 4 stages (Verify / Lookup / Rename / LBDIR) and both the
  // overview tracker and the per-stage detail. One tone, one icon, one word.
  const STATE = {
    pending: { tone: "mute", icon: "dot",     label: "Pending" },
    running: { tone: "info", icon: "spinner", label: "Running" },
    pass:    { tone: "ok",   icon: "check",    label: "Pass"    },
    action:  { tone: "warn", icon: "alert",   label: "Action"  },
    blocked: { tone: "bad",  icon: "x",        label: "Blocked" },
  };

  // Folder-level buckets (derived, but stored for the prototype).
  const BUCKET = {
    needs:   { label: "Needs you",      tone: "bad",  blurb: "A decision or fix is required before these can finish." },
    ready:   { label: "Ready to apply", tone: "warn", blurb: "Verified and identified — just confirm the rename." },
    running: { label: "Running",        tone: "info", blurb: "Auto-pipeline in progress. They'll move on their own." },
    shelf:   { label: "Ready to file",  tone: "info", blurb: "Reconciled & archive-clean — file into the collection for final storage." },
    done:    { label: "In collection",  tone: "ok",   blurb: "Filed to final storage and tagged in the collection." },
  };

  const STAGES = [
    { key: "verify",  n: 1, label: "Verify",  icon: "verify",     blurb: "Checksums vs audio on disk" },
    { key: "lookup",  n: 2, label: "Lookup",  icon: "lookup",     blurb: "Identify the LB# in the master DB" },
    { key: "rename",  n: 3, label: "Rename",  icon: "rename",     blurb: "Append the canonical (LB-XXXXX)" },
    { key: "lbdir",   n: 4, label: "LBDIR",   icon: "lbdir",      blurb: "Reconcile the official archive sidecar" },
    { key: "collect", n: 5, label: "Collect", icon: "collection", blurb: "File into final storage & tag in the collection" },
  ];

  // ── The collection's storage mounts ───────────────────────────────
  // Final storage is organized mount → year. The Collect stage routes a
  // finished folder to the right mount by its show year, with free space
  // shown so the user can override.
  const MOUNTS = [
    { id: "DYLAN1", free: "1.2 TB",  span: "Pre-1980 · misc" },
    { id: "DYLAN2", free: "840 GB",  span: "1970s – 1980s" },
    { id: "DYLAN3", free: "2.1 TB",  span: "1990s – 2000s" },
    { id: "DYLAN4", free: "6.4 TB",  span: "2010s – 2020s · current" },
  ];
  function mountForYear(y) {
    if (!y)        return "DYLAN4";
    if (y >= 2010) return "DYLAN4";
    if (y >= 1990) return "DYLAN3";
    if (y >= 1970) return "DYLAN2";
    return "DYLAN1";
  }
  // Propose where a finished folder should live, by parsing the show year
  // from its name. finalName is the on-disk name after rename (LB# appended).
  function proposeDest(f) {
    const m = (f.name.match(/(?:19|20)\d{2}/) || [])[0];
    const year = m ? parseInt(m, 10) : null;
    const mount = mountForYear(year);
    return {
      mount, year: year || "unsorted",
      path: `/mnt/${mount}/${year || "unsorted"}/`,
      finalName: f.proposed || f.name,
      routed: !!year,
    };
  }
  function destPath(mount, dest) {
    return `/mnt/${mount}/${dest.year}/`;
  }

  // ── helpers to fabricate believable detail rows ────────────────────
  const hx = (n) => Array.from({ length: n }, () => "0123456789abcdef"[Math.floor(Math.random() * 16)]).join("");
  function tracks(prefix, count, opts = {}) {
    const out = [];
    for (let i = 1; i <= count; i++) {
      const nn = String(i).padStart(2, "0");
      const missing = opts.missingFrom && i >= opts.missingFrom;
      out.push({
        n: `${prefix}_${nn}.flac`,
        mdE: hx(10) + "…", mdA: missing ? "—" : null,
        ffE: hx(10) + "…", ffA: missing ? "—" : null,
        disk: !missing, ok: missing ? "blocked" : "pass",
      });
    }
    return out;
  }
  // Resolve actual = expected for passing rows
  function settle(rows) { return rows.map(r => ({ ...r, mdA: r.mdA ?? r.mdE, ffA: r.ffA ?? r.ffE })); }

  // ── The batch ──────────────────────────────────────────────────────
  // steps: each stage -> { state, reason }
  const FOLDERS = [
    // ░░ NEEDS YOU ░░
    {
      id: "f-alpha", bucket: "needs",
      name: "bd2025-07-25 Alpharetta GA",
      path: "/mnt/HOPPER/bd2025-07-25 Alpharetta GA FLAC",
      fmt: "FLAC", tracks: 32, lb: null, stuckAt: "verify",
      steps: {
        verify: { state: "blocked", reason: "16 of 32 files listed in the FFP are missing on disk" },
        lookup: { state: "pending", reason: "Waiting on a clean verify" },
        rename: { state: "pending", reason: "Needs an LB# first" },
        lbdir:  { state: "pending", reason: "—" },
      },
      verify: { total: 32, pass: 16, miss: 16, mism: 0, extra: 0,
                files: settle(tracks("d01t", 32, { missingFrom: 17 })) },
    },
    {
      // No checksum sidecar on disk — Verify can't compare, must GENERATE first.
      id: "f-nochk", bucket: "needs",
      name: "bd2026-05-09 Columbus OH",
      path: "/mnt/HOPPER/bd2026-05-09 Columbus OH",
      fmt: "FLAC", tracks: 23, lb: null, stuckAt: "verify",
      steps: {
        verify: { state: "action",  reason: "No .ffp / .md5 checksums in this folder — generate them to continue" },
        lookup: { state: "pending", reason: "Needs checksums to identify against the DB" },
        rename: { state: "pending", reason: "Needs an LB# first" },
        lbdir:  { state: "pending", reason: "—" },
      },
      verify: { total: 23, pass: 0, miss: 0, mism: 0, extra: 0, noChecksums: true,
                files: settle(tracks("d01t", 23)) },
    },
    {
      // SHN source — verifying SHN needs shntool, which isn't installed.
      id: "f-shn", bucket: "needs",
      name: "gd1977-05-08 Cornell (Betty)",
      path: "/mnt/HOPPER/gd1977-05-08 Cornell U Barton Hall SHN",
      fmt: "SHN", tracks: 17, lb: null, stuckAt: "verify",
      steps: {
        verify: { state: "action",  reason: "shntool isn't installed — needed to decode .shn for hashing" },
        lookup: { state: "pending", reason: "Waiting on a clean verify" },
        rename: { state: "pending", reason: "Needs an LB# first" },
        lbdir:  { state: "pending", reason: "—" },
      },
      verify: { total: 17, pass: 0, miss: 0, mism: 0, extra: 0, shntool: "missing",
                files: settle(tracks("d01t", 17)) },
    },
    {
      id: "f-pitt", bucket: "needs",
      name: "bd2026-04-19 Pittsburgh PA",
      path: "/mnt/HOPPER/bd2026-04-19 Pittsburgh PA",
      fmt: "FLAC", tracks: 19, lb: "LB-16596?", stuckAt: "lookup",
      steps: {
        verify: { state: "pass",    reason: "19/19 match local checksums" },
        lookup: { state: "action",  reason: "3 candidate LB#s — pick the right show" },
        rename: { state: "pending", reason: "Blocked until the LB# is resolved" },
        lbdir:  { state: "pending", reason: "—" },
      },
      verify: { total: 19, pass: 19, miss: 0, mism: 0, extra: 0, files: settle(tracks("d01t", 19)) },
      candidates: [
        { lb: "LB-16596",  detail: "1981-04-19 · Pittsburgh PA · Civic Arena",          match: 17, of: 19, note: "Best match" },
        { lb: "LB-16596b", detail: "1981-04-19 · Pittsburgh PA · Civic Arena · alt src", match: 11, of: 19, note: "Partial source" },
        { lb: "LB-16604",  detail: "2004-04-19 · Pittsburgh PA · Mellon Arena",          match: 0,  of: 19, note: "Location-only — different year" },
      ],
    },
    {
      id: "f-charlotte", bucket: "needs",
      name: "bd2025-07-26 Charlotte NC",
      path: "/mnt/HOPPER/bd2025-07-26 Charlotte NC FLAC",
      fmt: "FLAC", tracks: 18, lb: null, stuckAt: "lookup",
      steps: {
        verify: { state: "pass",    reason: "18/18 match local checksums" },
        lookup: { state: "blocked", reason: "0 of 18 checksums found in the master DB" },
        rename: { state: "pending", reason: "No LB# to apply" },
        lbdir:  { state: "pending", reason: "—" },
      },
      verify: { total: 18, pass: 18, miss: 0, mism: 0, extra: 0, files: settle(tracks("d01t", 18)) },
      notfound: settle(tracks("d01t", 18)),
    },

    // ░░ READY TO APPLY ░░
    {
      id: "f-sf", bucket: "ready",
      name: "1980-11-22 San Francisco (Fixed LK LB-7451)",
      path: "/mnt/DYLAN1/Double LBs/1980-11-22 San Francisco (Fixed LK LB-7451) LB-8547",
      fmt: "FLAC", tracks: 28, lb: "LB-08547", confident: true, stuckAt: "rename",
      proposed: "1980-11-22 San Francisco (Fixed LK LB-7451) LB-8547 (LB-08547)",
      steps: {
        verify: { state: "pass",   reason: "28/28 match local checksums" },
        lookup: { state: "pass",   reason: "All 28 checksums map to LB-08547 (Concert)" },
        rename: { state: "action", reason: "Confident rename proposed — review & apply" },
        lbdir:  { state: "pending",reason: "Sidecar not retrieved yet (runs after rename)" },
      },
      verify: { total: 28, pass: 28, miss: 0, mism: 0, extra: 0, files: settle(tracks("d01t", 28)) },
      resolution: "single", resHint: "Single complete match in master DB · Concert",
      // 2 checksums in this source also appear under other LB#s (shared/duplicate sources)
      xref: [
        { md: "a17f08cc2e…", n: "d01t04.flac", lbs: ["LB-08547", "LB-08547b"], note: "Also in alt-source transfer" },
        { md: "5b9920ff14…", n: "d02t06.flac", lbs: ["LB-08547", "LB-11920"], note: "Same encore in a compilation" },
      ],
    },
    {
      // Folder already carries a WRONG LB# that must be stripped before the right one is appended.
      id: "f-wronglb", bucket: "ready",
      name: "1978-09-16 New Haven (LB-9001)",
      path: "/mnt/DYLAN1/1978-09-16 New Haven (LB-9001)",
      fmt: "FLAC", tracks: 24, lb: "LB-09014", confident: true, stuckAt: "rename",
      wrongLb: "LB-9001",
      proposed: "1978-09-16 New Haven (LB-09014)",
      steps: {
        verify: { state: "pass",   reason: "24/24 match local checksums" },
        lookup: { state: "pass",   reason: "All 24 checksums map to LB-09014 — not LB-9001" },
        rename: { state: "action", reason: "Existing LB-9001 is wrong — strip it and apply LB-09014" },
        lbdir:  { state: "pending",reason: "Sidecar not retrieved yet" },
      },
      verify: { total: 24, pass: 24, miss: 0, mism: 0, extra: 0, files: settle(tracks("d01t", 24)) },
      resolution: "single", resHint: "Folder mislabeled LB-9001 · correct entry is LB-09014",
    },
    {
      id: "f-madison", bucket: "ready",
      name: "bd2026-04-02 Madison WI",
      path: "/mnt/HOPPER/bd2026-04-02 Madison WI",
      fmt: "FLAC", tracks: 22, lb: "LB-16591", confident: true, stuckAt: "rename",
      proposed: "bd2026-04-02 Madison WI (LB-16591)",
      steps: {
        verify: { state: "pass",   reason: "22/22 match local checksums" },
        lookup: { state: "pass",   reason: "All 22 checksums map to LB-16591" },
        rename: { state: "action", reason: "Confident rename proposed — review & apply" },
        lbdir:  { state: "pending",reason: "Sidecar not retrieved yet" },
      },
      verify: { total: 22, pass: 22, miss: 0, mism: 0, extra: 0, files: settle(tracks("d01t", 22)) },
      resolution: "single", resHint: "Single complete match in master DB",
    },
    {
      id: "f-philly", bucket: "ready",
      name: "bd2026-04-22 Philadelphia PA",
      path: "/mnt/HOPPER/bd2026-04-22 Philadelphia PA",
      fmt: "FLAC", tracks: 16, lb: "LB-16597", confident: true, stuckAt: "rename",
      proposed: "bd2026-04-22 Philadelphia PA (LB-16597)",
      steps: {
        verify: { state: "pass",   reason: "16/16 match local checksums" },
        lookup: { state: "pass",   reason: "All 16 checksums map to LB-16597" },
        rename: { state: "action", reason: "Confident rename proposed — review & apply" },
        lbdir:  { state: "pending",reason: "Sidecar not retrieved yet" },
      },
      verify: { total: 16, pass: 16, miss: 0, mism: 0, extra: 0, files: settle(tracks("d01t", 16)) },
      resolution: "single", resHint: "Single complete match in master DB",
    },

    // ░░ RUNNING ░░
    {
      id: "f-toronto", bucket: "running",
      name: "bd2026-05-02 Toronto ON",
      path: "/mnt/HOPPER/bd2026-05-02 Toronto ON",
      fmt: "FLAC", tracks: 24, lb: null, stuckAt: "verify",
      progress: { done: 14, total: 24 },
      steps: {
        verify: { state: "running", reason: "Hashing 14 / 24 files…" },
        lookup: { state: "pending", reason: "Queued" },
        rename: { state: "pending", reason: "Queued" },
        lbdir:  { state: "pending", reason: "Queued" },
      },
      verify: { total: 24, pass: 14, miss: 0, mism: 0, extra: 0, files: settle(tracks("d01t", 24)) },
    },

    // ░░ NEEDS YOU · stuck at LBDIR (reconcile + extras) ░░
    {
      id: "f-cleveland", bucket: "needs",
      name: "bd2026-04-11 Cleveland OH (LB-16594)",
      path: "/mnt/ARCHIVE/bd2026-04-11 Cleveland OH (LB-16594)",
      fmt: "FLAC", tracks: 25, lb: "LB-16594", stuckAt: "lbdir",
      steps: {
        verify: { state: "pass",   reason: "25/25 match local checksums" },
        lookup: { state: "pass",   reason: "Matched LB-16594" },
        rename: { state: "pass",   reason: "Renamed · reversible for 30 days" },
        lbdir:  { state: "action", reason: "3 files moved/misnamed on disk + 4 files not in the sidecar" },
      },
      verify: { total: 25, pass: 22, miss: 3, mism: 0, extra: 4, files: settle(tracks("d01t", 25)) },
      lbdir: {
        retrieved: true, source: "cache",
        sidecarTotal: 25, present: 22, mismatch: 0, missing: 3,
        // Reconcile — disk files whose MD5 matches a "missing" sidecar entry, found at the wrong path
        recon: [
          { from: "extras/d01t03.flac",            to: "d01t03.flac", md: "7d22cc0817…" },
          { from: "_unsorted/track4.flac",         to: "d01t04.flac", md: "9f12cc88e0…" },
          { from: "renamed badly/d02 - t01.flac",  to: "d02t01.flac", md: "11ff44aa9b…" },
        ],
        // Extras — files present on disk but NOT referenced in lbdir → MOVE to /extras
        extras: [
          { p: "notes-personal.txt",   sz: "2.1 KB",  sel: true,  sys: false },
          { p: ".DS_Store",            sz: "8 KB",    sel: true,  sys: true  },
          { p: "Thumbs.db",            sz: "12 KB",   sel: true,  sys: true  },
          { p: "album-art-back.png",   sz: "1.2 MB",  sel: false, sys: false },
        ],
      },
    },

    // ░░ READY TO FILE ░░ (reconciled, archive-clean — awaiting the bridge)
    {
      id: "f-chicago", bucket: "shelf", stuckAt: "collect",
      name: "bd2026-04-08 Chicago IL (LB-16593)",
      path: "/mnt/HOPPER/incoming/bd2026-04-08 Chicago IL (LB-16593)",
      fmt: "FLAC", tracks: 26, lb: "LB-16593",
      steps: {
        verify:  { state: "pass",   reason: "26/26 match" },
        lookup:  { state: "pass",   reason: "Matched LB-16593" },
        rename:  { state: "pass",   reason: "Renamed · reversible for 30 days" },
        lbdir:   { state: "pass",   reason: "Sidecar reconciled · 26/26" },
        collect: { state: "action", reason: "Reconciled — file into /mnt/DYLAN4/2026/ and add to the collection" },
      },
      verify: { total: 26, pass: 26, miss: 0, mism: 0, extra: 0, files: settle(tracks("d01t", 26)) },
    },

    // ░░ IN COLLECTION ░░ (filed to final storage + tagged — the bridge already ran)
    {
      id: "f-lacrosse", bucket: "done", stuckAt: null,
      name: "bd2026-03-27 La Crosse WI (LB-16588)",
      path: "/mnt/DYLAN4/2026/bd2026-03-27 La Crosse WI (LB-16588)",
      fmt: "FLAC", tracks: 21, lb: "LB-16588",
      steps: {
        verify:  { state: "pass", reason: "21/21 match" },
        lookup:  { state: "pass", reason: "Matched LB-16588" },
        rename:  { state: "pass", reason: "Renamed · reversible for 30 days" },
        lbdir:   { state: "pass", reason: "Sidecar reconciled · 21/21" },
        collect: { state: "pass", reason: "Filed to /mnt/DYLAN4/2026/ · added to the collection" },
      },
      verify: { total: 21, pass: 21, miss: 0, mism: 0, extra: 0, files: settle(tracks("d01t", 21)) },
      dest: { mount: "DYLAN4", year: 2026, path: "/mnt/DYLAN4/2026/", finalName: "bd2026-03-27 La Crosse WI (LB-16588)", routed: true },
      collected: { at: "today · 14:02", mount: "DYLAN4", path: "/mnt/DYLAN4/2026/bd2026-03-27 La Crosse WI (LB-16588)", status: "Public", confirmed: "today", fp: false, size: "512 MB" },
    },
  ];

  // ── normalize ──────────────────────────────────────────────
  // Every folder carries the 5th 'collect' step + a proposed destination so the
  // tracker, stepper, and Collect stage can render uniformly.
  FOLDERS.forEach(f => {
    if (!f.steps.collect) {
      f.steps.collect = { state: "pending", reason: "Files into the collection after the sidecar reconciles" };
    }
    if (!f.dest) f.dest = proposeDest(f);
  });

  return { STATE, BUCKET, STAGES, MOUNTS, FOLDERS, proposeDest, destPath, mountForYear };
})();
