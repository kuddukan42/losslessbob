// library-data.js
// Sample data for the unified Library screen (Search + My Collection merged).
// One row universe: every row is a master-DB entry; `owned` is a lens, not a table.

window.LBB_LIB = (() => {

  // ── Rows ─────────────────────────────────────────────────────────────
  // Catalog fields are always present; file fields only when owned.
  const ROWS = [
    // 1980
    { lb: "LB-12", src: "Audience",   status: "Public",  date: "11/11/80", year: 1980, loc: "Warfield, San Francisco",
      rating: "B+", desc: "unknown cass > dat, rated EX–", xref: null, owned: true,
      folder: "1980-11-11 Warfield SF", path: "/mnt/DYLAN2/1980/", conf: "2026-05-13", fp: true,
      size: "734 MB", files: 22, format: "FLAC 16/44.1", cds: 2 },

    { lb: "LB-70", src: "Soundboard",   status: "Public",  date: "02/05/80", year: 1980, loc: "Civic Coliseum, Knoxville TN",
      rating: "A−", desc: "Holy Grail master from soundboard", xref: null, owned: true,
      folder: "1980-02-05 Knoxville TN", path: "/mnt/DYLAN2/1980/", conf: "2026-05-13", fp: true,
      size: "812 MB", files: 24, format: "FLAC 16/44.1", cds: 2 },

    { lb: "LB-456", src: "Master",  status: "Public",  date: "04/19/80", year: 1980, loc: "Massey Hall, Toronto ON",
      rating: "A",  desc: "Rock Solid master, complete 14-track set", xref: null, owned: true, dup: true,
      folder: "1980-04-19 Toronto Massey", path: "/mnt/DYLAN2/1980/", conf: "2026-05-13", fp: true,
      size: "688 MB", files: 16, format: "FLAC 16/44.1", cds: 2 },

    { lb: "LB-810", src: "Audience",  status: "Public",  date: "10/15/80", year: 1980, loc: "Fox Theatre, Atlanta GA",
      rating: "B",  desc: "Audience master, low-gen", xref: null, owned: true, dup: true,
      folder: "1980-10-15 Atlanta Fox", path: "/mnt/DYLAN2/1980/", conf: "2026-05-13", fp: true,
      size: "598 MB", files: 18, format: "FLAC 16/44.1", cds: 2 },

    { lb: "LB-921", src: "Soundboard",  status: "Public",  date: "11/27/80", year: 1980, loc: "Paramount Theatre, Portland OR",
      rating: "A−", desc: "Soundboard, complete · uncirculated low gen", xref: null, owned: false, wish: true },

    // 1981
    { lb: "LB-18", src: "Soundboard",   status: "Public",  date: "06/29/81", year: 1981, loc: "Earl's Court, London",
      title: "A Bird's Nest In Your Hair",
      rating: "A−", desc: "A Bird's Nest In Your Hair · Bootleg series", xref: "172", owned: true,
      folder: "1981-06-29 Earl's Court", path: "/mnt/DYLAN2/1981/", conf: "2026-05-13", fp: true,
      size: "624 MB", files: 26, format: "FLAC 16/44.1", cds: 2 },

    { lb: "LB-130", src: "Soundboard",  status: "Public",  date: "11/19/81", year: 1981, loc: "The Summit, Houston TX",
      rating: "B+", desc: "Soundboard master, full show", xref: null, owned: true,
      folder: "1981-11-19 Houston Summit", path: "/mnt/DYLAN2/1981/", conf: "2026-05-13", fp: true,
      size: "702 MB", files: 23, format: "FLAC 16/44.1", cds: 2 },

    { lb: "LB-1422", status: "Missing", date: "—", year: 1981, loc: "—",
      rating: "—",  desc: "No metadata · page missing from LB site", xref: null, owned: false },

    { lb: "LB-1571", src: "FM/Pre-FM", status: "Public",  date: "07/14/81", year: 1981, loc: "Palais des Papes, Avignon",
      rating: "B",  desc: "FM broadcast > pre-FM lineage uncertain", xref: null, owned: true, nofp: true,
      folder: "1981-07-14 Avignon FM", path: "/mnt/DYLAN2/1981/", conf: "2026-05-13", fp: false,
      size: "486 MB", files: 14, format: "FLAC 16/44.1", cds: 1 },

    { lb: "LB-2044", src: "Soundboard", status: "Public",  date: "06/21/81", year: 1981, loc: "Earl's Court, London",
      rating: "A",  desc: "Soundboard · first night of the Earl's Court run", xref: null, owned: false },

    // 1983
    { lb: "LB-13680", src: "Mixed", status: "Public", date: "02/16/83", year: 1983, loc: "Lone Star Café, NYC",
      rating: "A−", desc: "Late show · 15 tracks · IEM matrix", xref: null, owned: true,
      folder: "1983-02-16 Lone Star Cafe", path: "/mnt/DYLAN3/1983/", conf: "2026-05-14", fp: true,
      size: "540 MB", files: 15, format: "FLAC 16/44.1", cds: 1 },

    { lb: "LB-1964", src: "Master", status: "Public",  date: "xx/xx/83", year: 1983, loc: "First Infidels OTs",
      rating: "B",  desc: "Studio outtakes · 9 tracks · early shape", xref: null, owned: true,
      folder: "1983-xx-xx First Infidels OTs", path: "/mnt/DYLAN3/1983/", conf: "2026-05-14", fp: true,
      size: "412 MB", files: 9, format: "FLAC 16/44.1", cds: 1 },

    { lb: "LB-1971", src: "Master", status: "Private", date: "xx/xx/83", year: 1983, loc: "Power Station OTs",
      rating: "B+", desc: "Studio outtakes · 137 fragments · sequenced", xref: null, owned: false },

    // 2026
    { lb: "LB-16588", src: "Audience", status: "Public", date: "03/27/26", year: 2026, loc: "La Crosse Center, WI",
      rating: "B+", desc: "Audience master · fresh transfer", xref: null, owned: true, nofp: true,
      folder: "bd2026-03-27 La Crosse WI (LB-16588)", path: "/mnt/HOPPER/incoming/", conf: "yesterday", fp: false,
      size: "918 MB", files: 21, format: "FLAC 24/48", cds: 2 },

    { lb: "LB-16590", src: "Audience", status: "New",    date: "03/30/26", year: 2026, loc: "Genesee Theatre, Waukegan IL",
      rating: "—",  desc: "Just filed from Pipeline · awaiting confirm", xref: null, owned: true, unconf: true, nofp: true,
      folder: "bd2026.03.30.Waukegan.IL.flac", path: "/mnt/HOPPER/incoming/", conf: "—", fp: false,
      size: "884 MB", files: 19, format: "FLAC 24/48", cds: 2 },
  ];

  // ── Setlists (from master DB — available whether or not you own it) ──
  const SETLISTS = {
    "LB-18": {
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
    "LB-2044": {
      tracks: 12, length: "1h 04m",
      discs: [
        { label: "Single set", time: "64:10", tracks: [
          ["Gotta Serve Somebody", "5:58"], ["I Believe in You", "5:04"],
          ["Like a Rolling Stone", "6:48"], ["Till I Get It Right", "4:12", "debut"],
          ["Maggie's Farm", "5:25"], ["Ballad of a Thin Man", "4:30"],
          ["Slow Train", "5:50"], ["Lenny Bruce", "5:02"],
          ["Forever Young", "6:04"], ["In the Garden", "5:46"],
          ["Blowin' in the Wind", "4:55"], ["Knockin' on Heaven's Door", "4:16"],
        ]},
      ],
    },
    "LB-13680": {
      tracks: 15, length: "1h 18m",
      discs: [
        { label: "Late show", time: "78:06", tracks: [
          ["Don't Start Me Talkin'", "4:21"], ["Sweet Home Chicago", "6:02"],
          ["Mansion on the Hill", "5:14", "rare"], ["Key to the Highway", "4:48"],
          ["Going, Going, Gone", "5:33"], ["Lucky Old Sun", "4:57"],
          ["I Ain't Got No Home", "4:40"], ["Trouble in Mind", "6:11"],
          ["Stormy Weather", "5:05"], ["Big River", "4:29"],
          ["Roll On John", "5:18"], ["Milk Cow Blues", "4:52"],
          ["House of the Rising Sun", "5:44"], ["So Long, Good Luck and Goodbye", "4:36"],
          ["Goodnight Irene", "6:16"],
        ]},
      ],
    },
  };

  // ── Per-entry history (owned entries) ────────────────────────────────
  const HISTORY = {
    "LB-18": {
      torrents: [
        { d: "2024-08-12", f: "LB-18.A.Birds.Nest.torrent",   tag: "In qBt" },
        { d: "2023-02-04", f: "LB-18.full-show.v2.torrent",   tag: "In qBt" },
        { d: "2021-11-18", f: "LB-18.early-master.torrent",   tag: "Local" },
      ],
      forum: [
        { d: "2024-08-14", f: "RE-SEED: LB-18 Earl's Court night 2", tag: "Posted" },
        { d: "2023-02-05", f: "LB-18 v2 lineage notes",              tag: "Posted" },
      ],
    },
  };

  // ── Cross-references — what you own related to an unowned entry ─────
  const RELATED = {
    "LB-2044": [
      { lb: "LB-18", src: "Soundboard", date: "06/29/81", note: "Night 2 of the same Earl's Court run" },
    ],
    "LB-921": [
      { lb: "LB-12", src: "Audience", date: "11/11/80", note: "Same fall-1980 tour · 2 weeks earlier" },
    ],
  };

  // ── Facet definitions (counts are catalog-wide, illustrative) ───────
  const FACETS = {
    decade: [
      { k: "60s", n: 302 }, { k: "70s", n: 1841 }, { k: "80s", n: 4290 },
      { k: "90s", n: 3820 }, { k: "00s", n: 4109 }, { k: "10s", n: 1720 }, { k: "20s", n: 548 },
    ],
    status: [
      { k: "Public", n: 15184 }, { k: "Private", n: 1404 }, { k: "Missing", n: 42 },
    ],
    rating: [
      { k: "A", n: 912 }, { k: "A−", n: 1408 }, { k: "B+", n: 2290 },
      { k: "B", n: 1170 }, { k: "B−", n: 820 }, { k: "C", n: 312 },
    ],
    source: [
      { k: "Soundboard", n: 4108 }, { k: "FM/Pre-FM", n: 1822 },
      { k: "Audience", n: 8920 }, { k: "Master", n: 2304 }, { k: "Mixed", n: 1476 },
    ],
  };

  const TOTALS = { all: 16630, owned: 15967, unowned: 663 };

  return { ROWS, SETLISTS, HISTORY, RELATED, FACETS, TOTALS };
})();
