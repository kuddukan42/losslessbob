// splash-variants.jsx — three startup/splash directions. Dark, indigo accent.

(() => {
  const { DoubleSquareFrame, DrawFrame, Monogram, Wordmark, Tagline,
          useBoot, ProgressBar, Caret, LBB_w: w } = window;
  const Icon = window.LBB_Icon;
  const M = window.LBB_LAUNCH.meta;

  // Dark stage that fills the artboard. Subtle warm-black + faint accent glow.
  function Stage({ children, onClick, glow = true }) {
    return (
      <div onClick={onClick} style={{
        position: "relative", width: "100%", height: "100%", cursor: "pointer",
        background: "#131110",
        backgroundImage: glow
          ? "radial-gradient(120% 90% at 50% 42%, color-mix(in oklab, var(--lbb-accent-mid) 16%, transparent), transparent 55%)"
          : "none",
        display: "flex", alignItems: "center", justifyContent: "center",
        overflow: "hidden", fontFamily: "Inter, system-ui, sans-serif",
      }}>
        {/* film-grain hairline frame inset from the window edge */}
        <div style={{ position: "absolute", inset: 16, border: `1px solid ${w(0.05)}`, borderRadius: 4, pointerEvents: "none" }} />
        {children}
      </div>
    );
  }

  const Replay = () => (
    <div style={{ position: "absolute", bottom: 22, left: "50%", transform: "translateX(-50%)",
      fontSize: 10.5, color: w(0.22), letterSpacing: 0.3, display: "flex", alignItems: "center", gap: 6 }}>
      <Icon name="refresh" size={11} /> click to replay
    </div>
  );

  const VBuild = ({ side }) => (
    <div style={{ position: "absolute", bottom: 26, [side]: 30, fontFamily: "var(--lbb-mono)",
      fontSize: 10.5, color: w(0.3), letterSpacing: 0.4 }}>
      {side === "left" ? `v${M.version} · ${M.channel}` : `build ${M.build}`}
    </div>
  );

  // ── A · Launch card ────────────────────────────────────────────────────
  function SplashClassic() {
    const boot = useBoot();
    return (
      <Stage onClick={boot.replay}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
          <DoubleSquareFrame inset={8} radius={3} style={{ width: 440, height: 232 }}
            pad={0}>
            <div style={{ height: 232 - 0, display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", gap: 18, padding: "0 40px" }}>
              <Monogram size={52} radius={13} />
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
                <Wordmark size={38} />
                <Tagline size={11}>{M.tagline}</Tagline>
              </div>
            </div>
          </DoubleSquareFrame>

          {/* progress under the frame */}
          <div style={{ width: 440, marginTop: 30 }}>
            <ProgressBar pct={boot.pct} indeterminate={boot.overrun} />
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
              <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 11.5, color: w(0.55), letterSpacing: 0.2 }}>
                {boot.done
                  ? <span style={{ color: "var(--lbb-ok-fg)" }}>Ready · {M.checksums} checksums</span>
                  : <>{boot.label}<span style={{ color: w(0.32) }}> · {boot.detail}</span></>}
              </span>
              <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 11.5, color: w(0.4),
                fontVariantNumeric: "tabular-nums" }}>{boot.overrun ? "…" : `${boot.pct}%`}</span>
            </div>
          </div>
        </div>
        <VBuild side="left" />
        <VBuild side="right" />
        {boot.done && <Replay />}
      </Stage>
    );
  }

  // ── B · Boot log (terminal) ────────────────────────────────────────────
  function SplashTerminal() {
    const boot = useBoot();
    const steps = window.LBB_LAUNCH.boot;
    return (
      <Stage onClick={boot.replay} glow={false}>
        <DoubleSquareFrame inset={8} radius={3} style={{ width: 564, height: 320 }}>
          <div style={{ height: 320, display: "flex", flexDirection: "column", padding: "26px 30px" }}>
            {/* header row */}
            <div style={{ display: "flex", alignItems: "center", gap: 13, paddingBottom: 16,
              borderBottom: `1px solid ${w(0.1)}` }}>
              <Monogram size={38} radius={10} />
              <div>
                <Wordmark size={22} />
                <div style={{ marginTop: 6, fontFamily: "var(--lbb-mono)", fontSize: 9.5,
                  letterSpacing: 2, textTransform: "uppercase", color: w(0.4), whiteSpace: "nowrap" }}>
                  {M.tagline} · v{M.version}
                </div>
              </div>
              <div style={{ marginLeft: "auto", position: "relative", width: 46, height: 46, overflow: "hidden",
                borderRadius: 6, border: `1px solid ${w(0.08)}` }}>
                {/* mini scan animation */}
                <div style={{ position: "absolute", left: 0, right: 0, height: 6,
                  background: "linear-gradient(var(--lbb-accent-mid), transparent)",
                  animation: "lbbScan 1.4s linear infinite", opacity: boot.done ? 0 : 0.8 }} />
                <div style={{ position: "absolute", inset: 0, backgroundImage:
                  `repeating-linear-gradient(0deg, transparent 0 5px, ${w(0.05)} 5px 6px)` }} />
              </div>
            </div>

            {/* log */}
            <div style={{ flex: 1, paddingTop: 16, fontFamily: "var(--lbb-mono)", fontSize: 11.5,
              lineHeight: 1.85, color: w(0.7) }}>
              {steps.map((s, i) => {
                const reached = i < boot.idx || boot.done;
                const active = i === boot.idx && !boot.done;
                if (i > boot.idx && !boot.done) return null;
                return (
                  <div key={i} style={{ display: "grid", gridTemplateColumns: "14px 188px 1fr",
                    alignItems: "center", columnGap: 10, whiteSpace: "nowrap",
                    opacity: reached || active ? 1 : 0 }}>
                    <span style={{ color: reached ? "var(--lbb-ok-fg)" : "var(--lbb-accent-mid)" }}>
                      {reached ? "✓" : "›"}
                    </span>
                    <span style={{ color: w(0.78), overflow: "hidden", textOverflow: "ellipsis" }}>{s[0].toLowerCase()}</span>
                    <span style={{ color: w(0.32), overflow: "hidden", textOverflow: "ellipsis" }}>
                      {s[1]}{active && <Caret />}
                    </span>
                  </div>
                );
              })}
              {boot.done && (
                <div style={{ display: "grid", gridTemplateColumns: "14px 1fr", columnGap: 10,
                  alignItems: "center", marginTop: 2, whiteSpace: "nowrap", animation: "lbbUp 300ms ease" }}>
                  <span style={{ color: "var(--lbb-accent-mid)" }}>›</span>
                  <span style={{ color: "var(--lbb-accent-mid)", fontWeight: 600 }}>ready<Caret /></span>
                </div>
              )}
            </div>

            <ProgressBar pct={boot.pct} height={2} />
          </div>
        </DoubleSquareFrame>
        {boot.done && <Replay />}
      </Stage>
    );
  }

  // ── C · Draw-in (minimal) ──────────────────────────────────────────────
  function SplashDraw() {
    const boot = useBoot();
    return (
      <Stage onClick={boot.replay}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
          <DrawFrame width={420} height={210} inset={8} radius={3} dur={1400} run={boot.run}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14,
              animation: "lbbUp 700ms ease 0.7s both" }}>
              <Wordmark size={40} />
              <Tagline size={11}>{M.tagline}</Tagline>
            </div>
          </DrawFrame>

          <div style={{ marginTop: 34, display: "flex", flexDirection: "column", alignItems: "center", gap: 12,
            animation: "lbbUp 600ms ease 1s both" }}>
            <div style={{ width: 150 }}><ProgressBar pct={boot.pct} height={2} /></div>
            <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 10.5, letterSpacing: 1.5,
              textTransform: "uppercase", color: boot.done ? "var(--lbb-ok-fg)" : w(0.42) }}>
              {boot.done ? "Ready" : `Loading · ${boot.pct}%`}
            </span>
          </div>
        </div>
        <VBuild side="left" />
        <VBuild side="right" />
        {boot.done && <Replay />}
      </Stage>
    );
  }

  Object.assign(window, { SplashClassic, SplashTerminal, SplashDraw });
})();
