/**
 * Done.jsx — completion screen.
 *
 * donePayload (from push_done):
 *   { claims_seen, output_file, stopped, summary: {VERIFIED, FAILED, NO_DOCS,
 *     ERROR, skipped, manual_review, cache_hits, processed} | null }
 */
import { CheckCircle2, FileSpreadsheet, FileText, FolderOpen, RotateCcw, Settings as SettingsIcon, PauseCircle } from 'lucide-react';
import { call } from '../lib/bridge';
import { ScreenHeader, Stat } from './ui';

export default function Done({ donePayload, settings, onRunAgain, onSettings }) {
  const { output_file = '', stopped = false, summary = null, claims_seen = 0 } = donePayload ?? {};
  const s = summary || {};
  const failed = (s.FAILED || 0) + (s.NO_DOCS || 0) + (s.ERROR || 0);
  const review = s.manual_review || 0;
  const accent = stopped ? 'var(--warning)' : 'var(--success)';
  const Icon = stopped ? PauseCircle : CheckCircle2;

  let message;
  if (!summary) message = `${claims_seen} row${claims_seen === 1 ? '' : 's'} handled. Results are in the output file.`;
  else if (stopped) message = 'The run was stopped. Everything finished so far is saved; run again to continue.';
  else if (!s.processed) message = 'No new claims to process: every selected row was already done.';
  else if (review) message = `${review} claim${review === 1 ? ' needs' : 's need'} manual review. Filter the manual_review column for "YES" in the output file.`;
  else message = 'All processed claims were verified.';

  return (
    <div className="flex flex-col h-full">
      <ScreenHeader title={stopped ? 'Run stopped' : 'Run complete'} accent={accent} />

      <div className="flex-1 scroll-pane flex justify-center py-10 px-6">
        <div className="card flex flex-col items-center text-center" style={{ width: 620, padding: '44px 44px 36px', animation: 'fadeIn 0.6s cubic-bezier(0.16,1,0.3,1) both' }}>
          <Icon size={64} strokeWidth={1.5} style={{ color: accent }} aria-hidden />

          <h2 className="mt-5 mb-2" style={{ fontSize: 20, fontWeight: 700, color: '#fff' }}>
            {stopped ? 'Stopped safely' : 'Finished'}
          </h2>
          <p className="text-sm leading-relaxed mb-6" style={{ color: 'var(--text-secondary)', maxWidth: 460 }}>{message}</p>

          {summary && (
            <div className="grid grid-cols-4 gap-3 w-full mb-6">
              <Stat value={s.VERIFIED || 0} label="Verified" color="var(--success)" />
              <Stat value={review} label="Need review" color={review ? 'var(--warning)' : undefined} />
              <Stat value={failed} label="Failed" color={failed ? 'var(--error)' : undefined} />
              <Stat value={s.skipped || 0} label="Already done" />
            </div>
          )}

          <div className="w-full mb-6 text-left">
            <div className="section-label mb-2">Output file</div>
            <div className="text-xs font-mono break-all rounded-xl px-4 py-3"
                 style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>
              {output_file || settings?.output_file || '—'}
            </div>
          </div>

          <button id="btn-open-output" type="button" className="btn-success w-full mb-3 gap-2" style={{ height: 46 }}
                  onClick={() => call('open_file', output_file)} disabled={!output_file} autoFocus>
            <FileSpreadsheet size={17} aria-hidden /> Open results in Excel
          </button>
          <div className="grid grid-cols-2 gap-3 w-full mb-6">
            <button id="btn-open-log" type="button" className="btn gap-2" onClick={() => call('open_log')}>
              <FileText size={15} aria-hidden /> Log file
            </button>
            <button type="button" className="btn gap-2" onClick={() => call('open_folder', 'downloads')}>
              <FolderOpen size={15} aria-hidden /> Downloaded documents
            </button>
          </div>

          <div className="w-full mb-4" style={{ height: 1, background: 'var(--border)' }} />

          <div className="grid grid-cols-2 gap-3 w-full">
            <button id="btn-run-again" type="button" className="btn-ghost gap-2" onClick={onRunAgain}>
              <RotateCcw size={15} aria-hidden /> {stopped ? 'Continue the run' : 'Run again'}
            </button>
            <button id="btn-custom-range" type="button" className="btn-ghost gap-2" onClick={onSettings}>
              <SettingsIcon size={15} aria-hidden /> Change settings
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
