// m-app.jsx — mounts each screen inside an iOS frame on the design canvas.

(() => {
  const { LBM_ScreenLibrary, LBM_ScreenDetail, LBM_ScreenSearch,
          LBM_ScreenQueue, LBM_ScreenMap } = window;

  // A single interactive device: holds its own nav state across the tabs +
  // the detail screen, so reviewers can actually tap around each frame.
  function Device({ start = "library" }) {
    const [screen, setScreen] = React.useState(start);
    const onNav = (id) => setScreen(id);
    const onOpen = () => setScreen("detail");
    const onBack = () => setScreen("library");

    let content;
    if (screen === "library") content = <LBM_ScreenLibrary onNav={onNav} onOpen={onOpen} />;
    else if (screen === "detail") content = <LBM_ScreenDetail onBack={onBack} />;
    else if (screen === "search") content = <LBM_ScreenSearch onNav={onNav} onOpen={onOpen} />;
    else if (screen === "queue") content = <LBM_ScreenQueue onNav={onNav} />;
    else if (screen === "map") content = <LBM_ScreenMap onNav={onNav} onOpen={onOpen} />;

    return <IOSDevice>{content}</IOSDevice>;
  }

  const AB = window.DCArtboard, SEC = window.DCSection;

  function App() {
    return (
      <DesignCanvas>
        <SEC id="primary" title="LosslessBob Mobile" subtitle="A companion to the desktop app — browse your collection, monitor the studio-pc pipeline. iOS · tappable.">
          <AB id="library" label="Library — browse collection (home)" width={402} height={874}>
            <Device start="library" />
          </AB>
          <AB id="detail" label="Entry detail — LB metadata" width={402} height={874}>
            <Device start="detail" />
          </AB>
          <AB id="search" label="Search — “do I own this?” · offline" width={402} height={874}>
            <Device start="search" />
          </AB>
          <AB id="queue" label="Queue — monitor pipeline + approvals" width={402} height={874}>
            <Device start="queue" />
          </AB>
          <AB id="map" label="Map — concerts by place / date" width={402} height={874}>
            <Device start="map" />
          </AB>
        </SEC>
      </DesignCanvas>
    );
  }

  ReactDOM.createRoot(document.getElementById("root")).render(<App />);
})();
