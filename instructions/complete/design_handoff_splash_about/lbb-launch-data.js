// lbb-launch-data.js
// Content for the LosslessBob splash + about screens. Plain data — no deps.

window.LBB_LAUNCH = {
  meta: {
    name: "LosslessBob",
    tagline: "Checksum Lookup",
    version: "1.2.0",
    channel: "stable",
    build: "2026.05.29",
    db: "LB-16630",
    checksums: "704,624",
    copyright: "© 2024–2026 LosslessBob project · A community archival tool.",
  },

  // Real Electron startup phases. Order + timings measured from a normal
  // cold start (see startup trace, ~2.4s to window.show). [label, detail, atMs]
  // atMs = ms after main() when the phase BEGINS; the bar fills toward the next.
  // Production drives this from real IPC progress; the mock replays it at true speed.
  boot: [
    ["Starting backend",   "Flask · Waitress",               120],
    ["Opening database",   "checksum_lookup.db · LB-16630",   510],
    ["Loading interface",  "electron-vite · renderer",        792],
    ["Backend ready",      "localhost:5174",                 1679],
    ["Building views",     "14 panels",                      1712],
    ["Restoring session",  "geometry · shadows",             2381],
  ],
  bootReadyMs: 2407,   // measured: main start → window.show()

  // Tech stack — grouped for the about screen.
  stack: [
    { group: "Interface", rows: [
      ["GUI (primary)",   "Electron + React + TypeScript", "electron-vite", true],
      ["GUI (legacy)",    "PyQt6",                          "6.7.1 · frozen"],
      ["Attachments view","PyQt6-WebEngine",                "6.7.0"],
    ]},
    { group: "Backend", rows: [
      ["REST backend",    "Flask + Flask-CORS", "3.0.3 / 4.0.1"],
      ["WSGI server",     "Waitress",           "3.0.0"],
      ["Database",        "SQLite3",            "stdlib"],
      ["Bloom filter",    "pybloom-live",       "4.0.0"],
    ]},
    { group: "Ingest & web", rows: [
      ["Web scraping",    "BeautifulSoup4 + lxml", "4.12.3 / 6.1.0"],
      ["HTTP client",     "Requests",              "2.32.3"],
      ["File watching",   "Watchdog",              "4.0.1"],
      ["Torrent gen",     "torf",                  "4.3.1"],
      ["Credentials",     "keyring",               "25.7.0"],
    ]},
    { group: "Audio & DSP", rows: [
      ["Numerical",       "numpy",      "2.4.6"],
      ["Fingerprinting",  "librosa",    "0.11.0"],
      ["Audio I/O",       "soundfile",  "0.13.1"],
      ["Signal proc.",    "scipy",      "1.17.1"],
      ["JIT compilation", "numba",      "0.65.1"],
      ["Language",        "Python",     "3.11+"],
    ]},
  ],

  // Short architecture note for the about screen.
  arch: "GUI and backend are separated by a local Flask REST API on port 5174. " +
        "gui_next (Electron/React) is the active target; Flask runs as a child process. " +
        "The PyQt6 GUI is frozen as a fallback reference.",

  // Acknowledgements. tone: 'memory' gets the in-memoriam treatment.
  acks: [
    { name: "Losslessbob",  handle: "the original archive",
      note: "The archive and project that inspired this tool — the source of the LB numbering this app is built around." },
    { name: "Rumrunners",   handle: "system author · maintainer",
      note: "Creator of the LB system and its ongoing maintainer. The schema, conventions, and master database are his work." },
    { name: "Robert Cook",  handle: "r9453",  tone: "memory",
      note: "Contributor and close friend. His work and company shaped this project. Remembered." },
  ],

  // Changelog snippet — most recent release only.
  changelog: {
    version: "1.2.0",
    date: "May 29, 2026",
    entries: [
      ["new",     "Unified ingest Pipeline — verify → lookup → rename → LBDIR in one pass."],
      ["new",     "gui_next (Electron + React) is now the primary interface."],
      ["improved","Spectrogram and concert-map screens redrawn at higher fidelity."],
      ["changed", "PyQt6 GUI frozen — kept only as a fallback reference."],
      ["fixed",   "Checksum-index load time on large mounts cut roughly in half."],
    ],
  },

  links: [
    { icon: "globe",  label: "losslessbob.org",            sub: "Project home",      href: "#" },
    { icon: "lbdir",  label: "Documentation & LB system",  sub: "rumrunners guide",  href: "#" },
    { icon: "link",   label: "github · checksum-lookup",   sub: "Source & issues",   href: "#" },
    { icon: "star",   label: "Support the archive",        sub: "Donate / mirror",   href: "#" },
  ],
};
