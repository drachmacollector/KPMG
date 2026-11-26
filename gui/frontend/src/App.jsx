/**
 * App.jsx
 *
 * Root component — owns the screen-level state machine.
 *
 *   'splash'   ──[Launch]────────────▶ 'settings'
 *   'settings' ──[Save & Continue]───▶ 'run'
 *   'run'      ──[pipeline-done]─────▶ 'done'
 *   'done'     ──[Run Again]─────────▶ 'run'   (same settings)
 *   'done'     ──[Change settings]───▶ 'settings'
 *   'run'      ──[Settings]──────────▶ 'settings'  (only when no run is active)
 *
 * runId increases for every launch so the Run screen starts exactly one
 * pipeline per launch, even under React StrictMode's double-mount in dev.
 */
import { useState } from 'react';
import Splash   from './components/Splash';
import Settings from './components/Settings';
import Run      from './components/Run';
import Done     from './components/Done';

export default function App() {
  const [screen,      setScreen]      = useState('splash');
  const [settings,    setSettings]    = useState(null);
  const [donePayload, setDonePayload] = useState(null);
  const [runId,       setRunId]       = useState(0);

  function startRun(settingsDict) {
    if (settingsDict) setSettings(settingsDict);
    setDonePayload(null);
    setRunId(id => id + 1);
    setScreen('run');
  }

  function handleDone(payload) {
    setDonePayload(payload);
    setScreen('done');
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {screen === 'splash' && <Splash onLaunch={() => setScreen('settings')} />}
      {screen === 'settings' && <Settings onProceed={startRun} />}
      {screen === 'run' && (
        <Run
          key={runId}
          runId={runId}
          settings={settings}
          onDone={handleDone}
          onSettings={() => setScreen('settings')}
        />
      )}
      {screen === 'done' && (
        <Done
          donePayload={donePayload}
          settings={settings}
          onRunAgain={() => startRun()}
          onSettings={() => setScreen('settings')}
        />
      )}
    </div>
  );
}
