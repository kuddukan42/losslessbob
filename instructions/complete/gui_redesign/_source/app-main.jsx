// app-main.jsx — root App component that ties shell + screens + tweaks together.

(() => {
  const { LBB_AppShell: AppShell, LBB_TOKENS } = window;
  const { TweaksPanel, useTweaks, TweakSection, TweakRadio, TweakSelect, TweakToggle, TweakColor } = window;
  const Icon = window.LBB_Icon;

  // Each screen contributes its breadcrumb + body
  const SCREENS = [
    { id: "home",         crumbs: ["LosslessBob", "Home"],                   render: (p) => <window.LBB_ScreenHome {...p} /> },
    { id: "pipeline",     crumbs: ["LosslessBob", "Ingest", "Pipeline"],     render: (p) => <window.LBB_ScreenPipeline {...p} /> },
    { id: "verify",       crumbs: ["LosslessBob", "Ingest", "Verify"],       render: (p) => <window.LBB_ScreenVerify {...p} /> },
    { id: "lookup",       crumbs: ["LosslessBob", "Ingest", "Lookup"],       render: (p) => <window.LBB_ScreenLookup {...p} /> },
    { id: "rename",       crumbs: ["LosslessBob", "Ingest", "Rename"],       render: (p) => <window.LBB_ScreenRename {...p} /> },
    { id: "lbdir",        crumbs: ["LosslessBob", "Ingest", "LBDIR"],        render: (p) => <window.LBB_ScreenLBDIR {...p} /> },
    { id: "collection",   crumbs: ["LosslessBob", "Library", "My Collection"], render: (p) => <window.LBB_ScreenCollection {...p} /> },
    { id: "search",       crumbs: ["LosslessBob", "Library", "Search"],      render: (p) => <window.LBB_ScreenSearch {...p} /> },
    { id: "bootlegs",     crumbs: ["LosslessBob", "Library", "Bootlegs"],    render: (p) => <window.LBB_ScreenBootlegs {...p} /> },
    { id: "attachments",  crumbs: ["LosslessBob", "Assets", "Attachments"],  render: (p) => <window.LBB_ScreenAttachments {...p} /> },
    { id: "spectrograms", crumbs: ["LosslessBob", "Assets", "Spectrograms"], render: (p) => <window.LBB_ScreenSpectrograms {...p} /> },
    { id: "map",          crumbs: ["LosslessBob", "Assets", "Map"],          render: (p) => <window.LBB_ScreenMap {...p} /> },
    { id: "dbeditor",     crumbs: ["LosslessBob", "Curator", "DB Editor"],   render: (p) => <window.LBB_ScreenDBEditor {...p} /> },
    { id: "scraper",      crumbs: ["LosslessBob", "Curator", "Scraper"],     render: (p) => <window.LBB_ScreenScraper {...p} /> },
    { id: "setup",        crumbs: ["LosslessBob", "Settings", "Setup"],      render: (p) => <window.LBB_ScreenSetup {...p} /> },
    { id: "themes",       crumbs: ["LosslessBob", "Settings", "Themes"],     render: (p) => <window.LBB_ScreenThemes {...p} /> },
  ];

  const SCREEN_MAP = Object.fromEntries(SCREENS.map(s => [s.id, s]));

  function App() {
    // Tweaks (mirrored into LBB tokens)
    const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
      "mode":        "light",
      "accent":      "indigo",
      "density":     "default",
      "curatorMode": false,
      "screen":      "pipeline"
    }/*EDITMODE-END*/;

    const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

    // Push tweak values into LBB tokens whenever they change
    React.useEffect(() => {
      LBB_TOKENS.applyTheme({
        mode:    t.mode,
        accent:  t.accent,
        density: t.density,
      });
    }, [t.mode, t.accent, t.density]);

    const setNav = (id) => setTweak("screen", id);

    // If user toggles curator off while on a curator screen, bounce home
    React.useEffect(() => {
      if (!t.curatorMode && (t.screen === "dbeditor" || t.screen === "scraper")) {
        setTweak("screen", "home");
      }
    }, [t.curatorMode]);

    const screen = SCREEN_MAP[t.screen] || SCREEN_MAP.home;

    // Tag the active screen for editor / a11y context
    return (
      <AppShell
        active={t.screen}
        onNav={setNav}
        curatorMode={t.curatorMode}
        crumbs={screen.crumbs}
      >
        <div data-screen-label={`${screen.id} · ${screen.crumbs.slice(-1)[0]}`} style={{ height: "100%" }}>
          {screen.render({
            onNav: setNav,
            curatorMode: t.curatorMode,
            onSetCurator: (v) => setTweak("curatorMode", v),
            tweaks: t,
            setTweak,
          })}
        </div>

        {/* Floating tweaks panel — invisible until host activates */}
        <TweaksPanel title="Tweaks">
          <TweakSection label="Theme" />
          <TweakRadio label="Mode" value={t.mode}
            options={["light", "dark"]}
            onChange={(v) => setTweak("mode", v)} />

          <TweakSelect label="Accent" value={t.accent}
            options={["indigo", "plum", "rust", "forest", "teal", "amber", "gray", "crimson"]}
            onChange={(v) => setTweak("accent", v)} />

          <TweakRadio label="Density" value={t.density}
            options={["compact", "default", "comfortable"]}
            onChange={(v) => setTweak("density", v)} />

          <TweakSection label="App" />
          <TweakToggle label="Curator mode" value={t.curatorMode}
            onChange={(v) => setTweak("curatorMode", v)} />
          <TweakSelect label="Open screen" value={t.screen}
            options={SCREENS.filter(s => t.curatorMode || (s.id !== "dbeditor" && s.id !== "scraper")).map(s => s.id)}
            onChange={(v) => setTweak("screen", v)} />
        </TweaksPanel>
      </AppShell>
    );
  }

  window.LBB_App = App;
})();
