/**
 * App.jsx
 *
 * Root component — owns the screen-level state machine.
 *
 * Flow (strictly linear, no routing needed):
 *   'splash' ──[Launch]──────────────▶ 'settings'
 *   'settings' ──[Save & Continue]───▶ 'run'
 *   'run' ──[pipeline-done]───────────▶ 'done'
 *   'done' ──[Run Again]──────────────▶ 'run'   (same settings)
 *   'done' ──[Custom Range]───────────▶ 'settings'
 *   'run'  ──[⚙ Settings (no run)]───▶ 'settings'
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

  // Settings → Run: store the validated settings dict and enter Run screen
  function handleProceed(settingsDict) {
    setSettings(settingsDict);
    setDonePayload(null);
    setScreen('run');
  }

  // Run → Done: store the done payload (claims_seen, output_file)
  function handleDone(payload) {
    setDonePayload(payload);
    setScreen('done');
  }

  // Done → Run: run again with exactly the same settings
  function handleRunAgain() {
    setDonePayload(null);
    setScreen('run');
  }

  // Done → Settings: back to settings so user can change row range
  function handleCustomRange() {
    setScreen('settings');
  }

  // Run → Settings: only allowed when no run is in progress
  // (the Run screen disables the button while running; this is the handler)
  function handleGoSettings() {
    setScreen('settings');
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {screen === 'splash' && (
        <Splash onLaunch={() => setScreen('settings')} />
      )}
      {screen === 'settings' && (
        <Settings onProceed={handleProceed} />
      )}
      {screen === 'run' && (
        <Run
          settings={settings}
          onDone={handleDone}
          onSettings={handleGoSettings}
        />
      )}
      {screen === 'done' && (
        <Done
          donePayload={donePayload}
          settings={settings}
          onRunAgain={handleRunAgain}
          onCustomRange={handleCustomRange}
        />
      )}
    </div>
  );
}
