/**
 * Settings.jsx
 *
 * Configuration screen:
 *   1. System Check — Ollama, AI model, Python packages, Chromium, API key.
 *      Offers fixes inline (install / start Ollama, download the model).
 *   2. Files       — input workbook, sheet, output workbook.
 *   3. API keys    — Gemini (required), OpenRouter (optional fallback).
 *   4. Rows        — all rows or a range, plus run options.
 *   5. Advanced    — interpreter / pipeline overrides (developers only).
 *
 * Emits onProceed(settingsDict) after validation passes.
 */
import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import {
  ArrowRight, Download, Eye, EyeOff, FolderOpen, Play, RefreshCw, ExternalLink, Loader2,
} from 'lucide-react';
import { call, on } from '../lib/bridge';
import { ScreenHeader } from './ui';

const DEFAULT_FORM = {
  pipeline_dir:       '',
  python_exe:         '',
  input_file:         '',
  sheet_name:         '',
  output_file:        '',
  gemini_api_key:     '',
  openrouter_api_key: '',
  process_mode:       'all',
  start_row:          '2',
  end_row:            '100',
  delete_downloads:   true,
  retry_failed:       false,
};

function samePath(a, b) {
  return !!a && !!b && a.trim().replace(/\//g, '\\').toLowerCase() === b.trim().replace(/\//g, '\\').toLowerCase();
}

function validate(s) {
  const e = {};
  if (!s.input_file)     e.input_file = 'Choose the claims workbook.';
  if (!s.sheet_name)     e.sheet_name = 'Choose the sheet to process.';
  if (!s.output_file)    e.output_file = 'Choose where to save the results.';
  else if (samePath(s.input_file, s.output_file)) e.output_file = 'Must be a different file from the input, or the input would be overwritten.';
  else if (!/\.xlsx$/i.test(s.output_file)) e.output_file = 'The output file must end in .xlsx.';
  if (!s.gemini_api_key.trim()) e.gemini_api_key = 'A Gemini API key is required to verify colleges online.';
  if (s.process_mode === 'range') {
    const start = parseInt(s.start_row, 10);
    const end   = parseInt(s.end_row, 10);
    if (isNaN(start) || isNaN(end)) e.range = 'Start and end row must be whole numbers.';
    else if (start < 2)             e.range = 'Start row must be 2 or more (row 1 is the header).';
    else if (end < start)           e.range = 'End row must be the same as or after the start row.';
  }
  return e;
}

function formReducer(state, patch) {
  return { ...state, ...patch };
}

// Defined at module level: a component declared inside Settings would be a
// new type on every render, remounting the <input> and stealing focus on
// each keystroke.
function BrowseRow({ id, value, onChange, onBlur, onBrowse, placeholder, invalid, browseLabel = 'Browse…' }) {
  return (
    <div className="flex gap-2">
      <input
        id={id}
        className={`field flex-1 ${invalid ? 'field-error' : ''}`}
        value={value}
        onChange={e => onChange(e.target.value)}
        onBlur={onBlur}
        placeholder={placeholder}
        aria-invalid={invalid || undefined}
        spellCheck={false}
      />
      <button type="button" className="btn px-4 gap-2" onClick={onBrowse}>
        <FolderOpen size={15} aria-hidden /> {browseLabel}
      </button>
    </div>
  );
}

function Field({ label, htmlFor, error, hint, children }) {
  return (
    <div className="mb-4 last:mb-0">
      <label htmlFor={htmlFor} className="section-label block mb-2">{label}</label>
      {children}
      {error ? <div className="field-msg" role="alert">{error}</div> : hint ? <div className="field-hint">{hint}</div> : null}
    </div>
  );
}

function fmtBytes(n) {
  if (!n) return '0 MB';
  return n > 1e9 ? `${(n / 1e9).toFixed(2)} GB` : `${Math.round(n / 1e6)} MB`;
}

// ---------------------------------------------------------------------------
// System Check card
// ---------------------------------------------------------------------------
function SystemCheck({ check, checking, onRecheck, pull }) {
  async function act(action) {
    if (action === 'install_ollama') call('install_ollama');
    else if (action === 'start_ollama') { await call('start_ollama'); setTimeout(onRecheck, 4000); }
    else if (action === 'pull_model') call('pull_model');
  }

  const actionLabel = { install_ollama: 'Download Ollama', start_ollama: 'Start Ollama', pull_model: 'Download model' };
  const actionIcon  = { install_ollama: ExternalLink, start_ollama: Play, pull_model: Download };

  const pulling = pull && !pull.done;
  const pct = pull?.total ? Math.round((pull.completed || 0) / pull.total * 100) : null;

  return (
    <section className="group-box" aria-labelledby="syscheck-title">
      <div id="syscheck-title" className="group-title">System check</div>
      <div className="flex items-center mb-3">
        <p className="text-xs flex-1" style={{ color: 'var(--text-secondary)' }}>
          {checking ? 'Checking this computer…'
            : check?.blocking ? 'Some things need attention before you can run.'
            : check ? 'Everything is ready.' : ''}
        </p>
        <button type="button" className="btn-ghost text-xs gap-1.5" style={{ height: 30 }} onClick={onRecheck} disabled={checking}>
          <RefreshCw size={13} className={checking ? 'spin' : ''} aria-hidden /> Check again
        </button>
      </div>

      {!check && checking && (
        <div className="flex items-center gap-2 text-sm py-2" style={{ color: 'var(--text-muted)' }}>
          <Loader2 size={16} className="spin" aria-hidden /> This can take up to a minute the first time.
        </div>
      )}

      {!check && !checking && (
        <div className="text-sm py-2" style={{ color: 'var(--error)' }}>
          The system check could not run. Click "Check again"; if it keeps failing, reinstall MAHABOCW.
        </div>
      )}

      {check && (
        <ul className="flex flex-col gap-2.5">
          {check.items.map(item => {
            const Icon = actionIcon[item.action];
            const showPull = item.action === 'pull_model' && pull;
            return (
              <li key={item.id} className="flex items-start gap-3">
                <span className={`status-dot mt-1.5 status-${checking ? 'pending' : item.status}`} aria-hidden />
                <div className="flex-1 min-w-0">
                  <div className="text-sm" style={{ color: 'var(--text-primary)' }}>
                    {item.label}
                    <span className="sr-only"> — {item.status}</span>
                  </div>
                  <div className="text-xs break-words" style={{ color: item.status === 'error' && !(showPull && pulling) ? 'var(--error)' : 'var(--text-muted)' }}>
                    {showPull
                      ? (pull.error ? `Download failed: ${pull.error}` : pull.done ? 'Downloaded.' : `${pull.status || 'Starting…'}${pct !== null ? ` — ${pct}% (${fmtBytes(pull.completed)} of ${fmtBytes(pull.total)})` : ''}`)
                      : item.detail}
                  </div>
                  {showPull && pulling && pct !== null && (
                    <div className="progress-track mt-2"><div className="progress-fill" style={{ width: `${pct}%` }} /></div>
                  )}
                </div>
                {item.action && !(showPull && pulling) && item.status !== 'ok' && (
                  <button type="button" className="btn text-xs px-3 gap-1.5 shrink-0" style={{ height: 32 }} onClick={() => act(item.action)}>
                    {Icon && <Icon size={13} aria-hidden />} {actionLabel[item.action]}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Settings screen
// ---------------------------------------------------------------------------
export default function Settings({ onProceed }) {
  const [form,     dispatch]   = useReducer(formReducer, DEFAULT_FORM);
  const [env,      setEnv]     = useState(null);
  const [sheets,   setSheets]  = useState([]);
  const [pyStatus, setPyStatus]= useState(null);
  const [errors,   setErrors]  = useState({});
  const [touched,  setTouched] = useState(false);
  const [saving,   setSaving]  = useState(false);
  const [showKey,  setShowKey] = useState(false);
  const [loading,  setLoading] = useState(true);
  const [check,    setCheck]   = useState(null);
  const [checking, setChecking]= useState(false);
  const [pull,     setPull]    = useState(null);
  const formRef = useRef(form);
  formRef.current = form;

  const runCheck = useCallback(async () => {
    setChecking(true);
    try {
      setCheck(await call('system_check', formRef.current));
    } catch {
      setCheck(null);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    call('get_initial_state')
      .then(({ settings, environment }) => {
        dispatch(settings);
        formRef.current = { ...formRef.current, ...settings };
        setEnv(environment);
        if (settings.input_file) loadSheets(settings.input_file, settings.sheet_name);
      })
      .catch(() => {})
      .finally(() => { setLoading(false); runCheck(); });

    return on('model-pull', p => {
      setPull(p);
      if (p.done && !p.error) runCheck();
    });
  }, [runCheck]);

  useEffect(() => {
    if (touched) setErrors(validate(form));
  }, [form, touched]);

  async function loadSheets(filePath, preferredSheet) {
    if (!filePath) { setSheets([]); return; }
    const names = await call('get_sheet_names', filePath);
    setSheets(names);
    if (names.length) {
      dispatch({ sheet_name: names.includes(preferredSheet) ? preferredSheet : names[0] });
    }
  }

  async function browse(method, field, after) {
    const path = await call(method);
    if (path) { dispatch({ [field]: path }); after?.(path); }
  }

  async function testPython() {
    setPyStatus(null);
    setPyStatus(await call('test_python', form.python_exe));
  }

  // The Gemini key is checked live from the form; other items need a re-check.
  const checkItems = check?.items?.map(i =>
    i.id === 'gemini'
      ? { ...i, status: form.gemini_api_key.trim() ? 'ok' : 'error', detail: form.gemini_api_key.trim() ? 'Set' : 'Enter your key below.' }
      : i) ?? null;
  const blocking = checkItems ? checkItems.some(i => i.status === 'error') : true;
  const devMode = env && !env.install_root;

  async function handleSave() {
    setTouched(true);
    const errs = validate(form);
    setErrors(errs);
    if (Object.keys(errs).length) {
      document.querySelector('[aria-invalid="true"]')?.focus();
      return;
    }
    setSaving(true);
    try {
      await call('save_settings', form);
      onProceed(form);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full gap-2 text-sm" style={{ color: 'var(--text-muted)' }}>
        <Loader2 size={16} className="spin" aria-hidden /> Loading settings…
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <ScreenHeader title="Set up a run" subtitle="Check this computer, choose your files, then continue">
        <div className="pill">Step 1 of 2</div>
      </ScreenHeader>

      <div className="flex-1 scroll-pane px-11 py-7 flex flex-col gap-5">

        <SystemCheck check={check && { ...check, items: checkItems, blocking }} checking={checking} onRecheck={runCheck} pull={pull} />

        {/* ── Files ── */}
        <section className="group-box">
          <div className="group-title">Files</div>

          <Field label="Claims workbook (input)" htmlFor="f-input" error={errors.input_file}
                 hint="The Excel file with the claims to check. It is never modified.">
            <BrowseRow
              id="f-input"
              value={form.input_file}
              onChange={v => dispatch({ input_file: v })}
              onBlur={() => loadSheets(form.input_file, form.sheet_name)}
              onBrowse={() => browse('pick_input_file', 'input_file', p => loadSheets(p, form.sheet_name))}
              placeholder="Choose an .xlsx file"
              invalid={!!errors.input_file}
            />
          </Field>

          <Field label="Sheet" htmlFor="f-sheet" error={errors.sheet_name}>
            {sheets.length ? (
              <select id="f-sheet" className="field" value={form.sheet_name}
                      onChange={e => dispatch({ sheet_name: e.target.value })} style={{ cursor: 'pointer' }}>
                {sheets.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            ) : (
              <input id="f-sheet" className={`field ${errors.sheet_name ? 'field-error' : ''}`} value={form.sheet_name}
                     onChange={e => dispatch({ sheet_name: e.target.value })}
                     placeholder="Choose the workbook first" aria-invalid={!!errors.sheet_name || undefined} />
            )}
          </Field>

          <Field label="Results workbook (output)" htmlFor="f-output" error={errors.output_file}
                 hint="Results are saved here after every claim. If the file already exists, the run continues where it left off.">
            <BrowseRow
              id="f-output"
              value={form.output_file}
              onChange={v => dispatch({ output_file: v })}
              onBrowse={() => browse('pick_output_file', 'output_file')}
              placeholder="Choose where to save the results"
              invalid={!!errors.output_file}
              browseLabel="Save as…"
            />
          </Field>
        </section>

        {/* ── API keys ── */}
        <section className="group-box">
          <div className="group-title">API keys</div>

          <Field label="Gemini API key" htmlFor="f-gemini" error={errors.gemini_api_key}>
            <div className="flex gap-2">
              <input id="f-gemini" className={`field flex-1 ${errors.gemini_api_key ? 'field-error' : ''}`}
                     type={showKey ? 'text' : 'password'} value={form.gemini_api_key}
                     onChange={e => dispatch({ gemini_api_key: e.target.value })}
                     placeholder="Paste your Gemini API key" autoComplete="off" spellCheck={false}
                     aria-invalid={!!errors.gemini_api_key || undefined} />
              <button type="button" className="btn px-3" onClick={() => setShowKey(v => !v)}
                      aria-label={showKey ? 'Hide keys' : 'Show keys'} title={showKey ? 'Hide' : 'Show'}>
                {showKey ? <EyeOff size={16} aria-hidden /> : <Eye size={16} aria-hidden />}
              </button>
            </div>
            {!errors.gemini_api_key && (
              <div className="field-hint">
                Don't have one?{' '}
                <button type="button" className="link-btn" onClick={() => call('open_url', 'https://aistudio.google.com/apikey')}>Get a key from Google AI Studio</button>
              </div>
            )}
          </Field>

          <Field label="OpenRouter API key (optional)" htmlFor="f-openrouter"
                 hint="Backup service, used only when Gemini is unavailable.">
            <input id="f-openrouter" className="field" type={showKey ? 'text' : 'password'} value={form.openrouter_api_key}
                   onChange={e => dispatch({ openrouter_api_key: e.target.value })}
                   placeholder="Leave empty if you don't have one" autoComplete="off" spellCheck={false} />
          </Field>
          <p className="field-hint">Keys are stored encrypted for your Windows user account.</p>
        </section>

        {/* ── Rows & options ── */}
        <section className="group-box">
          <div className="group-title">Rows &amp; options</div>

          <fieldset>
            <legend className="sr-only">Which rows to process</legend>
            <label className="flex items-center gap-3 mb-3 cursor-pointer">
              <input type="radio" name="process_mode" checked={form.process_mode === 'all'}
                     onChange={() => dispatch({ process_mode: 'all' })} className="w-4 h-4" style={{ accentColor: 'var(--accent)' }} />
              <span>All rows</span>
            </label>
            <label className="flex items-center gap-3 mb-3 cursor-pointer">
              <input type="radio" name="process_mode" checked={form.process_mode === 'range'}
                     onChange={() => dispatch({ process_mode: 'range' })} className="w-4 h-4" style={{ accentColor: 'var(--accent)' }} />
              <span>Only some rows</span>
            </label>
          </fieldset>

          {form.process_mode === 'range' && (
            <div className="pl-7 mb-2">
              <div className="flex gap-6">
                <div>
                  <label htmlFor="f-start" className="section-label block mb-1.5">From row</label>
                  <input id="f-start" type="number" className={`field ${errors.range ? 'field-error' : ''}`} style={{ width: 120 }} min={2}
                         value={form.start_row} onChange={e => dispatch({ start_row: e.target.value })} aria-invalid={!!errors.range || undefined} />
                </div>
                <div>
                  <label htmlFor="f-end" className="section-label block mb-1.5">To row</label>
                  <input id="f-end" type="number" className={`field ${errors.range ? 'field-error' : ''}`} style={{ width: 120 }} min={2}
                         value={form.end_row} onChange={e => dispatch({ end_row: e.target.value })} />
                </div>
              </div>
              {errors.range
                ? <div className="field-msg" role="alert">{errors.range}</div>
                : <div className="field-hint">Use the row numbers shown in Excel. Row 2 is the first claim.</div>}
            </div>
          )}

          <div className="mt-4 flex flex-col gap-3" style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: 16 }}>
            <label className="flex items-start gap-3 cursor-pointer">
              <input type="checkbox" className="w-4 h-4 mt-0.5" style={{ accentColor: 'var(--accent)' }}
                     checked={form.delete_downloads} onChange={e => dispatch({ delete_downloads: e.target.checked })} />
              <span>
                Delete downloaded documents after each claim
                <span className="block text-xs" style={{ color: 'var(--text-muted)' }}>Recommended: the documents include Aadhaar and ration cards.</span>
              </span>
            </label>
            <label className="flex items-start gap-3 cursor-pointer">
              <input type="checkbox" className="w-4 h-4 mt-0.5" style={{ accentColor: 'var(--accent)' }}
                     checked={form.retry_failed} onChange={e => dispatch({ retry_failed: e.target.checked })} />
              <span>
                Try failed claims again
                <span className="block text-xs" style={{ color: 'var(--text-muted)' }}>Claims marked FAILED or NO_DOCS are normally skipped on later runs.</span>
              </span>
            </label>
          </div>
        </section>

        {/* ── Advanced ── */}
        <details className="group-box" style={{ paddingTop: 18 }}>
          <summary className="cursor-pointer text-sm font-semibold select-none" style={{ color: 'var(--text-secondary)' }}>
            Advanced (for developers)
          </summary>
          <div className="mt-5">
            <Field label="Pipeline folder" htmlFor="f-pipeline"
                   hint={`Leave empty to use: ${env?.default_pipeline_dir || 'not found'}`}>
              <BrowseRow id="f-pipeline" value={form.pipeline_dir} onChange={v => dispatch({ pipeline_dir: v })}
                         onBrowse={() => browse('pick_pipeline_folder', 'pipeline_dir')} placeholder="Automatic" />
            </Field>
            <Field label="Python interpreter" htmlFor="f-python"
                   hint={pyStatus ? undefined : `Leave empty to use: ${env?.default_python_exe || 'python'}`}>
              <div className="flex gap-2">
                <input id="f-python" className="field flex-1" value={form.python_exe} spellCheck={false}
                       onChange={e => dispatch({ python_exe: e.target.value })} placeholder="Automatic" />
                <button type="button" className="btn px-4" onClick={() => browse('pick_python_exe', 'python_exe')}>Browse…</button>
                <button type="button" className="btn px-4" onClick={testPython}>Test</button>
              </div>
              {pyStatus && (
                <div className="field-hint" style={{ color: pyStatus.ok ? 'var(--success)' : 'var(--error)' }}>
                  {pyStatus.ok ? `✓ ${pyStatus.version}` : `✗ ${pyStatus.error}`}
                </div>
              )}
            </Field>
            <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
              <span className="truncate">Working folder (logs, downloads, cache): {env?.data_dir}</span>
              <button type="button" className="link-btn shrink-0" onClick={() => call('open_folder', 'data')}>Open</button>
            </div>
          </div>
        </details>

        <div className="flex items-center justify-end gap-4 pb-2">
          {blocking && !checking && (
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Fix the items in the system check to continue.
              {devMode && (
                <>
                  {' '}
                  <button type="button" className="link-btn" onClick={() => { setCheck({ items: [], blocking: false }); }}>Ignore (dev)</button>
                </>
              )}
            </span>
          )}
          <button
            id="btn-save-continue"
            type="button"
            className="btn-primary px-8 gap-2"
            style={{ height: 48, fontSize: 15, minWidth: 220 }}
            onClick={handleSave}
            disabled={saving || checking || blocking}
          >
            {saving ? 'Saving…' : <>Save &amp; start <ArrowRight size={17} aria-hidden /></>}
          </button>
        </div>
      </div>
    </div>
  );
}
