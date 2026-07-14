// perf-data.js
// Performance-centric dataset for the Library.
// The organizing unit is the PERFORMANCE (a show: date + venue), NOT the LB# catalog number.
// Each performance carries one or more circulating RECORDINGS (sources), and `owned`
// is a per-recording lens. Coverage = how many of a show's recordings you hold.

window.LBB_PERF = (() => {

  // ── Source vocabulary ───────────────────────────────────────────────
  // code is the compact badge; full is the long label used in facets/detail.
  const SOURCES = {
    Soundboard: { code: "SBD", full: "Soundboard" },
    Audience:   { code: "AUD", full: "Audience"   },
    "FM/Pre-FM":{ code: "FM",  full: "FM / Pre-FM" },
    Master:     { code: "MST", full: "Master / Studio" },
    Mixed:      { code: "MTX", full: "Matrix / Mixed" },
  };

  // ── Performances ────────────────────────────────────────────────────
  // date is ISO (sort key); disp is the human label; dow = weekday.
  // recordings[]: { lb, src, rating, owned, lineage, + file fields when owned }
  const PERFS = [
    // ── 1980 · Musical Retrospective Tour ────────────────────────────
    {
      id: "1980-02-05-knoxville", date: "1980-02-05", disp: "Feb 5, 1980", dow: "Tue", year: 1980,
      venue: "Civic Coliseum", city: "Knoxville, TN", tour: "Gospel Tour", leg: "Winter 1980 · Southeast",
      status: "Public", tracks: 17, length: "1h 24m", setlist: "knox80",
      fams: {
        sbd: { label: "Soundboard master", by: "lb" },
        aud: { label: "Audience master", by: "lb" },
      },
      recordings: [
        { lb: "LB-70", src: "Soundboard", rating: "A−", owned: true, fam: "sbd", lineage: "Holy Grail master · SBD",
          folder: "1980-02-05 Knoxville TN", path: "/mnt/DYLAN2/1980/", conf: "2026-05-13", fp: true,
          size: "812 MB", files: 24, format: "FLAC 16/44.1", cds: 2 },
        { lb: "LB-71", src: "Audience", rating: "B", owned: false, fam: "aud", lineage: "audience master, low-gen" },
      ],
    },
    {
      id: "1980-04-19-toronto", date: "1980-04-19", disp: "Apr 19, 1980", dow: "Sat", year: 1980,
      venue: "Massey Hall", city: "Toronto, ON", tour: "Gospel Tour", leg: "Spring 1980 · Canada",
      status: "Public", tracks: 14, length: "1h 12m",
      fams: {
        mst: { label: "Rock Solid master", by: "ai+lb", conf: 0.99, note: "TapeMatch flags LB-460 as a byte-identical re-upload" },
        aud: { label: "Audience cassette", by: "lb" },
      },
      recordings: [
        { lb: "LB-456", src: "Master", rating: "A", owned: true, fam: "mst", lineage: "Rock Solid master · complete 14-track set",
          folder: "1980-04-19 Toronto Massey", path: "/mnt/DYLAN2/1980/", conf: "2026-05-13", fp: true,
          size: "688 MB", files: 16, format: "FLAC 16/44.1", cds: 2 },
        { lb: "LB-460", src: "Master", rating: "A", owned: false, fam: "mst", lineage: "re-upload re-tagged under a new LB# · same bytes as LB-456", dup: true },
        { lb: "LB-457", src: "Audience", rating: "B−", owned: true, fam: "aud", lineage: "second-gen audience cassette",
          folder: "1980-04-19 Toronto AUD", path: "/mnt/DYLAN2/1980/", conf: "2026-05-13", fp: true,
          size: "602 MB", files: 14, format: "FLAC 16/44.1", cds: 2 },
      ],
    },
    {
      id: "1980-10-15-atlanta", date: "1980-10-15", disp: "Oct 15, 1980", dow: "Wed", year: 1980,
      venue: "Fox Theatre", city: "Atlanta, GA", tour: "Musical Retrospective", leg: "Fall 1980 · Southeast",
      status: "Public", tracks: 18, length: "1h 31m",
      recordings: [
        { lb: "LB-810", src: "Audience", rating: "B", owned: true, lineage: "audience master, low-gen",
          folder: "1980-10-15 Atlanta Fox", path: "/mnt/DYLAN2/1980/", conf: "2026-05-13", fp: true,
          size: "598 MB", files: 18, format: "FLAC 16/44.1", cds: 2 },
      ],
    },
    {
      id: "1980-11-11-warfield", date: "1980-11-11", disp: "Nov 11, 1980", dow: "Tue", year: 1980,
      venue: "Warfield Theatre", city: "San Francisco, CA", tour: "Musical Retrospective", leg: "Fall 1980 · West Coast",
      status: "Public", tracks: 22, length: "1h 58m", setlist: "warf80",
      fams: {
        aud: { label: "Audience master", by: "ai", conf: 0.9, note: "2 uploads share one cassette transfer" },
        sbd: { label: "Soundboard (trade-only)", by: "lb", note: "a better source you don't own" },
      },
      recordings: [
        { lb: "LB-12", src: "Audience", rating: "B+", owned: true, fam: "aud", lineage: "unknown cass > dat, rated EX–",
          folder: "1980-11-11 Warfield SF", path: "/mnt/DYLAN2/1980/", conf: "2026-05-13", fp: true,
          size: "734 MB", files: 22, format: "FLAC 16/44.1", cds: 2 },
        { lb: "LB-9001", src: "Audience", rating: "B", owned: false, fam: "aud", lineage: "YouTube rip of the same audience master · AAC → FLAC" },
        { lb: "LB-988", src: "Soundboard", rating: "A−", owned: false, fam: "sbd", lineage: "low-gen SBD · circulates in trade-only circles",
          upgrade: true },
      ],
    },
    {
      id: "1980-11-27-portland", date: "1980-11-27", disp: "Nov 27, 1980", dow: "Thu", year: 1980,
      venue: "Paramount Theatre", city: "Portland, OR", tour: "Musical Retrospective", leg: "Fall 1980 · West Coast",
      status: "Public", tracks: 20, length: "1h 44m",
      recordings: [
        { lb: "LB-921", src: "Soundboard", rating: "A−", owned: false, lineage: "complete · uncirculated low gen", wish: true },
      ],
    },

    // ── 1981 · Shot of Love Tour ─────────────────────────────────────
    {
      id: "1981-06-21-earlscourt", date: "1981-06-21", disp: "Jun 21, 1981", dow: "Sun", year: 1981,
      venue: "Earl's Court", city: "London, UK", tour: "Shot of Love", leg: "Summer 1981 · Europe",
      status: "Public", tracks: 19, length: "1h 38m", setlist: "earls81",
      recordings: [
        { lb: "LB-2044", src: "Soundboard", rating: "A", owned: false, lineage: "first night of the Earl's Court run", wish: true },
        { lb: "LB-2045", src: "Audience", rating: "B+", owned: false, lineage: "audience master, near-complete" },
      ],
    },
    {
      id: "1981-06-29-earlscourt", date: "1981-06-29", disp: "Jun 29, 1981", dow: "Mon", year: 1981,
      venue: "Earl's Court", city: "London, UK", tour: "Shot of Love", leg: "Summer 1981 · Europe",
      status: "Public", tracks: 21, length: "1h 52m", title: "A Bird's Nest In Your Hair", xref: "172", setlist: "earls81",
      fams: {
        sbd: { label: "“A Bird's Nest” soundboard", by: "ai+lb", conf: 0.98, note: "3 uploads collapse to 1 master tape" },
        aud: { label: "Audience master", by: "ai", conf: 0.92, note: "2 transfers of the same cassette" },
        fm:  { label: "BBC FM partial", by: "lb", note: "6-song broadcast fragment" },
      },
      recordings: [
        { lb: "LB-18", src: "Soundboard", rating: "A−", owned: true, fam: "sbd", lineage: "Bootleg series · A Bird's Nest In Your Hair",
          folder: "1981-06-29 Earl's Court", path: "/mnt/DYLAN2/1981/", conf: "2026-05-13", fp: true,
          size: "624 MB", files: 26, format: "FLAC 16/44.1", cds: 2 },
        { lb: "LB-9921", src: "Soundboard", rating: "B+", owned: false, fam: "sbd", lineage: "lossy YouTube rip, re-tagged as a fresh upload" },
        { lb: "LB-14002", src: "Soundboard", rating: "B", owned: false, fam: "sbd", lineage: "generation-loss dupe · speed-corrected", dup: true },
        { lb: "LB-19", src: "Audience", rating: "B", owned: true, fam: "aud", lineage: "audience source · taper notes intact",
          folder: "1981-06-29 Earl's Court AUD", path: "/mnt/DYLAN2/1981/", conf: "2026-05-13", fp: true,
          size: "560 MB", files: 21, format: "FLAC 16/44.1", cds: 2 },
        { lb: "LB-15510", src: "Audience", rating: "B−", owned: false, fam: "aud", lineage: "alternate taper transfer of the same source" },
        { lb: "LB-20", src: "FM/Pre-FM", rating: "B+", owned: false, fam: "fm", lineage: "BBC partial broadcast · 6 songs" },
      ],
    },
    {
      id: "1981-07-14-avignon", date: "1981-07-14", disp: "Jul 14, 1981", dow: "Tue", year: 1981,
      venue: "Palais des Papes", city: "Avignon, FR", tour: "Shot of Love", leg: "Summer 1981 · Europe",
      status: "Public", tracks: 14, length: "1h 06m",
      recordings: [
        { lb: "LB-1571", src: "FM/Pre-FM", rating: "B", owned: true, lineage: "FM broadcast > pre-FM lineage uncertain", nofp: true,
          folder: "1981-07-14 Avignon FM", path: "/mnt/DYLAN2/1981/", conf: "2026-05-13", fp: false,
          size: "486 MB", files: 14, format: "FLAC 16/44.1", cds: 1 },
      ],
    },
    {
      id: "1981-11-19-houston", date: "1981-11-19", disp: "Nov 19, 1981", dow: "Thu", year: 1981,
      venue: "The Summit", city: "Houston, TX", tour: "Shot of Love", leg: "Fall 1981 · USA",
      status: "Public", tracks: 23, length: "1h 49m",
      recordings: [
        { lb: "LB-130", src: "Soundboard", rating: "B+", owned: true, lineage: "soundboard master, full show",
          folder: "1981-11-19 Houston Summit", path: "/mnt/DYLAN2/1981/", conf: "2026-05-13", fp: true,
          size: "702 MB", files: 23, format: "FLAC 16/44.1", cds: 2 },
      ],
    },
    {
      id: "1981-xx-missing", date: "1981-12-00", disp: "late 1981", dow: "—", year: 1981,
      venue: "Venue unconfirmed", city: "—", tour: "Shot of Love", leg: "Fall 1981 · USA",
      status: "Missing", tracks: null, length: "—",
      recordings: [
        { lb: "LB-1422", src: null, rating: "—", owned: false, lineage: "no metadata · page missing from LB site", missing: true },
      ],
    },

    // ── 1983 · Infidels era ──────────────────────────────────────────
    {
      id: "1983-02-16-lonestar", date: "1983-02-16", disp: "Feb 16, 1983", dow: "Wed", year: 1983,
      venue: "Lone Star Café", city: "New York, NY", tour: "Guest appearance", leg: "Winter 1983 · NYC",
      status: "Public", tracks: 15, length: "1h 18m", setlist: "lonestar83",
      fams: {
        ls: { label: "Late-show matrix + source", by: "ai+lb", conf: 0.95, note: "matrix was built from the raw AUD — TapeMatch links them" },
      },
      recordings: [
        { lb: "LB-13680", src: "Mixed", rating: "A−", owned: true, fam: "ls", lineage: "late show · 15 tracks · IEM matrix",
          folder: "1983-02-16 Lone Star Cafe", path: "/mnt/DYLAN3/1983/", conf: "2026-05-14", fp: true,
          size: "540 MB", files: 15, format: "FLAC 16/44.1", cds: 1 },
        { lb: "LB-13681", src: "Audience", rating: "B", owned: false, fam: "ls", lineage: "raw audience source the matrix was built from" },
      ],
    },
    {
      id: "1983-session-infidels", date: "1983-05-00", disp: "Apr–May 1983", dow: "sessions", year: 1983,
      venue: "Power Station", city: "New York, NY", tour: "Infidels sessions", leg: "Studio · 1983",
      status: "Private", tracks: null, length: "—", isSession: true,
      recordings: [
        { lb: "LB-1964", src: "Master", rating: "B", owned: true, lineage: "First Infidels outtakes · 9 tracks · early shape",
          folder: "1983-xx-xx First Infidels OTs", path: "/mnt/DYLAN3/1983/", conf: "2026-05-14", fp: true,
          size: "412 MB", files: 9, format: "FLAC 16/44.1", cds: 1 },
        { lb: "LB-1971", src: "Master", rating: "B+", owned: false, lineage: "Power Station outtakes · 137 fragments · sequenced", priv: true },
      ],
    },

    // ── 2026 · current tour ──────────────────────────────────────────
    {
      id: "2026-03-27-lacrosse", date: "2026-03-27", disp: "Mar 27, 2026", dow: "Fri", year: 2026,
      venue: "La Crosse Center", city: "La Crosse, WI", tour: "Rough & Rowdy Ways", leg: "Spring 2026 · Midwest",
      status: "Public", tracks: 17, length: "1h 35m",
      recordings: [
        { lb: "LB-16588", src: "Audience", rating: "B+", owned: true, lineage: "audience master · fresh transfer", nofp: true,
          folder: "bd2026-03-27 La Crosse WI (LB-16588)", path: "/mnt/HOPPER/incoming/", conf: "yesterday", fp: false,
          size: "918 MB", files: 21, format: "FLAC 24/48", cds: 2 },
      ],
    },
    {
      id: "2026-03-30-waukegan", date: "2026-03-30", disp: "Mar 30, 2026", dow: "Mon", year: 2026,
      venue: "Genesee Theatre", city: "Waukegan, IL", tour: "Rough & Rowdy Ways", leg: "Spring 2026 · Midwest",
      status: "New", tracks: 19, length: "1h 41m",
      recordings: [
        { lb: "LB-16590", src: "Audience", rating: "—", owned: true, lineage: "just filed from Pipeline · awaiting confirm", unconf: true, nofp: true,
          folder: "bd2026.03.30.Waukegan.IL.flac", path: "/mnt/HOPPER/incoming/", conf: "—", fp: false,
          size: "884 MB", files: 19, format: "FLAC 24/48", cds: 2 },
      ],
    },
  ];

  // ── Setlists (keyed by performance setlist id) ──────────────────────
  const SETLISTS = {
    earls81: {
      tracks: 21, length: "1h 52m",
      discs: [
        { label: "Disc 1", time: "48:55", tracks: [
          ["Gotta Serve Somebody", "6:12"], ["I Believe in You", "4:58"],
          ["Like a Rolling Stone", "7:05"], ["Man Gave Names to All the Animals", "5:40"],
          ["Maggie's Farm", "5:18"], ["I Don't Believe You", "4:42"],
          ["Dead Man, Dead Man", "6:08"], ["Girl from the North Country", "4:35"],
          ["Ballad of a Thin Man", "4:17"],
        ]},
        { label: "Disc 2", time: "63:20", tracks: [
          ["Slow Train", "6:01"], ["Let's Begin", "4:23"], ["Lenny Bruce", "5:10", "rare"],
          ["Mr. Tambourine Man", "5:55"], ["Solid Rock", "4:39"],
          ["Just Like a Woman", "5:32"], ["Watered-Down Love", "4:48"],
          ["Forever Young", "6:15"], ["When You Gonna Wake Up", "5:30"],
          ["In the Garden", "5:58"], ["Blowin' in the Wind", "4:51"],
          ["Knockin' on Heaven's Door", "4:18"],
        ]},
      ],
    },
    warf80: {
      tracks: 22, length: "1h 58m",
      discs: [
        { label: "Set", time: "118:00", tracks: [
          ["Gotta Serve Somebody", "5:48"], ["I Believe in You", "5:02"],
          ["Like a Rolling Stone", "6:40"], ["Till I Get It Right", "4:10"],
          ["Covenant Woman", "5:22", "rare"], ["Gospel Plow", "3:58"],
          ["Slow Train", "6:11"], ["Solid Rock", "4:36"],
          ["Just Like a Woman", "5:28"], ["Señor", "5:50"],
          ["Girl from the North Country", "4:40"], ["Mr. Tambourine Man", "5:48"],
        ]},
      ],
    },
    lonestar83: {
      tracks: 15, length: "1h 18m",
      discs: [
        { label: "Late show", time: "78:06", tracks: [
          ["Don't Start Me Talkin'", "4:21"], ["Sweet Home Chicago", "6:02"],
          ["Mansion on the Hill", "5:14", "rare"], ["Key to the Highway", "4:48"],
          ["Going, Going, Gone", "5:33"], ["Lucky Old Sun", "4:57"],
          ["I Ain't Got No Home", "4:40"], ["Trouble in Mind", "6:11"],
        ]},
      ],
    },
    knox80: {
      tracks: 17, length: "1h 24m",
      discs: [
        { label: "Set", time: "84:00", tracks: [
          ["Gotta Serve Somebody", "5:55"], ["I Believe in You", "5:00"],
          ["When You Gonna Wake Up", "5:30"], ["Covenant Woman", "5:18"],
          ["Solid Rock", "4:35"], ["Saving Grace", "5:02"],
          ["In the Garden", "5:55"], ["Are You Ready", "4:20"],
        ]},
      ],
    },
  };

  // ── Facet definitions (catalog-wide, illustrative counts) ───────────
  const FACETS = {
    decade: [
      { k: "60s", n: 261 }, { k: "70s", n: 1402 }, { k: "80s", n: 1188 },
      { k: "90s", n: 1320 }, { k: "00s", n: 1009 }, { k: "10s", n: 612 }, { k: "20s", n: 196 },
    ],
    coverage: [
      { k: "Covered",  n: 5104 }, { k: "Upgrade",  n: 612 },
      { k: "Gap",      n: 884 },  { k: "Undocumented", n: 42 },
    ],
    recordings: [
      { k: "Multiple sources", n: 2210 }, { k: "Single recording", n: 5990 },
      { k: "Soundboard exists", n: 1980 }, { k: "Audience only", n: 3120 },
    ],
    source: [
      { k: "Soundboard", n: 1980 }, { k: "FM/Pre-FM", n: 642 },
      { k: "Audience", n: 5044 }, { k: "Master", n: 820 }, { k: "Mixed", n: 414 },
    ],
    rating: [
      { k: "A", n: 412 }, { k: "A−", n: 708 }, { k: "B+", n: 1190 },
      { k: "B", n: 1470 }, { k: "B−", n: 620 }, { k: "C", n: 212 },
    ],
  };

  // Performance-level totals (illustrative)
  const TOTALS = { performances: 5988, recordings: 16630, families: 9740, covered: 5104, gaps: 884 };

  // ── Derived helpers ─────────────────────────────────────────────────
  const RATING_RANK = { "A": 6, "A−": 5, "B+": 4, "B": 3, "B−": 2, "C": 1, "—": 0 };

  // TapeMatch method vocabulary — how a family was clustered.
  // ai+lb = AI fingerprint/spectrogram match + LB catalog cross-reference (strongest)
  // ai    = AI fingerprint/spectrogram match only
  // lb    = LB catalog cross-reference only (or a lone, unmatched recording)
  const MATCH = {
    "ai+lb": { code: "AI + LB", icon: "tapematch", tone: "info" },
    "ai":    { code: "AI match", icon: "spectro",   tone: "info" },
    "lb":    { code: "LB-linked", icon: "link",     tone: "mute" },
  };

  // Group a performance's recordings into TapeMatch families.
  // A family is a cluster of LB# uploads that resolve to one underlying source tape.
  // Recordings carry `fam` (a key into p.fams); unkeyed recordings stand alone.
  function families(p) {
    const meta = p.fams || {};
    const groups = new Map();
    (p.recordings || []).forEach(r => {
      const key = r.fam || r.lb || "lone";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(r);
    });
    const out = [];
    groups.forEach((members, key) => {
      const m = meta[key] || {};
      const best = members.reduce((b, r) => (RATING_RANK[r.rating] || 0) > (RATING_RANK[b ? b.rating : "—"] || -1) ? r : b, null);
      const owned = members.filter(r => r.owned);
      const bestOwned = owned.reduce((b, r) => (RATING_RANK[r.rating] || 0) > (RATING_RANK[b ? b.rating : "—"] || -1) ? r : b, null);
      const canonical = bestOwned || best;
      const src = canonical ? canonical.src : (members[0] ? members[0].src : null);
      out.push({
        id: key, members,
        label: m.label || (src ? (SOURCES[src] || {}).full || src : "Recording"),
        by: m.by || "lb", conf: m.conf != null ? m.conf : null, note: m.note || null,
        src, canonical,
        best, bestRating: best ? best.rating : "—",
        owned: owned.length > 0, ownedCount: owned.length, total: members.length,
        multi: members.length > 1,
        dupes: members.filter(r => r.dup).length,
      });
    });
    out.sort((a, b) =>
      (b.owned - a.owned) ||
      ((RATING_RANK[b.bestRating] || 0) - (RATING_RANK[a.bestRating] || 0)) ||
      (b.total - a.total));
    return out;
  }

  function rollup(p) {
    const recs = p.recordings || [];
    const owned = recs.filter(r => r.owned);
    const best = recs.reduce((b, r) => (RATING_RANK[r.rating] || 0) > (RATING_RANK[b?.rating] || -1) ? r : b, null);
    const bestOwned = owned.reduce((b, r) => (RATING_RANK[r.rating] || 0) > (RATING_RANK[b?.rating] || -1) ? r : b, null);
    const fams = families(p);
    let coverage;
    if (p.status === "Missing") coverage = "Undocumented";
    else if (owned.length === 0) coverage = "Gap";
    else if (owned.length < recs.length && best && !best.owned) coverage = "Upgrade"; // a better source exists unowned
    else if (owned.length < recs.length) coverage = "Covered"; // own the best, missing a lesser source
    else coverage = "Covered";
    return {
      total: recs.length, ownedCount: owned.length,
      famTotal: fams.length, famOwned: fams.filter(f => f.owned).length,
      dupeCount: recs.filter(r => r.dup).length,
      bestRating: best ? best.rating : "—",
      bestOwnedRating: bestOwned ? bestOwned.rating : null,
      hasSBD: recs.some(r => r.src === "Soundboard"),
      multi: recs.length > 1,
      coverage,
    };
  }

  return { SOURCES, MATCH, PERFS, SETLISTS, FACETS, TOTALS, RATING_RANK, families, rollup };
})();
