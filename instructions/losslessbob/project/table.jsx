// table.jsx — Before/After results-table mock for LosslessBob
// Exports BeforeTable + AfterTable to window.

const ROWS = [
  { y: 1970, count: 8, group: true },
  { lb: "LB-01233", st: "Public", date: "xx/xx/70", loc: "New Morning Acetate …", r: "A",  owned: true,  xref: "—",       desc: "excellent sound small pop t11 0:15, 1:42, 2:22, t19 0:37, 1:20 caused by discontinuity. 1 If Not For You, 2 Day Of The Locusts, 3 Time Passes Slowly, 4 Gotta Travel On, 5 Went To See The Gypsy…" },
  { lb: "LB-03277", st: "Public", date: "12/xx/70", loc: "Carmel, New York, Th…", r: "C",  owned: false, xref: "—",       desc: "Earl Scruggs Documentary, mono t1 and t2 have big tv band; good sound [C]. East Virginia Blues (trad.), Nashville Skyline Rag, Nashville Skyline Rag…" },
  { lb: "LB-04631", st: "Public", date: "xx/xx/70", loc: "a few studio; Columbi…", r: "A",  owned: true,  xref: "01233",   desc: "From a Data DVD disc, a few 1970 files. bittorrent download 03/07; excellent sound [A]; quality notes given below on a song by song basis as different for each song. 1970 March Studio B Columbia…" },
  { lb: "LB-06700", st: "Public", date: "5/1/70",   loc: "Nashville, TN",         r: "A",  owned: false, xref: "—",       desc: "BOOTLEG: Possum Belly Overalls; cd > ultraplex > eac > wav > flac; Gold Standard Nash 105; George Harrison Sessions; 5/69 has asymetric wavs with bottom to -7db and top to -4db…" },
  { lb: "LB-06981", st: "Public", date: "5/1/70",   loc: "Bob Dylan and George…", r: "A",  owned: true,  xref: "—",       desc: "BOOTLEG: Yesterday; Bob Dylan and George Harrison are remembered for working together in the Traveling Wilburys in the late 1980's, and of course, Bob Dylan's guest appearance at the Concert…" },
  { lb: "LB-07960", st: "Public", date: "5/1/70",   loc: "Nashville and NYC",     r: "A",  owned: false, xref: "08343",   desc: "BOOTLEG: almost went to see elvis; version \"b\"; & George Harrison, CBS Studio Nashville, TN May 3, 1969 and CBS Studio B, NYC May 1, 1970; torrenter commented that this is bootleg…" },
  { lb: "LB-09382", st: "Public", date: "5/1/70",   loc: "Columbia Records Stu…", r: "A",  owned: true,  xref: "07960",   desc: "BOOTLEG: almost went to see elvis; version \"d\"; SBD studio > ? > Almost Went To See Elvis (Cool Daddy Productions) trade CDR > EAC > WAV > Wave Repair 4.9.3 to fix micro gaps and clicks…" },
  { lb: "LB-09521", st: "Public", date: "5/xx/70",  loc: "1970 studio sessions",  r: "B+", owned: false, xref: "—",       desc: "BOOTLEG: dylan harrison sessions vinyl; Transfer From My Vinyl, Sony PS-11W > Philips CDR 765 > EAC (secure mode) > TLH (level 8) > Maketorrent, more info at bobsboots.com…" },
  { y: 1971, count: 6, group: true },
  { lb: "LB-06134", st: "Public", date: "11/xx/71", loc: "Allen Ginsberg and Bo…", r: "B+", owned: true,  xref: "—",       desc: "All tracks taken from best quality / most complete circulating sources. Session Information: Record Plant, New York City, New York, 9–17, 20 November 1971, Produced by Allen Ginsberg & Friends…" },
  { lb: "LB-06135", st: "Public", date: "10/30/71", loc: "Allen Ginsberg & Frien…", r: "—", owned: false, xref: "06134",   desc: "Trade CDr circa 2002 > EAC > Wave Repair manual fix of index clicks, minor digi clicks, No ASM > flac lvl 8 verify. bittorrent download 05/08; in comparison to the portion on dvd 38 this is muffled…" },
  { lb: "LB-09846", st: "Public", date: "8/1/71",   loc: "THE CONCERT FOR B…",    r: "B+", owned: true,  xref: "—",       desc: "apple acetate re, GEORGE HARRISON, featuring Bob Dylan, Remasters Workshop RMW 700, DC offset eliminated; Acetate source declicked, pitch, phase and levels corrected; tape source processed…" },
  { lb: "LB-10666", st: "Public", date: "9/24/71",  loc: "Columbia Recording S…", r: "A",  owned: false, xref: "10667",   desc: "happytraumsession torrented 11/24. 1 intro, 2 I Shall Be Released, 3 tuning, 4 You Ain't Goin' Nowhere take 1, 5 You Ain't Goin' Nowhere, 6 Down In The Flood…" },
  { lb: "LB-10667", st: "Public", date: "9/24/71",  loc: "Columbia Recording S…", r: "A",  owned: true,  xref: "10666",   desc: "happytraumsession jvs gs, low gen. cassette from jvs > reel > ASC 5000 > Sony PCM-M10 > WAV > CDwave > TLH > FLAC torrented 05/25; in comparison this sounds similar to hg…" },
  { lb: "LB-11327", st: "Public", date: "xx/xx/71", loc: "Phone conversations …", r: "B+", owned: false, xref: "—",       desc: "aj weberman lowgen, Jan 8–9 1971, Dylan tries to correct a magazine article before publication and generally tries to reign in his most active critic at the time. The first short call was on a Friday…" },
  { y: 1972, count: 2, group: true },
  { lb: "LB-09058", st: "Public", date: "xx/xx/72", loc: "studio sessions as sid…", r: "A",  owned: false, xref: "—",       desc: "BOOTLEG: friends will disappear; hollow horn friends will disappear; Friends Will Disappear: Studio Sessions (Take 2) (Hollow Horn Recording Artist Vol. 7) bittorrent download 12/10…" },
  { lb: "LB-09606", st: "Public", date: "11/xx/72", loc: "Durango, Sam Peckin…", r: "—", owned: true,  xref: "—",       desc: "pitch-corrected it as it was running too fast. good to very good sound [B−] 0'40 Billy" },
];

