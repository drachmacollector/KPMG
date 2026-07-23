/**
 * Run.jsx
 *
 * Live pipeline execution dashboard.
 *
 * On mount: starts the pipeline via bridge.call('start_pipeline', settings)
 * and registers listeners for all push events from Python:
 *   pipeline-log            → append to log pane
 *   pipeline-progress       → update progress bar + counter
 *   pipeline-done           → transition to Done screen
 *   pipeline-error          → show error banner, unlock buttons
 *   pipeline-awaiting-login → show login confirmation banner
 *
 * Login confirmation banner:
 *   Shown when 'pipeline-awaiting-login' fires.  The pipeline's input()
 *   prompt has appeared, meaning a browser window is open waiting for the
 *   user to log into the MAHABOCW portal.  The user clicks "Continue" to
 *   send a newline to the subprocess stdin via bridge.call('confirm_login').
 *
 * Controls: Pause / Resume / Cancel via the corresponding Api methods.
 * Elapsed timer: maintained in JS with setInterval.
 */
import { useEffect, useRef, useState } from 'react';
import { call, on } from '../lib/bridge';

function fmtTime(secs) {
  const h = String(Math.floor(secs / 3600)).padStart(2, '0');
  const m = String(Math.floor((secs % 3600) / 60)).padStart(2, '0');
  const s = String(secs % 60).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

export default function Run({ settings, onDone, onSettings }) {
  const [status,       setStatus]      = useState('starting'); // starting|running|paused|done|error
  const [logLines,     setLogLines]    = useState([]);
  const [progress,     setProgress]    = useState({ count: 0, total: null });
  const [elapsed,      setElapsed]     = useState(0);
  const [errorMsg,     setErrorMsg]    = useState('');
  const [awaitLogin,   setAwaitLogin]  = useState(false);
  const [donePayload,  setDonePayload] = useState(null);
  const [totalRows,    setTotalRows]   = useState(null);

  const logRef        = useRef(null);
  const elapsedRef    = useRef(null);
  const atBottomRef   = useRef(true);

  // ------------------------------------------------------------------
  // Start pipeline + register push-event listeners on mount
  // ------------------------------------------------------------------
  useEffect(() => {
    let started = false;

    // Register listeners first so no events are missed
    const cleanups = [
      on('pipeline-log', ({ line }) => {
        setLogLines(prev => {
          const next = [...prev, line];
          // cap at 10,000 lines to mirror QPlainTextEdit.setMaximumBlockCount
          return next.length > 10_000 ? next.slice(next.length - 10_000) : next;
        });
      }),
      on('pipeline-progress', ({ count, total }) => {
        setProgress({ count, total });
      }),
      on('pipeline-done', (payload) => {
        setStatus('done');
        setDonePayload(payload);
        stopTimer();
        onDone(payload);
      }),
      on('pipeline-error', ({ message }) => {
        setStatus('error');
        setErrorMsg(message);
        stopTimer();
      }),
      on('pipeline-awaiting-login', () => {
        setAwaitLogin(true);
      }),
    ];

    // Start pipeline
    call('start_pipeline', settings)
      .then(({ total_rows }) => {
        started = true;
        setTotalRows(total_rows ?? null);
        setStatus('running');
        startTimer();
      })
      .catch(err => {
        setStatus('error');
        setErrorMsg(String(err));
      });

    return () => {
      cleanups.forEach(fn => fn());
      stopTimer();
    };
  }, []); // intentionally empty — run only once on mount

  // ------------------------------------------------------------------
  // Elapsed timer
  // ------------------------------------------------------------------
  function startTimer() {
    if (elapsedRef.current) return;
    elapsedRef.current = setInterval(() => setElapsed(s => s + 1), 1000);
  }
  function stopTimer() {
    if (elapsedRef.current) {
      clearInterval(elapsedRef.current);
      elapsedRef.current = null;
    }
  }

  // ------------------------------------------------------------------
  // Auto-scroll log pane (only when already at bottom)
  // ------------------------------------------------------------------
  useEffect(() => {
    const el = logRef.current;
    if (!el) return;
    if (atBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [logLines]);

  function handleLogScroll() {
    const el = logRef.current;
    if (!el) return;
    atBottomRef.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 8;
  }

  // ------------------------------------------------------------------
  // Controls
  // ------------------------------------------------------------------
  function handlePause() {
    if (status === 'paused') {
      call('resume_pipeline');
      setStatus('running');
      startTimer();
    } else {
      call('pause_pipeline');
      setStatus('paused');
      stopTimer();
    }
  }

  function handleCancel() {
    if (!window.confirm('Cancel the run?\n\nProgress already saved will not be lost — the next run will resume from where this one stopped.')) return;
    call('cancel_pipeline');
  }

  function handleConfirmLogin() {
    call('confirm_login');
    setAwaitLogin(false);
    setLogLines(prev => [...prev, '[GUI] Login confirmed — continuing…']);
  }

  function handleOpenLog() {
    call('open_log', settings?.pipeline_dir ?? '');
  }

  // ------------------------------------------------------------------
  // Derived progress metrics
  // ------------------------------------------------------------------
  const effectiveTotal = totalRows ?? progress.total;
  const pct = effectiveTotal && progress.count
    ? Math.min(100, Math.round(progress.count / effectiveTotal * 100))
    : null;

  const isRunning = status === 'running' || status === 'paused';

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  return (
    <div className="flex flex-col h-full bg-transparent">
      {/* Accent top bar */}
      <div className="accent-bar" />

      {/* Header */}
      <div className="screen-header">
        <div className="accent-stripe" />
        <div className="flex-1">
          <div style={{ fontSize: 20, fontWeight: 700, color: '#fff', letterSpacing: '-0.4px' }}>
            Run
          </div>
          <div className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
            {status === 'starting' && 'Starting pipeline…'}
            {status === 'running'  && 'Running…'}
            {status === 'paused'   && 'Paused'}
            {status === 'done'     && 'Completed successfully'}
            {status === 'error'    && 'Run ended with an error — see above'}
          </div>
        </div>

        {/* Elapsed */}
        <span
          className="text-xs font-semibold mr-4 font-mono"
          style={{ color: 'var(--text-muted)' }}
        >
          {fmtTime(elapsed)}
        </span>

        {/* Settings nav */}
        <button
          className="btn-ghost text-sm px-3"
          onClick={onSettings}
          disabled={isRunning}
          title="Return to configuration (only when no run is active)"
        >
          ⚙&nbsp; Settings
        </button>
      </div>

      {/* Error banner */}
      {status === 'error' && errorMsg && (
        <div
          className="flex items-start gap-3 px-6 py-4 text-sm shrink-0"
          style={{
            background: 'var(--error-subtle)',
            borderBottom: '1px solid var(--error-border)',
            animation: 'fadeIn 0.3s both',
          }}
        >
          <span style={{ fontSize: 16 }}>❌</span>
          <span style={{ color: 'var(--error)', fontWeight: 500 }}>{errorMsg}</span>
        </div>
      )}

      {/* Login confirmation banner — shown when pipeline awaits human login */}
      {awaitLogin && (
        <div
          className="flex items-center gap-4 px-6 py-4 shrink-0"
          style={{
            background: 'var(--accent-subtle)',
            borderBottom: '1px solid var(--border-accent)',
            animation: 'fadeIn 0.3s both',
          }}
        >
          <span style={{ fontSize: 22 }}>🔑</span>
          <div className="flex-1 text-sm" style={{ color: 'var(--text-primary)' }}>
            <strong>Action required:</strong> A browser window has opened.
            Log into the MAHABOCW portal, navigate to Claims, set up the
            filter — then click <strong>Continue</strong>.
          </div>
          <button
            id="btn-confirm-login"
            className="btn-primary px-5 shrink-0"
            style={{ height: 42, animation: 'none', boxShadow: '0 0 18px var(--accent-glow)' }}
            onClick={handleConfirmLogin}
          >
            ✓&nbsp; I've logged in — Continue
          </button>
        </div>
      )}

      {/* Log pane */}
      <div
        className="flex-1 flex flex-col px-6 py-4 overflow-hidden bg-transparent"
        style={{ minHeight: 0 }}
      >
        <div className="section-label mb-2">Live Output</div>
        <div
          ref={logRef}
          onScroll={handleLogScroll}
          className="flex-1 rounded-xl p-4 text-xs leading-relaxed font-mono overflow-y-auto scroll-pane"
          style={{
            background: 'var(--bg-deep)',
            border: '1px solid var(--border)',
            color: '#c8d6e8',
            fontFamily: "'Cascadia Code', 'Cascadia Mono', 'Consolas', monospace",
            minHeight: 0,
          }}
        >
          {logLines.length === 0 ? (
            <span style={{ color: 'var(--text-muted)' }}>
              {status === 'starting' ? 'Launching pipeline…' : 'Waiting for output…'}
            </span>
          ) : (
            logLines.map((line, i) => (
              <div key={i} className="whitespace-pre-wrap break-all">{line}</div>
            ))
          )}
        </div>
      </div>

      {/* Progress bar + stat */}
      <div
        className="px-6 py-4 flex items-center gap-6 shrink-0 bg-transparent"
        style={{
          borderTop: '1px solid var(--border)',
        }}
      >
        {/* Left: stat counter */}
        <div className="flex-shrink-0">
          <div
            style={{
              fontSize: 26,
              fontWeight: 800,
              color: '#fff',
              letterSpacing: '-1px',
              lineHeight: 1,
            }}
          >
            {progress.count > 0 ? progress.count.toLocaleString() : '—'}
          </div>
          <div className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
            {effectiveTotal
              ? `of ${effectiveTotal.toLocaleString()} claims processed`
              : 'claims processed'}
          </div>
        </div>

        {/* Right: progress bar */}
        <div className="flex-1">
          <div className="progress-track">
            {pct !== null ? (
              <div className="progress-fill" style={{ width: `${pct}%` }} />
            ) : progress.count > 0 ? (
              /* Indeterminate shuttle when total is unknown */
              <div
                style={{
                  height: '100%',
                  width: '30%',
                  borderRadius: 5,
                  background: 'linear-gradient(90deg, var(--accent), var(--accent-hover))',
                  animation: 'shuttleBar 1.5s linear infinite',
                  position: 'relative',
                }}
              />
            ) : null}
          </div>
          {pct !== null && (
            <div className="mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>
              {pct}% complete
            </div>
          )}
        </div>
      </div>

      {/* Button bar */}
      <div
        className="flex items-center gap-3 px-6 py-4 shrink-0 bg-transparent"
        style={{
          borderTop: '1px solid var(--border)',
          height: 72,
        }}
      >
        <button
          id="btn-pause-resume"
          className="btn px-5"
          style={{ height: 40, minWidth: 120 }}
          onClick={handlePause}
          disabled={!isRunning}
        >
          {status === 'paused' ? '▶  Resume' : '⏸  Pause'}
        </button>

        <button
          id="btn-cancel"
          className="btn-danger px-5"
          style={{ height: 40, minWidth: 110 }}
          onClick={handleCancel}
          disabled={!isRunning}
        >
          ■  Cancel
        </button>

        <span style={{ flexGrow: 1 }} />
        
        <button
          className="btn-ghost px-5"
          style={{ height: 40 }}
          onClick={handleOpenLog}
          title="Open the active log file"
        >
          📋&nbsp; Open Log File
        </button>
      </div>
    </div>
  );
}
