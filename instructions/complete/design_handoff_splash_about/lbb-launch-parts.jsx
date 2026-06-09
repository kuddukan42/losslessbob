// lbb-launch-parts.jsx
// Shared building blocks for splash + about: the double-square frame,
// the LB monogram, the wordmark, and the ~2s boot sequence hook.

(() => {
  const Icon = window.LBB_Icon;

  // Warm white at a given alpha (matches dark-mode fg #f1ecdf).
  const w = (a) => `rgba(241,236,223,${a})`;

  // ── DoubleSquareFrame ────────────────────────────────────────────────
  // Motif 0: a 1.5px outer square + a hairline inner square inset a few px.
  // `inset` controls the gap between the two lines. Static (CSS borders).
  function DoubleSquareFrame({ children, inset = 7, radius = 2, outer = 0.85, inner = 0.28, pad, style }) {
    return (
      <div style={{ position: "relative", ...style }}>
        <div style={{
          position: "absolute", inset: 0,
          border: `1.5px solid ${w(outer)}`, borderRadius: radius,
        }} />
        <div style={{
          position: "absolute", inset: inset,
          border: `1px solid ${w(inner)}`, borderRadius: Math.max(0, radius - 1),
        }} />
        <div style={{ position: "relative", padding: pad }}>{children}</div>
      </div>
    );
  }

  // ── DrawFrame ────────────────────────────────────────────────────────
  // SVG version whose outer stroke draws itself over `dur` ms (used by the
  // draw-in splash). Inner hairline fades in after.
  function DrawFrame({ width, height, inset = 7, radius = 2, dur = 1500, run = 0, children }) {
    const per = 2 * (width + height) - 8 * radius; // ~perimeter
    return (
      <div style={{ position: "relative", width, height }}>
        <svg width={width} height={height} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
          <rect x={0.75} y={0.75} width={width - 1.5} height={height - 1.5} rx={radius}
            fill="none" stroke={w(0.88)} strokeWidth={1.5}
            strokeDasharray={per} strokeDashoffset={per}
            style={{ animation: `lbbDraw ${dur}ms cubic-bezier(.6,.02,.2,1) ${run ? "0.05s" : "0s"} forwards` }} key={run} />
          <rect x={inset} y={inset} width={width - inset * 2} height={height - inset * 2} rx={Math.max(0, radius - 1)}
            fill="none" stroke={w(0.26)} strokeWidth={1}
            style={{ opacity: 0, animation: `lbbFade 600ms ease ${dur * 0.7}ms forwards` }} key={"i" + run} />
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
          {children}
        </div>
      </div>
    );
  }

  // ── Monogram ─────────────────────────────────────────────────────────
  // The LB mark in the accent square (matches the sidebar brand).
  function Monogram({ size = 44, radius = 10, font }) {
    return (
      <div style={{
        width: size, height: size, borderRadius: radius,
        background: "var(--lbb-accent-mid)", color: "var(--lbb-accent-onMid)",
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        fontWeight: 800, fontSize: font || size * 0.42, letterSpacing: -0.02,
        boxShadow: "0 1px 0 rgba(255,255,255,0.18) inset, 0 2px 8px rgba(0,0,0,0.35)",
        flex: "0 0 auto",
      }}>LB</div>
    );
  }

  // ── Wordmark ─────────────────────────────────────────────────────────
  function Wordmark({ size = 34, color, lossWeight = 700 }) {
    return (
      <span style={{
        fontSize: size, fontWeight: 700, letterSpacing: -size * 0.022,
        color: color || w(0.96), lineHeight: 1, whiteSpace: "nowrap",
      }}>
        <span style={{ fontWeight: 500, color: color || w(0.62) }}>Lossless</span><span>Bob</span>
      </span>
    );
  }

  // ── Tagline ──────────────────────────────────────────────────────────
  function Tagline({ children, size = 11 }) {
    return (
      <span style={{
        fontFamily: "var(--lbb-mono)", fontSize: size, letterSpacing: size * 0.28,
        textTransform: "uppercase", color: w(0.4), whiteSpace: "nowrap",
      }}>{children}</span>
    );
  }

  // ── useBoot ──────────────────────────────────────────────────────────
  // Drives the splash off the REAL startup phases in window.LBB_LAUNCH.boot,
  // each tagged with the ms offset at which it actually begins (atMs). The bar
  // tracks elapsed-vs-expected, so a normal ~2.4s boot finishes on time and a
  // slow boot honestly *overruns* (caller switches the bar to indeterminate)
  // instead of lying its way to 100%.
  //
  // Two drivers:
  //   useBoot()                  → mock: replays the phases at true speed
  //   useBoot({ dur })           → mock at a custom duration
  //   useBoot({ feed })          → production: feed = { elapsedMs, done }
  //                                 pushed from the Electron main process.
  //
  // Returns { pct, idx, label, detail, done, overrun, replay, run, elapsed }.
  function useBoot(arg = {}) {
    const data = window.LBB_LAUNCH;
    const steps = data.boot;
    const total = data.bootReadyMs || 2400;
    const opts = typeof arg === "number" ? { dur: arg } : (arg || {});
    const feed = opts.feed || null;            // real progress, or null for mock
    const dur = opts.dur || total;             // mock duration; default = real time

    const [t, setT] = React.useState(feed ? 0 : 0);
    const [run, setRun] = React.useState(0);
    const startRef = React.useRef(null);

    // Timed driver — only runs for the mock (no real feed supplied).
    React.useEffect(() => {
      if (feed) return;
      let raf;
      startRef.current = performance.now();
      const tick = (now) => {
        const e = Math.min(1, (now - startRef.current) / dur);
        setT(e);
        if (e < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
      return () => cancelAnimationFrame(raf);
    }, [run, feed]);

    // Resolve elapsed ms + done from whichever driver is active.
    const elapsed = feed ? (feed.elapsedMs || 0) : t * dur;
    const done = feed ? !!feed.done : t >= 1;

    // Current phase = last one whose atMs has been reached.
    let idx = 0;
    for (let i = 0; i < steps.length; i++) if (elapsed >= (steps[i][2] || 0)) idx = i;
    if (done) idx = steps.length - 1;
    const step = steps[idx] || steps[0];

    // Bar fills against the EXPECTED boot time. If we blow past it without a
    // done signal, the boot is slow — flag overrun and hold the bar short of
    // full so the UI can show an indeterminate state rather than a fake 100%.
    const overrun = !done && elapsed > total;
    const pct = done ? 100 : Math.min(96, Math.round((elapsed / total) * 100));

    const replay = () => { startRef.current = performance.now(); setT(0); setRun((r) => r + 1); };
    return { pct, idx, label: step[0], detail: step[1], done, overrun, replay, run, elapsed };
  }

  // ── ProgressBar ──────────────────────────────────────────────────────
  function ProgressBar({ pct, height = 3, track = w(0.1), indeterminate = false }) {
    return (
      <div style={{ height, background: track, borderRadius: 999, overflow: "hidden", width: "100%" }}>
        {indeterminate ? (
          <div style={{
            height: "100%", width: "40%", borderRadius: 999,
            background: "var(--lbb-accent-mid)",
            boxShadow: "0 0 10px var(--lbb-accent-mid)",
            animation: "lbbIndet 1.15s cubic-bezier(.5,0,.5,1) infinite",
          }} />
        ) : (
          <div style={{
            height: "100%", width: `${pct}%`,
            background: "var(--lbb-accent-mid)",
            boxShadow: "0 0 10px var(--lbb-accent-mid)",
            transition: "width 120ms linear",
          }} />
        )}
      </div>
    );
  }

  // Blinking caret for terminal-style splash.
  function Caret() {
    return <span style={{ display: "inline-block", width: 7, height: 13, marginLeft: 2,
      background: "var(--lbb-accent-mid)", verticalAlign: "-2px",
      animation: "lbbBlink 1s step-end infinite" }} />;
  }

  // One-time keyframes.
  if (!document.getElementById("lbb-launch-kf")) {
    const s = document.createElement("style");
    s.id = "lbb-launch-kf";
    s.textContent = `
      @keyframes lbbDraw { to { stroke-dashoffset: 0; } }
      @keyframes lbbFade { to { opacity: 1; } }
      @keyframes lbbBlink { 50% { opacity: 0; } }
      @keyframes lbbScan { 0% { transform: translateY(-100%); } 100% { transform: translateY(900%); } }
      @keyframes lbbUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
      @keyframes lbbIndet { 0% { transform: translateX(-110%); } 100% { transform: translateX(290%); } }
    `;
    document.head.appendChild(s);
  }

  Object.assign(window, {
    LBB_w: w,
    DoubleSquareFrame, DrawFrame, Monogram, Wordmark, Tagline,
    useBoot, ProgressBar, Caret,
  });
})();