// ---- BEFORE: faithful recreation of the current screen ----
function BeforeTable() {
  const beforeRating = { A: "#3f8f5e", "A−": "#3f8f5e", "B+": "#3f8f5e", B: "#3f8f5e", "B−": "#3f8f5e", C: "#b8860b", "—": "#9a958c" };
  return (
    <div className="bf-wrap">
      <div className="bf-toolbar">
        <div className="bf-tb-search">⌕ Search title, location, description, LB# …</div>
        <div className="bf-tb-ctrl">All Fields ⌄</div>
        <div className="bf-tb-ctrl bf-purple">⛁ Group by year ⌄</div>
        <div className="bf-tb-ctrl">Columns ⌄</div>
      </div>
      <div className="bf-meta">
        <span><b>743 results</b> <span className="bf-dim">of 16,630</span></span>
        <span className="bf-chip">Status: Public ✕</span>
        <span className="bf-chip">Decade: 1970s ✕</span>
        <span className="bf-chip">Best per date ✕</span>
        <span className="bf-sort">Sort: LB# ↑ ⌄</span>
      </div>
      <div className="bf-table">
        <div className="bf-head">
          <div className="c-lb">LB#</div>
          <div className="c-st">STATUS</div>
          <div className="c-date">DATE</div>
          <div className="c-loc">LOCATION</div>
          <div className="c-rate">★</div>
          <div className="c-desc">DESCRIPTION</div>
          <div className="c-xref">XREF</div>
          <div className="c-own">OWN</div>
        </div>
        <div className="bf-body">
          {ROWS.map((row, i) => row.group ? (
            <div className="bf-grouprow" key={i}>⌄ {row.y} <span className="bf-dim">{row.count}</span></div>
          ) : (
            <div className="bf-row" key={i}>
              <div className="c-lb mono">{row.lb}</div>
              <div className="c-st bf-public">Public</div>
              <div className="c-date mono">{row.date}</div>
              <div className="c-loc">{row.loc}</div>
              <div className="c-rate"><span className="bf-badge" style={{ color: beforeRating[row.r] }}>{row.r}</span></div>
              <div className="c-desc">{row.desc}</div>
              <div className="c-xref mono">{row.xref}</div>
              <div className="c-own">✓ …</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---- AFTER: neutral table, purple-only accent, green strictly semantic ----
const RATE = {
  A:  { fg: "#2f7d52", bg: "#eef6f0", bd: "#cfe6d8" },
  "A−": { fg: "#2f7d52", bg: "#eef6f0", bd: "#cfe6d8" },
  "B+": { fg: "#3a6ea5", bg: "#eef2f8", bd: "#d4e0ef" },
  B:  { fg: "#5d6470", bg: "#f1f1f3", bd: "#e0e1e5" },
  "B−": { fg: "#5d6470", bg: "#f1f1f3", bd: "#e0e1e5" },
  C:  { fg: "#a9701a", bg: "#fbf3e6", bd: "#eeddc2" },
};

function Rating({ r }) {
  if (r === "—") return <span className="af-dash">—</span>;
  const s = RATE[r] || RATE.B;
  return <span className="af-badge" style={{ color: s.fg, background: s.bg, borderColor: s.bd }}>{r}</span>;
}

// Split desc into a lead clause (kept dark) + remainder (dimmed); pull a sound grade like [A] or [B−]
function AfterDesc({ desc }) {
  const gradeMatch = desc.match(/\[([A-C][+−-]?)\]/);
  const grade = gradeMatch ? gradeMatch[1] : null;
  // lead = up to first sentence-ish boundary
  const m = desc.match(/^(.{0,70}?[.;])\s+(.*)$/);
  let lead, rest;
  if (m) { lead = m[1]; rest = m[2]; } else { lead = desc; rest = ""; }
  return (
    <span className="af-desc">
      {grade && <span className="af-grade">[{grade}]</span>}
      <span className="af-lead">{lead}</span>
      {rest && <span className="af-rest"> {rest}</span>}
    </span>
  );
}

function AfterTable() {
  return (
    <div className="af-wrap">
      <div className="af-toolbar">
        <div className="af-tb-search">⌕ Search title, location, description, LB# …</div>
        <div className="af-tb-ctrl">All Fields ⌄</div>
        <div className="af-tb-ctrl af-active">Group by year ⌄</div>
        <div className="af-tb-ctrl">Columns ⌄</div>
      </div>
      <div className="af-meta">
        <span><b>743 results</b> <span className="af-dim">of 16,630</span></span>
        <span className="af-chip">Public <em>✕</em></span>
        <span className="af-chip">1970s <em>✕</em></span>
        <span className="af-chip">Best per date <em>✕</em></span>
        <span className="af-sort">Sort <b>LB# ↑</b></span>
      </div>
      <div className="af-table">
        <div className="af-head">
          <div className="c-dot"></div>
          <div className="c-lb">LB#</div>
          <div className="c-date">DATE</div>
          <div className="c-loc">LOCATION</div>
          <div className="c-rate">RATING</div>
          <div className="c-desc">DESCRIPTION</div>
          <div className="c-xref">XREF</div>
          <div className="c-own">OWNED</div>
        </div>
        <div className="af-body">
          {ROWS.map((row, i) => row.group ? (
            <div className="af-grouprow" key={i}><span className="af-caret">⌄</span> {row.y} <span className="af-gcount">{row.count}</span></div>
          ) : (
            <div className="af-row" key={i}>
              <div className="c-dot"><span className="af-status-dot" title="Public"></span></div>
              <div className="c-lb mono">{row.lb}</div>
              <div className="c-date mono">{row.date}</div>
              <div className="c-loc">{row.loc}</div>
              <div className="c-rate"><Rating r={row.r} /></div>
              <div className="c-desc"><AfterDesc desc={row.desc} /></div>
              <div className="c-xref mono">{row.xref === "—" ? <span className="af-dash">—</span> : <a className="af-xref-link">{row.xref}</a>}</div>
              <div className="c-own">{row.owned ? <span className="af-check">✓</span> : <span className="af-dash">—</span>}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { BeforeTable, AfterTable });
