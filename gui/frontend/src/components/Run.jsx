/**
 * Run.jsx
 *
 * Live run dashboard.
 *
 * On mount it starts the pipeline once per runId and listens to:
 *   pipeline-log            {lines}      → log pane (batched, capped)
 *   pipeline-event          pipeline events (claim_start / claim_done / ...) → stats
 *   pipeline-progress       {count,total}→ progress bar
 *   pipeline-awaiting-login {}           → login banner
 *   pipeline-done / pipeline-error
 *
 * Stop offers "stop after the current claim" (graceful, via a stop file the
 * pipeline checks between claims) or "force stop" (kills the process tree).
 */
import { useEffect, useRef, useState } from 'react';
import {
  Pause, Play, Square, Settings as SettingsIcon, FileText, Copy, KeyRound, AlertTriangle, Loader2,
} from 'lucide-react';
import { call, on } from '../lib/bridge';
import { Modal, ScreenHeader, Stat } from './ui';
import { fmtDuration } from '../lib/format';

const MAX_LOG_LINES = 5000;

// Run ids that have already started a pipeline (survives StrictMode remounts).
const startedRuns = new Set();

function fmtClock(secs) {
  const h = String(Math.floor(secs / 3600)).padStart(2, '0');
  const m = String(Math.floor((secs % 3600) / 60)).padStart(2, '0');
  const s = String(secs % 60).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

function lineClass(line) {
  if (/\[-\]\s*(ERROR|FATAL)|Traceback|Error:/i.test(line)) return 'log-error';
  if (/\[!\]\s*WARNING|\[FAILED\]/.test(line)) return 'log-warn';
  if (/\[OK\]/.test(line)) return 'log-ok';
  if (line.startsWith('[GUI]')) return 'log-gui';
  return '';
}

const EMPTY_STATS = { VERIFIED: 0, FAILED: 0, NO_DOCS: 0, ERROR: 0, skipped: 0, manual_review: 0, cache_hits: 0 };

export default function Run({ runId, settings, onDone, onSettings }) {
  const [status,     setStatus]     = useState('starting'); // starting|login|running|paused|stopping|error
  const [logLines,   setLogLines]   = useState([]);
  const [progress,   setProgress]   = useState({ count: 0, total: null });
  const [elapsed,    setElapsed]    = useState(0);
  const [errorMsg,   setErrorMsg]   = useState('');
  const [stats,      setStats]      = useState(EMPTY_STATS);
  const [current,    setCurrent]    = useState(null);   // {ack, step}
  const [avgSecs,    setAvgSecs]    = useState(null);
  const [showStop,   setShowStop]   = useState(false);
  const [copied,     setCopied]     = useState(false);

  const logRef      = useRef(null);
  const timerRef    = useRef(null);
  const atBottomRef = useRef(true);
  const pendingRef  = useRef([]);
  const rafRef      = useRef(0);
  const claimT0     = useRef(null);
  const durations   = useRef([]);
  const onDoneRef   = useRef(onDone);
  onDoneRef.current = onDone;

  function appendLines(lines) {
    pendingRef.current.push(...lines);
    if (rafRef.current) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = 0;
      const batch = pendingRef.current;
      pendingRef.current = [];
      setLogLines(prev => {
        const next = prev.concat(batch);
        return next.length > MAX_LOG_LINES ? next.slice(next.length - MAX_LOG_LINES) : next;
      });
    });
  }

  function startTimer() {
    if (!timerRef.current) timerRef.current = setInterval(() => setElapsed(s => s + 1), 1000);
  }
  function stopTimer() {
    clearInterval(timerRef.current);
    timerRef.current = null;
  }

  useEffect(() => {
    const cleanups = [
      on('pipeline-log', ({ lines, line }) => appendLines(lines ?? (line ? [line] : []))),
      on('pipeline-progress', p => setProgress(p)),
      on('pipeline-awaiting-login', () => setStatus('login')),
      on('pipeline-event', ev => {
        switch (ev.event) {
          case 'run_start':
            setStatus(s => (s === 'stopping' ? s : 'running'));
            if (ev.total != null) setProgress(p => ({ ...p, total: ev.total }));
            break;
          case 'claim_start':
            claimT0.current = Date.now();
            setCurrent({ ack: ev.ack, step: 'starting', n: ev.n });
            break;
          case 'claim_step':
            setCurrent(c => (c ? { ...c, step: ev.step } : c));
            break;
          case 'claim_skipped':
            setStats(s => ({ ...s, skipped: s.skipped + 1 }));
            break;
          case 'claim_done': {
            if (claimT0.current) {
              durations.current.push((Date.now() - claimT0.current) / 1000);
              if (durations.current.length > 20) durations.current.shift();
              setAvgSecs(durations.current.reduce((a, b) => a + b, 0) / durations.current.length);
              claimT0.current = null;
            }
            setStats(s => ({
              ...s,
              [ev.status]: (s[ev.status] || 0) + 1,
              manual_review: s.manual_review + (ev.manual_review ? 1 : 0),
              cache_hits: s.cache_hits + (ev.via_cache ? 1 : 0),
            }));
            setCurrent(null);
            break;
          }
          default:
        }
      }),
      on('pipeline-done', payload => {
        stopTimer();
        onDoneRef.current(payload);
      }),
      on('pipeline-error', ({ message }) => {
        setStatus('error');
        setErrorMsg(message);
        setCurrent(null);
        stopTimer();
      }),
    ];

    if (!startedRuns.has(runId)) {
      startedRuns.add(runId);
      call('start_pipeline', settings)
        .then(res => {
          if (!res?.ok) {
            setStatus('error');
            setErrorMsg(res?.error || 'The run could not be started.');
            return;
          }
          if (res.total_rows != null) setProgress(p => ({ ...p, total: res.total_rows }));
          setStatus(s => (s === 'starting' ? 'running' : s));
          startTimer();
        })
        .catch(err => {
          setStatus('error');
          setErrorMsg(String(err));
        });
    } else {
      startTimer();
    }

    return () => {
      cleanups.forEach(fn => fn());
      stopTimer();
      cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    };
    // Runs once per mount (App keys this screen by runId); onDone is read via a ref.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-scroll only when already at the bottom.
  useEffect(() => {
    const el = logRef.current;
    if (el && atBottomRef.current) el.scrollTop = el.scrollHeight;
  }, [logLines]);

  function handleLogScroll() {
    const el = logRef.current;
    if (el) atBottomRef.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 8;
  }

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

  function gracefulStop() {
    setShowStop(false);
    call('stop_pipeline');
    setStatus('stopping');
    startTimer();
    appendLines(['[GUI] Stopping after the current claim…']);
  }

  function forceStop() {
    setShowStop(false);
    call('force_stop_pipeline');
    appendLines(['[GUI] Force-stopping…']);
  }

  function handleConfirmLogin() {
    call('confirm_login');
    setStatus('running');
    appendLines(['[GUI] Login confirmed — continuing…']);
  }

  async function copyLog() {
    const text = logLines.join('\n');
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  const total = progress.total;
  const pct = total ? Math.min(100, Math.round((progress.count / total) * 100)) : null;
  const active = ['starting', 'login', 'running', 'paused', 'stopping'].includes(status);
  const remaining = total ? Math.max(0, total - progress.count) : null;
  // Only estimate once a couple of claims have been timed.
  const eta = avgSecs && remaining && durations.current.length >= 2 ? fmtDuration(avgSecs * remaining) : null;
  const processed = stats.VERIFIED + stats.FAILED + stats.NO_DOCS + stats.ERROR;

  const subtitle = {
    starting: 'Starting — loading the OCR engine can take a minute…',
    login:    'Waiting for you to log in to the portal',
    running:  current ? `Claim ${current.ack} — ${current.step}` : 'Running…',
    paused:   'Paused',
    stopping: current ? `Stopping after claim ${current.ack}…` : 'Stopping…',
    error:    'The run ended with an error',
  }[status];

  return (
    <div className="flex flex-col h-full">
      <ScreenHeader title="Run" subtitle={subtitle}>
        <span className="text-xs font-semibold mr-2 font-mono" style={{ color: 'var(--text-muted)' }} aria-label="Elapsed time">
          {fmtClock(elapsed)}
        </span>
        <button type="button" className="btn-ghost text-sm px-3 gap-2" onClick={onSettings} disabled={active}
                title={active ? 'Available when the run has finished' : 'Back to settings'}>
          <SettingsIcon size={15} aria-hidden /> Settings
        </button>
      </ScreenHeader>

      {status === 'error' && errorMsg && (
        <div role="alert" className="flex items-start gap-3 px-6 py-4 text-sm shrink-0"
             style={{ background: 'var(--error-subtle)', borderBottom: '1px solid var(--error-border)' }}>
          <AlertTriangle size={18} style={{ color: 'var(--error)', flexShrink: 0, marginTop: 1 }} aria-hidden />
          <span className="whitespace-pre-wrap" style={{ color: 'var(--error)', fontWeight: 500 }}>{errorMsg}</span>
        </div>
      )}

      {status === 'login' && (
        <div className="flex items-center gap-5 px-6 py-4 shrink-0"
             style={{ background: 'var(--accent-subtle)', borderBottom: '1px solid var(--border-accent)', animation: 'fadeIn 0.3s both' }}>
          <KeyRound size={26} style={{ color: 'var(--text-accent)', flexShrink: 0 }} aria-hidden />
          <div className="flex-1 text-sm" style={{ color: 'var(--text-primary)' }}>
            <strong>Your turn:</strong> in the browser window that just opened —
            <ol className="list-decimal list-inside mt-1 text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              <li>Log in to the MAHABOCW portal (including the captcha).</li>
              <li>Open the <b>Claims</b> section and bring the <b>Acknowledgement Number</b> column into view.</li>
              <li>Open that column's menu (☰), click the funnel, and leave the filter box open.</li>
            </ol>
          </div>
          <button id="btn-confirm-login" type="button" className="btn-primary px-5 shrink-0" style={{ height: 44 }} onClick={handleConfirmLogin}>
            Done — start processing
          </button>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-6 gap-3 px-6 pt-4 shrink-0">
        <Stat value={total ? `${progress.count}/${total}` : progress.count || '—'} label="Rows done" />
        <Stat value={stats.VERIFIED} label="Verified" color="var(--success)" />
        <Stat value={stats.manual_review} label="Need review" color={stats.manual_review ? 'var(--warning)' : undefined} />
        <Stat value={stats.FAILED + stats.NO_DOCS + stats.ERROR} label="Failed" color={stats.FAILED + stats.NO_DOCS + stats.ERROR ? 'var(--error)' : undefined} />
        <Stat value={stats.skipped} label="Already done" />
        <Stat value={eta ?? '—'} label={eta ? `Left · ~${fmtDuration(avgSecs)} per claim` : 'Time left'} />
      </div>

      {/* Log */}
      <div className="flex-1 flex flex-col px-6 py-4 overflow-hidden" style={{ minHeight: 0 }}>
        <div className="flex items-center mb-2">
          <span className="section-label flex-1">Live output</span>
          <button type="button" className="btn-ghost text-xs gap-1.5" style={{ height: 28 }} onClick={copyLog} disabled={!logLines.length}>
            <Copy size={13} aria-hidden /> {copied ? 'Copied' : 'Copy'}
          </button>
          <button type="button" className="btn-ghost text-xs gap-1.5" style={{ height: 28 }} onClick={() => call('open_log')}>
            <FileText size={13} aria-hidden /> Full log file
          </button>
        </div>
        <div
          ref={logRef}
          onScroll={handleLogScroll}
          className="flex-1 rounded-xl p-4 text-xs leading-relaxed font-mono overflow-y-auto scroll-pane"
          style={{ background: 'var(--bg-deep)', border: '1px solid var(--border)', color: '#c8d6e8', minHeight: 0 }}
          role="log"
          aria-live="off"
        >
          {logLines.length === 0 ? (
            <span className="flex items-center gap-2" style={{ color: 'var(--text-muted)' }}>
              {status === 'starting' && <Loader2 size={13} className="spin" aria-hidden />}
              {status === 'starting' ? 'Launching the pipeline…' : 'Waiting for output…'}
            </span>
          ) : (
            logLines.map((line, i) => (
              <div key={i} className={`whitespace-pre-wrap break-all ${lineClass(line)}`}>{line}</div>
            ))
          )}
        </div>
      </div>

      {/* Progress + controls */}
      <div className="flex items-center gap-4 px-6 py-4 shrink-0" style={{ borderTop: '1px solid var(--border)' }}>
        <button id="btn-pause-resume" type="button" className="btn px-5 gap-2" style={{ minWidth: 120 }} onClick={handlePause}
                disabled={!['running', 'paused'].includes(status)}>
          {status === 'paused' ? <><Play size={15} aria-hidden /> Resume</> : <><Pause size={15} aria-hidden /> Pause</>}
        </button>
        {status === 'stopping' ? (
          <button type="button" className="btn-danger px-5 gap-2" onClick={forceStop}>
            <Square size={14} aria-hidden /> Force stop now
          </button>
        ) : (
          <button id="btn-cancel" type="button" className="btn-danger px-5 gap-2" style={{ minWidth: 110 }} onClick={() => setShowStop(true)} disabled={!active}>
            <Square size={14} aria-hidden /> Stop
          </button>
        )}

        <div className="flex-1 ml-2">
          <div className="progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct ?? undefined}>
            {pct !== null ? (
              <div className="progress-fill" style={{ width: `${pct}%` }} />
            ) : active ? (
              <div style={{ height: '100%', width: '30%', borderRadius: 5, position: 'relative',
                            background: 'linear-gradient(90deg, var(--accent), var(--accent-hover))',
                            animation: 'shuttleBar 1.5s linear infinite' }} />
            ) : null}
          </div>
          <div className="mt-1 text-xs flex" style={{ color: 'var(--text-muted)' }}>
            <span className="flex-1">{pct !== null ? `${pct}% complete` : ' '}</span>
            <span>{processed ? `${processed} processed this run · ${stats.cache_hits} from cache` : ''}</span>
          </div>
        </div>
      </div>

      {showStop && (
        <Modal
          title="Stop the run?"
          onClose={() => setShowStop(false)}
          actions={
            <>
              <button type="button" className="btn-ghost px-4" onClick={() => setShowStop(false)}>Keep running</button>
              <button type="button" className="btn-danger px-4" onClick={forceStop}>Force stop</button>
              {status !== 'login' && status !== 'starting' && (
                <button type="button" className="btn-primary px-4" onClick={gracefulStop}>Stop after this claim</button>
              )}
            </>
          }
        >
          Every finished claim is already saved, so the next run continues from where this one stops.
          <br /><br />
          <b>Stop after this claim</b> finishes the claim in progress first.{' '}
          <b>Force stop</b> ends immediately; the claim in progress is redone next time.
        </Modal>
      )}
    </div>
  );
}
