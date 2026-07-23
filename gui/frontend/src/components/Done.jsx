/**
 * Done.jsx
 *
 * Success / completion screen — shown after 'pipeline-done' fires.
 *
 * Receives donePayload from App.jsx, which comes from push_done():
 *   { claims_seen: number, output_file: string }
 *
 * Actions:
 *   1. Open output Excel file (api.open_file)
 *   2. Open latest log file   (api.open_log with pipeline_dir from settings)
 *   3. Run Again              (back to Run screen with same settings)
 *   4. Run Custom Range       (back to Settings to adjust row range)
 */
import { useEffect, useRef } from 'react';
import { call } from '../lib/bridge';

export default function Done({ donePayload, settings, onRunAgain, onCustomRange }) {
  const cardRef = useRef(null);

  // Fade in card on mount
  useEffect(() => {
    if (cardRef.current) {
      cardRef.current.style.animation = 'fadeIn 0.6s cubic-bezier(0.16,1,0.3,1) both';
    }
  }, []);

  const { claims_seen = 0, output_file = '' } = donePayload ?? {};

  function openOutput() { call('open_file', output_file); }
  function openLog()    { call('open_log',  settings?.pipeline_dir ?? ''); }

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--bg-base)' }}>
      {/* Accent top bar — green for done */}
      <div
        style={{
          height: 3,
          background: 'linear-gradient(90deg, var(--success) 0%, #86efac 100%)',
          flexShrink: 0,
        }}
      />

      {/* Header */}
      <div className="screen-header">
        {/* Green accent stripe */}
        <div
          style={{
            width: 3,
            height: 44,
            borderRadius: 2,
            background: 'linear-gradient(180deg, var(--success) 0%, #86efac 100%)',
            flexShrink: 0,
          }}
        />
        <div className="flex-1">
          <div style={{ fontSize: 20, fontWeight: 700, color: '#fff', letterSpacing: '-0.4px' }}>
            Run Complete
          </div>
        </div>
        <span
          className="pill text-xs font-semibold px-3 py-1 rounded-full"
          style={{
            color: 'var(--success)',
            background: 'var(--success-subtle)',
            border: '1px solid var(--success-border)',
          }}
        >
          Done  ✓
        </span>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 scroll-pane flex justify-center pt-12 pb-12 px-6">
        <div
          ref={cardRef}
          className="card flex flex-col items-center text-center"
          style={{ width: 560, padding: '56px 48px 40px' }}
        >
          {/* Check icon */}
          <div
            className="flex items-center justify-center mb-6"
            style={{
              width: 88,
              height: 88,
              borderRadius: '50%',
              background: 'var(--success-subtle)',
              border: '2px solid var(--success-border)',
              fontSize: 36,
              fontWeight: 900,
              color: 'var(--success)',
            }}
          >
            ✓
          </div>

          {/* Title */}
          <h2
            style={{
              fontSize: 20,
              fontWeight: 700,
              color: '#fff',
              letterSpacing: '-0.3px',
              marginBottom: 10,
            }}
          >
            Pipeline Finished Successfully
          </h2>

          {/* Subtitle */}
          <p className="text-sm leading-relaxed mb-2" style={{ color: 'var(--text-secondary)', maxWidth: 400 }}>
            All records have been verified and saved to the output file.
          </p>

          {/* Claims count */}
          {claims_seen > 0 && (
            <div
              className="mb-6 px-5 py-2 rounded-full text-sm font-semibold"
              style={{
                background: 'var(--accent-subtle)',
                border: '1px solid var(--border-accent)',
                color: 'var(--text-accent)',
              }}
            >
              {claims_seen.toLocaleString()} claim{claims_seen !== 1 ? 's' : ''} processed
            </div>
          )}

          {/* Output path */}
          <div className="w-full mb-6 text-left">
            <div className="section-label mb-2">Output File</div>
            <div
              className="text-xs font-mono break-all rounded-xl px-4 py-3"
              style={{
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
              }}
            >
              {output_file || '—'}
            </div>
          </div>

          {/* Divider */}
          <div className="w-full mb-6" style={{ height: 1, background: 'var(--border)' }} />

          {/* Primary actions */}
          <button
            id="btn-open-output"
            className="btn-success w-full mb-3"
            style={{ height: 44, fontSize: 14 }}
            onClick={openOutput}
            disabled={!output_file}
          >
            📂&nbsp; Open Output File
          </button>

          <button
            id="btn-open-log"
            className="btn w-full mb-6"
            style={{ height: 44, fontSize: 14 }}
            onClick={openLog}
          >
            📋&nbsp; Open Latest Log File
          </button>

          {/* Secondary divider */}
          <div className="w-full mb-4" style={{ height: 1, background: 'var(--border)' }} />

          {/* Secondary actions */}
          <button
            id="btn-run-again"
            className="btn-ghost w-full mb-2"
            style={{ height: 40 }}
            onClick={onRunAgain}
          >
            ↩&nbsp; Run Again &nbsp;(same settings)
          </button>

          <button
            id="btn-custom-range"
            className="btn-ghost w-full"
            style={{ height: 40 }}
            onClick={onCustomRange}
          >
            ⚙&nbsp; Run on Custom Row Range…
          </button>
        </div>
      </div>
    </div>
  );
}
